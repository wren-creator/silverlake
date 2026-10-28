"""PASE batch B4, the text filters: sort uniq cut tr sed nl fold rev tee xargs.

Wording, usage lines and statuses come from the PUB400 run of 2026-10-28 (ssh-pase-b4, kept local). Where the run did not
reach a case (an unknown option on `rev`, say) the wording is a guess and docs/pase.md says so. Every filter reads a file
or the pipe and returns lines; nothing here reaches a host file or process. Work is capped: MAX_LINES lines in, MAX_LINE
characters a line, and sed refuses a pattern that could take forever to match."""

from __future__ import annotations

import re

from . import ifs

MAX_LINES = 20000
MAX_LINE = 4096
MAX_RUNS = 200                                  # commands one xargs may start


class Err(str):
    """A line meant for stderr. It is still a str, so callers and tests see plain text, but a pipe or a `>` leaves it out and
    the terminal still shows it, in order."""


TR_USAGE = ("tr: Invalid combination of options and Strings.\n"
            "Usage: tr [ [-c|-C] | -[c|C]ds | -[c|C]s | -ds | -s ] [-A] String1 String2\n"
            "       tr { -[c|C]d | -[c|C]s | -d | -s } [-A] String1\n"
            "       [LANG=ll_RR] tr -L c1-cn C1-Cn c1c2c3c4c5c6...cn C1C2C3C4C5C6...CN (add a user specified range)\n"
            "       [LANG=ll_RR] tr -L c1-cn C1-Cn (delete a user specified range)")
CUT_USAGE = "Usage: cut {-b <list> [-n] | -c <list> | -f <list> [-d <char>] [-s]} file ..."
SED_USAGE = "Usage:\tsed [-n] [-u] Script [File ...]\n\tsed [-n] [-u] [-e Script] ... [-f Script_file] ... [File ...]"
SORT_USAGE = ("Usage:   sort\t[-AbcCdfimnru] [-T Directory] [-t Character] [-o File]\n"
              "\t\t[-y[Kilobytes]] [-z Recordsize] [-k Keydefinition]...\n"
              "\t\t[[+Position1][-Position2]]... [File]...")
UNIQ_USAGE = "Usage: uniq [-c | -d | -u] [-f Fields] [-s Chars] [-Fields] [+Chars] [Input_file [Output_file]]"
FOLD_USAGE = "Usage: fold [-bs] [-w Width] [File...]"

CLASSES = {"alpha": "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ", "digit": "0123456789",
           "lower": "abcdefghijklmnopqrstuvwxyz", "upper": "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "space": " \t\n\r\f\v",
           "alnum": "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789", "punct": "!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~"}


def tr_set(text: str) -> str:
    """The characters a tr string stands for: escapes (\\n \\t \\\\ \\NNN), ranges (a-z) and classes ([:upper:])."""
    out: list[str] = []
    i = 0
    while i < len(text):
        c = text[i]
        if text.startswith("[:", i) and (end := text.find(":]", i + 2)) > 0 and text[i + 2:end] in CLASSES:
            out.append(CLASSES[text[i + 2:end]])
            i = end + 2
            continue
        if c == "\\" and i + 1 < len(text):
            m = re.match(r"[0-7]{1,3}", text[i + 1:])
            if m:
                c, i = chr(int(m[0], 8)), i + len(m[0])
            else:
                c, i = {"n": "\n", "t": "\t", "r": "\r"}.get(text[i + 1], text[i + 1]), i + 1
        if i + 2 < len(text) and text[i + 1] == "-":
            lo, hi = ord(c), ord(text[i + 2])
            if hi >= lo:
                out.append("".join(chr(n) for n in range(lo, hi + 1)))
                i += 3
                continue
        out.append(c)
        i += 1
    return "".join(out)


def parse_list(spec: str) -> list[tuple[int, int | None]] | None:
    """cut's list: 1,3 or 2-4 or 2- or -3. Ranges as (first, last or None for the end), 1 based."""
    out: list[tuple[int, int | None]] = []
    for part in spec.replace(" ", ",").split(","):
        m = re.fullmatch(r"(\d*)(-?)(\d*)", part)
        if not part or not m or (not m[1] and not m[3]):
            return None
        first = int(m[1]) if m[1] else 1
        last = (int(m[3]) if m[3] else None) if m[2] else first
        if first < 1 or (last is not None and last < first):
            return None
        out.append((first, last))
    return out


