import asyncio
import json
import os
from pathlib import Path

import pytest

from silverlake.net import server as srv
from silverlake.oracle import scenario
from silverlake.oracle.client import CaptureError
from silverlake.oracle.diff import diff_captures, diff_snapshots
from silverlake.oracle.terminal import DecodeError, Terminal
from silverlake.proto import datastream as ds
from silverlake.proto import ebcdic
from silverlake.screens.model import Input, Screen, Text
from silverlake.screens.render import render
from silverlake.screens.signon import SignonController, signon_screen


def decode(screen: Screen) -> dict:
    t = Terminal()
    t.apply(render(screen))
    return t.snapshot()


# -- terminal: encoder and decoder agree ---------------------------------------

def test_render_then_decode_recovers_the_screen():
    snap = decode(Screen([
        Text(1, 30, "Title", ds.ATTR_WHITE),
        Input(5, 20, 8, "a"),
        Input(6, 20, 12, "b", hidden=True),
    ], cursor="b"))
    assert [(f["row"], f["col"], f["length"], f["hidden"]) for f in snap["fields"]] == [
        (5, 20, 8, False), (6, 20, 12, True)]
    assert snap["cursor"] == [6, 20]
    assert snap["runs"][0] == {"row": 1, "col": 30, "attr": "0x22", "length": 5, "text": "Title"}


def test_cursor_homes_to_first_input_without_ic():
    t = Terminal()
    sf = bytes([ds.ESC, ds.CMD_WRITE_TO_DISPLAY, 0, 0, ds.ORDER_SBA, 3, 10, ds.ORDER_SF, 0x40, 0x00, 0x24, 0, 6])
    t.apply(sf)
    assert t.snapshot()["cursor"] == [2, 10]


def test_bare_attribute_after_start_of_field_keeps_the_field():
    """A real host re-writes a field's attribute cell as a bare attribute.
    That used to erase the field."""
    t = Terminal()
    t.apply(bytes([
        ds.ESC, ds.CMD_WRITE_TO_DISPLAY, 0, 0,
        ds.ORDER_SBA, 6, 24, ds.ORDER_SF, 0x40, 0x00, 0x27, 0x00, 0x80,
        ds.ORDER_SBA, 6, 24, 0x27,
    ]))
    [f] = t.snapshot()["fields"]
    assert (f["row"], f["col"], f["length"], f["hidden"]) == (5, 24, 128, True)


def test_clear_unit_resets_and_alternate_screen_is_27x132():
    t = Terminal()
    t.apply(render(signon_screen("D")))
    t.apply(bytes([ds.ESC, ds.CMD_CLEAR_UNIT]))
    assert t.snapshot()["fields"] == []
    t.apply(bytes([ds.ESC, 0x20, 0x00]))
    assert (t.rows, t.cols) == (27, 132)


def test_read_and_query_events():
    t = Terminal()
    assert [e.kind for e in t.apply(bytes([ds.ESC, ds.CMD_READ_MDT_FIELDS, 0, 0]))] == ["read"]
    wsf = bytes([ds.ESC, 0xF3, 0x00, 0x05, 0xD9, 0x70, 0x00])
    assert [e.kind for e in t.apply(wsf)] == ["query"]


def test_message_ids_are_extracted():
    snap = decode(Screen([Text(20, 2, "CPF1107 - Password not correct. Also MCH1210 and SQL0204.")]))
    assert snap["message_ids"] == ["CPF1107", "MCH1210", "SQL0204"]


@pytest.mark.parametrize("bad", [
    bytes([0x11, 1, 1]),                                             # not an ESC command
    bytes([ds.ESC]),                                                 # ESC at the end
    bytes([ds.ESC, ds.CMD_WRITE_TO_DISPLAY, 0, 0, ds.ORDER_SBA, 99, 1]),  # off the screen
])
def test_malformed_streams_raise(bad):
    with pytest.raises(DecodeError):
        Terminal().apply(bad)


# -- a real host record, when web3270's fixture is next door ---------------------

FIXTURE = Path(os.environ.get("SILVERLAKE_WEB3270", Path(__file__).parents[2] / "web3270")) \
    / "Bridge_server/features/fixtures/ibmi-pub400-23-signon-record.hex"


