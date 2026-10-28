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

Built: pwd, cd, ls (-l -a), cat, id, whoami, echo ($VAR), env, export, exit, and the writing set: mkdir (-p),
touch, rm (-r -f), cp, mv, chmod, `> file` and `>> file` at the end of a command, and `system 'CL command'`,
which runs through the CL dispatcher as the signed on profile. Not built: pipes, input redirection, `;`, `&`,
command substitution, globbing, scripts, and every other command.

The wording of the refusals follows the AIX style PASE inherits (`ls: 0653-341 The file X does not exist.`,
`cat: 0652-050 Cannot open X.`), written from how those tools are known to speak and not captured from a real
system, so docs/pase.md lists it as unverified. The same goes for what `id` prints."""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass, field

from . import ifs
from .profiles import Profile, ProfileStore

BANNER = "Simulated PASE terminal. Not an AIX runtime: a few commands over a virtual IFS."
UNSUPPORTED = re.compile(r"[|&;<`]|\$\(")
SYSTEM_PATH = "/QOpenSys/usr/bin:/usr/bin"
BUILTINS = frozenset({"cd", "pwd", "echo", "export", "exit", "logout"})
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
    job: object = None

    def __post_init__(self) -> None:
        home = ifs.home_of(self.actor)
        self.cwd = self.cwd or home
        base = {"HOME": home, "USER": self.actor.name, "LOGNAME": self.actor.name, "PATH": SYSTEM_PATH,
                "SHELL": "/QOpenSys/usr/bin/ksh", "LANG": "EN_US", "TERM": "xterm"}
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
        line = line.strip()
        if not line or line.startswith("#"):
            return []
        if UNSUPPORTED.search(line):
            return ["ksh: that syntax is not available in the simulator (no pipes, redirection, ; & or substitution)."]
        try:
            words = shlex.split(line)
        except ValueError:
            return ["ksh: a quote was not closed."]
        redirect = None
        if len(words) >= 2 and re.fullmatch(r">>?", words[-2]):
            redirect, words = (words[-2], words[-1]), words[:-2]
        elif any(re.fullmatch(r">>?", w) for w in words) or any(w.endswith(">") for w in words):
            return ["ksh: the redirection must be the last thing on the line: command > file."]
        if not words:
            return []
        if re.fullmatch(r"[A-Za-z_]\w*=.*", words[0]) and len(words) == 1:
            name, _, value = words[0].partition("=")
            self.env[name] = self.expand(value)
            return []
        name, args = words[0], [self.expand(w) for w in words[1:]]
        script = None if name in BUILTINS else self.find_script(name)
        fn = getattr(self, "cmd_" + name, None) if re.fullmatch(r"[a-z][a-z0-9]*", name) else None
        if script is not None:
            out = self.run_script(script, name)
        elif "/" in name or fn is None:
            return [f"ksh: {name}: not found."]
        else:
            out = fn(args)
        if redirect is None:
            return out
        target = self.path(self.expand(redirect[1]))
        try:
            ifs.write(self.store, self.actor, target, "".join(l + "\n" for l in out), append=redirect[0] == ">>")
        except ifs.IfsError as exc:
            return [self._write_error("ksh", exc, redirect[1])]
        return []

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
            return [f"ksh: {name}: 0403-016 Cannot execute: too many nested scripts."]
        try:
            text = ifs.read(self.store, self.actor, path)
        except ifs.IfsError:
            return [f"ksh: {name}: 0403-006 Execute permission denied."]
        out: list[str] = []
        self.depth += 1
        try:
            for line in text.splitlines()[:200]:
                if line.strip() in ("exit", "logout"):
                    break
                out += self.run(line)
        finally:
            self.depth -= 1
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
            finally:
                self.depth -= 1
        return out

    def expand(self, word: str) -> str:
        return re.sub(r"\$(\w+)|\$\{(\w+)\}", lambda m: self.env.get(m.group(1) or m.group(2), ""), word)

    # -- the commands ------------------------------------------------------------------------------------------

    def cmd_pwd(self, args: list[str]) -> list[str]:
        return [self.cwd]

    def cmd_cd(self, args: list[str]) -> list[str]:
        target = self.path(args[0] if args else "~")
        try:
            entry = ifs.lookup(self.store, self.actor, target)
        except ifs.IfsError as exc:
            return [self._cd_error(exc, args[0] if args else "~")]
        if not entry.is_dir:
            return [f"ksh: cd: {args[0]}: [Not a directory]"]
        if "x" not in entry.mode:
            return [f"ksh: cd: {args[0]}: [Permission denied]"]
        self.cwd = target
        return []

    @staticmethod
    def _cd_error(exc: ifs.IfsError, given: str) -> str:
        why = {"ENOENT": "No such file or directory", "EACCES": "Permission denied", "ENOTDIR": "Not a directory"}
        return f"ksh: cd: {given}: [{why.get(exc.kind, exc.kind)}]"

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
                continue
            if len(paths) > 1 and entry.is_dir:
                out += ["", f"{given}:"] if out else [f"{given}:"]
            rows = [e for e in rows if hidden or not e.path.rsplit("/", 1)[-1].startswith(".")]
            out += [self._long(e) if long else e.path.rsplit("/", 1)[-1] for e in rows]
        return out

    @staticmethod
    def _ls_error(exc: ifs.IfsError, given: str) -> str:
        if exc.kind == "EACCES":
            return f"ls: 0653-345 {given}: Permission denied."
        return f"ls: 0653-341 The file {given} does not exist."

    def _long(self, e: ifs.Entry) -> str:
        return f"{ifs.perms(e)}   1 {e.owner:<10} 0 {e.size:>8} {ifs.STAMP} {e.path.rsplit('/', 1)[-1]}"

    def cmd_cat(self, args: list[str]) -> list[str]:
        if not args:
            return ["cat: 0652-050 Cannot open standard input in the simulator."]
        out: list[str] = []
        for given in args:
            try:
                out += ifs.read(self.store, self.actor, self.path(given)).splitlines()
            except ifs.IfsError as exc:
                out.append(f"cat: 0652-050 Cannot open {given}." if exc.kind != "EISDIR"
                           else f"cat: 0652-050 {given} is a directory.")
        return out

    def cmd_id(self, args: list[str]) -> list[str]:
        uid = ifs.uid_of(self.store, self.actor)
        return [f"uid={uid}({self.actor.name}) gid={uid}({self.actor.name})"]

    def cmd_whoami(self, args: list[str]) -> list[str]:
        return [self.actor.name]

    def cmd_echo(self, args: list[str]) -> list[str]:
        return [" ".join(args)]

    def cmd_env(self, args: list[str]) -> list[str]:
        return [f"{k}={v}" for k, v in sorted(self.env.items())]

    def cmd_export(self, args: list[str]) -> list[str]:
        for a in args:
            name, sep, value = a.partition("=")
            if not re.fullmatch(r"[A-Za-z_]\w*", name):
                return [f"ksh: export: {a}: not a valid identifier."]
            if sep:
                self.env[name] = value
        return []

    def cmd_exit(self, args: list[str]) -> list[str]:
        self.done = True
        return []

    cmd_logout = cmd_exit

    # -- writing -----------------------------------------------------------------------------------------------

    @staticmethod
    def _write_error(cmd: str, exc: ifs.IfsError, given: str) -> str:
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
            return ["system: 0653-401 usage: system 'CL command'"]
        line = " ".join(args)
        text = textview.outcome_text(self.store, commands.execute(self.store, self.actor, line, self._job()), line)
        return text.splitlines()

    def _job(self):
        from ..cl.session import Session
        if self.job is None:
            self.job = Session.for_profile(self.actor.current_library)
        return self.job

    def cmd_db2(self, args: list[str]) -> list[str]:
        """Run one SQL statement as the signed on profile, over the physical files (system/sql.py)."""
        from . import sql
        if not args:
            return ["db2: usage: db2 \"SQL statement\""]
        return sql.render(sql.run(self.store, self.actor, self._job(), " ".join(args)))