def picked(items: list[str], ranges: list[tuple[int, int | None]]) -> list[str]:
    keep = []
    for n, item in enumerate(items, 1):
        if any(a <= n and (b is None or n <= b) for a, b in ranges):
            keep.append(item)
    return keep


# -- sed ---------------------------------------------------------------------------------------------------------

def bre(pattern: str) -> str:
    """A basic regular expression as Python writes it: \\( \\) group, and ( ) | + ? { } are plain characters."""
    out, i = [], 0
    while i < len(pattern):
        c = pattern[i]
        if c == "\\" and i + 1 < len(pattern):
            n = pattern[i + 1]
            out.append({"(": "(", ")": ")", "{": "{", "}": "}"}.get(n, "\\" + n if n.isdigit() else re.escape(n) if n not in "wWsSdDbB" else "\\" + n))
            i += 2
            continue
        out.append("\\" + c if c in "(){}|+?" else c)
        i += 1
    return "".join(out)


class SedError(Exception):
    pass


def sed_compile(script: str):
    """One sed script into a list of commands: (address, function, argument). Functions: s d p q. Addresses: none, N, N,M,
    /re/, $. Raises SedError with PUB400's wording."""
    commands = []
    parts = _split_script(script)
    for text in parts:
        text = text.strip()
        if not text:
            continue
        m = re.match(r"(\d+|\$|/(?:[^/\\]|\\.)*/)?(?:,(\d+|\$))?\s*", text)
        addr = (m[1], m[2]) if m and m[1] else None
        rest = text[m.end():] if m else text
        if not rest:
            raise SedError(f"Function {text} cannot be parsed.")
        fn = rest[0]
        if fn == "s":
            if len(rest) < 2:
                raise SedError(f"Function {text} cannot be parsed.")
            delim = rest[1]
            pieces = _split_on(rest[2:], delim)
            if len(pieces) < 3 or pieces[2] is None:
                raise SedError(f"Function {text} cannot be parsed.")
            pat, repl, flags = pieces[0], pieces[1], pieces[2]
            if re.search(r"\)[*+]|\\\)\*|\\\)\\\{", pat):
                raise SedError(f"Function {text} cannot be parsed.")      # a repeated group is where matching can run away
            try:
                rx = re.compile(bre(pat))
            except re.error:
                raise SedError(f"Function {text} cannot be parsed.")
            commands.append((addr, "s", (rx, repl, "g" in flags, "p" in flags)))
        elif fn in "dpq" and not rest[1:].strip():
            commands.append((addr, fn, None))
        else:
            raise SedError(f"{fn} is not a recognized function.")
    return commands


def _split_script(script: str) -> list[str]:
    parts, cur, i, delim_stack = [], "", 0, None
    while i < len(script):
        c = script[i]
        if c == "\\" and i + 1 < len(script):
            cur += script[i:i + 2]
            i += 2
            continue
        if cur.lstrip()[:1] == "s" and delim_stack is None and len(cur.lstrip()) == 1:
            delim_stack = [c, 1]
        elif delim_stack is not None and c == delim_stack[0]:
            delim_stack[1] += 1
        if (c == ";" or c == "\n") and (delim_stack is None or delim_stack[1] >= 3):
            parts.append(cur)
            cur, delim_stack = "", None
        else:
            cur += c
        i += 1
    parts.append(cur)
    return parts


def _split_on(text: str, delim: str) -> list[str | None]:
    """The pattern, the replacement and the flags of an s command, or fewer when the text ran out."""
    out, cur, i = [], "", 0
    while i < len(text):
        c = text[i]
        if c == "\\" and i + 1 < len(text):
            cur += text[i] + text[i + 1] if text[i + 1] != delim else delim
            i += 2
            continue
        if c == delim and len(out) < 2:
            out.append(cur)
            cur = ""
        else:
            cur += c
        i += 1
    if len(out) == 2:
        out.append(cur)
    return out


