"""A simulated PASE shell. A fixed list of commands over the virtual IFS (system/ifs.py), as the signed on
profile, and nothing else: no process is ever started, no host file is read, and a line that is not one of
these commands is refused in the shell's own voice. That is what makes it safe to leave on a training box and
why `reset.sh` puts everything back exactly.

A name is looked up the way a shell does it: a word with a slash is a path; cd, pwd, echo, export and exit are
the shell's own; anything else is looked for as an executable file along $PATH, directory by directory, before
the simulator's own ls, cat, id and the rest are tried. So a script named `id` in an early PATH directory wins
over `id`, which is the point of the PATH lessons. A script is a stream file with `x` for the profile; each
line runs as that profile through this same shell (no interpreter, no shebang meaning, five levels deep at
most). `login()` reads /QOpenSys/etc/profile and then ~/.profile, as a login shell does.

The read-only batch PUB400 has (uname, hostname, date, logname, printenv, ps, head, tail, wc, grep) was captured
on 2026-10-27 and its wording and layout are copied. The simulator has no pipes and no input, so head, tail, wc
and grep need a file name; with none, they read an empty input and print nothing, where a real one would wait.

Built: pwd, cd, ls (-l -a), cat, id, echo ($VAR), env, export, exit, and the writing set: mkdir (-p),
touch, rm (-r -f), cp, mv, chmod, `> file` and `>> file` at the end of a command, and `system 'CL command'`,
which runs through the CL dispatcher as the signed on profile. A line may hold several commands joined by `;`,
`&&` and `||`, read left to right; every command leaves an exit status in `status`, which `$?` shows and which
`&&` and `||` act on. Words may use `*`, `?` and `[...]` (matched against the directories the profile can list,
a pattern with no match stays as typed) and a leading `~`. Not built: pipes, input redirection, `&`, command
substitution, `if` and `for`, and every other command.

The shell is bsh, as PUB400 showed over ssh on 2026-10-27, and what it said is copied: a missing path in `ls`
is `X not found`, `cat` says `cat: cannot open X`, `cd` says `X: No such file or directory`, an unknown command
says `bsh: name: not found`, and `id` prints `uid=N(name) gid=0` with the name in lower case. There is no
`whoami`, because there is none there. Other wording (permission denied in `ls`, the write commands) was not
captured and is still a guess, see docs/pase.md."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

from . import ifs
from .profiles import Profile, ProfileStore

BANNER = "Simulated PASE terminal. Not an AIX runtime: a few commands over a virtual IFS."
NOT_AVAILABLE = "bsh: that syntax is not available in the simulator (no pipes, input redirection, & or substitution)."
MAX_COMMANDS = 100                             # per line, so `;` cannot be used to loop the work
MAX_GLOB = 1000                                # names one pattern may produce, and directory entries it may look at
SYSTEM_PATH = "/QOpenSys/usr/bin:/usr/bin"
BUILTINS = frozenset({"cd", "pwd", "echo", "export", "exit", "logout"})
NODE_NAME = "SILVERLAKE"
HOST_NAME = "SILVERLAKE.LOCALDOMAIN"
MACHINE_ID = "0078000000A1"                    # made up: a real one is the machine's serial based id
MAX_DEPTH = 5
SYSTEM_PROFILE = "/QOpenSys/etc/profile"


@dataclass
class Shell:
    store: ProfileStore
    actor: Profile
    cwd: str = ""
    env: dict[str, str] = field(default_factory=dict)
    done: bool = False
    depth: int = 0
    status: int = 0                              # the exit status of the last command, what `$?` shows
    leaving: bool = False                        # `exit` inside a script ends the script, not the shell
    job: object = None
    clock: object = None                         # a callable giving "now" in UTC, for tests; None means the real time

    def __post_init__(self) -> None:
        home = ifs.home_of(self.actor)
        self.cwd = self.cwd or home
        base = {"HOME": home, "USER": self.actor.name, "LOGNAME": self.actor.name, "PATH": SYSTEM_PATH,
                "SHELL": "/QOpenSys/usr/bin/bsh", "LANG": "EN_US", "TERM": "xterm"}
        self.env = {**base, **self.env}
        if self.cwd not in self.store.ifs and not self.cwd.startswith(ifs.QSYS):
            self.cwd = "/"

    @property
    def prompt(self) -> str:
        return "$ "

    def path(self, arg: str) -> str:
        return ifs.normalize(arg, self.cwd, self.env["HOME"])

    # -- running a line ----------------------------------------------------------------------------------------

    def run(self, line: str) -> list[str]:
        """One line: commands joined by `;`, `&&` and `||`, read left to right. `status` holds the last one's exit
        status afterwards."""
        parts = self.split_line(line)
        if isinstance(parts, str):
            self.status = 2
            return [parts]
        out: list[str] = []
        for joint, text in parts:
            if self.done or self.leaving:
                break
            if (joint == "&&" and self.status != 0) or (joint == "||" and self.status == 0):
                continue
            out += self.run_simple(text)
        return out

    @staticmethod
    def split_line(line: str) -> list[tuple[str, str]] | str:
        """The line cut at `;`, `&&` and `||` that are not quoted, as (joint before it, command) pairs, or a
        message when the line uses syntax the simulator does not have. A `#` that starts a word ends the line."""
        parts: list[tuple[str, str]] = []
        joint, start, end, quote, i = ";", 0, len(line), "", 0
        while i < len(line):
            ch, two = line[i], line[i:i + 2]
            if ch == "\\" and quote != "'":
                i += 2
                continue
            if quote:
                if ch == quote:
                    quote = ""
                elif quote == '"' and (ch == "`" or two == "$("):
                    return NOT_AVAILABLE
                i += 1
                continue
            if ch in "'\"":
                quote = ch
            elif ch == "`" or two == "$(" or ch == "<" or (ch == "|" and two != "||") or (ch == "&" and two != "&&"):
                return NOT_AVAILABLE
            elif ch == "#" and (i == 0 or line[i - 1].isspace()):
                end = i
                break
            elif ch == ";" or two in ("&&", "||"):
                op = ch if ch == ";" else two
                parts.append((joint, line[start:i]))
                joint, start = op, i + len(op)
                i += len(op)
                continue
            i += 1
        if quote:
            return "bsh: a quote was not closed."
        parts.append((joint, line[start:end]))
        if len(parts) > MAX_COMMANDS:
            return f"bsh: too many commands on one line (the simulator stops at {MAX_COMMANDS})."
        for n, (j, text) in enumerate(parts):
            if not text.strip() and (j != ";" or n < len(parts) - 1) and not (n == len(parts) - 1 and j == ";" and n > 0):
                return f"bsh: syntax error: {j} is not expected."
        return [(j, t) for j, t in parts if t.strip()]

    def run_simple(self, text: str) -> list[str]:
        words, redirect = self.words_of(text)
        if isinstance(words, str):
            self.status = 2
            return [words]
        if not words:
            return []
        self.status = 0
        if re.fullmatch(r"[A-Za-z_]\w*=.*", words[0]) and len(words) == 1:
            name, _, value = words[0].partition("=")
            self.env[name] = value
            return []
        name, args = words[0], words[1:]
        script = None if name in BUILTINS else self.find_script(name)
        fn = getattr(self, "cmd_" + name, None) if re.fullmatch(r"[a-z][a-z0-9]*", name) else None
        if script is not None:
            out = self.run_script(script, name)
        elif "/" in name or fn is None:
            self.status = 127
            return [f"bsh: {name}: not found"]
        else:
            out = fn(args)
        if redirect is None:
            return out
        target = self.path(redirect[1])
        try:
            ifs.write(self.store, self.actor, target, "".join(l + "\n" for l in out), append=redirect[0] == ">>")
        except ifs.IfsError as exc:
            return [self._write_error("bsh", exc, redirect[1])]
        return []

    def words_of(self, text: str) -> tuple[list[str] | str, tuple[str, str] | None]:
        """The words of one command after quoting, $VAR, $? and ~ and then globbing, and the redirection at its
        end if there is one. A message instead of the words when the command is not well formed."""
        tokens: list[tuple[str, str]] = []                      # (text, mask): mask has a 1 for every char a glob may use
        cur_t, cur_m, have, i = "", "", False, 0

        def flush() -> None:
            nonlocal cur_t, cur_m, have
            if have:
                tokens.append((cur_t, cur_m))
            cur_t, cur_m, have = "", "", False

        while i < len(text):
            ch = text[i]
            if ch.isspace():
                flush()
            elif ch in "<>" or (ch == ">" and text[i:i + 2] == ">>"):
                flush()
                op = ">>" if text[i:i + 2] == ">>" else ">"
                tokens.append((op, "op"))
                i += len(op) - 1
            elif ch == "'":
                end = text.index("'", i + 1)
                cur_t, cur_m, have = cur_t + text[i + 1:end], cur_m + "0" * (end - i - 1), True
                i = end
            elif ch == '"':
                have, i = True, i + 1
                while text[i] != '"':
                    if text[i] == "\\" and text[i + 1] in '"\\$`':
                        i += 1
                        cur_t, cur_m = cur_t + text[i], cur_m + "0"
                    elif text[i] == "$":
                        value, i = self.dollar(text, i)
                        cur_t, cur_m = cur_t + value, cur_m + "0" * len(value)
                        continue
                    else:
                        cur_t, cur_m = cur_t + text[i], cur_m + "0"
                    i += 1
            elif ch == "\\" and i + 1 < len(text):
                i += 1
                cur_t, cur_m, have = cur_t + text[i], cur_m + "0", True
            elif ch == "$":
                value, i = self.dollar(text, i)
                for n, piece in enumerate(re.split(r"(\s+)", value)):      # unquoted, so it splits and may glob
                    if n % 2:
                        flush()
                    elif piece:
                        cur_t, cur_m, have = cur_t + piece, cur_m + "1" * len(piece), True
                continue
            elif ch == "~" and not have and (i + 1 == len(text) or text[i + 1] in "/ \t"):
                cur_t, cur_m, have = self.env["HOME"], "0" * len(self.env["HOME"]), True
            else:
                cur_t, cur_m, have = cur_t + ch, cur_m + "1", True
            i += 1
        flush()
        redirect = None
        if any(m == "op" for _, m in tokens):
            if len(tokens) >= 2 and tokens[-2][1] == "op" and tokens[-1][1] != "op" \
                    and sum(m == "op" for _, m in tokens) == 1:
                redirect = (tokens[-2][0], tokens[-1][0])
                tokens = tokens[:-2]
            else:
                return "bsh: the redirection must be the last thing on the line: command > file.", None
        words: list[str] = []
        for word, mask in tokens:
            words += self.glob(word, mask)
        return words, redirect

    def dollar(self, text: str, i: int) -> tuple[str, int]:
        """The value of the `$` expression at text[i], and where the text goes on. A lone `$` is itself."""
        m = re.compile(r"\$(\?|\w+)|\$\{(\w+)\}").match(text, i)
        if not m:
            return "$", i + 1
        name = m.group(1) or m.group(2)
        return (str(self.status) if name == "?" else self.env.get(name, "")), m.end()

    def glob(self, word: str, mask: str) -> list[str]:
        """`word` itself, or the names that match it when it has a `*`, `?` or `[...]` that was not quoted. A
        pattern that matches nothing stays as typed. Each part between slashes is matched on its own, a name
        that starts with a dot only by a part that does too, and the profile only sees what it may list."""
        if not any(m == "1" and c in "*?[" for c, m in zip(word, mask)):
            return [word]
        parts, pos = [], 0
        for piece in word.split("/"):
            parts.append((piece, mask[pos:pos + len(piece)]))
            pos += len(piece) + 1
        found = [""] if not word.startswith("/") else ["/"]
        seen = 0
        for n, (piece, pmask) in enumerate(parts):
            if n == 0 and word.startswith("/"):
                continue
            rx = self._glob_regex(piece, pmask)
            nxt: list[str] = []
            for base in found:
                joined = lambda name: (base if base.endswith("/") or not base else base + "/") + name
                if rx is None:
                    nxt.append(joined(piece))
                    continue
                try:
                    entries = ifs.listdir(self.store, self.actor, self.path(base or "."))
                except ifs.IfsError:
                    continue
                for e in entries:
                    seen += 1
                    name = e.path.rsplit("/", 1)[-1]
                    if seen > MAX_GLOB:
                        break
                    if rx.fullmatch(name) and (not name.startswith(".") or piece.startswith(".")):
                        nxt.append(joined(name))
            found = nxt[:MAX_GLOB]
        hits = []
        for path in sorted(found):
            try:
                ifs.lookup(self.store, self.actor, self.path(path))
            except ifs.IfsError:
                continue
            hits.append(path)
        return hits or [word]

    @staticmethod
    def _glob_regex(piece: str, mask: str):
        """The regular expression for one path part, or None when it has nothing to match."""
        out, i, wild = "", 0, False
        while i < len(piece):
            c, live = piece[i], mask[i] == "1"
            if live and c == "*":
                out, wild = out + "[^/]*", True
            elif live and c == "?":
                out, wild = out + "[^/]", True
            elif live and c == "[":
                end = i + 2 if piece[i + 1:i + 2] in ("!", "^") else i + 1
                end += 1 if piece[end:end + 1] == "]" else 0
                while end < len(piece) and piece[end] != "]":
                    end += 1
                if end >= len(piece):
                    out += re.escape(c)
                else:
                    body = piece[i + 1:end]
                    body = "^" + body[1:] if body[:1] in ("!", "^") else body
                    out, wild, i = out + "[" + body.replace("\\", "\\\\") + "]", True, end
            else:
                out += re.escape(c)
            i += 1
        return re.compile(out) if wild else None

    def find_script(self, name: str) -> str | None:
        """The path of the executable stream file `name` means, or None. A slash makes it a path, otherwise each
        $PATH directory is tried in order. The profile needs `x` on the file."""
        if "/" in name:
            candidates = [self.path(name)]
        else:
            candidates = [ifs.normalize(d + "/" + name, self.cwd, self.env["HOME"])
                          for d in self.env.get("PATH", "").split(":") if d]
        for path in candidates:
            try:
                entry = ifs.lookup(self.store, self.actor, path)
            except ifs.IfsError:
                continue
            if not entry.is_dir and "x" in entry.mode and path in self.store.ifs:
                return path
        return None

    def run_script(self, path: str, name: str) -> list[str]:
        if self.depth >= MAX_DEPTH:
            return [f"bsh: {name}: 0403-016 Cannot execute: too many nested scripts."]
        try:
            text = ifs.read(self.store, self.actor, path)
        except ifs.IfsError:
            return [f"bsh: {name}: 0403-006 Execute permission denied."]
        out: list[str] = []
        self.depth += 1
        try:
            for line in text.splitlines()[:200]:
                out += self.run(line)
                if self.leaving:
                    break
        finally:
            self.depth -= 1
            self.leaving = False
        return out

    def login(self) -> list[str]:
        """What a login shell does first: the system profile, then the profile's own. What they print is shown."""
        out: list[str] = []
        for path in (SYSTEM_PROFILE, self.env["HOME"] + "/.profile"):
            try:
                text = ifs.read(self.store, self.actor, path)
            except ifs.IfsError:
                continue
            self.depth += 1
            try:
                for line in text.splitlines()[:200]:
                    out += self.run(line)
                    if self.leaving:
                        break
            finally:
                self.depth -= 1
                self.leaving = False
        return out

    # -- the commands ------------------------------------------------------------------------------------------

    def cmd_pwd(self, args: list[str]) -> list[str]:
        return [self.cwd]

    def cmd_cd(self, args: list[str]) -> list[str]:
        target = self.path(args[0] if args else "~")
        try:
            entry = ifs.lookup(self.store, self.actor, target)
        except ifs.IfsError as exc:
            self.status = 1
            return [self._cd_error(exc, args[0] if args else "~")]
        if not entry.is_dir:
            self.status = 1
            return [f"{args[0]}: Not a directory"]
        if "x" not in entry.mode:
            self.status = 1
            return [f"{args[0]}: Permission denied"]
        self.cwd = target
        return []

    @staticmethod
    def _cd_error(exc: ifs.IfsError, given: str) -> str:
        why = {"ENOENT": "No such file or directory", "EACCES": "Permission denied", "ENOTDIR": "Not a directory"}
        return f"{given}: {why.get(exc.kind, exc.kind)}"

    def cmd_ls(self, args: list[str]) -> list[str]:
        flags = "".join(a[1:] for a in args if a.startswith("-") and len(a) > 1)
        long, hidden = "l" in flags, "a" in flags
        paths = [a for a in args if not a.startswith("-") or a == "-"] or ["."]
        out: list[str] = []
        for given in paths:
            target = self.path(given)
            try:
                entry = ifs.lookup(self.store, self.actor, target)
                rows = ifs.listdir(self.store, self.actor, target) if entry.is_dir else [entry]
            except ifs.IfsError as exc:
                out.append(self._ls_error(exc, given))
                self.status = 2
                continue
            if len(paths) > 1 and entry.is_dir:
                out += ["", f"{given}:"] if out else [f"{given}:"]
            rows = [e for e in rows if hidden or not e.path.rsplit("/", 1)[-1].startswith(".")]
            out += [self._long(e) if long else e.path.rsplit("/", 1)[-1] for e in rows]
        return out

    @staticmethod
    def _ls_error(exc: ifs.IfsError, given: str) -> str:
        if exc.kind == "EACCES":
            return f"ls: 0653-345 {given}: Permission denied."     # not captured: PUB400 only showed the missing case
        return f"{given} not found"

    def _long(self, e: ifs.Entry) -> str:
        return f"{ifs.perms(e)}   1 {e.owner:<10} 0 {e.size:>8} {ifs.STAMP} {e.path.rsplit('/', 1)[-1]}"

    def cmd_cat(self, args: list[str]) -> list[str]:
        if not args:
            self.status = 2
            return ["cat: cannot open standard input in the simulator"]
        out: list[str] = []
        for given in args:
            try:
                out += ifs.read(self.store, self.actor, self.path(given)).splitlines()
            except ifs.IfsError as exc:
                out.append(f"cat: cannot open {given}")
                self.status = 2
        return out

    def cmd_id(self, args: list[str]) -> list[str]:
        uid = ifs.uid_of(self.store, self.actor)
        return [f"uid={uid}({self.actor.name.lower()}) gid=0"]

    def cmd_echo(self, args: list[str]) -> list[str]:
        return [" ".join(args)]

    def cmd_env(self, args: list[str]) -> list[str]:
        return [f"{k}={v}" for k, v in sorted(self.env.items())]

    def cmd_export(self, args: list[str]) -> list[str]:
        for a in args:
            name, sep, value = a.partition("=")
            if not re.fullmatch(r"[A-Za-z_]\w*", name):
                self.status = 1
                return [f"bsh: export: {a}: not a valid identifier."]
            if sep:
                self.env[name] = value
        return []

    def cmd_exit(self, args: list[str]) -> list[str]:
        """`exit [N]`. At the prompt it ends the shell; inside a script it ends the script. N is taken modulo 256,
        and anything that is not a number is 2, a guess."""
        if args:
            self.status = int(args[0]) % 256 if re.fullmatch(r"-?\d+", args[0]) else 2
        if self.depth:
            self.leaving = True
        else:
            self.done = True
        return []

    cmd_logout = cmd_exit

    # -- writing -----------------------------------------------------------------------------------------------

    def _write_error(self, cmd: str, exc: ifs.IfsError, given: str) -> str:
        self.status = 1
        why = {"EACCES": "0653-345 {0}: Permission denied.", "ENOENT": "0653-341 The file {0} does not exist.",
               "EEXIST": "0653-340 {0} already exists.", "ENOTDIR": "0653-346 {0} is not a directory.",
               "EISDIR": "0653-347 {0} is a directory.", "ENOTEMPTY": "0653-348 {0} is not empty.",
               "EPERM": "0653-349 {0}: Operation not permitted.", "EINVAL": "0653-350 {0}: invalid mode."}
        return f"{cmd}: " + why.get(exc.kind, exc.kind).format(given)

    def cmd_mkdir(self, args: list[str]) -> list[str]:
        parents = "-p" in args
        out: list[str] = []
        for given in [a for a in args if a != "-p"]:
            target = self.path(given)
            try:
                if parents:
                    walk = ""
                    for part in [p for p in target.split("/") if p]:
                        walk += "/" + part
                        if walk not in self.store.ifs:
                            ifs.make(self.store, self.actor, walk, "dir")
                    continue
                ifs.make(self.store, self.actor, target, "dir")
            except ifs.IfsError as exc:
                out.append(self._write_error("mkdir", exc, given))
        return out

    def cmd_touch(self, args: list[str]) -> list[str]:
        out: list[str] = []
        for given in args:
            target = self.path(given)
            try:
                if target not in self.store.ifs:
                    ifs.make(self.store, self.actor, target, "file")
                else:
                    ifs.lookup(self.store, self.actor, target)
            except ifs.IfsError as exc:
                out.append(self._write_error("touch", exc, given))
        return out

    def cmd_rm(self, args: list[str]) -> list[str]:
        flags = "".join(a[1:] for a in args if a.startswith("-") and len(a) > 1)
        out: list[str] = []
        for given in [a for a in args if not a.startswith("-")]:
            try:
                target = self.path(given)
                if target in self.store.ifs and self.store.ifs[target].is_dir and "r" not in flags:
                    out.append(f"rm: 0653-603 {given} is a directory.")
                    continue
                ifs.remove(self.store, self.actor, target, recursive="r" in flags)
            except ifs.IfsError as exc:
                if not ("f" in flags and exc.kind == "ENOENT"):
                    out.append(self._write_error("rm", exc, given))
        return out

    def _two(self, name: str, args: list[str], fn) -> list[str]:
        args = [a for a in args if not a.startswith("-")]
        if len(args) != 2:
            self.status = 2
            return [f"{name}: 0653-401 usage: {name} source target"]
        try:
            fn(self.store, self.actor, self.path(args[0]), self.path(args[1]))
        except ifs.IfsError as exc:
            return [self._write_error(name, exc, args[0] if exc.path == self.path(args[0]) else args[1])]
        return []

    def cmd_cp(self, args: list[str]) -> list[str]:
        return self._two("cp", args, ifs.copy)

    def cmd_mv(self, args: list[str]) -> list[str]:
        return self._two("mv", args, ifs.move)

    def cmd_chmod(self, args: list[str]) -> list[str]:
        if len(args) < 2:
            self.status = 2
            return ["chmod: 0653-401 usage: chmod mode file ..."]
        out: list[str] = []
        for given in args[1:]:
            try:
                ifs.chmod(self.store, self.actor, self.path(given), args[0])
            except ifs.IfsError as exc:
                out.append(self._write_error("chmod", exc, args[0] if exc.kind == "EINVAL" else given))
        return out

    def cmd_system(self, args: list[str]) -> list[str]:
        """Run a CL command as the signed on profile, as the real `system` utility does, and print what it said."""
        from ..cl import commands
        from ..net import textview
        if not args:
            self.status = 2
            return ["system: 0653-401 usage: system 'CL command'"]
        line = " ".join(args)
        outcome = commands.execute(self.store, self.actor, line, self._job())
        message = outcome.message
        if outcome.view or outcome.signoff or outcome.go or outcome.cmdentry or (
                message is not None and message.id[:3] in ("CPF", "CPD", "CPE", "MCH")):
            self.status = 1                          # the real utility returns non zero when the command fails, a guess for which messages
        return textview.outcome_text(self.store, outcome, line).splitlines()

    def _job(self):
        from ..cl.session import Session
        if self.job is None:
            self.job = Session.for_profile(self.actor.current_library)
        return self.job

    def cmd_db2(self, args: list[str]) -> list[str]:
        """Run one SQL statement as the signed on profile, over the physical files (system/sql.py)."""
        from . import sql
        if not args:
            self.status = 2
            return ["db2: usage: db2 \"SQL statement\""]
        result = sql.run(self.store, self.actor, self._job(), " ".join(args))
        if result.error:
            self.status = 4                          # the db2 command line returns 4 for an SQL error, from IBM's page, not seen here
        return sql.render(result)

    # -- the small read-only batch, wording copied from PUB400 ------------------------------------------------------

    def cmd_uname(self, args: list[str]) -> list[str]:
        from ..net import hostsvr
        v, r = re.match(r"V(\d+)R(\d+)", hostsvr.OS_LEVEL).groups()
        fields = {"s": "OS400", "n": NODE_NAME, "r": r, "v": v, "m": MACHINE_ID}
        flags = "".join(a[1:] for a in args if a.startswith("-") and len(a) > 1)
        if "a" in flags:
            return [" ".join(fields[k] for k in "snrvm")]
        picked = [fields[k] for k in "snrvm" if k in flags]
        return [" ".join(picked) if picked else "OS400"]

    def cmd_hostname(self, args: list[str]) -> list[str]:
        return [HOST_NAME]

    def cmd_date(self, args: list[str]) -> list[str]:
        now = (self.clock or (lambda: datetime.now(timezone.utc)))()
        return [now.strftime(f"%a %b {now.day:2d} %H:%M:%S UTC %Y")]      # %e is not portable, the padding is the same

    def cmd_logname(self, args: list[str]) -> list[str]:
        self.status = 1
        return ["logname: getlogin failed"]               # what PUB400 said over ssh, where there is no terminal

    def cmd_printenv(self, args: list[str]) -> list[str]:
        if not args:
            return self.cmd_env([])
        self.status = 0 if args[0] in self.env else 1
        return [self.env[a] for a in args[:1] if a in self.env]

    def cmd_ps(self, args: list[str]) -> list[str]:
        self.status = 1                                   # and PUB400 exited 1 with it, there being nothing to list
        return ["    PID    TTY  TIME CMD"]               # PUB400 listed no process for the login, and neither do we

    def _lines_of(self, name: str, given: str) -> tuple[list[str] | None, str]:
        try:
            return ifs.read(self.store, self.actor, self.path(given)).splitlines(), ""
        except ifs.IfsError as exc:
            if name == "wc":
                return None, f"wc: cannot open {given}"
            if name == "grep":
                return None, f"grep: can't open {given}"
            return None, f"{given}: {'Permission denied' if exc.kind == 'EACCES' else 'No such file or directory'}"

    @staticmethod
    def _count_option(args: list[str]) -> tuple[int, list[str]]:
        """`-n N`, `-nN` or `-N` for head and tail, and the file names that are left."""
        count, files, i = 10, [], 0
        while i < len(args):
            a = args[i]
            if a == "-n" and i + 1 < len(args) and args[i + 1].isdigit():
                count, i = int(args[i + 1]), i + 1
            elif re.fullmatch(r"-n?\d+", a):
                count = int(a.lstrip("-n"))
            elif not a.startswith("-") or a == "-":
                files.append(a)
            i += 1
        return count, files

    def _head_tail(self, name: str, args: list[str], pick) -> list[str]:
        count, files = self._count_option(args)
        out: list[str] = []
        for given in files:
            lines, err = self._lines_of(name, given)
            if lines is None:
                out.append(err)
                self.status = 1
                continue
            if len(files) > 1:
                out += (["" ] if out else []) + [f"==> {given} <=="]
            out += pick(lines, count)
        return out

    def cmd_head(self, args: list[str]) -> list[str]:
        return self._head_tail("head", args, lambda lines, n: lines[:n])

    def cmd_tail(self, args: list[str]) -> list[str]:
        return self._head_tail("tail", args, lambda lines, n: lines[-n:] if n else [])

    def cmd_wc(self, args: list[str]) -> list[str]:
        flags = "".join(a[1:] for a in args if a.startswith("-") and len(a) > 1)
        wanted = [k for k in "lwc" if k in flags] or ["l", "w", "c"]
        out: list[str] = []
        for given in [a for a in args if not a.startswith("-")]:
            try:
                text = ifs.read(self.store, self.actor, self.path(given))
            except ifs.IfsError:
                out.append(f"wc: cannot open {given}")
                self.status = 2
                continue
            counts = {"l": text.count("\n"), "w": len(text.split()), "c": len(text.encode())}
            out.append("".join(f"{counts[k]:8d}" for k in wanted) + f" {given}")
        return out

    def cmd_grep(self, args: list[str]) -> list[str]:
        flags, rest, options = "", [], True
        for a in args:                         # options end at the first word that is not one, or at `--`
            if options and a == "--":
                options = False
            elif options and a.startswith("-") and len(a) > 1:
                flags += a[1:]
            else:
                options = False
                rest.append(a)
        if not rest:
            self.status = 2
            return ["Usage: grep [-i] [-v] [-n] [-c] pattern [file ...]"]
        pattern, files = rest[0], rest[1:]
        try:
            rx = re.compile(pattern, re.I if "i" in flags else 0)
        except re.error:
            self.status = 2
            return [f"grep: 0651-209 The regular expression {pattern} is not valid."]
        out: list[str] = []
        matched, failed = False, False
        for given in files:
            lines, err = self._lines_of("grep", given)
            if lines is None:
                out.append(err)
                failed = True
                continue
            hits = [(n, l) for n, l in enumerate(lines, 1) if bool(rx.search(l)) != ("v" in flags)]
            matched = matched or bool(hits)
            prefix = f"{given}:" if len(files) > 1 else ""
            if "c" in flags:
                out.append(f"{prefix}{len(hits)}")
            else:
                out += [f"{prefix}{str(n) + ':' if 'n' in flags else ''}{l}" for n, l in hits]
        self.status = 2 if failed else (0 if matched else 1)            # 1 for no match and 2 for a file it could not open, as PUB400 did
        return out
