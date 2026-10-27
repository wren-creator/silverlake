"""Scenarios: what to do on a host, and the capture format.

A scenario is a list of actions. The harness first waits for the host's opening
screen, then for each action presses a key (typing into fields first) and waits
for the next screen. Every screen waited on is snapshotted, so a scenario with
N actions yields N + 1 snapshots.

Field values may use ${NAME} to read an environment variable, so a scenario can
sign on with a real profile without the password ever being written into the
repo. Scenarios that fail a sign-on use a made-up user, never a real one, so a
real profile never racks up failed attempts.
"""

import asyncio
import ipaddress
import os
import random
import re
import time
from datetime import UTC, datetime
from pathlib import Path

from .client import Capture, CaptureError, Client

SCENARIOS: dict[str, list[dict]] = {
    # The opening screen, nothing typed.
    "signon": [],
    # A user that does not exist, so no real profile counts a failed attempt.
    "signon-unknown-user": [
        {"fill": {"0": "SLNOUSR1", "1": "notarealpw1"}, "key": "ENTER"},
    ],
}

# Scenarios that sign on as a real (test) profile. The user and password come
# from the environment, never from a file, and a password is never sent over a
# cleartext connection to anything but loopback. Every scenario ends by typing
# SIGNOFF, so the job does not linger on a shared system. F3 on the real MAIN
# menu does not sign off (the first run on PUB400 showed that).
USER_ENV, PASS_ENV = "SILVERLAKE_ORACLE_USER", "SILVERLAKE_ORACLE_PASS"
# A scenario that creates something names it ${SILVERLAKE_ORACLE_TESTLIB}. The harness
# makes a fresh random name for every run and overrides any value from the environment,
# so a delete can only ever target a library this run created.
TESTLIB_ENV = "SILVERLAKE_ORACLE_TESTLIB"
_SIGNON = {"fill": {"0": "${%s}" % USER_ENV, "1": "${%s}" % PASS_ENV}, "key": "ENTER"}


_SIGNOFF = {"fill": {"0": "SIGNOFF"}, "key": "ENTER"}


def _cmd(line: str) -> list[dict]:
    """Run one command from the menu's command line, then F3 back."""
    return [{"fill": {"0": line}, "key": "ENTER"}, {"key": "F3"}]


_TESTLIB = "${%s}" % TESTLIB_ENV

AUTHENTICATED: dict[str, list[dict]] = {
    # Sign on, look at the first screen, sign off. Run this before any other.
    "auth-probe": [_SIGNON, _SIGNOFF],
    # Read-only questions about libraries and authority.
    "auth-libs": [_SIGNON, *_cmd("DSPLIBL"), *_cmd("DSPOBJAUT OBJ(QSYS) OBJTYPE(*LIB)"),
                  *_cmd("DSPOBJAUT OBJ(QGPL) OBJTYPE(*LIB)"), _SIGNOFF],
    # Read-only questions about finding objects and authorization lists. The two last ones
    # are expected to be refused, and the refusal wording is what is being collected.
    "auth-objects": [_SIGNON, *_cmd("WRKOBJ OBJ(QSYS/QGPL) OBJTYPE(*LIB)"),
                     *_cmd("WRKOBJ OBJ(QSYS/QSYS*) OBJTYPE(*LIB)"),
                     *_cmd("WRKOBJOWN USRPRF(*CURRENT) OBJTYPE(*LIB)"),
                     *_cmd("WRKOBJ OBJ(SLNOSUCH/*ALL)"),
                     *_cmd("WRKAUTL AUTL(*ALL)"), *_cmd("DSPAUTL AUTL(QPWFSERVER)"),
                     *_cmd("WRKOBJOWN USRPRF(QSYS)"), _SIGNOFF],
}
# The only scenario that changes the host. Creates a throwaway library, looks at the
# authority a new library gets, deletes it, and signs off. Delete and display only
# run if the host said the library was created.
AUTHENTICATED["auth-crtlib"] = [
    _SIGNON,
    {"fill": {"0": f"CRTLIB LIB({_TESTLIB}) TEXT('Silverlake oracle test, deleted at once')"}, "key": "ENTER",
     "proceed_if": [_TESTLIB, "created"]},
    *_cmd(f"DSPOBJAUT OBJ({_TESTLIB}) OBJTYPE(*LIB)"),
    {"fill": {"0": f"DLTLIB LIB({_TESTLIB})"}, "key": "ENTER"},
    {**_SIGNOFF, "always": True},
]
SCENARIOS.update(AUTHENTICATED)

MIN_REMOTE_INTERVAL = 10.0  # seconds between connections to the same remote host
ALLOW_ENV = "SILVERLAKE_ORACLE_HOSTS"


def is_loopback(host: str) -> bool:
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return host == "localhost"


