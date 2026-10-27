"""Jobs, the smallest model that teaches something.

A job here is a row, not a process: a name, a user, a number, a type, a subsystem and a
status. Live 5250 sessions are interactive jobs (named after the display device, as on a
real system) and a seeded set of system jobs stands beside them, so WRKACTJOB has something
true to show. Nothing is scheduled, no CPU is used, and the table lives in memory: a restart
gives the seeded jobs and no sessions.

What the PUB400 capture settled: a basic profile lists every active job on the system,
other people's included, so job names, users and what each is running (the function column,
such as PGM-ARCPSTDA or CMD-STRQSH) are visible to anyone who may run WRKACTJOB. That is the
reconnaissance value, and it is not gated on *JOBCTL. What *JOBCTL will gate (hold, end,
change someone else's job) is built with those options, not here.

The seeded system jobs are our own picks, in the shape of a real system's. Their numbers
and names are not copied from the capture."""

from dataclasses import dataclass, field
from datetime import datetime, timezone

# Subsystem, then its jobs: (name, user, type, function, status)
_SEED = {
    "QCTL": [("QSYSSCD", "QPGMR", "BCH", "PGM-QEZSCNEP", "EVTW")],
    "QINTER": [],
    "QBATCH": [],
    "QSERVER": [("QZLSSERVER", "QUSER", "ASJ", "", "SIGW")],
    "QSYSWRK": [("QTCPIP", "QTCP", "BCH", "PGM-QTCPIP", "EVTW"),
                ("QTFTP00001", "QTCP", "BCI", "PGM-QTFTPSRV", "EVTW")],
    "QUSRWRK": [("QZDASOINIT", "QUSER", "PJ", "PGM-QZDASOINIT", "PSRW"),
                ("QZDASOINIT", "QUSER", "PJ", "PGM-QZDASOINIT", "PSRW"),
                ("QZSOSIGN", "QUSER", "PJ", "PGM-QZSOSIGN", "PSRW")],
}


@dataclass
class Job:
    name: str
    user: str
    number: str
    type: str                    # SBS subsystem, INT interactive, BCH batch, BCI, ASJ, PJ prestart
    subsystem: str
    status: str = "DEQW"
    function: str = ""
    cpu: float = 0.0
    spooled: list = field(default_factory=list)

    @property
    def qualified(self) -> str:
        return f"{self.number}/{self.user}/{self.name}"


class JobTable:
    def __init__(self) -> None:
        self.jobs: list[Job] = []
        self._next = 1000
        for sbs, members in _SEED.items():
            self.jobs.append(Job(sbs, "QSYS", self._number(), "SBS", sbs, "DEQW"))
            for name, user, typ, func, status in members:
                self.jobs.append(Job(name, user, self._number(), typ, sbs, status, func))

    def _number(self) -> str:
        self._next += 1
        return f"{self._next:06d}"

    def start_interactive(self, user: str, device: str) -> Job:
        job = Job(device, user, self._number(), "INT", "QINTER", "DSPW", "MENU-MAIN")
        self.jobs.append(job)
        return job

    def end(self, job: Job | None) -> None:
        if job is not None and job in self.jobs:
            self.jobs.remove(job)

    def find(self, name: str, user: str | None = None) -> list[Job]:
        return [j for j in self.jobs if j.type != "SBS" and j.name == name and (user is None or j.user == user)]

    def active(self, subsystem: str = "*ALL") -> list[Job]:
        """The WRKACTJOB order: each subsystem, then its jobs, in the order they started."""
        out: list[Job] = []
        for sbs in (j for j in self.jobs if j.type == "SBS"):
            if subsystem != "*ALL" and sbs.name != subsystem:
                continue
            out.append(sbs)
            out += [j for j in self.jobs if j.type != "SBS" and j.subsystem == sbs.name]
        return out


def now_stamp() -> tuple[str, str]:
    t = datetime.now(timezone.utc)
    return t.strftime("%y-%m-%d"), t.strftime("%H:%M:%S") + " UTC"
