"""Job control: HLDJOB, RLSJOB, ENDJOB, CHGJOB.

Rules, from IBM's 7.5 command pages (read, quoted from the pages themselves):
  HLDJOB, RLSJOB, ENDJOB  the issuer runs under the same user profile as the job's user identity,
                          or holds *JOBCTL. ENDJOB enforces that "even when ending the current job".
  CHGJOB                  the same, or the command is issued from the job being changed. Changing
                          RUNPTY, TIMESLICE, PURGE, DFTWAIT, TSEPOOL, WLCGRP, CPUTIME, MAXTMPSTG or
                          PRCRSCPTY needs *JOBCTL. Nothing on any of the four pages involves *SPLCTL.
Inferred, not read on a page: which condition raises each message below (the IDs are listed there),
that a refused JOBCTL-only change uses CPF1337 (that part of CHGJOB's page came through only as a
summary), that a subsystem monitor is "not a valid job type" for these commands, and that ending a
seeded system job just removes it until the next restart. Priorities and limits are stored and
shown, and change nothing: there is no scheduler."""

from . import messages
from .authority import SpecialAuthority
from .jobs import Job
from .objects import Done, _no, _ok
from .profiles import Profile, ProfileStore

SA = SpecialAuthority
JOBCTL_ONLY = ("RUNPTY", "TIMESLICE", "PURGE", "DFTWAIT", "CPUTIME", "MAXTMPSTG")
_LIMITS = {"JOBPTY": (0, 9), "OUTPTY": (1, 9), "RUNPTY": (1, 99), "TIMESLICE": (1, 9999999),
           "DFTWAIT": (1, 9999999), "CPUTIME": (1, 9999999), "MAXTMPSTG": (1, 2147483647)}


def _doc(id_: str, text: str) -> messages.Message:
    return messages.Message(id_, text, messages.DOCUMENTED)


def can_control(store: ProfileStore, actor: Profile, job: Job) -> bool:
    return actor.name == job.user or SA.JOBCTL in store.special_authorities(actor)


def find(store: ProfileStore, spec: tuple, current: Job | None, allow_current: bool):
    """JOB(name/user/number) with * parts, or JOB(*) for the issuer's own job."""
    if spec == "*":
        if current is None or not allow_current:
            return None, _doc("CPF1342", "Current job not allowed as job name on this command.")
        return current, None
    name, user, number = spec
    hits = [j for j in store.jobs.jobs if j.name == name and user in ("*", j.user) and number in ("*", j.number)]
    if not hits:
        return None, _doc("CPF1321", f"Job {name} user {user} job number {number} not found.")
    if len(hits) > 1:
        return None, messages.syntax(f"More than one job named {name}. Give the job as number/user/name.")
    job = hits[0]
    if job.type == "SBS":
        return None, _doc("CPF1343", f"Job {job.qualified} not valid job type for function.")
    return job, None


def _refuse(job: Job) -> Done:
    return _no(_doc("CPF1344", f"Not authorized to control job {job.qualified}."))


def hold(store: ProfileStore, actor: Profile, job: Job) -> Done:
    if not can_control(store, actor, job):
        return _refuse(job)
    if job.status == "HLD":
        return _no(_doc("CPF1346", f"Job {job.qualified} already held."))
    job.held_from, job.status = job.status, "HLD"
    return _ok(f"Job {job.qualified} held.")


def release(store: ProfileStore, actor: Profile, job: Job) -> Done:
    if not can_control(store, actor, job):
        return _refuse(job)
    if job.status != "HLD":
        return _no(_doc("CPF1349", f"Job {job.qualified} not released, the job is not held."))
    job.status, job.held_from = job.held_from or "DEQW", ""
    return _ok(f"Job {job.qualified} released.")


def end(store: ProfileStore, actor: Profile, job: Job) -> Done:
    if not can_control(store, actor, job):
        return _refuse(job)
    store.jobs.end(job)
    return _ok(f"Job {job.qualified} ended.")


