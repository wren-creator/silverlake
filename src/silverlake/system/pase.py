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
on 2026-10-27 and its wording and layout are copied. With a pipe or `<` head, tail, wc, grep and cat read what they
were given; with no file and no input they print nothing, where a real one would wait.

Built: pwd, cd, ls (-l -a), cat, id, echo ($VAR), env, export, exit, and the writing set: mkdir (-p),
touch, rm (-r -f), cp, mv, chmod, `> file` and `>> file` at the end of a command, and `system 'CL command'`,
which runs through the CL dispatcher as the signed on profile. B2 (captured 2026-10-28) added basename, dirname,
which, type, test and [, file, rmdir, umask, du and find. A line may hold several commands joined by `;`,
`&&` and `||`, read left to right; every command leaves an exit status in `status`, which `$?` shows and which
`&&` and `||` act on. Words may use `*`, `?` and `[...]` (matched against the directories the profile can list,
a pattern with no match stays as typed). There is no `~` expansion, because bsh has none. A line that does not
parse is refused whole, before anything runs. `a | b` feeds b what a printed (stdout only: lines marked `Err` are
stderr, shown but never piped or written to a file), `< file` is its input, and a `command` between backticks is
run by a nested copy of this shell and replaced by what it printed. bsh has no `$(...)`, and says so as a syntax
error. Not built: `&`, subshells, here documents, `2>`, `if` and `for`, and every other command.

The shell is bsh, as PUB400 showed over ssh on 2026-10-27, and what it said is copied: a missing path in `ls`
is `X not found`, `cat` says `cat: cannot open X`, `cd` says `X: No such file or directory`, an unknown command
says `bsh: name: not found`, and `id` prints `uid=N(name) gid=0` with the name in lower case. There is no
`whoami`, because there is none there. Other wording (permission denied in `ls`, the write commands) was not
captured and is still a guess, see docs/pase.md."""

from __future__ import annotations

import posixpath
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from fnmatch import fnmatchcase

from . import ifs, pasei, spool
from .archives import Archives
from .heavyfilters import Heavy
from .textfilters import Err, Filters
from .authority import Auth, SecuredObject, SpecialAuthority
from .profiles import Profile, ProfileStore

BANNER = "Simulated PASE terminal. Not an AIX runtime: a few commands over a virtual IFS."
NOT_AVAILABLE = "bsh: that syntax is not available in the simulator (no &, subshells or here documents)."
MAX_FIND = 5000                                # entries find or du will look at
MAX_STAGES = 20                                # commands in one pipeline
MAX_SUB = 5                                    # backticks inside backticks
SUB_LIMIT = 64 * 1024                          # characters one substitution may bring back
MAX_COMMANDS = 100                             # per line, so `;` cannot be used to loop the work
MAX_GLOB = 1000                                # names one pattern may produce, and directory entries it may look at
SYSTEM_PATH = "/QOpenSys/usr/bin:/usr/bin"
BUILTINS = frozenset({"cd", "pwd", "echo", "export", "exit", "logout"})
QSH_ONLY = frozenset({"db2", "datarea", "dataq", "catsplf"})      # symlinks into QSYS.LIB programs: bsh says `cannot execute`
JOB_PID = 872856                               # what getjobid and ps show for this shell, made up like PUB400's own numbers
JOB_ID = "679199/QUSER/QP0ZSPWT"
NODE_NAME = "SILVERLAKE"
HOST_NAME = "SILVERLAKE.LOCALDOMAIN"
MACHINE_ID = "0078000000A1"                    # made up: a real one is the machine's serial based id
MAX_DEPTH = 5
SYSTEM_PROFILE = "/QOpenSys/etc/profile"


@dataclass
class Shell(Filters, Heavy, Archives):
    store: ProfileStore
    actor: Profile
    cwd: str = ""
    env: dict[str, str] = field(default_factory=dict)
    done: bool = False
    depth: int = 0
    status: int = 0                              # the exit status of the last command, what `$?` shows
    leaving: bool = False                        # `exit` inside a script ends the script, not the shell
    stdin: list[str] | None = None               # what the command now running was piped, or None when it has no input
    sub_errors: list = field(default_factory=list)   # what a backtick command printed to stderr, shown ahead of its line
    sub_depth: int = 0
    umask: int = 0o022                           # the mask new files and directories are made with (PUB400 started at 022)
    qsh_level: int = 0
    qsh: bool = False                            # inside `qsh -c`: the QSYS.LIB utilities run, and errors use QSH's wording
    batch: bool = False                          # a command run with no terminal (ssh host cmd): a failed cd or export ends it
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
        """bsh has no tilde expansion (`echo ~` printed `~` on PUB400), so `~` is an ordinary name here."""
        return ifs.normalize("./" + arg if arg.startswith("~") else arg, self.cwd, self.env["HOME"])

    # -- running a line ----------------------------------------------------------------------------------------

    def run(self, line: str) -> list[str]:
        """One line: pipelines joined by `;`, `&&` and `||`, read left to right. `status` holds the last one's exit
        status afterwards."""
        parts = self.split_line(line)
        if parts is None:                                  # a trailing `|`: PUB400's bsh ran nothing and said nothing
            self.status = 0
            return []
        if isinstance(parts, str):
            self.status = 2
            return [Err(parts)]
        out: list[str] = []
        for joint, stages in parts:
            if self.done or self.leaving:
                break
            if (joint == "&&" and self.status != 0) or (joint == "||" and self.status == 0):
                continue
            out += self.run_pipeline(stages)
        return out

    @staticmethod
    def _scan(text: str):
        """(index, char) for every character outside quotes, backticks and backslash escapes. A backtick inside double
        quotes is skipped as a whole. ValueError when a quote or a backtick is not closed."""
        i, n = 0, len(text)
        while i < n:
            ch = text[i]
            if ch == "\\":
                i += 2
            elif ch == "'":
                j = text.find("'", i + 1)
                if j < 0:
                    raise ValueError(ch)
                i = j + 1
            elif ch in "\"`":
                j = i + 1
                while j < n and text[j] != ch:
                    if text[j] == "\\":
                        j += 1
                    elif ch == '"' and text[j] == "`":
                        j += 1
                        while j < n and text[j] != "`":
                            j += 2 if text[j] == "\\" else 1
                    j += 1
                if j >= n:
                    raise ValueError(ch)
                i = j + 1
            else:
                yield i, ch
                i += 1

    @classmethod
    def split_line(cls, line: str) -> list[tuple[str, list[str]]] | str | None:
        """The line cut at `;`, `&&` and `||` that are not quoted, as (joint before it, pipeline) pairs where a pipeline is
        its commands split at `|`. A message instead when the line cannot run, and None for a trailing `|`, which PUB400's
        bsh swallowed. A `#` that starts a word ends the line. Nothing here runs anything."""
        try:
            tops = list(cls._scan(line))
        except ValueError:
            return "bsh: a quote was not closed."
        parts: list[tuple[str, str]] = []
        joint, start, end, k = ";", 0, len(line), 0
        while k < len(tops):
            i, ch = tops[k]
            two = line[i:i + 2]
            if ch == "#" and (i == 0 or line[i - 1].isspace()):
                end = i
                break
            if ch == "$" and line[i + 1:i + 2] == "(":
                return "bsh: syntax error at line 1: `(' unexpected"          # bsh has no $(...), only backticks
            if ch in "()" or (ch == "&" and two != "&&") or two == "<<":
                return NOT_AVAILABLE
            if two == ";;":
                return "bsh: syntax error at line 1: `;;' unexpected"
            if ch == ";" or two in ("&&", "||"):
                op = ch if ch == ";" else two
                parts.append((joint, line[start:i]))
                joint, start = op, i + len(op)
                k += len(op)
                continue
            k += 1
        parts.append((joint, line[start:end]))
        if len(parts) > MAX_COMMANDS:
            return f"bsh: too many commands on one line (the simulator stops at {MAX_COMMANDS})."
        for n, (j, text) in enumerate(parts):
            if text.strip():
                continue
            last = n == len(parts) - 1
            if last and (j == ";" and n > 0 or len(parts) == 1):
                continue                                           # `echo a;` and an empty line are fine
            # What PUB400's bsh said: the whole line is refused before anything runs, and the token it names is the
            # operator after the empty command, `end of file` at the end of the line and (odd, but copied) for a
            # `;` that starts the line.
            token = "end of file" if last or (n == 0 and parts[n + 1][0] == ";") else parts[n + 1][0]
            return f"bsh: syntax error at line 1: `{token}' unexpected"
        out: list[tuple[str, list[str]]] = []
        swallowed = False
        for j, text in parts:
            if not text.strip():
                continue
            cuts = [i for i, ch in cls._scan(text) if ch == "|"]
            stages = [text[a:b] for a, b in zip([0] + [c + 1 for c in cuts], cuts + [len(text)])]
            if len(stages) > MAX_STAGES:
                return f"bsh: too many commands in one pipeline (the simulator stops at {MAX_STAGES})."
            empty = [n for n, st in enumerate(stages) if not st.strip()]
            if empty == [len(stages) - 1] and len(stages) > 1:
                swallowed = True
            elif empty:
                return "bsh: syntax error at line 1: `|' unexpected"
            out.append((j, stages))
        return None if swallowed else out

    def run_pipeline(self, stages: list[str]) -> list[str]:
        """Each command's output is the next one's input. What reaches the terminal is every command's errors, in order,
        and the last command's output. The status is the last command's, as PUB400 showed
        (`cat /nosuchfile | cat; echo $?` printed 0)."""
        out: list[str] = []
        stdin: list[str] | None = None
        for n, text in enumerate(stages):
            lines = self.run_simple(text, stdin)
            if n == len(stages) - 1:
                out += lines
            else:
                out += [l for l in lines if isinstance(l, Err)]
                stdin = [l for l in lines if not isinstance(l, Err)]
        return out

    def run_simple(self, text: str, stdin: list[str] | None = None) -> list[str]:
        self.sub_errors = []
        parsed = self.words_of(text)
        shown: list[str] = self.sub_errors                       # errors from a backtick command come out first
        if isinstance(parsed, str):
            self.status = 2
            return shown + [Err(parsed)]
        words, redir_in, redir_out = parsed
        if not words:
            return shown
        self.status = 0
        if re.fullmatch(r"[A-Za-z_]\w*=.*", words[0]) and len(words) == 1:
            name, _, value = words[0].partition("=")
            self.env[name] = value
            return shown
        if redir_in is not None:                                 # a file beats the pipe, and a file that will not open stops the command
            if redir_in == "/dev/null":
                stdin = []
            else:
                try:
                    stdin = ifs.read(self.store, self.actor, self.path(redir_in)).splitlines()
                except ifs.IfsError:
                    self.status = 1
                    return shown + [Err(f"bsh: {redir_in}: cannot open")]
        name, args = words[0], words[1:]
        script = None if name in BUILTINS else self.find_script(name)
        fn = getattr(self, "cmd_" + name, None) if re.fullmatch(r"[A-Za-z][A-Za-z0-9]*", name) else None
        if name == "[":
            fn = self.cmd_bracket
        if script is None and ("/" in name or fn is None):
            if self.qsh:
                self.status = 127
                return shown + [Err(f"qsh: 001-0019 Error found searching for command {name}. No such path or directory.")]
            self.status = 1                                    # PUB400's bsh, not the 127 other shells give
            return shown + [Err(f"bsh: {name}: not found")]
        if script is None and name in QSH_ONLY and not self.qsh:
            self.status = 1
            return shown + [Err(f"bsh: {name}: cannot execute")]
        before, self.stdin = self.stdin, (None if script is not None else stdin)
        try:
            out = self.run_script(script, name) if script is not None else fn(args)
        finally:
            self.stdin = before
        out = shown + out
        if redir_out is None:
            return out
        errors = [l for l in out if isinstance(l, Err)]
        target = self.path(redir_out[1])
        if redir_out[1] == "/dev/null":                          # not captured: the usual sink, so a reflexive `> /dev/null` works
            return errors
        try:
            ifs.write(self.store, self.actor, target, "".join(l + "\n" for l in out if not isinstance(l, Err)),
                      append=redir_out[0] == ">>", umask=self.umask)
        except ifs.IfsError as exc:
            return errors + [self._write_error("bsh", exc, redir_out[1])]
        return errors

    def words_of(self, text: str):
        """The words of one command after quoting, $VAR, $? and `backticks` and then globbing, with the file for `<` and
        the one for `>` or `>>` if there are any: (words, in, out). A message instead when the command is not well formed."""
        tokens: list[tuple[str, str]] = []                      # (text, mask): mask has a 1 for every char a glob may use
        cur_t, cur_m, have, i = "", "", False, 0

        def flush() -> None:
            nonlocal cur_t, cur_m, have
            if have:
                tokens.append((cur_t, cur_m))
            cur_t, cur_m, have = "", "", False

        def unquoted(value: str) -> None:                       # a $VAR or a backtick result outside quotes splits and may glob
            nonlocal cur_t, cur_m, have
            for n, piece in enumerate(re.split(r"(\s+)", value)):
                if n % 2:
                    flush()
                elif piece:
                    cur_t, cur_m, have = cur_t + piece, cur_m + "1" * len(piece), True

        while i < len(text):
            ch = text[i]
            if ch.isspace():
                flush()
            elif ch in "<>":
                flush()
                op = ">>" if text[i:i + 2] == ">>" else ch
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
                    elif text[i] == "`":
                        value, i = self.backtick(text, i)
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
                unquoted(value)
                continue
            elif ch == "`":
                value, i = self.backtick(text, i)
                unquoted(value)
                continue
            else:
                cur_t, cur_m, have = cur_t + ch, cur_m + "1", True
            i += 1
        flush()
        words_in: list[tuple[str, str]] = []
        redir_in = redir_out = None
        k = 0
        while k < len(tokens):
            tok, mask = tokens[k]
            if mask != "op":
                words_in.append((tok, mask))
                k += 1
                continue
            if k + 1 >= len(tokens) or tokens[k + 1][1] == "op":
                nxt = tokens[k + 1][0] if k + 1 < len(tokens) else "end of file"
                return f"bsh: syntax error at line 1: `{nxt}' unexpected"
            if tok == "<":
                redir_in = tokens[k + 1][0]
            elif k + 2 == len(tokens) and redir_out is None:             # the output file ends the command, as before
                redir_out = (tok, tokens[k + 1][0])
            else:
                return "bsh: the redirection must be the last thing on the line: command > file."
            k += 2
        words: list[str] = []
        for word, mask in words_in:
            words += self.glob(word, mask)
        return words, redir_in, redir_out

    def backtick(self, text: str, i: int) -> tuple[str, int]:
        """What the command between the backticks at text[i] printed, and where the text goes on. `$(...)` is not here
        because bsh has none."""
        j = i + 1
        while j < len(text) and text[j] != "`":
            j += 2 if text[j] == "\\" else 1
        return self.substitute(text[i + 1:j].replace("\\`", "`")), j + 1

    def substitute(self, command: str) -> str:
        """Run `command` as a nested copy of this shell and bring back what it printed, without the trailing newlines.
        What it printed to stderr is shown anyway. The nested run cannot change the directory, the variables or end the
        shell, and cannot nest more than MAX_SUB deep or bring back more than SUB_LIMIT characters."""
        if self.sub_depth >= MAX_SUB:
            self.sub_errors.append(Err("bsh: too many nested backticks."))
            return ""
        saved = (self.cwd, dict(self.env), self.done, self.leaving, self.stdin, self.sub_errors, self.status)
        self.sub_depth += 1
        self.sub_errors = []
        try:
            lines = self.run(command)
        finally:
            self.sub_depth -= 1
            errors = self.sub_errors
            self.cwd, self.env, self.done, self.leaving, self.stdin, self.sub_errors, self.status = saved
        self.sub_errors += errors + [l for l in lines if isinstance(l, Err)]
        return "\n".join(l for l in lines if not isinstance(l, Err))[:SUB_LIMIT].rstrip("\n")

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
                names = [e.path.rsplit("/", 1)[-1] for e in entries]
                if piece.startswith("."):
                    names = [".", ".."] + names                        # `.*` matched both on PUB400
                for name in names:
                    seen += 1
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
            return [Err(f"bsh: {name}: 0403-016 Cannot execute: too many nested scripts.")]
        try:
            text = ifs.read(self.store, self.actor, path)
        except ifs.IfsError:
            return [Err(f"bsh: {name}: 0403-006 Execute permission denied.")]
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
        target = self.path(args[0]) if args else self.env["HOME"]
        given = args[0] if args else target
        try:
            entry = ifs.lookup(self.store, self.actor, target)
        except ifs.IfsError as exc:
            if self.qsh and exc.kind == "ENOENT":
                self.status = 1
                return [Err(f"cd: 001-0008 Error found changing to directory {given}.")]
            return self._abort([self._cd_error(exc, given)])
        if not entry.is_dir:
            return self._abort([f"{given}: Not a directory"])
        if "x" not in entry.mode:
            return self._abort([f"{given}: Permission denied"])
        self.cwd = target
        return []

    def _abort(self, out: list[str]) -> list[str]:
        """A failed `cd` or `export` in PUB400's bsh ends the shell when there is no terminal: `cd /nosuchdir || echo x`
        printed the error and nothing else, status 1. In a script it ends the script. At a prompt it is a guess that
        the shell carries on."""
        self.status = 1
        if self.depth:
            self.leaving = True
        elif self.batch:
            self.done = True
        return [Err(line) for line in out]

    @staticmethod
    def _cd_error(exc: ifs.IfsError, given: str) -> str:
        why = {"ENOENT": "No such file or directory", "EACCES": "Permission denied", "ENOTDIR": "Not a directory"}
        return Err(f"{given}: {why.get(exc.kind, exc.kind)}")

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
                if self.qsh and exc.kind == "ENOENT":
                    out.append(Err(f"ls: 001-2113 Error found getting information for object {given}. No such path or directory."))
                    self.status = 1
                    continue
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
            return Err(f"ls: 0653-345 {given}: Permission denied.")     # not captured: PUB400 only showed the missing case
        return Err(f"{given} not found")

    def _long(self, e: ifs.Entry) -> str:
        return f"{ifs.perms(e)}   1 {e.owner:<10} 0 {e.size:>8} {ifs.STAMP} {e.path.rsplit('/', 1)[-1]}"

    def cmd_cat(self, args: list[str]) -> list[str]:
        if not args and self.stdin is None:
            self.status = 2
            return [Err("cat: cannot open standard input in the simulator")]
        out: list[str] = []
        for given in args or ["-"]:
            if given == "-":                                   # standard input, which is what a pipe or `<` gave it
                out += self.stdin or []
                continue
            try:
                out += ifs.read(self.store, self.actor, self.path(given)).splitlines()
            except ifs.IfsError as exc:
                out.append(Err(f"cat: cannot open {given}"))
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
                return self._abort([f"bsh: {a}: is not an identifier"])
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
        return Err(f"{cmd}: " + why.get(exc.kind, exc.kind).format(given))

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
                            ifs.make(self.store, self.actor, walk, "dir", umask=self.umask)
                    continue
                ifs.make(self.store, self.actor, target, "dir", umask=self.umask)
            except ifs.IfsError as exc:
                out.append(self._write_error("mkdir", exc, given))
        return out

    def cmd_touch(self, args: list[str]) -> list[str]:
        out: list[str] = []
        for given in args:
            target = self.path(given)
            try:
                if target not in self.store.ifs:
                    ifs.make(self.store, self.actor, target, "file", umask=self.umask)
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
                    out.append(Err(f"rm: 0653-603 {given} is a directory."))
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
            return [Err(f"{name}: 0653-401 usage: {name} source target")]
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
            return [Err("chmod: 0653-401 usage: chmod mode file ...")]
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
            return [Err("Usage: system [-beEhiIkKnOpqsv] command")]      # PUB400's own line
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
            self.status = 4                          # the usage line went to stdout, status 4 (PUB400, qsh -c db2)
            return ['  USAGE: CMD ¬-v| ¬-S| ¬-s| ¬-t ! -T<char> ! -d| ¬-r RDBNAME ¬-u USERNAME -p PASSWORD| | <"SQLSTMT" ! -i ! -f FILENAME DEFAULT_LIB>']
        result = sql.run(self.store, self.actor, self._job(), " ".join(args))
        if result.error:
            self.status = 4                          # the db2 command line returns 4 for an SQL error, from IBM's page, not seen here
        return [Err(l) for l in sql.render(result)] if result.error else sql.render(result)

    # -- B3: the IBM i side, wording copied from PUB400 (ssh-pase-b3a, b3b, b3c, 2026-10-28) ---------------------------

    def cmd_qsh(self, args: list[str]) -> list[str]:
        """QSH, the other shell. `qsh -c 'line'` or a script on standard input. datarea, dataq, catsplf and db2 only run
        inside it (bsh says `cannot execute`), and its errors read differently."""
        if args[:1] == ["-c"] and len(args) >= 2:
            lines = [args[1]]
        elif not args and self.stdin is not None:
            lines = list(self.stdin)
        else:
            self.status = 2
            return [Err("qsh: 001-0019 Error found searching for command. Use qsh -c 'command'.")]
        if self.qsh_level >= MAX_DEPTH:
            self.status = 1
            return [Err("qsh: too many nested shells")]
        before = (self.qsh, self.done, self.leaving, self.stdin)
        self.qsh, self.stdin = True, None
        self.qsh_level += 1
        out: list[str] = []
        try:
            for line in lines[:200]:
                out += self.run(line)
                if self.done or self.leaving:
                    break
        finally:
            self.qsh_level -= 1
            self.qsh, self.done, self.leaving, self.stdin = before
        return out

    def _usage(self, name: str, code: str, lines: list[str], missing: bool = False) -> list[str]:
        self.status = 1
        head = [Err(f"{name}: 001-0098 Required argument is not specified.")] if missing else []
        return head + [Err(f"{name}: {code} usage:")] + [Err("    " + l) for l in lines]

    DATAREA_USAGE = ["datarea -r [-l] [-s substring] data-area", "datarea -w [-l] [-s substring] data-area [data ...]"]
    DATAQ_USAGE = ["dataq -c queue", "dataq -r [-lp] [-n number] [-t seconds] queue", "dataq -w [-l] [-n number] queue [data ...]"]

    def _qsys_object(self, name: str, given: str, want: str, need):
        """(object, None) or (None, error lines). `need` is the authority the use wants, from pasei.may."""
        path = self.path(given)
        found, why = pasei.find_object(self.store, self.actor, path, want)
        if why == "must specify an object in the QSYS.LIB file system.":
            self.status = 1
            return None, [Err(f"{name}: 001-2242 Path name {given} must specify an object in the QSYS.LIB file system.")]
        if found is None:
            self.status = 1
            return None, [Err(f"{name}: 001-2113 Error found getting information for object {path}. No such path or directory.")]
        if not pasei.may(self.store, self.actor, found, need):
            self.status = 1                              # not captured: the wording of a refusal here is a guess
            return None, [Err(f"{name}: 001-2113 Error found getting information for object {path}. Permission denied.")]
        return found, None

    @staticmethod
    def _options(args: list[str], with_value: str) -> tuple[set[str], dict[str, str], list[str]] | None:
        """Single letter options, the ones in `with_value` taking the next word; None when one is missing its value."""
        flags: set[str] = set()
        values: dict[str, str] = {}
        i = 0
        while i < len(args) and args[i].startswith("-") and len(args[i]) > 1:
            for n, ch in enumerate(args[i][1:]):
                if ch in with_value:
                    rest = args[i][n + 2:]
                    if rest:
                        values[ch] = rest
                    elif i + 1 < len(args):
                        i += 1
                        values[ch] = args[i]
                    else:
                        return None
                    break
                flags.add(ch)
            i += 1
        return flags, values, args[i:]

    def cmd_datarea(self, args: list[str]) -> list[str]:
        parsed = self._options(args, "s")
        if parsed is None or not ({"r", "w"} & parsed[0]) or not parsed[2]:
            return self._usage("datarea", "001-3111", self.DATAREA_USAGE, missing=True)
        flags, values, rest = parsed
        write = "w" in flags and "r" not in flags
        obj, err = self._qsys_object("datarea", rest[0], "*DTAARA", Auth.UPD if write else Auth.READ)
        if err:
            return err
        if write:
            pasei.area_set(self.store, obj, " ".join(rest[1:]), values.get("s"))
            return []
        return [pasei.area_text(obj, values.get("s")).rstrip()]

    def cmd_dataq(self, args: list[str]) -> list[str]:
        parsed = self._options(args, "nt")
        if parsed is None or not ({"r", "w", "c"} & parsed[0]) or not parsed[2]:
            return self._usage("dataq", "001-3110", self.DATAQ_USAGE, missing=True)
        flags, values, rest = parsed
        if "c" in flags:
            key = pasei.parse_qsys_path(self.path(rest[0]))
            lib = self.store.find_library(key[0]) if key and key[2] == "*DTAQ" else None
            if lib is None:
                return self._qsys_object("dataq", rest[0], "*DTAQ", Auth.READ)[1] or []
            if (key[0], key[1], "*DTAQ") in self.store.objects:
                self.status = 1
                return [Err(f"dataq: 001-2113 Error found creating object {self.path(rest[0])}. Object already exists.")]
            if Auth.ADD not in self.store.object_authority(self.actor, lib) and \
                    SpecialAuthority.ALLOBJ not in self.store.special_authorities(self.actor):
                self.status = 1
                return [Err(f"dataq: 001-2113 Error found creating object {self.path(rest[0])}. Permission denied.")]
            obj = SecuredObject(key[1], self.actor.name, library=key[0], type="*DTAQ", public=lib.public,
                                data={"entries": [], "maxlen": 128})
            self.store.objects[obj.key] = obj
            self.store.on_change()
            return []
        write = "w" in flags and "r" not in flags
        obj, err = self._qsys_object("dataq", rest[0], "*DTAQ", Auth.UPD if write else Auth.READ)
        if err:
            return err
        entries: list[str] = obj.data.setdefault("entries", [])
        if write:
            entries.append(" ".join(rest[1:])[:int(obj.data.get("maxlen", 128))])
            del entries[:-pasei.MAX_QUEUE]
            self.store.on_change()
            return []
        count = int(values["n"]) if values.get("n", "").isdigit() else 1
        taken = entries[:count]
        if "p" not in flags:
            del entries[:count]
            self.store.on_change()
        return taken

    def cmd_catsplf(self, args: list[str]) -> list[str]:
        usage = ["catsplf -j qualified-job [-aen] splfname splfnum", "catsplf -p pid [-aen] splfname splfnum"]
        parsed = self._options(args, "jp")
        if parsed is None or ("j" not in parsed[1] and "p" not in parsed[1]) or len(parsed[2]) != 2:
            return self._usage("catsplf", "001-3113", usage, missing=True)
        _, values, (name, number) = parsed
        if "p" in values:
            if values["p"] != str(JOB_PID):
                self.status = 1
                return [Err(f"catsplf: 001-2193 Error found getting job identifier for process identifier {values['p']}.")]
            job = JOB_ID
        else:
            job = values["j"]
        if not re.fullmatch(r"\d+|\*LAST|\*ONLY|\*ANY", number.upper()):
            self.status = 1
            return [Err(f"catsplf: 001-0032 Number {number} is not valid.")]      # a guess: the wording is getjobid's
        parts = job.split("/")
        known = len(parts) == 3 and (job == JOB_ID or any(f.job == job for f in self.store.spool))
        if not known:
            self.status = 1
            return [Err(f"catsplf: 001-2373 Job {job} was not found.")]
        found, why = spool.find(self.store, self.actor, name.upper(), (parts[2], parts[1], parts[0]), number)
        if found is None:
            self.status = 1                              # the wording below is a guess: only the missing job was captured
            return [Err(f"catsplf: {why.text}" if why.id == "CPF3492" else
                        f"catsplf: Spooled file {name} number {number} was not found in job {job}.")]
        return list(found.lines)

    def cmd_getjobid(self, args: list[str]) -> list[str]:
        parsed = self._options(args, "")
        if parsed is None or parsed[0] - set("jsv"):
            self.status = 1
            return [Err("getjobid: 001-3027 usage: getjobid [-jsv] [pid ...]")]
        flags, _, pids = parsed
        out: list[str] = []
        for pid in pids:
            if not pid.isdigit():
                self.status = 1
                return [Err(f"getjobid: 001-0032 Number {pid} is not valid.")]
        if "v" in flags:
            out.append("PID        PPID       PGRP       Status          Job Name")
            out.append("---------- ---------- ---------- --------------- ----------------------------")
        for pid in pids or [str(JOB_PID)]:
            if not pid.isdigit():
                self.status = 1
                return out + [Err(f"getjobid: 001-0032 Number {pid} is not valid.")]
            if int(pid) != JOB_PID:
                self.status = 1
                return out + [Err(f"getjobid: 001-2193 Error found getting job identifier for process identifier {pid}.")]
            if "v" in flags:
                out.append(f"{JOB_PID:>10} {JOB_PID - 1:>10} {JOB_PID - 1:>10} {'Running':<15} {JOB_ID}")
            elif "s" in flags:
                out.append(JOB_ID)
            else:
                out.append(f"Process identifier {pid} is {JOB_ID}")
        return out

    def cmd_sysval(self, args: list[str]) -> list[str]:
        parsed = self._options(args, "")
        if parsed is None or not parsed[2] or parsed[0] - set("np"):
            self.status = 1
            return [Err("sysval: 001-3049 usage:"), Err("    sysval [-p] systemValue ..."),
                    Err("    sysval -n [-p] networkAttr ...")]
        flags, _, names = parsed
        out: list[str] = []
        for name in names:
            value = (pasei.NETATTRS.get(name.upper()) if "n" in flags else pasei.sysval(self.store, name))
            if value is None:
                self.status = 1
                return out + [Err(f"sysval: 001-2219 System value {name.upper()} is not valid.")]
            out.append(f"{name.upper()}={value}" if "p" in flags else value)
        return out

    def cmd_getconf(self, args: list[str]) -> list[str]:
        if not args or args == ["-a"]:
            self.status = 2
            return [Err(l) for l in ("Usage: getconf [ -v specification ] system_var",
                                     "       getconf [ -v specification ] path_var pathname",
                                     "       getconf Device_var Device_Path", "       getconf -a")]
        name = args[0].upper()
        if name in pasei.GETCONF_PATH and len(args) == 2:
            try:
                ifs.lookup(self.store, self.actor, self.path(args[1]))
            except ifs.IfsError:
                self.status = 1
                return [Err(f"getconf: {args[1]}: No such file or directory")]      # a guess: the missing path was not captured
            return [pasei.GETCONF_PATH[name]]
        if name in pasei.GETCONF and len(args) == 1:
            return [pasei.GETCONF[name]]
        self.status = 2
        return [Err("getconf: specified variable is not valid on this system")]

    def cmd_dspmsg(self, args: list[str]) -> list[str]:
        """The AIX message catalog utility. PUB400 has no catalogs a login can name, so only the default text prints."""
        text, self.status = pasei.dspmsg(args)
        if self.status:
            return [Err(text)]
        return [text] if text else []

    def cmd_Rfile(self, args: list[str]) -> list[str]:
        """Reads and writes database file members. Only the usage line and `-r` were looked at: -r prints the records the
        way `cat` does (a guess at the layout), and writing is not built."""
        words = [a for a in args if not a.startswith("-")]
        if "-r" not in args or not words:
            self.status = 2
            return [Err("usage: Rfile -r|-w|-h [-abKlqQs] [-c CL-command] [-C CL-command] file...")]
        return self.cmd_cat(words)

    def cmd_setccsid(self, args: list[str]) -> list[str]:
        usage = "setccsid: 001-3047 usage: setccsid [-R [-H | -L | -P]] [-h] ccsid file ..."
        words = [a for a in args if not a.startswith("-") or a == "-"]
        if len(words) < 2:
            self.status = 1
            return [Err(usage)]
        if not words[0].isdigit():
            self.status = 1
            return [Err(f"setccsid: 001-0032 Number {words[0]} is not valid.")]
        out: list[str] = []
        for given in words[1:]:
            try:
                entry = ifs.lookup(self.store, self.actor, self.path(given))
            except ifs.IfsError:
                out.append(Err(f"setccsid: 001-2113 Error found getting information for object {self.path(given)}. No such path or directory."))
                self.status = 1
                continue
            if "w" not in entry.mode:                    # a guess: only a missing file was captured
                out.append(Err(f"setccsid: 001-2113 Error found changing object {self.path(given)}. Permission denied."))
                self.status = 1
        return out                                       # the IFS keeps no CCSID, so a file that is there just succeeds

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
        return [Err("logname: getlogin failed")]               # what PUB400 said over ssh, where there is no terminal

    def cmd_printenv(self, args: list[str]) -> list[str]:
        if not args:
            return self.cmd_env([])
        self.status = 0 if args[0] in self.env else 1
        return [self.env[a] for a in args[:1] if a in self.env]

    def cmd_ps(self, args: list[str]) -> list[str]:
        self.status = 1                                   # and PUB400 exited 1 with it, there being nothing to list
        return ["    PID    TTY  TIME CMD"]               # PUB400 listed no process for the login, and neither do we

    def _lines_of(self, name: str, given: str) -> tuple[list[str] | None, str]:
        if given == "-":
            return list(self.stdin or []), ""
        try:
            return ifs.read(self.store, self.actor, self.path(given)).splitlines(), ""
        except ifs.IfsError as exc:
            if name == "wc":
                return None, Err(f"wc: cannot open {given}")
            if name == "grep":
                return None, Err(f"grep: can't open {given}")
            return None, Err(f"{given}: {'Permission denied' if exc.kind == 'EACCES' else 'No such file or directory'}")

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
        if not files and self.stdin is not None:
            files = ["-"]
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
        names = [a for a in args if not a.startswith("-")]
        if not names and self.stdin is not None:               # counts of what was piped in, with no name after them
            text = "".join(l + "\n" for l in self.stdin)
            counts = {"l": text.count("\n"), "w": len(text.split()), "c": len(text.encode())}
            return ["".join(f"{counts[k]:8d}" for k in wanted)]
        for given in names:
            try:
                text = ifs.read(self.store, self.actor, self.path(given))
            except ifs.IfsError:
                out.append(Err(f"wc: cannot open {given}"))
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
            return [Err("Usage: grep [-i] [-v] [-n] [-c] pattern [file ...]")]
        pattern, files = rest[0], rest[1:]
        if not files and self.stdin is not None:
            files = ["-"]                                       # a file named on the line wins over the pipe, as on PUB400
        try:
            rx = re.compile(pattern, re.I if "i" in flags else 0)
        except re.error:
            self.status = 2
            return [Err(f"grep: 0651-209 The regular expression {pattern} is not valid.")]
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

    # -- B2: files and lookup, wording copied from PUB400 (ssh-pase-b2, 2026-10-28) -------------------------------

    NOT_FILES = frozenset({"export", "exit", "logout", "bracket"})      # shell words with no program of that name

    def _system_path(self, name: str) -> str | None:
        """Where the system keeps a command the simulator provides, or None. Only `cd`, `pwd` and `echo` are known to
        have a program as well as a builtin (`which cd` printed one); `db2` lives in /usr/bin."""
        if name in self.NOT_FILES or not re.fullmatch(r"[A-Za-z][A-Za-z0-9]*", name) or not hasattr(self, "cmd_" + name):
            return None
        return "/usr/bin/" + name if name in QSH_ONLY else "/QOpenSys/usr/bin/" + name

    def _where(self, name: str) -> str | None:
        """The program a name means, as `which` finds it: along PATH, an executable stream file first and then the
        simulator's own command if that directory is the one it lives in."""
        if "/" in name:
            found = self.find_script(name)
            return self.path(name) if found else None
        home = self._system_path(name)
        for d in [d for d in self.env.get("PATH", "").split(":") if d]:
            candidate = ifs.normalize(d + "/" + name, self.cwd, self.env["HOME"])
            try:
                entry = ifs.lookup(self.store, self.actor, candidate)
            except ifs.IfsError:
                entry = None
            if entry is not None and not entry.is_dir and "x" in entry.mode and candidate in self.store.ifs:
                return candidate
            if home is not None and candidate == home:
                return home
        return None

    def cmd_basename(self, args: list[str]) -> list[str]:
        if not args:
            self.status = 1
            return [Err("Usage: basename string [suffix]")]
        name = args[0].rstrip("/") if args[0].strip("/") else ("/" if args[0] else "")
        base = name.rsplit("/", 1)[-1] if name != "/" else "/"
        suffix = args[1] if len(args) > 1 else ""
        if suffix and base.endswith(suffix) and base != suffix:
            base = base[:-len(suffix)]
        return [base]

    def cmd_dirname(self, args: list[str]) -> list[str]:
        if not args:
            return ["."]                                       # PUB400 printed a dot and exited 0
        path = args[0]
        if not path.strip("/"):
            return ["/" if path else "."]
        head = path.rstrip("/")
        if "/" not in head:
            return ["."]
        return [head.rsplit("/", 1)[0].rstrip("/") or "/"]

    def cmd_which(self, args: list[str]) -> list[str]:
        out: list[str] = []
        for name in args:
            found = self._where(name)
            if found:
                out.append(found)
            else:
                self.status = 1
                out.append(Err(f"no {name} in " + " ".join(d for d in self.env.get("PATH", "").split(":") if d)))
        return out

    def cmd_type(self, args: list[str]) -> list[str]:
        out: list[str] = []
        for name in args:
            found = None if name in BUILTINS else self._where(name)
            if name in BUILTINS:
                out.append(f"{name} is a shell builtin")
            elif found:
                out.append(f"{name} is {found}")
            else:
                self.status = 1
                out.append(f"{name} not found ")               # to stdout, with the trailing space, as PUB400 did
        return out

    UNARY_TESTS = frozenset("-f -d -e -r -w -x -s -z -n -L -h -p -b -c -u -g -k -t".split())
    BINARY_TESTS = frozenset("= != -eq -ne -lt -le -gt -ge".split())

    def cmd_test(self, args: list[str]) -> list[str]:
        """test, and [ ]. A missing operand ends a shell with no terminal, as PUB400's bsh did
        (`test -f; echo $?` printed one error and no status)."""
        pos = 0

        def peek() -> str | None:
            return args[pos] if pos < len(args) else None

        def primary() -> bool:
            nonlocal pos
            tok = peek()
            if tok is None:
                raise ValueError("argument expected")
            if tok == "!":
                pos += 1
                return not primary()
            if tok in self.UNARY_TESTS and not (pos + 2 < len(args) + 0 and args[pos + 1] in self.BINARY_TESTS):
                if pos + 1 >= len(args):
                    raise ValueError("argument expected")
                operand = args[pos + 1]
                pos += 2
                return self._test_unary(tok, operand)
            if pos + 2 < len(args) + 0 and args[pos + 1] in self.BINARY_TESTS:
                left, op, right = args[pos:pos + 3]
                pos += 3
                return self._test_binary(left, op, right)
            pos += 1
            return tok != ""

        def conj() -> bool:
            nonlocal pos
            value = primary()
            while peek() == "-a":
                pos += 1
                value = primary() and value
            return value

        def disj() -> bool:
            nonlocal pos
            value = conj()
            while peek() == "-o":
                pos += 1
                value = conj() or value
            return value

        if not args:
            self.status = 1
            return []
        try:
            result = disj()
            if pos < len(args):
                raise ValueError("argument expected")
        except ValueError as exc:
            return self._abort([f"bsh: test: {exc}"])
        self.status = 0 if result else 1
        return []

    def cmd_bracket(self, args: list[str]) -> list[str]:
        if not args or args[-1] != "]":
            return self._abort(["bsh: test: ] missing"])
        return self.cmd_test(args[:-1])

    def _test_unary(self, op: str, operand: str) -> bool:
        if op == "-z":
            return operand == ""
        if op == "-n":
            return operand != ""
        target = self.path(operand)
        if self._system_path(posixpath.basename(target)) == target:            # the simulator's own commands count as programs
            return op in ("-e", "-f", "-r", "-x", "-s")
        try:
            entry = ifs.lookup(self.store, self.actor, target)
        except ifs.IfsError:
            return False
        return {"-e": True, "-f": not entry.is_dir, "-d": entry.is_dir, "-r": "r" in entry.mode, "-w": "w" in entry.mode,
                "-x": "x" in entry.mode, "-s": entry.size > 0}.get(op, False)

    @staticmethod
    def _test_binary(left: str, op: str, right: str) -> bool:
        if op == "=":
            return left == right
        if op == "!=":
            return left != right
        try:
            a, b = int(left), int(right)
        except ValueError:
            return False                                       # `test 3 -lt x` printed 1 on PUB400, with no message
        return {"-eq": a == b, "-ne": a != b, "-lt": a < b, "-le": a <= b, "-gt": a > b, "-ge": a >= b}[op]

    def cmd_file(self, args: list[str]) -> list[str]:
        out: list[str] = []
        for given in args:
            try:
                entry = ifs.lookup(self.store, self.actor, self.path(given))
            except ifs.IfsError:
                out.append(f"file: cannot open {given}")        # to stdout, exit 0, as on PUB400
                continue
            kind = "directory" if entry.is_dir else ("ascii text" if entry.size else "empty")      # "empty" is a guess
            out.append(f"{given}: {kind}")
        return out

    def cmd_rmdir(self, args: list[str]) -> list[str]:
        parents = "-p" in args
        names = [a for a in args if a != "-p"]
        if not names:
            self.status = 2
            return [Err("Usage: rmdir [-p] Directory ...")]
        why = {"EACCES": "Permission denied", "ENOENT": "No such file or directory", "ENOTDIR": "A path name is not a directory",
               "ENOTEMPTY": "File exists"}                       # only the permission case was seen; the rest are guesses
        out: list[str] = []
        for given in names:
            target = first = self.path(given)
            while True:
                try:
                    ifs.rmdir(self.store, self.actor, target)
                except ifs.IfsError as exc:
                    if target == first:                      # with -p, stopping at a parent that cannot go is not an error
                        out += [Err(f"rmdir: {given} not removed."), Err(why.get(exc.kind, exc.kind))]
                        self.status = 2
                    break
                target = posixpath.dirname(target)
                if not parents or target in ("", "/"):
                    break
        return out

    def cmd_umask(self, args: list[str]) -> list[str]:
        """`umask` prints the mask, `umask 077` sets it. PUB400 ignored `-S` and `umask 99`, saying nothing and exiting 0, so
        anything that is not octal digits is ignored here too."""
        if not args:
            return [f"{self.umask:03o}"]
        if re.fullmatch(r"[0-7]{1,4}", args[0]):
            self.umask = int(args[0], 8)
        return []

    @staticmethod
    def _blocks(entry: ifs.Entry) -> int:
        """512 byte blocks, from 4 KB allocation units as PUB400's 433 byte file showed (8 blocks, 4 KB)."""
        return 8 if entry.is_dir else -(-entry.size // 4096) * 8

    def cmd_du(self, args: list[str]) -> list[str]:
        flags = "".join(a[1:] for a in args if a.startswith("-") and len(a) > 1)
        summary, kilo, every = "s" in flags, "k" in flags, "a" in flags
        shown = lambda blocks: -(-blocks // 2) if kilo else blocks
        out: list[str] = []
        seen = 0

        def walk(path: str, given: str, top: bool) -> int:
            nonlocal seen
            seen += 1
            entry = ifs.lookup(self.store, self.actor, path)
            total = self._blocks(entry)
            if entry.is_dir and seen < MAX_FIND:
                try:
                    children = ifs.listdir(self.store, self.actor, path)
                except ifs.IfsError:
                    children = []
                    out.append(Err(f"du: {given}: Permission denied"))               # a guess at the wording
                    self.status = 2
                for child in children:
                    total += walk(child.path, given.rstrip("/") + "/" + child.path.rsplit("/", 1)[-1], False)
            if (top or not summary) and (entry.is_dir or every or top):
                out.append(f"{shown(total)}\t{given}")
            return total

        for given in [a for a in args if not a.startswith("-")] or ["."]:
            try:
                walk(self.path(given), given, True)
            except ifs.IfsError as exc:
                out.append(Err(f"du: {given}: " + ("Permission denied" if exc.kind == "EACCES" else "No such file or directory")))
                self.status = 2
        return out

    def cmd_find(self, args: list[str]) -> list[str]:
        """find path... [-name pattern] [-type f|d] [-perm [-]mode] [-user name] [-print] [-o]. What PUB400's find
        refused is refused the same way (`-maxdepth`, `-user` with a name it cannot find). It lists in sorted order."""
        starts = []
        i = 0
        while i < len(args) and not args[i].startswith("-") and args[i] not in ("!", "("):
            starts.append(args[i])
            i += 1
        if not starts:
            self.status = 1
            return [Err("Usage: find path-list [predicate-list]")]            # a guess
        groups: list[list] = [[]]
        printed = False
        while i < len(args):
            tok = args[i]
            if tok == "-o":
                groups.append([])
                i += 1
            elif tok in ("-a", ):
                i += 1
            elif tok == "-print":
                printed = True
                i += 1
            elif tok in ("-name", "-type", "-perm", "-user"):
                if i + 1 >= len(args):
                    self.status = 1
                    return [Err(f"find: missing argument to {tok}")]            # a guess
                value = args[i + 1]
                if tok == "-user" and value.upper() not in self.store.profiles:
                    self.status = 1
                    return [Err("find: cannot find -user name")]
                if tok == "-perm" and not re.fullmatch(r"-?[0-7]{1,4}", value):
                    self.status = 1
                    return [Err(f"find: bad option {value}")]                    # a guess
                groups[-1].append((tok, value))
                i += 2
            else:
                self.status = 1
                return [Err(f"find: bad option {tok}")]
            if not groups[-1] and tok != "-o" and len(groups) > 1 and i >= len(args):
                self.status = 1
                return [Err("find: missing argument")]                           # a guess
        out: list[str] = []
        visited = 0

        def matches(entry: ifs.Entry, given: str) -> bool:
            name = given.rstrip("/").rsplit("/", 1)[-1] or "/"
            octal = self._octal(entry)
            for group in groups:
                ok = True
                for tok, value in group:
                    if tok == "-name":
                        ok = fnmatchcase(name, value)
                    elif tok == "-type":
                        ok = value == ("d" if entry.is_dir else "f")
                    elif tok == "-user":
                        ok = entry.owner == value.upper()
                    else:
                        want = int(value.lstrip("-"), 8)
                        ok = (octal & want) == want if value.startswith("-") else octal == want
                    if not ok:
                        break
                if ok:
                    return True
            return False

        def walk(path: str, given: str) -> None:
            nonlocal visited
            visited += 1
            if visited > MAX_FIND:
                return
            try:
                entry = ifs.lookup(self.store, self.actor, path)
            except ifs.IfsError:
                return
            if matches(entry, given):
                out.append(given)
            if entry.is_dir:
                try:
                    children = ifs.listdir(self.store, self.actor, path)
                except ifs.IfsError:
                    out.append(Err(f"find: cannot open {given}"))                # a guess
                    self.status = 1
                    return
                for child in children:
                    walk(child.path, given.rstrip("/") + "/" + child.path.rsplit("/", 1)[-1])

        for given in starts:
            target = self.path(given)
            try:
                ifs.lookup(self.store, self.actor, target)
            except ifs.IfsError:
                out.append(Err(f"find: bad status-- {given}"))
                self.status = 1
                continue
            walk(target, given)
        if visited > MAX_FIND:
            out.append(Err(f"find: stopped after {MAX_FIND} entries (the simulator's limit)"))
            self.status = 1
        return out

    @staticmethod
    def _octal(entry: ifs.Entry) -> int:
        """The mode as a number. The group digit repeats the public one, as the long listing does."""
        def digit(m: str) -> int:
            return (4 if "r" in m else 0) + (2 if "w" in m else 0) + (1 if "x" in m else 0)
        return digit(entry.owner_mode) << 6 | digit(entry.public) << 3 | digit(entry.public)
