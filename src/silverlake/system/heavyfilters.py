"""PASE batch B5, the heavier filters: awk diff cmp comm join paste od strings split pr.

Wording, layouts and statuses come from the PUB400 run of 2026-10-28 (ssh-pase-b5, kept local). `od` there is big endian, as
the machine is, and prints addresses in octal whatever -A says. What the run did not reach is a guess and docs/pase.md
says so. Work is capped: MAX_LINES lines a file, MAX_DIFF lines for diff, and awk stops at its own step limit.

There are no file times in the virtual IFS, so every file is dated 2026-10-26 09:00 (the IFS's own stamp)."""

from __future__ import annotations

import difflib
import re

from . import awk, ifs
from .textfilters import MAX_LINE, MAX_LINES, Err

MAX_DIFF = 2000
STAMP_UNIFIED = "2026-10-26 09:00:00.000000000 +0000"
STAMP_CONTEXT = "Mon Oct 26 09:00:00 2026"
STAMP_PR = "Oct 26 09:00 2026"

DIFF_USAGE = ("Usage: diff [-bitw] [[-C Lines|-D String|-e|-f|-n|-U Lines|-c|-u]|[-h]] File1 File2\n"
              "       diff [-bilrstw] [[-C Lines|-e|-f|-n|-U Lines|-c|-u]|[-h]] [-S File] Directory1 Directory2")
JOIN_USAGE = "Usage: join [-a Num] [-v Num] [-[j] Num Field] [-t Chr] [-o Fieldlist [-e str]] File1 File2"
SPLIT_USAGE = ("usage: split [-l line_count] [-a suffix_length] [file [name]]\n"
               "   or: split -b number[k|m] [-a suffix_length] [file [name]]")


def _lines(text: str) -> list[str]:
    return [l[:MAX_LINE] for l in text.splitlines()[:MAX_LINES]]