def change(store: ProfileStore, actor: Profile, job: Job, changes: dict, own_job: bool) -> Done:
    """`changes` maps attribute to a value other than *SAME. The first problem stops everything,
    so a refused change leaves the job as it was."""
    if not (own_job or can_control(store, actor, job)):
        return _refuse(job)
    held = SA.JOBCTL in store.special_authorities(actor)
    clean = {}
    for key, value in changes.items():
        if key in JOBCTL_ONLY and not held:
            return _no(_doc("CPF1337", f"{job.qualified} not authorized to change parameters."))
        if key == "PURGE":
            if value not in ("*YES", "*NO"):
                return _no(messages.syntax("Value for parameter PURGE not valid. Use *YES or *NO."))
        elif key in _LIMITS:
            low, high = _LIMITS[key]
            if value == "*NOMAX" and key in ("DFTWAIT", "CPUTIME", "MAXTMPSTG"):
                pass
            elif not (value.isdigit() and low <= int(value) <= high):
                return _no(messages.syntax(f"Value for parameter {key} not valid. Use {low} to {high}"
                                           + (" or *NOMAX." if key in ("DFTWAIT", "CPUTIME", "MAXTMPSTG") else ".")))
        clean[key] = value
    job.attrs.update(clean)
    return _ok(f"Job {job.qualified} changed.")


# -- DSPJOBLOG and WRKJOB ---------------------------------------------------------------------------
#
# Rules, from IBM's 7.5 pages (quoted):
#   DSPJOBLOG  *JOBCTL, or the job has the same user name as the issuer. And: "To display a job log
#              for a job that has all object (*ALLOBJ) special authority, you must have *ALLOBJ
#              special authority" (or the QIBM_ACCESS_ALLOBJ_JOBLOG function usage, not modeled).
#              The refusal is CPF2441, "Not authorized to display job log." CPF1070 is not found.
#   WRKJOB     the same-user-or-*JOBCTL rule as HLDJOB. The refusal is CPF1071, "No authority to job".
# Nothing on those pages mentions *SPLCTL. Inferred: that a job that has ended (its log already a
# spool file) is CPF2443 here and is read with DSPSPLF, and that a seeded system job has no log.

def log_lines(job: Job) -> list[str]:
    """The live job log as the real display shows it (captured): each command as `3>> COMMAND`
    and the message it raised as plain text."""
    from .spool import mask
    out: list[str] = []
    for _when, kind, text in job.log:
        out.append(("3>> " + mask(text)) if kind == "command" else text)
    return out


def display_log(store: ProfileStore, actor: Profile, spec, current: Job | None):
    if spec == "*":
        job = current
        if job is None:
            return None, _doc("CPF1070", "Job not found.")
    else:
        name, user, number = spec
        hits = [j for j in store.jobs.jobs if j.name == name and user in ("*", j.user) and number in ("*", j.number)]
        if not hits:
            ended = [f for f in store.spool if f.name == "QPJOBLOG" and f.job_name == name
                     and user in ("*", f.user) and number in ("*", f.job_number)]
            if ended:
                return None, _doc("CPF2443", "Job log not displayed or listed because job has ended.")
            return None, _doc("CPF1070", f"Job {number}/{user}/{name} not found.")
        if len(hits) > 1:
            return None, messages.syntax(f"More than one job named {name}. Give the job as number/user/name.")
        job = hits[0]
    held = store.special_authorities(actor)
    if actor.name != job.user and SA.JOBCTL not in held:
        return None, _doc("CPF2441", "Not authorized to display job log.")
    owner = store.profiles.get(job.user)
    if owner is not None and SA.ALLOBJ in store.special_authorities(owner) and SA.ALLOBJ not in held \
            and actor.name != job.user:
        return None, _doc("CPF2441", "Not authorized to display job log.")
    if job.type == "SBS" or (not job.log and job.type != "INT"):
        return None, _doc("CPF2523", "No job log information.")
    return job, None


def work_with(store: ProfileStore, actor: Profile, spec, current: Job | None):
    if spec == "*":
        if current is None:
            return None, _doc("CPF1070", "Job not found.")
        return current, None
    name, user, number = spec
    hits = [j for j in store.jobs.jobs if j.name == name and user in ("*", j.user) and number in ("*", j.number)]
    if not hits:
        return None, _doc("CPF1070", f"Job {number}/{user}/{name} not found.")
    if len(hits) > 1:
        return None, messages.syntax(f"More than one job named {name}. Give the job as number/user/name.")
    job = hits[0]
    if not can_control(store, actor, job):
        return None, _doc("CPF1071", f"No authority to job {job.qualified}.")
    return job, None
