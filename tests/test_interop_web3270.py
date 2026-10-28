"""Silverlake against web3270's tn5250 client, an implementation we did not
write for this project and that has been debugged against a real IBM i. Skipped
when node or web3270 is not around."""

import asyncio
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from silverlake.net import server as srv
from silverlake.screens.signon import SignonController

HERE = Path(__file__).parent
WEB3270 = Path(os.environ.get("SILVERLAKE_WEB3270", HERE.parent.parent / "web3270"))
SESSION_JS = WEB3270 / "Bridge_server" / "tn5250" / "session.js"

pytestmark = pytest.mark.skipif(
    not shutil.which("node") or not SESSION_JS.exists(),
    reason="needs node and a web3270 checkout (set SILVERLAKE_WEB3270)",
)


def run_client(devname=None):
    async def go():
        server = await srv.serve("127.0.0.1", 0, SignonController)
        port = server.sockets[0].getsockname()[1]
        try:
            args = ["node", str(HERE / "interop" / "web3270_client.mjs"), str(port)]
            if devname:
                args.append(devname)
            proc = await asyncio.to_thread(
                subprocess.run, args, cwd=WEB3270 / "Bridge_server",
                capture_output=True, text=True, timeout=30,
            )
        finally:
            server.close()
            await server.wait_closed()
        assert proc.returncode == 0, proc.stderr
        return json.loads(proc.stdout.strip().splitlines()[-1])
    return asyncio.run(go())


def test_real_client_signs_on_and_round_trips():
    out = run_client()
    first, second = out["first"], out["second"]

    assert any("Sign On" in line for line in first["text"])
    assert any("QPADEV0001" in line for line in first["text"])

    # five input fields, at the columns and lengths we drew, password hidden
    assert [(f["row"], f["col"], f["length"], f["nondisplay"]) for f in first["inputs"]] == [
        (5, 52, 10, False), (6, 52, 10, True), (7, 52, 10, False),
        (8, 52, 10, False), (9, 52, 10, False),
    ]
    assert first["cursor"] == [5, 52]

    # the client sent exactly what was typed, at the field addresses
    assert [f["data"] for f in out["sent"]] == ["tester", "secret"]

    assert any("TESTER" in line for line in second["text"])
    assert any("CPF1120" in line for line in second["text"])
    assert not any("secret" in line.lower() for line in second["text"])


def test_real_client_device_name_reaches_the_screen():
    out = run_client(devname="MYTERM01")
    assert any("MYTERM01" in line for line in out["first"]["text"])