@pytest.mark.skipif(not FIXTURE.exists(), reason="needs a web3270 checkout")
def test_real_ibmi_signon_record_structure():
    """Structure only. The record is not copied into this repo."""
    t = Terminal()
    t.apply(ds.split_gds(bytes.fromhex(FIXTURE.read_text().strip()))[1])
    snap = t.snapshot()
    user, pw = snap["fields"]
    assert (user["row"], user["col"], user["length"], user["hidden"]) == (4, 24, 10, False)
    assert (pw["row"], pw["col"], pw["length"], pw["hidden"]) == (5, 24, 128, True)
    assert snap["cursor"] == [4, 24]
    assert snap["geometry"] == [24, 80]


# -- diff ---------------------------------------------------------------------------

def test_identical_screens_have_no_diff():
    s = decode(signon_screen("QPADEV0001"))
    assert diff_snapshots(s, s) == []


def test_diff_reports_field_and_cursor_differences():
    a = decode(Screen([Input(5, 20, 10, "a")]))
    b = decode(Screen([Input(5, 20, 50, "a", hidden=True), Input(6, 20, 3, "b")]))
    out = diff_snapshots(a, b)
    assert "input fields: 1 != 2" in out
    assert "field[0].length: 10 != 50" in out
    assert "field[0].hidden: False != True" in out
    assert "field[0].attr: 0x24 != 0x27" in out


def test_wording_differs_only_when_asked():
    a = decode(Screen([Text(2, 5, "Hello there")]))
    b = decode(Screen([Text(2, 5, "Howdy folks!")]))
    assert diff_snapshots(a, b) == []
    assert any("text at row=2" in d for d in diff_snapshots(a, b, text=True))


def test_diff_flags_a_run_in_a_different_attribute_or_place():
    a = decode(Screen([Text(2, 5, "x", ds.ATTR_WHITE)]))
    b = decode(Screen([Text(2, 6, "x", ds.ATTR_WHITE)]))
    assert any(d.startswith("run only in A") for d in diff_snapshots(a, b))
    assert any(d.startswith("run only in B") for d in diff_snapshots(a, b))


def test_fields_only_ignores_runs():
    a = decode(Screen([Text(2, 5, "x"), Input(5, 20, 4, "a")]))
    b = decode(Screen([Text(9, 5, "x"), Input(5, 20, 4, "a")]))
    assert diff_snapshots(a, b)
    assert diff_snapshots(a, b, fields_only=True) == []


def test_diff_captures_prefixes_screen_index_and_counts_screens():
    s1, s2 = decode(Screen([Input(1, 5, 3, "a")])), decode(Screen([Input(1, 5, 4, "a")]))
    out = diff_captures({"snapshots": [s1, s1]}, {"snapshots": [s1, s2, s1]})
    assert "screens: 2 != 3" in out
    assert "screen 1: field[0].length: 3 != 4" in out


# -- scenarios and the remote guard ------------------------------------------------

def test_remote_host_needs_the_allowlist(tmp_path, monkeypatch):
    monkeypatch.delenv(scenario.ALLOW_ENV, raising=False)
    with pytest.raises(CaptureError, match="not allowlisted"):
        scenario.check_target("pub400.com", tmp_path)
    scenario.check_target("127.0.0.1", tmp_path)  # loopback is always fine


def test_remote_host_is_rate_limited(tmp_path, monkeypatch):
    monkeypatch.setenv(scenario.ALLOW_ENV, "pub400.com, other.example")
    scenario.check_target("PUB400.com", tmp_path)
    with pytest.raises(CaptureError, match="moments ago"):
        scenario.check_target("pub400.com", tmp_path)


def test_env_expansion(monkeypatch):
    monkeypatch.setenv("SL_X", "abc")
    assert scenario.expand("pre-${SL_X}-post") == "pre-abc-post"
    monkeypatch.delenv("SL_X")
    with pytest.raises(CaptureError, match="SL_X"):
        scenario.expand("${SL_X}")


def test_unknown_scenario():
    with pytest.raises(CaptureError):
        asyncio.run(scenario.run_scenario("127.0.0.1", 1, "nope"))


# -- the whole loop against a live Silverlake ---------------------------------------