class Heavy:
    """Mixed into the Shell beside Filters."""

    def _file(self, given: str) -> str | None:
        try:
            return ifs.read(self.store, self.actor, self.path(given))
        except ifs.IfsError:
            return None

    @staticmethod
    def _err_lines(text: str) -> list[str]:
        return [Err(l) for l in text.split("\n")]

    # -- awk ---------------------------------------------------------------------------------------------------

    def cmd_awk(self, args: list[str]) -> list[str]:
        fs, assigns, program, rest, i = " ", {}, None, [], 0
        while i < len(args):
            a = args[i]
            if a == "-F" and i + 1 < len(args):
                fs, i = args[i + 1], i + 1
            elif a.startswith("-F") and len(a) > 2:
                fs = a[2:]
            elif a == "-v" and i + 1 < len(args):
                name, _, value = args[i + 1].partition("=")
                assigns[name], i = value, i + 1
            elif a == "-f" and i + 1 < len(args):
                text = self._file(args[i + 1])
                if text is None:
                    self.status = 2
                    return [Err(f"awk: Cannot find or open file {args[i + 1]}.")]
                program, i = text, i + 1
            elif a == "-u":
                pass
            elif a == "--":
                rest += args[i + 1:]
                break
            elif a.startswith("-") and len(a) > 1 and program is None and not rest:
                self.status = 2
                return [Err(awk.USAGE)]
            else:
                rest.append(a)
            i += 1
        if program is None:
            if not rest:
                self.status = 2
                return [Err(awk.USAGE)]
            program, rest = rest[0], rest[1:]
        files = []
        for word in rest:
            if re.fullmatch(r"[A-Za-z_]\w*=.*", word):
                name, _, value = word.partition("=")
                assigns[name] = value
            else:
                files.append(word)
        try:
            engine = awk.Awk(program, fs, assigns)
        except awk.AwkError as exc:
            self.status = 2
            return [Err(l) for l in (awk.syntax_error(exc) if exc.text == "syntax" else exc.text.split("\n"))]
        inputs: list[list[str]] = []
        for given in files or ["-"]:
            if given == "-":
                inputs.append(list(self.stdin or [])[:MAX_LINES])
                continue
            text = self._file(given)
            if text is None:
                self.status = 2
                return [Err(f"awk: Cannot find or open file {given}."), Err(""), Err(" The source line number is 1.")]
            inputs.append(_lines(text))
        try:
            code = engine.run(inputs)
        except awk.AwkError as exc:
            self.status = 2
            return self._shown(engine) + [Err(l) for l in exc.text.split("\n")]
        self.status = code
        return self._shown(engine)

    @staticmethod
    def _shown(engine) -> list[str]:
        text = "".join(engine.out)
        return text[:-1].split("\n") if text.endswith("\n") else (text.split("\n") if text else [])

    # -- diff cmp comm -----------------------------------------------------------------------------------------

    def cmd_diff(self, args: list[str]) -> list[str]:
        style, context, ignore, files, i = "normal", 3, set(), [], 0
        while i < len(args):
            a = args[i]
            if a in ("-c", "-u"):
                style = "context" if a == "-c" else "unified"
            elif a in ("-C", "-U") and i + 1 < len(args) and args[i + 1].isdigit():
                style, context, i = ("context" if a == "-C" else "unified"), int(args[i + 1]), i + 1
            elif re.fullmatch(r"-[CU]\d+", a):
                style, context = ("context" if a[1] == "C" else "unified"), int(a[2:])
            elif a.startswith("-") and len(a) > 1:
                bad = [c for c in a[1:] if c not in "bitwhrls"]
                if bad:
                    self.status = 2
                    return [Err(f"diff: illegal option -- {bad[0]}")] + self._err_lines(DIFF_USAGE)
                ignore |= set(a[1:])
            else:
                files.append(a)
            i += 1
        if len(files) != 2:
            self.status = 2
            return [Err("diff: two filename arguments required")] + self._err_lines(DIFF_USAGE)
        texts = []
        for given in files:
            text = self._file(given)
            if text is None:
                self.status = 2
                return [Err(f"diff: {given}: No such file or directory")]
            texts.append(_lines(text))
        a_lines, b_lines = texts
        if len(a_lines) > MAX_DIFF or len(b_lines) > MAX_DIFF:
            self.status = 2
            return [Err("diff: the files are too large for the simulator")]

        def norm(line: str) -> str:
            if "i" in ignore:
                line = line.lower()
            if "w" in ignore:
                line = re.sub(r"\s+", "", line)
            elif "b" in ignore:
                line = re.sub(r"\s+", " ", line.rstrip())
            return line

        matcher = difflib.SequenceMatcher(None, [norm(l) for l in a_lines], [norm(l) for l in b_lines], autojunk=False)
        ops = [op for op in matcher.get_opcodes() if op[0] != "equal"]
        self.status = 1 if ops else 0
        if not ops:
            return []
        if style == "unified":
            return list(difflib.unified_diff(a_lines, b_lines, files[0], files[1], STAMP_UNIFIED, STAMP_UNIFIED, n=context,
                                             lineterm=""))
        if style == "context":
            return list(difflib.context_diff(a_lines, b_lines, files[0], files[1], STAMP_CONTEXT, STAMP_CONTEXT, n=context,
                                             lineterm=""))
        out: list[str] = []
        for tag, i1, i2, j1, j2 in ops:
            left = f"{i1 + 1},{i2}" if i2 - i1 > 1 else f"{i2 if tag == 'insert' else i1 + 1}"
            right = f"{j1 + 1},{j2}" if j2 - j1 > 1 else f"{j2 if tag == 'delete' else j1 + 1}"
            out.append(f"{left}{ {'replace': 'c', 'delete': 'd', 'insert': 'a'}[tag] }{right}")
            out += ["< " + l for l in a_lines[i1:i2]]
            if tag == "replace":
                out.append("---")
            out += ["> " + l for l in b_lines[j1:j2]]
        return out

    def cmd_cmp(self, args: list[str]) -> list[str]:
        flags = {a for a in args if a in ("-l", "-s")}
        files = [a for a in args if a not in ("-l", "-s")]
        if len(files) != 2 or any(a.startswith("-") and a != "-" for a in files):
            self.status = 2
            return [Err("usage: cmp [-l | -s] file1 file2")]
        data = []
        for given in files:
            text = self._file(given)
            if text is None:
                self.status = 2
                return [Err(f"cmp: cannot open {given}")]
            data.append(text.encode()[:MAX_LINES * 80])
        a, b = data
        out: list[str] = []
        self.status = 0
        for n in range(min(len(a), len(b))):
            if a[n] != b[n]:
                self.status = 1
                if "-s" in flags:
                    return []
                if "-l" in flags:
                    out.append(f"{n + 1:6d} {a[n]:3o} {b[n]:3o}")
                    continue
                return [f"{files[0]} {files[1]} differ: char {n + 1}, line {a[:n].count(b'\n') + 1}"]
        if len(a) != len(b):
            self.status = 1
            if "-s" not in flags:
                out.append(Err(f"cmp: EOF on {files[0] if len(a) < len(b) else files[1]}"))
        return out

    def cmd_comm(self, args: list[str]) -> list[str]:
        hide = "".join(a[1:] for a in args if re.fullmatch(r"-[123]+", a))
        files = [a for a in args if not re.fullmatch(r"-[123]+", a)]
        if len(files) != 2:
            self.status = 2
            return [Err("usage: comm [-123] file1 file2")]
        both = []
        for given in files:
            text = self._file(given) if given != "-" else "".join(l + "\n" for l in self.stdin or [])
            if text is None:
                self.status = 1
                return [Err(f"comm: cannot open {given}")]
            both.append(_lines(text))
        a, b = both
        shift = lambda col: "\t" * sum(1 for c in "123"[:col - 1] if c not in hide)
        out: list[str] = []
        i = j = 0
        while i < len(a) or j < len(b):
            if j >= len(b) or (i < len(a) and a[i] < b[j]):
                col, line, i = 1, a[i], i + 1
            elif i >= len(a) or b[j] < a[i]:
                col, line, j = 2, b[j], j + 1
            else:
                col, line, i, j = 3, a[i], i + 1, j + 1
            if str(col) not in hide:
                out.append(shift(col) + line)
        return out

    # -- join paste --------------------------------------------------------------------------------------------

    def cmd_join(self, args: list[str]) -> list[str]:
        j1 = j2 = 1
        sep: str | None = None
        unpaired: set[int] = set()
        order: list[str] | None = None
        filler, files, i = "", [], 0
        while i < len(args):
            a = args[i]
            nxt = args[i + 1] if i + 1 < len(args) else ""
            if re.fullmatch(r"-(t|e|o|a|v|j1|j2|j|1|2)(?!$).+", a) and a[:2] != "-j" or re.fullmatch(r"-j[12]?\d+", a):
                flag, value = (a[:3], a[3:]) if a[:3] in ("-j1", "-j2") else (a[:2], a[2:])
                args = args[:i] + [flag, value] + args[i + 1:]
                a, nxt = flag, value
            if a in ("-j", "-1", "-2", "-j1", "-j2", "-a", "-t", "-o", "-e", "-v") and not nxt:
                self.status = 1
                return self._err_lines(JOIN_USAGE)
            if a == "-j":
                j1 = j2 = int(nxt) if nxt.isdigit() else 1
                i += 1
            elif a in ("-1", "-j1"):
                j1, i = int(nxt) if nxt.isdigit() else 1, i + 1
            elif a in ("-2", "-j2"):
                j2, i = int(nxt) if nxt.isdigit() else 1, i + 1
            elif a == "-t":
                sep, i = nxt[:1], i + 1
            elif a == "-a" and nxt in ("1", "2"):
                unpaired.add(int(nxt))
                i += 1
            elif a == "-o":
                order, i = nxt.replace(",", " ").split(), i + 1
            elif a == "-e":
                filler, i = nxt, i + 1
            elif a.startswith("-") and len(a) > 1 and a != "-":
                self.status = 1
                return self._err_lines(JOIN_USAGE)
            else:
                files.append(a)
            i += 1
        if len(files) != 2:
            self.status = 1
            return self._err_lines(JOIN_USAGE)
        both = []
        for given in files:
            text = self._file(given)
            if text is None:
                self.status = 1
                return [Err(f"join: Cannot open file {given}")]
            both.append(_lines(text))

        def split(line: str) -> list[str]:
            return line.split(sep) if sep else line.split()

        def key(fields: list[str], n: int) -> str:
            return fields[n - 1] if 0 < n <= len(fields) else ""

        joiner = sep or " "
        right: dict[str, list[list[str]]] = {}
        for line in both[1]:
            f = split(line)
            right.setdefault(key(f, j2), []).append(f)
        out, matched = [], set()
        for line in both[0]:
            f = split(line)
            k = key(f, j1)
            for g in right.get(k, []):
                matched.add(k)
                if order:
                    cells = [self._pick(f, g, spec, filler) for spec in order]
                else:
                    cells = [k] + [x for n, x in enumerate(f, 1) if n != j1] + [x for n, x in enumerate(g, 1) if n != j2]
                out.append(joiner.join(cells))
            if k not in right and 1 in unpaired:
                out.append(joiner.join(f))
        if 2 in unpaired:
            for line in both[1]:
                if key(split(line), j2) not in matched:
                    out.append(joiner.join(split(line)))
        return out

    @staticmethod
    def _pick(f: list[str], g: list[str], spec: str, filler: str) -> str:
        m = re.fullmatch(r"([012])(?:\.(\d+))?", spec)
        if not m:
            return filler
        which, n = m[1], int(m[2] or 0)
        src = f if which == "1" else g
        return src[n - 1] if 0 < n <= len(src) else filler

    def cmd_paste(self, args: list[str]) -> list[str]:
        delims, serial, files, i = ["\t"], False, [], 0
        while i < len(args):
            a = args[i]
            if a == "-s":
                serial = True
            elif a.startswith("-d"):
                value = a[2:] or (args[i + 1] if i + 1 < len(args) else "\t")
                if not a[2:]:
                    i += 1
                delims = list(value.replace("\\t", "\t").replace("\\n", "\n")) or ["\t"]
            else:
                files.append(a)
            i += 1
        columns: list[list[str]] = []
        piped = iter(self.stdin or [])
        dashes = files.count("-")
        for given in files:
            if given == "-":
                columns.append(("-", None))
                continue
            text = self._file(given)
            if text is None:
                self.status = 1
                return [Err(f"paste: {given}: cannot open")]
            columns.append((given, _lines(text)))
        stdin_lines = list(self.stdin or [])
        seen = 0
        resolved: list[list[str]] = []
        for name, lines in columns:
            if lines is None:                                  # each `-` takes every n-th line of the pipe
                resolved.append(stdin_lines[seen::max(dashes, 1)])
                seen += 1
            else:
                resolved.append(lines)
        if serial:
            return [self._glue(col, delims) for col in resolved]
        rows = max((len(c) for c in resolved), default=0)
        return [self._glue([c[r] if r < len(c) else "" for c in resolved], delims) for r in range(rows)]

    @staticmethod
    def _glue(cells: list[str], delims: list[str]) -> str:
        out = ""
        for n, cell in enumerate(cells):
            out += (delims[(n - 1) % len(delims)] if n else "") + cell
        return out

    # -- od strings --------------------------------------------------------------------------------------------

    def cmd_od(self, args: list[str]) -> list[str]:
        kinds: list[str] = []
        skip, count, verbose, files, i = 0, None, False, [], 0
        no_address = False
        while i < len(args):
            a = args[i]
            if a in ("-j", "-N", "-A", "-t") and i + 1 < len(args):
                value = args[i + 1]
                i += 1
                if a == "-j" and value.isdigit():
                    skip = int(value)
                elif a == "-N" and value.isdigit():
                    count = int(value)
                elif a == "-t":
                    kinds.append(value)
            elif a.startswith("-A") and len(a) > 2:
                no_address = no_address or a[2:] == "n"
            elif a.startswith("-") and len(a) > 1 and a != "-":
                for ch in a[1:]:
                    if ch == "v":
                        verbose = True
                    elif ch in "cbxdo":
                        kinds.append({"c": "c", "b": "o1", "x": "x2", "d": "u2", "o": "o2"}[ch])
                    elif ch == "A":
                        pass
            else:
                files.append(a)
            i += 1
        if files:
            data = b""
            for given in files:
                text = self._file(given)
                if text is None:
                    self.status = 1
                    return [Err(f"{given}: No such file or directory")]
                data += text.encode()
        else:
            data = "".join(l + "\n" for l in self.stdin or []).encode()
        data = data[skip:]
        if count is not None:
            data = data[:count]
        data = data[:MAX_LINES * 16]
        spec = kinds[0] if kinds else "o2"
        out: list[str] = []
        previous, starred = None, False
        for off in range(0, len(data), 16):
            chunk = data[off:off + 16]
            if not verbose and chunk == previous and len(chunk) == 16:
                if not starred:
                    out.append("*")
                    starred = True
                continue
            previous, starred = chunk, False
            body = self._od_cells(chunk, spec)
            out.append(("\t" if no_address else f"{off:07o} ") + body)
        out.append("" if no_address else f"{len(data):07o}")
        return out

    @staticmethod
    def _od_cells(chunk: bytes, spec: str) -> str:
        if spec == "c":
            names = {0: "\\0", 7: "\\a", 8: "\\b", 9: "\\t", 10: "\\n", 11: "\\v", 12: "\\f", 13: "\\r"}
            return "".join(f"{(names.get(b) or (chr(b) if 32 <= b < 127 else f'{b:03o}')):>4}" for b in chunk)
        m = re.fullmatch(r"([xodu])([124])?", spec) or re.fullmatch(r"([xodu])(\d)?", "o2")
        kind, width = m[1], int(m[2] or 2)
        cells = []
        for n in range(0, len(chunk), width):
            raw = chunk[n:n + width].ljust(width, b"\0")
            value = int.from_bytes(raw, "big")
            digits = {"x": f"{value:0{width * 2}x}", "o": f"{value:0{ {1: 3, 2: 6, 4: 11}[width] }o}",
                      "d": f"{value:{ {1: 3, 2: 5, 4: 10}[width] }d}", "u": f"{value:{ {1: 3, 2: 5, 4: 10}[width] }d}"}[kind]
            cells.append(" " + digits)
        return "".join(cells)

    def cmd_strings(self, args: list[str]) -> list[str]:
        minimum, files, i = 4, [], 0
        while i < len(args):
            a = args[i]
            if a == "-n" and i + 1 < len(args) and args[i + 1].isdigit():
                minimum, i = int(args[i + 1]), i + 1
            elif re.fullmatch(r"-n?\d+", a):
                minimum = int(a.lstrip("-n"))
            elif a.startswith("-") and len(a) > 1:
                pass
            else:
                files.append(a)
            i += 1
        out: list[str] = []
        for given in files:                                    # standard input was never read on PUB400: nothing prints
            text = self._file(given)
            if text is None:
                self.status = 1
                out.append(Err(f"{given}: No such file or directory"))
                continue
            for run in re.findall(r"[ -~\t]+", text[:MAX_LINES * 80]):
                if len(run) >= minimum:
                    out.append(run)
        return out

    # -- pr split ----------------------------------------------------------------------------------------------

    def cmd_pr(self, args: list[str]) -> list[str]:
        header = None
        numbered = bare = double = False
        length, offset, width, columns, files, i = 66, 0, 72, 1, [], 0
        while i < len(args):
            a = args[i]
            nxt = args[i + 1] if i + 1 < len(args) else ""
            if a == "-h" and nxt:
                header, i = nxt, i + 1
            elif a == "-l" and nxt.isdigit():
                length, i = int(nxt), i + 1
            elif a == "-o" and nxt.isdigit():
                offset, i = int(nxt), i + 1
            elif a == "-w" and nxt.isdigit():
                width, i = int(nxt), i + 1
            elif re.fullmatch(r"-\d+", a):
                columns = max(int(a[1:]), 1)
            elif a.startswith("-") and len(a) > 1:
                numbered = numbered or "n" in a[1:]
                bare = bare or "t" in a[1:]
                double = double or "d" in a[1:]
            else:
                files.append(a)
            i += 1
        out: list[str] = []
        for given in files or ["-"]:
            text = "".join(l + "\n" for l in self.stdin or []) if given == "-" else self._file(given)
            if text is None:
                self.status = 1
                out.append(Err(f"pr: Cannot open file {given}."))
                continue
            title = header if header is not None else ("" if given == "-" else given)
            lines = _lines(text)
            if numbered:
                lines = [f"{n:5d}\t{l}" for n, l in enumerate(lines, 1)]
            if double:
                lines = [x for l in lines for x in (l, "")]
            plain = bare or length <= 10
            body = length if plain else length - 10
            page = 0
            for start in range(0, max(len(lines), 1), body * columns):
                chunk = lines[start:start + body * columns]
                page += 1
                rows = self._columns(chunk, columns, width) if columns > 1 else chunk
                rows = [" " * offset + r for r in rows]
                if plain:
                    out += rows
                    continue
                out += ["", "", f"{STAMP_PR} {title} Page {page}", "", ""]
                out += rows + [""] * (body - len(rows)) + [""] * 5
        return out

    @staticmethod
    def _columns(chunk: list[str], n: int, width: int) -> list[str]:
        per = -(-len(chunk) // n)
        colw = width // n
        rows = []
        for r in range(per):
            cells = [chunk[c * per + r] if c * per + r < len(chunk) else "" for c in range(n)]
            rows.append("".join(cell[:colw - 1].ljust(colw) for cell in cells[:-1]) + cells[-1][:colw - 1])
        return [r.rstrip() if not r.strip() else r for r in rows]

    def cmd_split(self, args: list[str]) -> list[str]:
        lines_per, suffix, rest, i = 1000, 2, [], 0
        while i < len(args):
            a = args[i]
            nxt = args[i + 1] if i + 1 < len(args) else ""
            if a == "-l" and nxt.isdigit():
                lines_per, i = max(int(nxt), 1), i + 1
            elif a == "-a" and nxt.isdigit():
                suffix, i = max(int(nxt), 1), i + 1
            elif a.startswith("-") and len(a) > 1 and a != "-":
                self.status = 1
                return [Err(f"split: illegal option -- {a[1]}")] + self._err_lines(SPLIT_USAGE)
            else:
                rest.append(a)
            i += 1
        source = rest[0] if rest else "-"
        prefix = rest[1] if len(rest) > 1 else "x"
        text = "".join(l + "\n" for l in self.stdin or []) if source == "-" else self._file(source)
        if text is None:
            self.status = 1
            return [Err("cannot open input")]
        lines = _lines(text)
        names = []
        for n in range(0, len(lines), lines_per):
            index = n // lines_per
            if index >= 26 ** suffix:
                self.status = 1
                return [Err("split: too many files")]
            tail = "".join(chr(97 + (index // 26 ** p) % 26) for p in reversed(range(suffix)))
            target = self.path(prefix + tail)
            try:
                ifs.write(self.store, self.actor, target, "".join(l + "\n" for l in lines[n:n + lines_per]), umask=self.umask)
            except ifs.IfsError as exc:
                self.status = 1
                return [self._write_error("split", exc, prefix + tail)]
            names.append(target)
        return []
