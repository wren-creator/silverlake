"""Spool files, output queues and job logs: WRKSPLF, DSPSPLF, DLTSPLF.

A spool file belongs to a job (name, user, number), has a number within that job, and sits on
an output queue, which is a `*OUTQ` object with its own authority and three settings that decide
who may see what. Every session leaves a `QPJOBLOG` on `QEZJOBLOG` when it ends, as the real
PUB400 does (captured: one per past session, user data holding the job name).

What a real basic profile did (captured): `WRKSPLF` listed only its own files, and displaying
one of its job logs showed the commands it ran and the messages they raised.

The rules for other people's files, from IBM's CRTOUTQ page (parts of that page were only
available as a summary, so they are marked):
  DSPDTA(*NO)     users with authority to the queue can display only their own files unless they
                  hold a special authority (the CRTOUTQ default)                        [summary]
  DSPDTA(*YES)    anyone with authority to read the queue can display any file on it   [summary]
  DSPDTA(*OWNER)  the file's owner or a user with *SPLCTL; the page's example adds the queue's
                  owner and job control authority                                       [summary]
  OPRCTL(*YES)    a user with *JOBCTL can control the queue's files (the default)      [summary]
  *SPLCTL         controls and displays every file. Its page text was not found; the rule is
                  inferred from the CRTOUTQ wording above.
Inferred, not read on a page: that listing other people's entries needs *READ to the queue, that
deleting follows the same "control" rule as holding, and that the owner of the file may always
display, hold and delete it. A refusal is CPF3492, "Not authorized to spooled file." (listed on
the DSPSPLF and DLTSPLF pages, condition inferred).

Passwords are never written into a job log: a PASSWORD parameter is logged as asterisks. That is
our choice, not something seen on a page."""

import fnmatch
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime

from . import messages
from .authority import Auth, SpecialAuthority
from .objects import Done, _no, _ok
from .profiles import Profile, ProfileStore

SA = SpecialAuthority
LINES_PER_PAGE = 16


