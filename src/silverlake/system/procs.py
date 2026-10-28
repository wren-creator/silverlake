"""PASE batch B8, process control: kill jobs ulimit nice nohup wait fg bg alias unalias, and real rows for ps.

Usage lines, error text, statuses and column layouts come from the PUB400 run of 2026-10-28 (ssh-pase-b8, kept local). What
that run did not reach is a guess and docs/pase.md says so. There are no real processes: the table `ps` shows is a short
made up one (the rows on PUB400 are other people's jobs and are not copied, only the layout), the login's own shell and `ps`
are added to it, and `kill` can only end this shell. Nothing here signals a host process or starts one. `nice` and `nohup`
run the command as it is, `sleep` style: wording, not scheduling."""

from __future__ import annotations

import re

from . import ifs
from .authority import SpecialAuthority
from .textfilters import Err

SIGNALS = ("NULL HUP INT QUIT ILL TRAP ABRT EMT FPE KILL BUS SEGV SYS PIPE ALRM TERM URG STOP TSTP CONT CHLD TTIN TTOU IO XCPU "
           "XFSZ MSG WINCH PWR USR1 USR2 PROF DANGER VTALRM MIGRATE PRE VIRT ALRM1 WAITING RECONFIG CPUFAIL GRANT RETRACT "
           "SOUND SAK").split()
SIGNAL_LIST = ["NULL HUP INT QUIT ILL TRAP ABRT EMT FPE KILL BUS SEGV SYS PIPE ALRM TERM URG ",
               "STOP TSTP CONT CHLD TTIN TTOU IO XCPU XFSZ MSG WINCH PWR USR1 USR2 PROF DANGER ",
               "VTALRM MIGRATE PRE VIRT ALRM1 WAITING RECONFIG CPUFAIL GRANT RETRACT SOUND SAK"]
ENDS_THE_SHELL = {"HUP", "KILL"}               # a login shell ignores TERM, INT and QUIT; a guess for what bsh does

KILL_USAGE = ["usage: kill [ -signal | -s signal] pid ...", "usage: kill -l [exit_status]"]
NICE_USAGE = ["usage: nice [-n increment] command [argument...]", "usage: nice [-increment] command [argument...]"]
NOHUP_USAGE = "usage: nohup { -p pid | command [arg ...] }"
ULIMIT_USAGE = "bsh: Usage: ulimit [-H | -S] [ -c | -d | -f | -m | -r | -s | -t | -u] [limit]"
ULIMITS = ["cputime \tunlimited", "filesize \tunlimited", "datasize \tunlimited", "stacksize \tunlimited",
           "coredumpsize \tunlimited", "memory \t\tunlimited", "threads \tunlimited", "processes \tunlimited"]
ULIMIT_FLAGS = set("cdfmrstu")
KSH_ALIASES = ["autoload='typeset -fu'", "command='command '", "functions='typeset -f'", "hash='alias -t -'", "history='fc -l'",
               "integer='typeset -i'", "local=typeset", "nohup='nohup '", "r='fc -e -'", "stop='kill -STOP'",
               "suspend='if [[ ${0#-} = $0 ]] ; then kill -STOP $$; else dspmsg -s 1 ksh.cat SUSPEND \"suspend: cannot suspend login shell",
               "\"; fi '", "type='whence -v'"]

# A short made up system table in PUB400's layout: (user, pid, ppid, started, time, command). The real rows are other
# people's jobs. The ssh session that carries the login and the login's own processes are added at run time.
SYSTEM_ROWS = [
    ("qsys", 37, 1, "Oct 25", "1:56", "[QP0ZSPWP]"),
    ("qtcp", 41, 1, "Oct 25", "0:13", "[QTFTP00000]"),
    ("qsecofr", 63, 1, "Oct 25", "0:38", "[sshd]"),
    ("qusrsys", 72, 1, "Oct 25", "1:35", "[QZSOSIGN]"),
    ("qusrsys", 74, 72, "Oct 25", "0:10", "[QZDASOINIT]"),
]
PS_COLUMNS = {"pid": "PID", "ppid": "PPID", "user": "USER", "comm": "COMMAND", "args": "COMMAND", "tty": "TT", "time": "TIME"}
STARTED = "09:00:00"                            # the IFS keeps no times, so the login's own rows start at the IFS's stamp