def capture_local(name):
    async def go():
        server = await srv.serve("127.0.0.1", 0, SignonController)
        try:
            return await scenario.run_scenario("127.0.0.1", server.sockets[0].getsockname()[1], name)
        finally:
            server.close()
            await server.wait_closed()
    return asyncio.run(go())


def test_capture_signon_from_live_silverlake():
    cap = capture_local("signon")
    assert len(cap["snapshots"]) == 1
    snap = cap["snapshots"][0]
    assert len(snap["fields"]) == 5
    assert snap["cursor"] == [5, 52]
    assert cap["records_hex"][0], "raw records are kept for local inspection"
    json.dumps(cap)  # serializable


def test_capture_unknown_user_scenario_takes_two_screens():
    cap = capture_local("signon-unknown-user")
    assert len(cap["snapshots"]) == 2
    text = " ".join(r["text"] for r in cap["snapshots"][1]["runs"])
    assert "SLNOUSR1" in text


def test_local_against_itself_has_no_structural_diff():
    a, b = capture_local("signon"), capture_local("signon")
    assert diff_captures(a, b) == []


def test_query_is_answered_and_screen_still_arrives():
    """A host that sends a Query before its screen must get a reply."""
    sent = []

    async def go():
        async def host(reader, writer):
            from silverlake.proto import telnet as tn
            for opt in (tn.OPT_TTYPE, tn.OPT_BINARY, tn.OPT_EOR):
                writer.write(tn.command(tn.DO, opt))
            writer.write(tn.command(tn.WILL, tn.OPT_BINARY) + tn.command(tn.WILL, tn.OPT_EOR))
            query = bytes([ds.ESC, 0xF3, 0x00, 0x05, 0xD9, 0x70, 0x00])
            writer.write(tn.record(ds.gds_record(query, ds.OPCODE_NO_OP)))
            writer.write(tn.record(ds.gds_record(render(Screen([Input(2, 5, 4, "a")])))))
            await writer.drain()
            p = tn.Parser()
            while True:
                data = await reader.read(4096)
                if not data:
                    return
                sent.extend(p.feed(data))
        server = await asyncio.start_server(host, "127.0.0.1", 0)
        try:
            port = server.sockets[0].getsockname()[1]
            from silverlake.oracle.client import Client
            c = Client("127.0.0.1", port)
            await c.connect()
            cap = await c.wait_screen(5)
            await asyncio.sleep(0.1)
            await c.close()
            return cap
        finally:
            server.close()
            await server.wait_closed()

    cap = asyncio.run(go())
    assert cap.snapshot["fields"][0]["length"] == 4
    # cursor 0,0 then AID 0x88, the inbound structured field marker
    replies = [e for e in sent if hasattr(e, "data") and ds.split_gds(e.data)[1][:3] == bytes([0, 0, 0x88])]
    assert replies, "client did not answer the Query"
    assert ebcdic.encode("3179") in replies[0].data


# -- re-deriving snapshots from raw records ----------------------------------------

def test_reanalyze_rebuilds_snapshots_from_records():
    cap = capture_local("signon-unknown-user")
    stale = {**cap, "snapshots": [{"stale": True}, {"stale": True}]}
    fresh = scenario.reanalyze(stale)
    assert fresh["snapshots"] == cap["snapshots"]
    assert len(fresh["error_lines"]) == 2


def test_reanalyze_leaves_captures_without_records_alone():
    cap = {"snapshots": [{"x": 1}]}
    assert scenario.reanalyze(cap) == cap


def test_diff_survives_a_snapshot_missing_a_newer_key():
    a = decode(Screen([Input(5, 20, 10, "a")]))
    old = json.loads(json.dumps(a))
    del old["fields"][0]["monocase"]
    assert any("monocase" in d for d in diff_snapshots(old, a)) is True


# -- authenticated scenarios and TLS --------------------------------------------------------------

import asyncio as _asyncio  # noqa: E402
import ssl as _ssl  # noqa: E402

from silverlake.net import server as _srv  # noqa: E402
from silverlake.screens.signon import SignonController as _Signon  # noqa: E402


def _run_local(name, user, password, monkeypatch):
    monkeypatch.setenv(scenario.USER_ENV, user)
    monkeypatch.setenv(scenario.PASS_ENV, password)

    async def go():
        server = await _srv.serve("127.0.0.1", 0, _Signon)
        try:
            port = server.sockets[0].getsockname()[1]
            return await scenario.run_scenario("127.0.0.1", port, name)
        finally:
            server.close()
            await server.wait_closed()
    return _asyncio.run(go())


