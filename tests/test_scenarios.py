"""The scenario registry: every lesson loads, its vulnerable values are what the seed really holds, a lesson flips
both ways, the state is saved, and the command line behaves."""

import os

import pytest

from silverlake import scenarios
from silverlake.screens.model import Text
from silverlake.screens.signon import SignonController
from silverlake.system import profiles, state
from silverlake.system.authority import Auth

REG = scenarios.registry()


def norm(v):
    return sorted(v) if isinstance(v, list) and all(isinstance(x, str) for x in v) else v


@pytest.fixture
def store():
    return profiles.load()


def test_the_registry_loads_every_lesson_with_a_group_and_a_summary():
    assert len(REG) == 22
    for s in REG.values():
        assert s.group in scenarios.GROUPS and s.summary and s.title


@pytest.mark.parametrize("sid", list(REG))
def test_the_vulnerable_values_are_what_the_seed_holds(store, sid):
    for c in REG[sid].changes:
        assert norm(scenarios.get(store, c)) == norm(scenarios._value(c.vulnerable)), (c.target, c.field)


@pytest.mark.parametrize("sid", list(REG))
def test_a_lesson_flips_and_flips_back(store, sid):
    s = REG[sid]
    scenarios.apply(store, s, "secure")
    assert scenarios.current(store, sid) == "secure"
    for c in s.changes:
        assert norm(scenarios.get(store, c)) == norm(scenarios._value(c.secure)), (c.target, c.field)
    scenarios.apply(store, s, "vulnerable")
    for c in s.changes:
        assert norm(scenarios.get(store, c)) == norm(scenarios._value(c.vulnerable)), (c.target, c.field)


def test_a_bad_target_or_state_is_refused(store):
    with pytest.raises(scenarios.ScenarioError):
        scenarios.apply(store, REG["runcmd-qcmdexc"], "paranoid")
    bad = scenarios.Change("object:APPLIB/NOPE/*PGM", "owner", "A", "B")
    with pytest.raises(scenarios.ScenarioError):
        scenarios.put(store, bad, "A")


def test_the_state_of_each_lesson_is_saved_with_the_rest(tmp_path):
    st, db = state.open_store(None, tmp_path)
    scenarios.apply(st, REG["empdir-override"], "secure")
    st.on_change()
    db.close()
    st2, db2 = state.open_store(None, tmp_path)
    assert scenarios.current(st2, "empdir-override") == "secure" and scenarios.current(st2, "runcmd-qcmdexc") == "vulnerable"
    assert st2.objects[("APPLIB", "EMPDIR", "*PGM")].owner == "QDFTOWN"
    db2.close()


def test_mode_flips_every_lesson_and_names_the_range(store):
    scenarios.set_mode(store, "secure")
    assert store.system.mode == "secure" and all(scenarios.current(store, s) == "secure" for s in REG)
    scenarios.set_mode(store, "vulnerable")
    assert store.system.mode == "vulnerable" and store.profiles["OPERATOR"].password == "OPERATOR"


def text(s):
    return " | ".join(f.text for f in s.fields if isinstance(f, Text))


def signed(store, user="STUDENT", dev="QPADEV0171"):
    c = SignonController(dev, store)
    c.handle("ENTER", {"user": user, "password": user})
    return c


def test_secure_default_passwords_close_the_guess_and_leave_the_student_account(store):
    scenarios.apply(store, REG["default-passwords"], "secure")
    assert store.check_signon("OPERATOR", "OPERATOR").profile is None
    assert store.check_signon("STUDENT", "STUDENT").profile is not None


def test_secure_payrun_no_longer_runs_the_program_in_qtemp(store):
    from test_overrides import hijack, can_read_payroll, run
    scenarios.apply(store, REG["payrun-qtemp"], "secure")
    c = signed(store)
    run(c, "ADDLIBLE APPLIB *LAST")
    hijack(store, c)
    run(c, "CALL PGM(PAYRUN)")
    assert not can_read_payroll(store)


def test_secure_empdir_is_refused_the_redirected_file(store):
    scenarios.apply(store, REG["empdir-override"], "secure")
    c = signed(store)
    c.handle("ENTER", {"command": "ADDLIBLE APPLIB"})
    c.handle("ENTER", {"command": "OVRDBF FILE(STAFF) TOFILE(APPLIB/PAYROLL)"})
    assert "Not authorized" in text(c.handle("ENTER", {"command": "CALL PGM(EMPDIR)"}))


def test_secure_cpyf_gives_the_copy_no_public_authority(store):
    scenarios.apply(store, REG["cpyf-escape"], "secure")
    c = signed(store, "OPERATOR")
    c.handle("ENTER", {"command": "ADDLIBLE SCRATCH"})
    c.handle("ENTER", {"command": "CPYF FROMFILE(APPLIB/PAYROLL) TOFILE(SCRATCH/MYPAY) CRTFILE(*YES)"})
    copy = store.objects[("SCRATCH", "MYPAY", "*FILE")]
    assert Auth.READ not in store.authority_to_object(store.profiles["STUDENT"], copy)


def test_reset_clears_what_the_exploit_left(store):
    s = REG["cpyf-escape"]
    c = signed(store, "OPERATOR")
    c.handle("ENTER", {"command": "ADDLIBLE SCRATCH"})
    c.handle("ENTER", {"command": "CPYF FROMFILE(APPLIB/PAYROLL) TOFILE(SCRATCH/MYPAY) CRTFILE(*YES)"})
    scenarios.apply(store, s, "secure")
    done = scenarios.reset(store, s)
    assert ("SCRATCH", "MYPAY", "*FILE") not in store.objects and any("MYPAY" in d for d in done)
    assert scenarios.current(store, s.id) == "vulnerable"
    payadj = REG["payadj-overadopt"]
    store.objects[("APPLIB", "PAYROLL", "*FILE")].data["records"][0]["SALARY"] = 1
    scenarios.reset(store, payadj)
    assert store.objects[("APPLIB", "PAYROLL", "*FILE")].data["records"][0]["SALARY"] == 98000
    store.profiles["EVIL"] = store.profiles["STUDENT"]
    scenarios.reset(store, REG["runcmd-qcmdexc"])
    assert "EVIL" not in store.profiles


def test_command_line_lists_sets_and_refuses_while_the_server_runs(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("SILVERLAKE_STATE_DIR", str(tmp_path))
    assert scenarios.main(["list"]) == 0 and "runcmd-qcmdexc" in capsys.readouterr().out
    assert scenarios.main(["set", "runcmd-qcmdexc", "secure"]) == 0
    assert scenarios.main(["show", "runcmd-qcmdexc"]) == 0 and "(secure)" in capsys.readouterr().out
    (tmp_path / "silverlake.pid").write_text(str(os.getpid()))              # a process that is alive
    assert scenarios.main(["set", "runcmd-qcmdexc", "vulnerable"]) == 1
    assert "overwrite" in capsys.readouterr().err
    (tmp_path / "silverlake.pid").unlink()
    assert scenarios.main(["mode", "secure"]) == 0
    assert scenarios.main(["set", "nope", "secure"]) == 1
