"""File overrides: OVRDBF and DLTOVR.

An override tells the job that a program opening file X should get file Y instead. It is checked when the
file is opened, not when the override is made, so OVRDBF itself needs no authority and cannot fail on a
file that is not there. What the open then checks is the authority of whoever the call stack holds, which
is the whole point for the range: a program that adopts its owner opens the file the *caller* chose with
the *owner's* authority.

From IBM's OVRDBF page, found on the web and not read on a real system: TOFILE names the replacement,
OVRSCOPE is *ACTGRPDFN, *CALLLVL or *JOB, and SECURE(*YES) protects an override from being replaced by
later overrides at lower call levels.

Simplifications, on purpose: this job has one call level for overrides, so every OVRSCOPE acts as *JOB, and
a later override of the same file replaces an earlier one unless the earlier one is secure, in which case it
is ignored. That is also how a program defends itself: it overrides its own file, securely, before it opens
it, and nothing the caller did survives. MBR is accepted and ignored (a file has one member here)."""

from __future__ import annotations


def apply(session, file: str, to: str, secure: bool) -> None:
    """OVRDBF. `to` is "*FILE" (the override only sets options) or "LIB/NAME" or "NAME"."""
    old = session.overrides.get(file)
    if old is not None and old["secure"]:
        return                                             # secured: later overrides are ignored
    session.overrides[file] = {"to": to, "secure": secure}


def delete(session, file: str) -> None:
    """DLTOVR. A secured override stays until the job ends or it is deleted by name, which a program can
    do too, so *ALL does not skip it."""
    if file == "*ALL":
        session.overrides.clear()
    else:
        session.overrides.pop(file, None)


def target(session, file: str) -> str:
    """The file a program that opens `file` gets: the override's, or the file itself."""
    ov = session.overrides.get(file)
    return file if ov is None or ov["to"] == "*FILE" else ov["to"]