def test_auth_probe_signs_on_then_off_against_local_silverlake(monkeypatch):
    cap = _run_local("auth-probe", "STUDENT", "STUDENT", monkeypatch)
    assert len(cap["snapshots"]) == 3
    text = lambda i: " ".join(r["text"] for r in cap["snapshots"][i]["runs"])  # noqa: E731
    assert "Sign On" in text(0) and "Selection or command" in text(1) and "Sign On" in text(2)


def test_auth_libs_runs_every_command_and_returns_to_the_menu(monkeypatch):
    cap = _run_local("auth-libs", "STUDENT", "STUDENT", monkeypatch)
    text = lambda i: " ".join(r["text"] for r in cap["snapshots"][i]["runs"])  # noqa: E731
    assert len(cap["snapshots"]) == 9
    assert "Display Library List" in text(2) and "Display Object Authority" in text(4)
    assert "Display Object Authority" in text(6) and "Sign On" in text(8)
    assert all("Selection or command" in text(i) for i in (1, 3, 5, 7))


def test_a_refused_signon_stops_after_one_attempt(monkeypatch):
    with pytest.raises(scenario.CaptureError, match="did not get past sign-on"):
        _run_local("auth-libs", "STUDENT", "wrong-password", monkeypatch)


def test_a_refused_signon_sends_nothing_more(monkeypatch):
    sent = []
    real = scenario.Client.send_aid
    monkeypatch.setattr(scenario.Client, "send_aid", lambda self, key, fill=None: (sent.append(key), real(self, key, fill))[1])
    with pytest.raises(scenario.CaptureError):
        _run_local("auth-libs", "NOSUCH", "x", monkeypatch)
    assert sent == ["ENTER"]                      # the one sign-on attempt, and nothing after it


def test_a_missing_variable_fails_before_any_connection(monkeypatch):
    monkeypatch.delenv(scenario.USER_ENV, raising=False)
    monkeypatch.delenv(scenario.PASS_ENV, raising=False)
    # Port 1 on loopback has nothing listening. Reaching the connect would be a different error.
    with pytest.raises(scenario.CaptureError, match="environment variable"):
        _asyncio.run(scenario.run_scenario("127.0.0.1", 1, "auth-probe"))


def test_a_password_is_never_sent_in_cleartext_beyond_loopback(monkeypatch):
    monkeypatch.setenv(scenario.USER_ENV, "X")
    monkeypatch.setenv(scenario.PASS_ENV, "Y")
    with pytest.raises(scenario.CaptureError, match="Use TLS"):
        _asyncio.run(scenario.run_scenario("pub400.com", 23, "auth-probe"))


def _fills(name):
    return [a["fill"]["0"] for a in scenario.SCENARIOS[name] if "fill" in a and "1" not in a["fill"]]


def test_the_read_only_scenarios_only_read_and_never_leave_a_job():
    for name in scenario.AUTHENTICATED:
        assert scenario.SCENARIOS[name][-1]["fill"] == {"0": "SIGNOFF"}      # never leave a job behind
        assert scenario.SCENARIOS[name][0]["fill"]["1"] == "${SILVERLAKE_ORACLE_PASS}"   # no literal secret
        if name == "auth-crtlib":
            continue
        assert all(c.split()[0] in ("DSPLIBL", "DSPOBJAUT", "WRKOBJ", "WRKOBJOWN", "WRKAUTL", "DSPAUTL", "SIGNOFF") for c in _fills(name)), name


def test_the_one_scenario_that_changes_the_host_touches_only_its_own_library():
    cmds = _fills("auth-crtlib")
    changing = [c for c in cmds if c.split()[0] in ("CRTLIB", "DLTLIB")]
    assert [c.split()[0] for c in changing] == ["CRTLIB", "DLTLIB"]
    assert all("${SILVERLAKE_ORACLE_TESTLIB}" in c for c in cmds if c.split()[0] != "SIGNOFF")
    assert all(c.split()[0] in ("CRTLIB", "DSPOBJAUT", "DLTLIB", "SIGNOFF") for c in cmds)
    actions = scenario.SCENARIOS["auth-crtlib"]
    create = next(i for i, a in enumerate(actions) if a.get("fill", {}).get("0", "").startswith("CRTLIB"))
    delete = next(i for i, a in enumerate(actions) if a.get("fill", {}).get("0", "").startswith("DLTLIB"))
    assert actions[create]["proceed_if"] and create < delete                  # delete is gated on the create