def sed_run(commands, lines: list[str], quiet: bool) -> list[str]:
    out: list[str] = []
    total = len(lines)
    ranges: dict[int, bool] = {}
    for n, line in enumerate(lines, 1):
        printed_by_p, deleted, quit_now = False, False, False
        for k, (addr, fn, arg) in enumerate(commands):
            if addr is not None:
                first, last = addr
                if last is None:
                    hit = _hit(first, n, line, total)
                elif ranges.get(k):
                    hit = True
                    if _hit(last, n, line, total):
                        ranges[k] = False
                else:
                    hit = _hit(first, n, line, total)
                    if hit and not _hit(last, n, line, total) and not (last.isdigit() and int(last) <= n):
                        ranges[k] = True
                if not hit:
                    continue
            if fn == "s":
                rx, repl, glob, show = arg
                new = rx.sub(lambda m: _expand(repl, m), line, count=0 if glob else 1)
                if show and new != line:
                    out.append(new)
                line = new
            elif fn == "d":
                deleted = True
                break
            elif fn == "p":
                out.append(line)
            elif fn == "q":
                quit_now = True
        if not deleted and not quiet:
            out.append(line)
        if quit_now:
            break
    return out


def _hit(spec: str, n: int, line: str, total: int) -> bool:
    if spec == "$":
        return n == total
    if spec.isdigit():
        return n == int(spec)
    try:
        return re.search(bre(spec[1:-1]), line) is not None
    except re.error:
        return False


def _expand(repl: str, m: re.Match) -> str:
    out, i = [], 0
    while i < len(repl):
        c = repl[i]
        if c == "\\" and i + 1 < len(repl):
            n = repl[i + 1]
            out.append((m.group(int(n)) or "") if n.isdigit() and int(n) <= (m.re.groups) and n != "0" else
                       "\n" if n == "n" else n)
            i += 2
        elif c == "&":
            out.append(m.group(0))
            i += 1
        else:
            out.append(c)
            i += 1
    return "".join(out)


# -- sort --------------------------------------------------------------------------------------------------------

def sort_key(line: str, key: tuple[int, int | None] | None, sep: str | None, numeric: bool, fold: bool, blanks: bool) -> tuple:
    text = line
    if key is not None:
        fields = line.split(sep) if sep else line.split()
        first, last = key
        text = (sep or " ").join(fields[first - 1:last] if last else fields[first - 1:])
    if blanks:
        text = text.lstrip()
    if numeric:
        m = re.match(r"\s*(-?\d+(?:\.\d+)?)", text)
        return (float(m[1]) if m else 0.0, line)
    return ((text.lower() if fold else text), line)


