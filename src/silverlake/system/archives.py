"""PASE batch B6, archives and odds and ends: tar zcat compress uncompress pax ar more sleep time.

Usage lines, error text and statuses come from the PUB400 run of 2026-10-28 (ssh-pase-b6, kept local). What that run did not
reach (the listing layouts, the `-v` lines, what a damaged archive says) is a guess and docs/pase.md says so.

The virtual IFS holds text, not bytes, so these are not the real file formats. An archive is a text container that
`tar`, `pax` and `ar` all read and write (`ar` marks its own with `!<arch>`), and a `.Z` file is the original text behind a
marker line, so `compress` does not shrink anything. Round trips work and nothing here touches a host file or process.
Work is capped: MAX_ENTRIES members and MAX_BYTES of content to an archive. `sleep` never waits and `time` shows fixed
figures, because nothing in the simulator runs for a measurable time."""

from __future__ import annotations

import re

from . import ifs
from .textfilters import Err

MAX_ENTRIES = 2000
MAX_BYTES = 1_000_000
TAR_MAGIC = "SLTAR1"
AR_MAGIC = "!<arch>"
Z_MARK = "\x1f\x9dSLZ1"
STAMP = "Oct 26 09:00 2026"
MAX_TIME_DEPTH = 8

TAR_USAGE = ("Usage: tar -{c|r|t|u|x} [ -BdDEFhilmopRsUvwZ ] [ -Number ] [ -f TarFile ]\n"
             "\t   [ -b Blocks ] [ -S [ Feet ] | [ Feet@Density ] | [ Blocksb ] ]\n"
             "\t   [ -L InputList ] [-X ExcludeFile] [ -N Blocks ] [ -C Directory ] File ...\n"
             "Usage: tar {c|r|t|u|x} [ bBdDEfFhilLXmNopRsSUvwZ[0-9] ]\n"
             "\t   [ Blocks ] [ TarFile ] [ InputList ] [ ExcludeFile ] \n"
             "\t   [ [ Feet ] | [ Feet@Density ] | [ Blocksb ] ] [-C Directory ] File ...")
AR_USAGE = ("Usage: ar [-X{32|64|32_64|d64|any}] [-clsvCT] [-g|o] {-h|p|t|x}\n"
            "\t\t [--] Archive [File ...]\n"
            "\tar [-X{32|64|32_64|d64|any}] [-clsvCT] [-g|o] {-m|r[u]}\n"
            "\t\t[{-a|b|i} {PositionName}] [--] Archive File ...\n"
            "\tar [-X{32|64|32_64|d64|any}] [-clsvCT] [-g|o] {-d|q} [--]\n"
            "\t\t Archive File ...\n"
            "\tar [-X{32|64|32_64|d64|any}] [-clvCT] {-g|o|s|w} [--] Archive")
TIME_USAGE = "usage: time [-p] utility [argument...]"
SLEEP_USAGE = "usage: sleep time"

# tar's key letters: those that take the next word, those that do nothing here, and the three it does
TAR_ARGS = set("bfLXNS")
TAR_QUIET = set("BdDEFhilmopRsUwZ0123456789")


def pack(magic: str, entries: list[tuple[str, str, int, str]]) -> str:
    """(kind, name, octal mode, text) members into the container: a header line per member, then the text, then a newline."""
    out = [magic, "\n"]
    for kind, name, mode, text in entries:
        out.append(f"{kind} {mode:o} {len(text)} {name}\n{text}\n")
    return "".join(out)


def unpack(magic: str, text: str) -> list[tuple[str, str, int, str]] | None:
    """The members of a container, or None when it is not one (wrong magic, a header that does not parse, a short body)."""
    if not text.startswith(magic + "\n"):
        return None
    pos, members = len(magic) + 1, []
    while pos < len(text) and len(members) <= MAX_ENTRIES:
        end = text.find("\n", pos)
        m = re.fullmatch(r"(file|dir) ([0-7]+) (\d+) (.+)", text[pos:end]) if end != -1 else None
        if not m:
            return None
        size = int(m.group(3))
        body = text[end + 1:end + 1 + size]
        if len(body) != size or text[end + 1 + size:end + 2 + size] != "\n":
            return None
        members.append((m.group(1), m.group(4), int(m.group(2), 8), body))
        pos = end + 2 + size
    return members


def _octal(mode: str) -> int:
    return sum(1 << (2 - i) for i, c in enumerate(mode) if c != "-" and i < 3)


