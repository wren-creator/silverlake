"""A simulated PASE shell. A fixed list of commands over the virtual IFS (system/ifs.py), as the signed on
profile, and nothing else: no process is ever started, no host file is read, and a line that is not one of
these commands is refused in the shell's own voice. That is what makes it safe to leave on a training box and
why `reset.sh` puts everything back exactly.

Built: pwd, cd, ls (-l -a), cat, id, whoami, echo ($VAR), env, export and exit. Not built: pipes, redirection,
`;`, `&`, command substitution, globbing, scripts, and every other command.

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
UNSUPPORTED = re.compile(r"[|&;<>`]|\$\(")
SYSTEM_PATH = "/QOpenSys/usr/bin:/usr/bin"


@dataclass
class Shell:
    store: ProfileStore
    actor: Profile
    cwd: str = ""
    env: dict[str, str] = field(default_factory=dict)
    done: bool = False

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
        name, args = words[0], [self.expand(w) for w in words[1:]]
        fn = getattr(self, "cmd_" + name, None) if re.fullmatch(r"[a-z]+", name) else None
        if fn is None:
            return [f"ksh: {name}: not found."]
        return fn(args)

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