@dataclass
class SpoolFile:
    name: str
    user: str
    job_name: str
    job_number: str
    file_no: int = 1
    outq: str = "QEZJOBLOG"
    outq_lib: str = "QUSRSYS"
    user_data: str = ""
    status: str = "RDY"
    lines: list[str] = field(default_factory=list)
    created: str = ""
    form_type: str = "*STD"
    priority: int = 5
    copies: int = 1

    @property
    def pages(self) -> int:
        return max(1, -(-len(self.lines) // 55))

    @property
    def job(self) -> str:
        return f"{self.job_number}/{self.user}/{self.job_name}"

    def stamp(self) -> datetime:
        return datetime.fromisoformat(self.created) if self.created else datetime.now()


def to_row(f: SpoolFile) -> dict:
    return asdict(f)


def from_row(d: dict) -> SpoolFile:
    return SpoolFile(**d)


# -- who may do what -------------------------------------------------------------------------------

def _queue(store: ProfileStore, f: SpoolFile):
    return store.objects.get((f.outq_lib, f.outq, "*OUTQ"))


def _setting(q, key: str, default: str) -> str:
    return (q.data or {}).get(key, default) if q is not None else default


def can_control(store: ProfileStore, actor: Profile, f: SpoolFile) -> bool:
    """Hold, delete, see attributes: the owner, *SPLCTL, or *JOBCTL where the queue allows it."""
    special = store.special_authorities(actor)
    if actor.name == f.user or SA.SPLCTL in special:
        return True
    return SA.JOBCTL in special and _setting(_queue(store, f), "oprctl", "*YES") == "*YES"


def can_display(store: ProfileStore, actor: Profile, f: SpoolFile) -> bool:
    if can_control(store, actor, f):
        return True
    q = _queue(store, f)
    held = store.authority_to_object(actor, q) if q is not None else Auth.READ
    mode = _setting(q, "dspdta", "*NO")
    if mode == "*YES":
        return Auth.READ in held
    return mode == "*OWNER" and q is not None and actor.name == q.owner


def can_list(store: ProfileStore, actor: Profile, f: SpoolFile) -> bool:
    if can_control(store, actor, f):
        return True
    q = _queue(store, f)
    return q is None or Auth.READ in store.authority_to_object(actor, q)


def select(store: ProfileStore, actor: Profile, user: str = "*CURRENT", name: str = "*ALL",
           job: tuple | None = None) -> list[SpoolFile]:
    """WRKSPLF SELECT(user ... name): *CURRENT is only your own files, a name or *ALL is every
    file you may list."""
    out = []
    for f in store.spool:
        if user == "*CURRENT":
            if f.user != actor.name:
                continue
        elif not can_list(store, actor, f):
            continue
        elif user != "*ALL" and not fnmatch.fnmatchcase(f.user, user):
            continue
        if name != "*ALL" and not fnmatch.fnmatchcase(f.name, name):
            continue
        if job is not None:
            jn, ju, jnum = job
            if not (jn in ("*", f.job_name) and ju in ("*", f.user) and jnum in ("*", f.job_number)):
                continue
        out.append(f)
    return sorted(out, key=lambda f: (f.stamp(), f.file_no))


def find(store: ProfileStore, actor: Profile, name: str, job: str | tuple, splnbr: str):
    """DSPSPLF and DLTSPLF selection. `job` is "*" (your own current job) or (name, user, number)
    with "*" parts allowed, `splnbr` is *ONLY, *LAST, *ANY or a number. Returns (file, message)."""
    if job == "*":
        return None, _msg("CPF3342", "Job not found.")        # callers pass the session's own job instead
    jn, ju, jnum = job
    hits = [f for f in store.spool if f.name == name
            and (jn in ("*", f.job_name)) and (ju in ("*", f.user)) and (jnum in ("*", f.job_number))]
    if not hits:
        return None, _msg("CPF3303", f"File {name} not found in job {jnum}/{ju}/{jn}.")
    if splnbr.isdigit():
        hits = [f for f in hits if f.file_no == int(splnbr)]
        if not hits:
            return None, _msg("CPF3303", f"File {name} not found in job {jnum}/{ju}/{jn}.")
    elif splnbr == "*LAST":
        hits = [max(hits, key=lambda f: f.file_no)]
    elif splnbr == "*ONLY" and len(hits) > 1:
        return None, _msg("CPF3340", f"More than one file with specified name found in job {jnum}/{ju}/{jn}.")
    f = hits[0]
    if not can_display(store, actor, f):
        return None, _msg("CPF3492", "Not authorized to spooled file.")
    return f, None


def _msg(id_: str, text: str) -> messages.Message:
    return messages.Message(id_, text, messages.DOCUMENTED)


def delete(store: ProfileStore, actor: Profile, f: SpoolFile) -> Done:
    if not can_control(store, actor, f):
        return _no(_msg("CPF3492", "Not authorized to spooled file."))
    store.spool.remove(f)
    store.on_change()
    return _ok(f"File {f.name} number {f.file_no} deleted.")


def hold(store: ProfileStore, actor: Profile, f: SpoolFile, hold: bool) -> Done:
    """HLDSPLF and RLSSPLF. The pages were not read for authority, so the same control rule as
    delete applies (inferred). Holding a held file or releasing a ready one is not an error."""
    if not can_control(store, actor, f):
        return _no(_msg("CPF3492", "Not authorized to spooled file."))
    f.status = "HLD" if hold else "RDY"
    store.on_change()
    return _ok(f"File {f.name} number {f.file_no} {'held' if hold else 'released'}.")


# -- job logs --------------------------------------------------------------------------------------

_PASSWORD = re.compile(r"(PASSWORD|PWD)\(([^)]*)\)", re.IGNORECASE)


def mask(line: str, fold: bool = True) -> str:
    """Upper case outside quotes, as a 5250 command line does, and no passwords."""
    parts = line.split("'")
    folded = "'".join(p if i % 2 or not fold else p.upper() for i, p in enumerate(parts))
    return _PASSWORD.sub(lambda m: f"{m.group(1).upper()}(*****)", folded)


def write_joblog(store: ProfileStore, job, entries: list[tuple[datetime, str, str]]) -> SpoolFile | None:
    """Called when a session ends. `entries` are (time, kind, text): a command typed, or a message
    a command raised. Layout follows the captured job log, wording of the header is ours."""
    if job is None:
        return None
    now = datetime.now()
    lines = [
        f" SILVERLAKE  Job Log                       {now:%y-%m-%d}  {now:%H:%M:%S}",
        f"   Job name . . . . . . . . . . :   {job.name:<14}User  . . . . . . :   {job.user}",
        f"   Job description  . . . . . . :   {job.user:<14}Library . . . . . :   QGPL",
        " MSGID      TYPE                    SEV  DATE      TIME             FROM PGM",
    ]
    for when, kind, text in entries:
        label = "Command" if kind == "command" else "Information"
        lines.append(f" {'*NONE' if kind == 'command' else 'CPF9898':<10} {label:<24}"
                     f"{'' if kind == 'command' else '00':<5}{when:%y-%m-%d}  {when:%H:%M:%S},000000  QCMD")
        lines.append(f"                                      Message . . . . :   {mask(text, kind == 'command')}")
    number = job.number
    existing = [f.file_no for f in store.spool if f.job_number == number and f.job_name == job.name]
    f = SpoolFile("QPJOBLOG", job.user, job.name, number, (max(existing) + 1) if existing else 1,
                  "QEZJOBLOG", "QUSRSYS", job.name, "RDY", lines, now.isoformat(timespec="seconds"))
    store.spool.append(f)
    store.on_change()
    return f


def ensure_queues(store: ProfileStore) -> None:
    """A state file saved before output queues existed gets its two queues now."""
    from .authority import SecuredObject, USE
    for lib, name, text, dspdta in (("QUSRSYS", "QEZJOBLOG", "Job logs", "*OWNER"),
                                    ("QGPL", "QPRINT", "Default printer output", "*YES")):
        key = (lib, name, "*OUTQ")
        if key not in store.objects and (lib, "*LIB") and store.find_library(lib):
            store.objects[key] = SecuredObject(name, "QSYS", public=USE, library=lib, type="*OUTQ", text=text,
                                               data={"dspdta": dspdta, "oprctl": "*YES", "autchk": "*OWNER"})