def perm_string(kind: str, mode: int) -> str:
    bits = "".join(("r" if (mode >> s) & 4 else "-") + ("w" if (mode >> s) & 2 else "-") + ("x" if (mode >> s) & 1 else "-")
                   for s in (6, 3, 0))
    return ("d" if kind == "dir" else "-") + bits


def _blocks(size: int) -> int:
    return (size + 511) // 512


def _to_lines(text: str) -> list[str]:
    return text.split("\n")[:-1]


def _from_lines(lines: list[str] | None) -> str:
    return "".join(l + "\n" for l in lines or [])


class Archives:
    """Mixed into the Shell beside Filters and Heavy."""

    # -- shared -------------------------------------------------------------------------------------------------

    def _gather(self, given: str, name: str, out: list, budget: list[int]) -> str | None:
        """Add a file, or a directory and everything under it, to `out`. A message when something cannot be read."""
        try:
            entry = ifs.lookup(self.store, self.actor, self.path(given))
        except ifs.IfsError:
            return f"{name}: No such file or directory"
        mode = (_octal(entry.owner_mode) << 6) | (_octal(entry.public) << 3) | _octal(entry.public)
        if entry.is_dir:
            out.append(("dir", name.rstrip("/") + "/", mode, ""))
            try:
                children = ifs.listdir(self.store, self.actor, self.path(given))
            except ifs.IfsError:
                return f"{name}: Permission denied"
            for child in children:
                base = child.path.rsplit("/", 1)[-1]
                message = self._gather(child.path, f"{name.rstrip('/')}/{base}", out, budget)
                if message:
                    return message
            return None
        try:
            text = ifs.read(self.store, self.actor, self.path(given))
        except ifs.IfsError:
            return f"{name}: Permission denied"
        budget[0] += len(text)
        if len(out) >= MAX_ENTRIES or budget[0] > MAX_BYTES:
            return f"{name}: the simulator stops an archive at {MAX_ENTRIES} members and {MAX_BYTES} bytes"
        out.append(("file", name, mode, text))
        return None

    def _put(self, target: str, text: str, command: str) -> str | None:
        try:
            ifs.write(self.store, self.actor, self.path(target), text, umask=self.umask)
        except ifs.IfsError as exc:
            return self._write_error(command, exc, target)
        return None

    def _extract(self, members: list, command: str, verbose, names: list[str] | None = None) -> list[str]:
        out: list[str] = []
        for kind, name, mode, text in members:
            if names and not any(name.rstrip("/") == n.rstrip("/") or name.startswith(n.rstrip("/") + "/") for n in names):
                continue
            target = self.path(name)
            try:
                for parent in self._parents(target):
                    ifs.make(self.store, self.actor, parent, "dir", umask=self.umask)
                if kind == "dir":
                    if target not in self.store.ifs:
                        ifs.make(self.store, self.actor, target, "dir", umask=self.umask)
                else:
                    ifs.write(self.store, self.actor, target, text, umask=self.umask)
                    if mode & 0o100:
                        ifs.chmod(self.store, self.actor, target, "u+x")
            except ifs.IfsError as exc:
                out.append(self._write_error(command, exc, name))
                continue
            if verbose:
                out.append(verbose(kind, name, mode, text))
        return out

    def _parents(self, target: str) -> list[str]:
        """The directories above `target` that do not exist yet, outermost first."""
        missing, cur = [], target.rsplit("/", 1)[0]
        while cur and cur not in self.store.ifs and cur != "/":
            missing.append(cur)
            cur = cur.rsplit("/", 1)[0]
        return missing[::-1]

    # -- tar ----------------------------------------------------------------------------------------------------

    def cmd_tar(self, args: list[str]) -> list[str]:
        usage = [Err(l) for l in TAR_USAGE.split("\n")]
        self.status = 1
        if not args:
            return usage
        dashed = args[0].startswith("-")
        key, rest = args[0].lstrip("-"), list(args[1:])
        if args[0].startswith("--"):
            return [Err("tar: illegal option -- -")] + usage
        function, verbose, archive, i, words = "", False, None, 0, []
        letters = list(key)
        for n, ch in enumerate(letters):
            if ch in "ctx":
                function = function or ch
            elif ch == "v":
                verbose = True
            elif ch in TAR_ARGS:
                if not rest:
                    return usage
                value = rest.pop(0)
                archive = value if ch == "f" else archive
            elif ch in TAR_QUIET:
                pass
            elif ch in "ru":
                return [Err(f"tar: -{ch} (append and update) is not built into the simulator.")]
            else:
                return ([Err(f"tar: illegal option -- {ch}")] if dashed else []) + usage
        while rest and rest[0].startswith("-") and len(rest[0]) > 1:      # -f after the key letters, or more flags
            flag = rest.pop(0)
            if flag == "-f" and rest:
                archive = rest.pop(0)
            elif flag == "-v":
                verbose = True
        words = rest
        if not function:
            return usage
        if archive is None:
            archive = "/dev/rmt0"
        return {"c": self._tar_create, "t": self._tar_list, "x": self._tar_extract}[function](archive, words, verbose)

    def _tar_open(self, archive: str) -> tuple[list | None, list[str]]:
        if archive == "-":
            if self.stdin is None:
                self.status = 1
                return None, [Err("tar: -: No such file or directory")]
            text = _from_lines(self.stdin)
        else:
            try:
                text = ifs.read(self.store, self.actor, self.path(archive))
            except ifs.IfsError:
                self.status = 1
                return None, [Err(f"tar: {archive}: No such file or directory")]
        members = unpack(TAR_MAGIC, text)
        if members is None:
            self.status = 1
            return None, [Err("tar: This is not a valid tar archive file.")]        # a guess: nothing damaged was ever read
        return members, []

    def _tar_create(self, archive: str, words: list[str], verbose: bool) -> list[str]:
        members: list = []
        out: list[str] = []
        for given in words:
            message = self._gather(given, given, members, [0])
            if message:
                self.status = 2
                return [Err("tar: " + message)]
        if not words:
            self.status = 1
            return [Err(l) for l in TAR_USAGE.split("\n")]
        if verbose:
            for kind, name, mode, text in members:
                out.append(f"a {name.rstrip('/') if kind == 'dir' else name}, " +
                           (f"{len(text)} bytes, {_blocks(len(text))} media blocks." if kind == "file" else "0 media blocks."))
        text = pack(TAR_MAGIC, members)
        self.status = 0
        if archive == "-":
            return _to_lines(text)
        failed = self._put(archive, text, "tar")
        if failed:
            return [Err(failed)]
        return out

    def _tar_list(self, archive: str, words: list[str], verbose: bool) -> list[str]:
        members, errors = self._tar_open(archive)
        if members is None:
            return errors
        self.status = 0
        keep = [m for m in members if not words or any(m[1].rstrip("/") == w.rstrip("/") or m[1].startswith(w.rstrip("/") + "/")
                                                       for w in words)]
        if verbose:
            return [f"{perm_string(k, mode)} {0:>3}/{0:<3} {len(text):>7} {STAMP} {name}" for k, name, mode, text in keep]
        return [name for _, name, _, _ in keep]

    def _tar_extract(self, archive: str, words: list[str], verbose: bool) -> list[str]:
        members, errors = self._tar_open(archive)
        if members is None:
            return errors
        self.status = 0
        say = (lambda k, n, m, t: f"x {n.rstrip('/')}, " + (f"{len(t)} bytes, {_blocks(len(t))} media blocks." if k == "file"
                                                          else "0 media blocks.")) if verbose else None
        out = self._extract(members, "tar", say, words)
        if any(isinstance(l, Err) for l in out):
            self.status = 1
        return out

    # -- compress, uncompress, zcat --------------------------------------------------------------------------------

    def _z_args(self, args: list[str]) -> tuple[bool, list[str], str | None]:
        to_stdout, files = False, []
        for a in args:
            if a == "-c":
                to_stdout = True
            elif a in ("-f", "-v", "-d", "-q"):
                pass
            elif a.startswith("-") and len(a) > 1:
                return to_stdout, files, a
            else:
                files.append(a)
        return to_stdout, files, None

    def cmd_compress(self, args: list[str]) -> list[str]:
        to_stdout, files, bad = self._z_args(args)
        if bad:
            self.status = 2
            return [Err(f"compress: illegal option -- {bad[1]}"), Err("Usage: compress [-fvcC] [-b bits] [file ...]")]
        self.status = 0
        if not files:
            if self.stdin is None:
                return []
            return [Z_MARK] + list(self.stdin)
        out: list[str] = []
        for given in files:
            try:
                text = ifs.read(self.store, self.actor, self.path(given))
            except ifs.IfsError:
                self.status = 1
                out.append(Err(f"{given}: No such file or directory"))
                continue
            packed = Z_MARK + "\n" + text
            if to_stdout:
                out += _to_lines(packed) if packed.endswith("\n") else packed.split("\n")
                continue
            failed = self._put(given + ".Z", packed, "compress")
            if failed:
                out.append(failed)
                continue
            try:
                ifs.remove(self.store, self.actor, self.path(given))
            except ifs.IfsError as exc:
                out.append(self._write_error("compress", exc, given))
        return out

    def _unz(self, name: str, to_stdout: bool, command: str, text: str | None = None) -> list[str]:
        shown = name if name.endswith(".Z") else name + ".Z"
        if text is None:
            try:
                text = ifs.read(self.store, self.actor, self.path(shown))
            except ifs.IfsError:
                self.status = 1
                return [Err(f"{shown}: No such file or directory")]
        if not text.startswith(Z_MARK + "\n"):
            self.status = 1
            return [Err(f"{shown}: not in compressed format")]                      # a guess
        body = text[len(Z_MARK) + 1:]
        if to_stdout:
            return _to_lines(body) if body.endswith("\n") else body.split("\n") if body else []
        target = shown[:-2]
        failed = self._put(target, body, command)
        if failed:
            return [failed]
        try:
            ifs.remove(self.store, self.actor, self.path(shown))
        except ifs.IfsError as exc:
            return [self._write_error(command, exc, shown)]
        return []

    def cmd_uncompress(self, args: list[str]) -> list[str]:
        to_stdout, files, bad = self._z_args(args)
        if bad:
            self.status = 2
            return [Err(f"uncompress: illegal option -- {bad[1]}"), Err("Usage: uncompress [-cfqv] [file ...]")]
        self.status = 0
        if not files and self.stdin is not None:
            return self._unz("stdin", True, "uncompress", _from_lines(self.stdin))
        out: list[str] = []
        for given in files:
            out += self._unz(given, to_stdout, "uncompress")
        return out

    def cmd_zcat(self, args: list[str]) -> list[str]:
        _, files, bad = self._z_args(args)
        if bad:
            self.status = 2
            return [Err(f"zcat: illegal option -- {bad[1]}"), Err("Usage: zcat [file ...]")]
        self.status = 0
        if not files and self.stdin is not None:
            return self._unz("stdin", True, "zcat", _from_lines(self.stdin))
        out: list[str] = []
        for given in files:
            out += self._unz(given, True, "zcat")
        return out

    # -- pax ----------------------------------------------------------------------------------------------------

    def cmd_pax(self, args: list[str]) -> list[str]:
        mode, verbose, archive, words, i = "", False, None, [], 0
        while i < len(args):
            a = args[i]
            if a == "-f" and i + 1 < len(args):
                archive, i = args[i + 1], i + 1
            elif a.startswith("-") and len(a) > 1 and a != "-":
                for ch in a[1:]:
                    if ch in "rw":
                        mode += ch
                    elif ch == "v":
                        verbose = True
                    elif ch not in "dkunx":
                        self.status = 2
                        return [Err(f"pax: illegal option -- {ch}"), Err("Usage: pax [-cdnvx] [-f archive] [pattern ...]")]
            else:
                words.append(a)
            i += 1
        self.status = 0
        if mode == "w":
            names = words or [l for l in self.stdin or [] if l]
            members: list = []
            for given in names:
                message = self._gather(given, given, members, [0])
                if message:
                    self.status = 1
                    return [Err("pax: " + message)]
            text = pack(TAR_MAGIC, members)
            if archive is None or archive == "-":
                return _to_lines(text)
            failed = self._put(archive, text, "pax")
            return [Err(failed)] if failed else []
        if archive is None or archive == "-":
            if not self.stdin:                      # PUB400 printed this for an empty stdin; a bare `pax` there sat waiting
                self.status = 1
                return [Err("pax: No input")]
            text = _from_lines(self.stdin)
        else:
            try:
                text = ifs.read(self.store, self.actor, self.path(archive))
            except ifs.IfsError:
                self.status = 1
                return [Err(f"pax: {archive}: No such file or directory")]      # a guess: only the empty input was seen
        members = unpack(TAR_MAGIC, text)
        if members is None:
            self.status = 1
            return [Err("pax: Invalid archive format")]
        if mode == "r":
            say = (lambda k, n, m, t: n) if verbose else None
            out = self._extract(members, "pax", say, words)
            if any(isinstance(l, Err) for l in out):
                self.status = 1
            return out
        if verbose:
            return [f"{perm_string(k, m)} {0:>3}/{0:<3} {len(t):>7} {STAMP} {n}" for k, n, m, t in members]
        return [n for _, n, _, _ in members]

    # -- ar -----------------------------------------------------------------------------------------------------

    def cmd_ar(self, args: list[str]) -> list[str]:
        usage = [Err(l) for l in AR_USAGE.split("\n")]
        if len(args) < 2:
            self.status = 1
            return usage
        flags = args[0].lstrip("-")
        op = next((c for c in flags if c in "tprxdq"), "")
        if not op or any(c not in "tprxdqcvlsCTgo" for c in flags):
            self.status = 1
            return usage
        verbose = "v" in flags
        archive, files = args[1], args[2:]
        self.status = 0
        try:
            text = ifs.read(self.store, self.actor, self.path(archive))
        except ifs.IfsError:
            text = None
        if text is None and op in "tpxd":
            self.status = 1
            return [Err(f"ar: 0707-100 {archive} does not exist.")]
        members = unpack(AR_MAGIC, text) if text is not None else []
        if members is None:
            self.status = 1
            return [Err(f"ar: {archive} is not in the archive format.")]                     # a guess
        if op == "t":
            names = [m for m in members if not files or m[1] in files]
            if verbose:
                return [f"{perm_string(k, mode)} {0:>3}/{0:<3} {len(t):>7} {STAMP} {n}" for k, n, mode, t in names]
            return [n for _, n, _, _ in names]
        if op == "p":
            out: list[str] = []
            for _, n, _, t in members:
                if not files or n in files:
                    out += t.split("\n")[:-1] if t.endswith("\n") else t.split("\n") if t else []
            return out
        if op == "x":
            out = self._extract([m for m in members if m[0] == "file" and (not files or m[1] in files)], "ar",
                                (lambda k, n, m, t: f"x - {n}") if verbose else None)
            if any(isinstance(l, Err) for l in out):
                self.status = 1
            return out
        if op == "d":
            keep = [m for m in members if m[1] not in files]
            failed = self._put(archive, pack(AR_MAGIC, keep), "ar")
            return ([f"d - {m[1]}" for m in members if m[1] in files] if verbose else []) if not failed else [Err(failed)]
        out = []
        added: list = []
        for given in files:                                                    # r and q: add or replace, q always appends
            gathered: list = []
            message = self._gather(given, given.rsplit("/", 1)[-1], gathered, [0])
            if message or not gathered or gathered[0][0] == "dir":
                self.status = 1
                return [Err(f"ar: 0707-100 {given} does not exist.")]
            added.append(gathered[0])
            out.append(f"{'r' if op == 'r' and any(m[1] == gathered[0][1] for m in members) else 'a'} - {gathered[0][1]}")
        names = {m[1] for m in added}
        merged = ([m for m in members if m[1] not in names] if op == "r" else list(members)) + added
        if len(merged) > MAX_ENTRIES:
            self.status = 1
            return [Err(f"ar: the simulator stops an archive at {MAX_ENTRIES} members")]
        failed = self._put(archive, pack(AR_MAGIC, merged), "ar")
        if failed:
            return [Err(failed)]
        return out if verbose else []

    # -- more, sleep, time ----------------------------------------------------------------------------------------

    def cmd_more(self, args: list[str]) -> list[str]:
        files = [a for a in args if not (a.startswith("-") and len(a) > 1) and not a.startswith("+")]
        if not files:
            return [] if self.stdin is None else list(self.stdin)
        out: list[str] = []
        self.status = 0
        for given in files:
            try:
                out += ifs.read(self.store, self.actor, self.path(given)).splitlines()
            except ifs.IfsError as exc:
                self.status = 1
                out.append(Err(f"{given}: " + ("Permission denied" if exc.kind == "EACCES" else
                                              "Is a directory" if exc.kind == "EISDIR" else "No such file or directory")))
        return out

    def cmd_sleep(self, args: list[str]) -> list[str]:
        if len(args) != 1:
            self.status = 2
            return [Err(SLEEP_USAGE)]
        if not args[0].isdigit():
            self.status = 2
            return [Err("sleep: bad character in argument")]
        self.status = 0                                  # and it returns at once: nothing here waits
        return []

    def cmd_time(self, args: list[str]) -> list[str]:
        posix = bool(args) and args[0] == "-p"
        words = args[1:] if posix else args
        if not words:
            self.status = 1
            return [Err(TIME_USAGE)]
        depth = getattr(self, "_time_depth", 0)
        if depth >= MAX_TIME_DEPTH:
            self.status = 1
            return [Err("time: too many nested commands")]
        self._time_depth = depth + 1
        try:
            line = " ".join("'" + w.replace("'", "'\\''") + "'" for w in words)
            out = self.run_simple(line, self.stdin)
        finally:
            self._time_depth = depth
        figures = ["real 0.03", "user 0.00", "sys 0.00"] if posix else ["real   0.03", "user   0.00", "sys    0.00"]
        return list(out) + ([] if posix else [Err("")]) + [Err(f) for f in figures]