class Filters:
    """Mixed into the Shell. Each cmd_ reads self.stdin or named files and returns lines, setting self.status."""

    def _input(self, name: str, files: list[str], bad_status: int, message) -> tuple[list[str] | None, list[str]]:
        """All the lines of the files, or of the pipe when none are named; (None, errors) if one could not be read."""
        if not files:
            return list((self.stdin or [])[:MAX_LINES]), []
        lines: list[str] = []
        errors: list[str] = []
        for given in files:
            if given == "-":
                lines += list(self.stdin or [])
                continue
            try:
                lines += ifs.read(self.store, self.actor, self.path(given)).splitlines()
            except ifs.IfsError:
                errors.append(Err(message(given)))
                self.status = bad_status
        if errors:
            return None, errors
        return [l[:MAX_LINE] for l in lines[:MAX_LINES]], []

    @staticmethod
    def _usage_text(text: str) -> list[str]:
        return [Err(l) for l in text.split("\n")]

    # -- sort uniq rev nl fold ---------------------------------------------------------------------------------

    def cmd_sort(self, args: list[str]) -> list[str]:
        flags: set[str] = set()
        sep = key = None
        files: list[str] = []
        i = 0
        while i < len(args):
            a = args[i]
            if a == "--":
                files += args[i + 1:]
                break
            if a.startswith("-") and len(a) > 1:
                for n, ch in enumerate(a[1:]):
                    if ch in "tkzoTy":
                        value = a[n + 2:] or (args[i + 1] if i + 1 < len(args) else None)
                        if value is None:
                            self.status = 2
                            return [Err(f"sort: option requires an argument -- {ch}")] + self._usage_text(SORT_USAGE)
                        if not a[n + 2:]:
                            i += 1
                        if ch == "t":
                            sep = value[:1]
                        elif ch == "k":
                            m = re.match(r"(\d+)(?:\.\d+)?(?:,(\d+))?", value)
                            if not m or int(m[1]) < 1:
                                self.status = 2
                                return [Err(f"sort: bad key {value}")]
                            key = (int(m[1]), int(m[2]) if m[2] else None)
                        break
                    if ch not in "AbcCdfimnru":
                        self.status = 2
                        return [Err(f"sort: illegal option -- {ch}")] + self._usage_text(SORT_USAGE)
                    flags.add(ch)
            else:
                files.append(a)
            i += 1
        lines, errors = self._input("sort", files, 2, lambda g: f"sort: can't open {g}")
        if lines is None:
            return errors
        keyed = [(sort_key(l, key, sep, "n" in flags, "f" in flags, "b" in flags), l) for l in lines]
        if flags & {"c", "C"}:
            for (k1, _), (k2, l2) in zip(keyed, keyed[1:]):
                if (k2 > k1) if "r" in flags else (k2 < k1):
                    self.status = 1
                    return [] if "C" in flags else [Err(f"sort: disorder: {l2}")]
            return []
        keyed.sort(key=lambda p: p[0], reverse="r" in flags)
        out = [l for _, l in keyed]
        if "u" in flags:
            seen, unique = set(), []
            for k, l in keyed:
                if k[0] not in seen:
                    seen.add(k[0])
                    unique.append(l)
            out = unique
        return out

    def cmd_uniq(self, args: list[str]) -> list[str]:
        flags, files, skip_f, skip_s = set(), [], 0, 0
        i = 0
        while i < len(args):
            a = args[i]
            if a in ("-f", "-s") and i + 1 < len(args) and args[i + 1].isdigit():
                if a == "-f":
                    skip_f = int(args[i + 1])
                else:
                    skip_s = int(args[i + 1])
                i += 2
                continue
            if re.fullmatch(r"-\d+", a):
                skip_f = int(a[1:])
            elif re.fullmatch(r"\+\d+", a):
                skip_s = int(a[1:])
            elif a.startswith("-") and len(a) > 1:
                bad = [c for c in a[1:] if c not in "cdu"]
                if bad:
                    self.status = 1
                    return [Err(f"uniq: illegal option -- {bad[0]}")] + self._usage_text(UNIQ_USAGE)
                flags |= set(a[1:])
            else:
                files.append(a)
            i += 1
        lines, errors = self._input("uniq", files[:1], 1, lambda g: f"uniq: cannot open {g}")
        if lines is None:
            return errors

        def same(a: str, b: str) -> bool:
            def cut(s: str) -> str:
                s = " ".join(s.split()[skip_f:]) if skip_f else s
                return s[skip_s:]
            return cut(a) == cut(b)

        groups: list[list[str]] = []
        for line in lines:
            if groups and same(groups[-1][0], line):
                groups[-1].append(line)
            else:
                groups.append([line])
        out = []
        for g in groups:
            if ("d" in flags and len(g) < 2) or ("u" in flags and len(g) > 1):
                continue
            out.append(f"{len(g):4d} {g[0]}" if "c" in flags else g[0])
        return out

    def cmd_rev(self, args: list[str]) -> list[str]:
        lines, errors = self._input("rev", [a for a in args if not a.startswith("-") or a == "-"], 1,
                                    lambda g: f"rev: cannot open {g}")
        return errors if lines is None else [l[::-1] for l in lines]

    def cmd_nl(self, args: list[str]) -> list[str]:
        style, sep, width, files, i = "t", "\t", 6, [], 0
        while i < len(args):
            a = args[i]
            if a.startswith("-b") and len(a) > 2:
                style = a[2:]
            elif a == "-b" and i + 1 < len(args):
                style, i = args[i + 1], i + 1
            elif a.startswith("-s") and len(a) > 2:
                sep = a[2:]
            elif a == "-s" and i + 1 < len(args):
                sep, i = args[i + 1], i + 1
            elif a.startswith("-w") and a[2:].isdigit():
                width = int(a[2:])
            elif a == "-w" and i + 1 < len(args) and args[i + 1].isdigit():
                width, i = int(args[i + 1]), i + 1
            elif not a.startswith("-") or a == "-":
                files.append(a)
            i += 1
        lines, errors = self._input("nl", files, 1, lambda g: f"CANNOT OPEN FILE {g}")
        if lines is None:
            return errors
        out, n = [], 0
        for line in lines:
            if style == "n" or (style == "t" and not line.strip()):
                out.append(" " * (width + len(sep)) + line if line else "")       # blank lines are left alone: a guess, not captured
            else:
                n += 1
                out.append(f"{n:>{width}}{sep}{line}")
        return out

    def cmd_fold(self, args: list[str]) -> list[str]:
        width, spaces, files, i = 80, False, [], 0
        while i < len(args):
            a = args[i]
            if a == "-w" and i + 1 < len(args) and args[i + 1].isdigit():
                width, i = int(args[i + 1]), i + 1
            elif re.fullmatch(r"-w\d+", a):
                width = int(a[2:])
            elif re.fullmatch(r"-\d+", a):
                width = int(a[1:])
            elif a.startswith("-") and len(a) > 1:
                bad = [c for c in a[1:] if c not in "bs"]
                if bad:
                    self.status = 1
                    return [Err(f"fold: illegal option -- {bad[0]}")] + self._usage_text(FOLD_USAGE)
                spaces = spaces or "s" in a
            else:
                files.append(a)
            i += 1
        width = max(width, 1)
        lines, errors = self._input("fold", files, 2, lambda g: f"Cannot open file {g}")
        if lines is None:
            return errors
        out: list[str] = []
        for line in lines:
            while len(line) > width:
                cut = width
                if spaces:
                    at = line.rfind(" ", 0, width)
                    cut = at + 1 if at >= 0 else width
                out.append(line[:cut])
                line = line[cut:]
            out.append(line)
        return out

    # -- cut tr tee --------------------------------------------------------------------------------------------

    def cmd_cut(self, args: list[str]) -> list[str]:
        mode = spec = None
        delim, only, files, i = "\t", False, [], 0
        while i < len(args):
            a = args[i]
            if a[:2] in ("-b", "-c", "-f") and len(a) >= 2:
                value = a[2:] or (args[i + 1] if i + 1 < len(args) else None)
                if value is None:
                    break
                if not a[2:]:
                    i += 1
                mode, spec = a[1], value
            elif a[:2] == "-d":
                value = a[2:] or (args[i + 1] if i + 1 < len(args) else "")
                if not a[2:]:
                    i += 1
                delim = value[:1] or "\t"
            elif a == "-s":
                only = True
            elif a == "-n":
                pass
            elif a.startswith("-") and len(a) > 1:
                self.status = 1
                return [Err(f"cut: illegal option -- {a[1]}")] + self._usage_text(CUT_USAGE)
            else:
                files.append(a)
            i += 1
        ranges = parse_list(spec) if spec else None
        if mode is None or ranges is None:
            self.status = 1
            return self._usage_text(CUT_USAGE)
        lines, errors = self._input("cut", files, 1, lambda g: f"cut: cannot open {g}")      # the missing file wording is a guess
        if lines is None:
            return errors
        out = []
        for line in lines:
            if mode in "bc":
                out.append("".join(picked(list(line), ranges)))
            elif delim not in line:
                if not only:
                    out.append(line)
            else:
                out.append(delim.join(picked(line.split(delim), ranges)))
        return out

    def cmd_tr(self, args: list[str]) -> list[str]:
        flags = "".join(a[1:] for a in args if a.startswith("-") and len(a) > 1 and a != "-L")
        sets = [a for a in args if not a.startswith("-") or a == "-"]
        want = 1 if ("d" in flags or ("s" in flags and not sets[1:])) and not ("d" in flags and "s" in flags) else 2
        if "d" in flags and "s" in flags:
            want = 2
        if not sets or len(sets) != want and not ("s" in flags and len(sets) in (1, 2)) or set(flags) - set("cCdsA"):
            self.status = 1
            return self._usage_text(TR_USAGE)
        text = "\n".join(self.stdin or [])
        if self.stdin:
            text += "\n"
        first = tr_set(sets[0])
        if "d" in flags:
            kill = set(first)
            text = "".join(c for c in text if (c in kill) == bool(set("cC") & set(flags)))
            if "s" in flags and len(sets) > 1:
                text = self._squeeze(text, set(tr_set(sets[1])))
        elif len(sets) > 1 and not (set("cC") & set(flags)):         # -c with a translation did nothing on PUB400: kept as seen
            to = tr_set(sets[1])
            table = {}
            for n, c in enumerate(first):
                table.setdefault(c, to[min(n, len(to) - 1)] if to else c)
            text = "".join(table.get(c, c) for c in text)
            if "s" in flags:
                text = self._squeeze(text, set(to))
        elif "s" in flags:
            text = self._squeeze(text, set(first))
        return text[:-1].split("\n") if text.endswith("\n") else (text.split("\n") if text else [])

    @staticmethod
    def _squeeze(text: str, chars: set[str]) -> str:
        out: list[str] = []
        for c in text:
            if out and out[-1] == c and c in chars:
                continue
            out.append(c)
        return "".join(out)

    def cmd_tee(self, args: list[str]) -> list[str]:
        append = "-a" in args
        lines = list(self.stdin or [])
        out: list[str] = []
        for given in [a for a in args if not a.startswith("-")]:
            if given == "/dev/null":
                continue
            try:
                ifs.write(self.store, self.actor, self.path(given), "".join(l + "\n" for l in lines), append=append,
                          umask=self.umask)
            except ifs.IfsError as exc:
                out.append(self._write_error("tee", exc, given))
                self.status = 1
        return lines + out

    def cmd_sed(self, args: list[str]) -> list[str]:
        quiet, scripts, files, i = False, [], [], 0
        while i < len(args):
            a = args[i]
            if a == "-n":
                quiet = True
            elif a == "-u":
                pass
            elif a == "-e" and i + 1 < len(args):
                scripts.append(args[i + 1])
                i += 1
            elif a.startswith("-") and len(a) > 1:
                self.status = 1
                return [Err(f"sed: illegal option -- {a[1]}")] + self._usage_text(SED_USAGE)        # a guess at the wording
            elif not scripts:
                scripts.append(a)
            else:
                files.append(a)
            i += 1
        if not scripts:
            self.status = 1
            return self._usage_text(SED_USAGE)
        try:
            commands = sed_compile("\n".join(scripts))
        except SedError as exc:
            self.status = 2
            return [Err(f"sed: {exc}")]
        lines, errors = self._input("sed", files, 2, lambda g: f"sed: Cannot open {g}.")      # a guess: the missing file was not run
        if lines is None:
            return errors
        return sed_run(commands, lines, quiet)

    # -- xargs -------------------------------------------------------------------------------------------------

    def cmd_xargs(self, args: list[str]) -> list[str]:
        per, repl, trace, i = None, None, False, 0
        while i < len(args) and args[i].startswith("-") and len(args[i]) > 1:
            a = args[i]
            if a == "-n" and i + 1 < len(args) and args[i + 1].isdigit():
                per, i = max(int(args[i + 1]), 1), i + 1
            elif re.fullmatch(r"-n\d+", a):
                per = max(int(a[2:]), 1)
            elif a == "-I" and i + 1 < len(args):
                repl, i = args[i + 1], i + 1
            elif a.startswith("-I") and len(a) > 2:
                repl = a[2:]
            elif a == "-t":
                trace = True
            elif a == "-p":
                self.status = 1
                return [Err("xargs: can't read from tty for -p")]
            else:
                self.status = 1
                return [Err(f"xargs: illegal option -- {a[1]}")]
            i += 1
        command = args[i:] or ["echo"]
        name = command[0]
        if (not re.fullmatch(r"[A-Za-z][A-Za-z0-9]*", name) or not hasattr(self, "cmd_" + name)
                or name in self.NOT_FILES) and self.find_script(name) is None:
            self.status = 127
            return [Err(f"xargs: {name}: No such file or directory")]
        source = [l for l in (self.stdin or [])[:MAX_LINES]]
        if repl is not None:
            batches = [[l] for l in source if l.strip()]
        else:
            words = [w for l in source for w in l.split()]
            size = per or max(len(words), 1)
            batches = [words[n:n + size] for n in range(0, len(words), size)]
        out: list[str] = []
        failed = False
        for batch in batches[:MAX_RUNS]:
            if repl is not None:
                words = [a.replace(repl, batch[0]) for a in command]
            else:
                words = command + batch
            line = " ".join(_quote(w) for w in words)
            if trace:
                out.append(Err(" ".join(words) + " "))
            out += self.run(line)
            failed = failed or self.status != 0
            if self.done or self.leaving:
                break
        self.status = 123 if failed else 0
        return out


def _quote(word: str) -> str:
    return "'" + word.replace("'", "'\\''") + "'" if word and not re.fullmatch(r"[\w./:=@%+,-]+", word) else (word or "''")