class Procs:
    """Mixed into the Shell beside Filters, Heavy, Archives and SshTools."""

    # -- the process table ------------------------------------------------------------------------------------------

    def _processes(self, job_pid: int) -> list[dict]:
        """Every row `ps -ef` would show: the system's, this login's ssh session, its shell and the `ps` being run."""
        me = self.actor.name.lower()
        rows = [{"user": u, "uid": 0 if u == "qsecofr" else 100 + i, "pid": p, "ppid": pp, "start": s, "time": t, "cmd": c}
                for i, (u, p, pp, s, t, c) in enumerate(SYSTEM_ROWS)]
        uid = ifs.uid_of(self.store, self.actor)
        rows.append({"user": "qsecofr", "uid": 0, "pid": job_pid - 2, "ppid": 63, "start": STARTED, "time": "0:00", "cmd": "[sshd]"})
        rows.append({"user": me, "uid": uid, "pid": job_pid, "ppid": job_pid - 2, "start": STARTED, "time": "0:00", "cmd": "bsh"})
        rows.append({"user": me, "uid": uid, "pid": job_pid + 1, "ppid": job_pid, "start": STARTED, "time": "0:00", "cmd": "ps"})
        return rows

    def cmd_ps(self, args: list[str]) -> list[str]:
        from .pase import JOB_PID
        rows = self._processes(JOB_PID)
        select, fields, full, i = None, None, False, 0
        while i < len(args):
            a = args[i]
            letters = a[1:] if a.startswith("-") else a
            if a in ("-o",) and i + 1 < len(args):
                fields, i = [f.strip().lower() for f in args[i + 1].split(",")], i + 1
            elif a in ("-p", "-u") and i + 1 < len(args):
                select, i = (a, args[i + 1]), i + 1
            elif re.fullmatch(r"-?[eAfl]+", a):
                select, full = select or ("-e", ""), full or "f" in letters
            else:
                self.status = 1
                return [Err(f"ps: illegal option -- {a.lstrip('-')[:1]}")]                     # a guess: nothing unknown was tried
            i += 1
        chosen: list[dict] = []
        if select is None:
            chosen = []                                                                         # PUB400 listed nothing for a login
        elif select[0] == "-e":
            chosen = rows
        elif select[0] == "-p":
            wanted = {int(p) for p in re.split(r"[ ,]+", select[1]) if p.isdigit()}
            chosen = [r for r in rows if r["pid"] in wanted]
        else:
            who = select[1]
            chosen = [r for r in rows if r["user"] == who.lower() or str(r["uid"]) == who]
        shape = "u" if select and select[0] == "-u" else "e" if full else "p"       # -p and plain -e use the short layout
        out = self._ps_table(chosen, fields, shape)
        self.status = 0 if chosen else 1
        return out

    def _ps_table(self, rows: list[dict], fields: list[str] | None, shape: str) -> list[str]:
        if fields is not None:
            bad = [f for f in fields if f not in PS_COLUMNS]
            if bad:
                self.status = 1
                return [Err(f"ps: unknown output format {bad[0]}")]                           # a guess: only pid,ppid,comm was tried
            def cell(r, f):
                return {"pid": f"{r['pid']:>6}", "ppid": f"{r['ppid']:>6}", "user": f"{r['user']:<8}", "comm": r["cmd"],
                        "args": r["cmd"], "tty": f"{'-':>6}", "time": f"{r['time']:>5}"}[f]
            def head(f):
                return {"pid": f"{'PID':>6}", "ppid": f"{'PPID':>6}", "user": f"{'USER':<8}", "tty": f"{'TT':>6}",
                        "time": f"{'TIME':>5}"}.get(f, PS_COLUMNS[f])
            return [" ".join(head(f) for f in fields)] + [" ".join(cell(r, f) for f in fields) for r in rows]
        if shape == "e":
            out = [f"{'UID':>8} {'PID':>6} {'PPID':>6} {'C':>3} {'STIME':>8} {'TTY':>6} {'TIME':>5} CMD"]
            return out + [f"{r['user'][:8]:>8} {r['pid']:>6} {r['ppid']:>6} {0:>3} {r['start']:>8} {'-':>6} {r['time']:>5} {r['cmd']}"
                          for r in rows]
        if shape == "u":
            out = [f"{'UID':>9} {'PID':>6} {'TTY':>6} {'TIME':>5} CMD"]
            return out + [f"{r['uid']:>9} {r['pid']:>6} {'-':>6} {r['time']:>5} {r['cmd']}" for r in rows]
        out = [f"{'PID':>7} {'TTY':>6} {'TIME':>5} CMD"]
        return out + [f"{r['pid']:>7} {'-':>6} {r['time']:>5} {r['cmd']}" for r in rows]

    # -- kill, jobs, wait, fg, bg ------------------------------------------------------------------------------------

    def cmd_kill(self, args: list[str]) -> list[str]:
        from .pase import JOB_PID
        if not args:
            self.status = 2
            return [Err(l) for l in KILL_USAGE]
        if args[0] == "-l":
            self.status = 0
            if len(args) > 1:
                n = int(args[1]) if args[1].isdigit() else -1
                n = n - 128 if n > 128 else n
                if not 0 <= n < len(SIGNALS):
                    self.status = 2
                    return [Err(f"kill: {args[1]}: bad signal number")]                          # a guess
                return [SIGNALS[n]]
            return list(SIGNAL_LIST)
        signal, rest = "TERM", list(args)
        first = rest[0]
        if first == "-s" and len(rest) > 1:
            signal, rest = rest[1], rest[2:]
        elif first.startswith("-") and len(first) > 1 and first != "--":
            signal, rest = first[1:], rest[1:]
        elif first == "--":
            rest = rest[1:]
        name = signal.upper().removeprefix("SIG")
        if signal.isdigit() and int(signal) < len(SIGNALS):
            name = SIGNALS[int(signal)]
        if name not in SIGNALS:
            self.status = 2
            return [Err(f"kill: {signal}: bad signal name")]                                       # a guess
        if not rest:
            self.status = 2
            return [Err(l) for l in KILL_USAGE]
        by_pid = {r["pid"]: r for r in self._processes(JOB_PID)}
        out: list[str] = []
        self.status = 0
        for word in rest:
            if not re.fullmatch(r"\d+", word):
                out.append(Err(f"kill: {word}: arguments must be process or job IDs"))              # a guess
                self.status = 2
                continue
            row = by_pid.get(int(word))
            if row is None:
                out.append(Err(f"kill: {word}: no such process"))                                   # copied
                self.status = 2
            elif row["uid"] != ifs.uid_of(self.store, self.actor) and not self._all_object():
                out.append(Err(f"kill: {word}: Not owner"))                                         # a guess
                self.status = 2
            elif name in ENDS_THE_SHELL and row["pid"] == JOB_PID:
                self.done = True
        return out

    def _all_object(self) -> bool:
        return SpecialAuthority.ALLOBJ in self.store.special_authorities(self.actor)

    def cmd_jobs(self, args: list[str]) -> list[str]:
        self.status = 0                                          # nothing runs in the background here
        return []

    def cmd_wait(self, args: list[str]) -> list[str]:
        self.status = 0
        return []

    def cmd_fg(self, args: list[str]) -> list[str]:
        self.status = 1                                          # PUB400 printed nothing and exited 1: there is no job
        return []

    cmd_bg = cmd_fg

    # -- alias, unalias, ulimit ----------------------------------------------------------------------------------

    def cmd_alias(self, args: list[str]) -> list[str]:
        self.status = 0                                          # `alias ll=...` then `ll` was `not found`: the alias dies with its process
        return list(KSH_ALIASES) if not args else []

    def cmd_unalias(self, args: list[str]) -> list[str]:
        if not args:
            self.status = 1
            return [Err("/QOpenSys/usr/bin/unalias[53]: unalias: bad argument count")]
        known = {l.split("=", 1)[0] for l in KSH_ALIASES if re.match(r"\w+=", l)}
        self.status = 0 if all(a in known for a in args) else 1   # nothing printed for an unknown name, status 1 (copied); known ones a guess
        return []

    def cmd_ulimit(self, args: list[str]) -> list[str]:
        flags = [a for a in args if a.startswith("-")]
        letters = {c for a in flags for c in a[1:]}
        values = [a for a in args if not a.startswith("-")]
        if not args:
            self.status = 0
            return list(ULIMITS)
        if not letters - {"H", "S"} <= ULIMIT_FLAGS or len(letters - {"H", "S"}) > 1 or len(values) > 1:
            self.status = 1
            return [Err(ULIMIT_USAGE)]
        self.status = 0
        if values:
            return [] if values[0] == "unlimited" or values[0].isdigit() else [Err(ULIMIT_USAGE)]      # accepted and not enforced
        return ["unlimited"] if letters - {"H", "S"} else list(ULIMITS)                               # a guess: one value for one flag

    # -- nice, nohup -----------------------------------------------------------------------------------------------

    def _run_words(self, words: list[str]) -> list[str]:
        depth = getattr(self, "_wrap_depth", 0)
        if depth >= 8:
            self.status = 1
            return [Err("too many nested commands")]
        self._wrap_depth = depth + 1
        try:
            return self.run_simple(" ".join("'" + w.replace("'", "'\\''") + "'" for w in words), self.stdin)
        finally:
            self._wrap_depth = depth

    def cmd_nice(self, args: list[str]) -> list[str]:
        words = list(args)
        if words[:1] == ["-n"] and len(words) > 1:
            words = words[2:]
        elif words and re.fullmatch(r"-+\d+", words[0]):
            words = words[1:]
        if not words:
            self.status = 2
            return [Err(l) for l in NICE_USAGE]
        return self._run_words(words)                           # the priority change is not modelled

    def cmd_nohup(self, args: list[str]) -> list[str]:
        if not args or args[0] == "-p":
            self.status = 127
            return [Err(NOHUP_USAGE)]
        return self._run_words(args)                             # no nohup.out: standard output was not a terminal on PUB400