def check_target(host: str, state_dir: Path) -> None:
    """Loopback is always fine. Anything else must be named in
    SILVERLAKE_ORACLE_HOSTS, and is rate limited, so this tool cannot be
    pointed at a system by accident or in a loop."""
    if is_loopback(host):
        return
    allowed = {h.strip().lower() for h in os.environ.get(ALLOW_ENV, "").split(",") if h.strip()}
    if host.lower() not in allowed:
        raise CaptureError(
            f"{host} is not allowlisted. Set {ALLOW_ENV}={host} to capture from it deliberately.")
    state_dir.mkdir(parents=True, exist_ok=True)
    stamp = state_dir / f".oracle-last-{re.sub(r'[^a-z0-9.-]', '_', host.lower())}"
    now = time.time()
    if stamp.exists():
        wait = MIN_REMOTE_INTERVAL - (now - float(stamp.read_text() or 0))
        if wait > 0:
            raise CaptureError(f"last connection to {host} was moments ago, wait {wait:.0f}s")
    stamp.write_text(str(now))


def _not_signed_on(snapshot: dict) -> bool:
    """Still at a password prompt, or the host answered with a message ID. Either
    way the next action is not safe to send, so the run stops. Stopping is the
    cautious side: a legitimate screen with a message ID ends the run early."""
    return bool(snapshot["message_ids"]) or any(f["hidden"] for f in snapshot["fields"])


def expand(value: str) -> str:
    def sub(m: re.Match) -> str:
        name = m.group(1)
        if name not in os.environ:
            raise CaptureError(f"scenario needs environment variable {name}")
        return os.environ[name]
    return re.sub(r"\$\{(\w+)\}", sub, value)


async def run_scenario(host: str, port: int, name: str, devname: str | None = None,
                       timeout: float = 15.0, tls: bool = False) -> dict:
    if name not in SCENARIOS:
        raise CaptureError(f"unknown scenario {name!r}, have: {', '.join(sorted(SCENARIOS))}")
    if name in AUTHENTICATED and not tls and not is_loopback(host):
        raise CaptureError(f"{name} sends a password. Use TLS (--tls) for anything but loopback.")
    # Resolve every value before connecting, so a missing variable cannot leave
    # a half finished session on someone else's system.
    os.environ[TESTLIB_ENV] = "SLT" + "".join(random.choices("0123456789", k=5))
    actions = [({int(k): expand(v) for k, v in a.get("fill", {}).items()}, a["key"],
                [expand(t).lower() for t in a.get("proceed_if", [])], bool(a.get("always")))
               for a in SCENARIOS[name]]
    client = Client(host, port, devname, tls=tls)
    await client.connect()
    captures: list[Capture] = []
    skipped: list[int] = []
    try:
        captures.append(await client.wait_screen(timeout))
        skipping = False
        for i, (fill, key, proceed_if, always) in enumerate(actions):
            if skipping and not always:
                skipped.append(i)
                continue
            client.send_aid(key, fill)
            captures.append(await client.wait_screen(timeout))
            if proceed_if:
                seen = " ".join(r["text"] for r in captures[-1].snapshot["runs"]).lower()
                if not all(t in seen for t in proceed_if):
                    skipping = True       # the host did not do what we asked: ask nothing more, just sign off
            if name in AUTHENTICATED and i == 0 and _not_signed_on(captures[-1].snapshot):
                # One attempt only. Never retype a password the host refused, and
                # do not type commands into a screen we did not expect.
                ids = ", ".join(captures[-1].snapshot["message_ids"]) or "none"
                raise CaptureError(f"did not get past sign-on, stopping (message IDs: {ids}). "
                                   "Nothing further was sent.")
    finally:
        await client.close()
    return {
        "target": f"{host}:{port}",
        "scenario": name,
        "captured_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "testlib": os.environ.get(TESTLIB_ENV) if "TESTLIB" in repr(SCENARIOS[name]) else None,
        "skipped_actions": skipped,
        "snapshots": [c.snapshot for c in captures],
        "error_lines": [c.error_line for c in captures],
        # Raw host records, hex. Local only: this is the real system's wording.
        "records_hex": [[r.hex() for r in c.records] for c in captures],
    }


def reanalyze(cap: dict) -> dict:
    """Rebuild a capture's snapshots from its raw records, so a capture taken
    before the decoder learned something new is still comparable. Records for
    one screen are applied in order on a terminal that carries state across
    screens, as a real one does. Captures without raw records keep what they
    have."""
    from ..proto import datastream as ds
    from .terminal import Terminal

    if not cap.get("records_hex"):
        return cap
    term = Terminal()
    snaps, errors = [], []
    for records in cap["records_hex"]:
        term.error_line = ""
        for rec in records:
            term.apply(ds.split_gds(bytes.fromhex(rec))[1])
        snaps.append(term.snapshot())
        errors.append(term.error_line)
    return {**cap, "snapshots": snaps, "error_lines": errors}


def run(host: str, port: int, name: str, **kw) -> dict:
    return asyncio.run(run_scenario(host, port, name, **kw))
