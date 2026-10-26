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


def expand(value: str) -> str:
    def sub(m: re.Match) -> str:
        name = m.group(1)
        if name not in os.environ:
            raise CaptureError(f"scenario needs environment variable {name}")
        return os.environ[name]
    return re.sub(r"\$\{(\w+)\}", sub, value)


async def run_scenario(host: str, port: int, name: str, devname: str | None = None,
                       timeout: float = 15.0) -> dict:
    if name not in SCENARIOS:
        raise CaptureError(f"unknown scenario {name!r}, have: {', '.join(sorted(SCENARIOS))}")
    client = Client(host, port, devname)
    await client.connect()
    captures: list[Capture] = []
    try:
        captures.append(await client.wait_screen(timeout))
        for action in SCENARIOS[name]:
            fill = {int(k): expand(v) for k, v in action.get("fill", {}).items()}
            client.send_aid(action["key"], fill)
            captures.append(await client.wait_screen(timeout))
    finally:
        await client.close()
    return {
        "target": f"{host}:{port}",
        "scenario": name,
        "captured_at": datetime.now(UTC).isoformat(timespec="seconds"),
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