def _run_shared(name, monkeypatch, store, extra_env=None):
    monkeypatch.setenv(scenario.USER_ENV, "STUDENT")
    monkeypatch.setenv(scenario.PASS_ENV, "STUDENT")
    for k, v in (extra_env or {}).items():
        monkeypatch.setenv(k, v)

    async def go():
        server = await _srv.serve("127.0.0.1", 0, lambda display: _Signon(display, store))
        try:
            return await scenario.run_scenario("127.0.0.1", server.sockets[0].getsockname()[1], name)
        finally:
            server.close()
            await server.wait_closed()
    return _asyncio.run(go())


def test_auth_crtlib_creates_looks_deletes_and_signs_off_locally(monkeypatch):
    from silverlake.system import profiles
    store = profiles.load()
    cap = _run_shared("auth-crtlib", monkeypatch, store)
    lib = cap["testlib"]
    assert lib.startswith("SLT") and len(lib) == 8 and cap["skipped_actions"] == []
    assert store.find_library(lib) is None                                   # created, then deleted
    text = lambda i: " ".join(r["text"] for r in cap["snapshots"][i]["runs"])  # noqa: E731
    assert f"Library {lib} created" in text(2) and "Display Object Authority" in text(3)
    assert f"Library {lib} deleted" in text(5) and "Sign On" in text(6)
    assert len(cap["snapshots"]) == 7


def test_the_test_library_name_cannot_be_chosen_from_outside(monkeypatch):
    from silverlake.system import profiles
    store = profiles.load()
    cap = _run_shared("auth-crtlib", monkeypatch, store, {scenario.TESTLIB_ENV: "APPLIB"})
    assert cap["testlib"] != "APPLIB" and store.find_library("APPLIB") is not None


def test_if_the_create_fails_nothing_is_displayed_or_deleted_and_the_job_signs_off(monkeypatch):
    from silverlake.system import profiles
    store = profiles.load()
    sent = []
    real = scenario.Client.send_aid
    monkeypatch.setattr(scenario.Client, "send_aid",
                        lambda self, key, fill=None: (sent.append(dict(fill or {})), real(self, key, fill))[1])
    # Make the create fail: the library already exists under every name the run could pick.
    monkeypatch.setattr(scenario.random, "choices", lambda *a, **k: list("00000"))
    from silverlake.system.authority import SecuredObject
    store.objects[("QSYS", "SLT00000", "*LIB")] = SecuredObject("SLT00000", "QSECOFR", public=profiles.EXCLUDE)
    cap = _run_shared("auth-crtlib", monkeypatch, store)
    commands = [f.get(0, "") for f in sent]
    assert any(c.startswith("CRTLIB") for c in commands)
    assert not any(c.startswith(("DLTLIB", "DSPOBJAUT")) for c in commands)
    assert commands[-1] == "SIGNOFF" and cap["skipped_actions"]
    assert store.find_library("SLT00000") is not None                          # someone else's, untouched
    assert "Sign On" in " ".join(r["text"] for r in cap["snapshots"][-1]["runs"])


def test_tls_uses_a_verifying_context_and_the_host_name(monkeypatch):
    from silverlake.oracle.client import Client
    seen = {}

    async def fake_open(host, port, ssl=None, server_hostname=None):
        seen.update(ssl=ssl, server_hostname=server_hostname)
        raise ConnectionRefusedError

    monkeypatch.setattr(_asyncio, "open_connection", fake_open)
    with pytest.raises(ConnectionRefusedError):
        _asyncio.run(Client("pub400.com", 992, tls=True).connect())
    assert seen["server_hostname"] == "pub400.com"
    assert seen["ssl"].verify_mode == _ssl.CERT_REQUIRED and seen["ssl"].check_hostname
    seen.clear()
    with pytest.raises(ConnectionRefusedError):
        _asyncio.run(Client("127.0.0.1", 23).connect())
    assert seen["ssl"] is None and seen["server_hostname"] is None
