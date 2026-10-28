"""Flags: derived from an instance secret, planted where the exploit reaches, scored from a submission or the saved state."""

import re

import pytest

from silverlake import flags, scenarios
from silverlake.screens.model import Text
from silverlake.screens.signon import SignonController
from silverlake.system import profiles
from silverlake.system.authority import Auth

REG = scenarios.registry()


@pytest.fixture
def store():
    return profiles.load()


def text(s):
    return " | ".join(f.text for f in s.fields if isinstance(f, Text))


def signed(store, user, dev="QPADEV0181"):
    c = SignonController(dev, store)
    c.handle("ENTER", {"user": user, "password": user})
    return c


def run(c, line):
    return c.handle("ENTER", {"command": line})


def test_a_flag_is_twelve_hex_and_depends_on_the_scenario_and_the_secret(monkeypatch):
    f = flags.flag("qsysopr-recon")
    assert re.fullmatch(r"FLAG\{[0-9a-f]{12}\}", f) and f != flags.flag("runcmd-qcmdexc")
    assert flags.flag("qsysopr-recon") == f                       # the same after a reset
    monkeypatch.setenv("SILVERLAKE_INSTANCE_SECRET", "another range")
    assert flags.flag("qsysopr-recon") != f


def test_the_secret_file_is_made_once_and_kept(tmp_path, monkeypatch):
    monkeypatch.delenv("SILVERLAKE_INSTANCE_SECRET")
    monkeypatch.setenv("SILVERLAKE_SECRET_FILE", str(tmp_path / "secret"))
    a = flags.secret()
    assert flags.secret() == a and (tmp_path / "secret").stat().st_mode & 0o077 == 0


def test_the_seed_holds_no_placeholder_and_every_text_flag_is_planted_once_or_more(store):
    blob = repr([(o.data, o.text) for o in store.objects.values()]) + repr([f.lines for f in store.spool]) \
        + repr([n.content for n in store.ifs.values()])
    assert "@@" not in blob
    for s in flags.lessons(REG):
        if s.flag["kind"] == "text":
            assert flags.flag(s.id) in blob, s.id


def test_every_lesson_has_a_flag_with_a_task():
    assert len(flags.lessons(REG)) == len(REG)
    for s in REG.values():
        assert s.flag["kind"] in ("text", "state", "fact") and s.flag["task"]
        if s.flag["kind"] == "fact":
            assert s.flag["fact"] in flags.FACTS
        if s.flag["kind"] == "state":
            assert s.flag["check"] in flags.CHECKS


def test_secure_passwords_come_from_the_secret_and_fit_the_seed_rules(store):
    scenarios.apply(store, REG["default-passwords"], "secure")
    pw = store.profiles["OPERATOR"].password
    assert pw == flags.password("OPERATOR") and 8 <= len(pw) <= 10 and any(c.isdigit() for c in pw)
    assert store.check_signon("OPERATOR", pw).profile is not None


# -- each text flag is reachable the way the lesson says, and not once the lesson is fixed ----------------------

def test_default_passwords_flag_is_in_the_security_officers_job_log(store):
    c = signed(store, "QSECOFR")
    run(c, "ADDLIBLE APPLIB")
    f = next(f for f in store.spool if f.name == "QPJOBLOG")
    assert flags.flag("default-passwords") in "\n".join(f.lines)
    scenarios.apply(store, REG["default-passwords"], "secure")
    assert store.check_signon("QSECOFR", "QSECOFR").profile is None


def test_the_vault_is_only_for_all_object_authority(store):
    vault = store.objects[("APPLIB", "VAULT", "*FILE")]
    assert Auth.READ in store.authority_to_object(store.profiles["SVCACCT"], vault)
    assert Auth.READ not in store.authority_to_object(store.profiles["STUDENT"], vault)
    scenarios.apply(store, REG["overprivileged-accounts"], "secure")
    assert Auth.READ not in store.authority_to_object(store.profiles["SVCACCT"], vault)


def test_the_maintenance_notes_are_for_the_clerk_who_has_no_command_line(store):
    notes = store.objects[("APPLIB", "MAINTLOG", "*FILE")]
    assert Auth.READ in store.authority_to_object(store.profiles["CLERK"], notes)
    assert Auth.READ not in store.authority_to_object(store.profiles["STUDENT"], notes)
    c = signed(store, "CLERK")
    assert "not allowed" in text(run(c, "DSPPFM FILE(APPLIB/MAINTLOG)")).lower() or "capabilit" in text(run(c, "DSPPFM FILE(APPLIB/MAINTLOG)")).lower()
    s = c.handle("ENTER", {"command": "9"})                       # the menu's way out
    s = run(c, "DSPPFM FILE(APPLIB/MAINTLOG)")
    assert flags.flag("clerk-menu-escape") in text(s)


def test_the_operator_queue_message_and_the_report_flag_are_readable_until_fixed(store):
    queue = store.objects[("QSYS", "QSYSOPR", "*MSGQ")]
    assert flags.flag("qsysopr-recon") in repr(queue.data["messages"])
    student = store.profiles["STUDENT"]
    assert Auth.READ in store.authority_to_object(student, queue)
    scenarios.apply(store, REG["qsysopr-recon"], "secure")
    assert Auth.READ not in store.authority_to_object(student, queue)
    from silverlake.system import spool
    pay = next(f for f in store.spool if f.name == "PAYRPT")
    assert flags.flag("qprint-report-leak") in "\n".join(pay.lines) and spool.can_display(store, student, pay)
    scenarios.apply(store, REG["qprint-report-leak"], "secure")
    assert not spool.can_display(store, student, pay)


def test_the_payroll_heading_and_the_audit_employee_carry_their_flags(store):
    pf = store.objects[("APPLIB", "REGRPT", "*FILE")]
    assert flags.flag("regrpt-outq") in pf.data["dds"]
    pay = store.objects[("APPLIB", "PAYROLL", "*FILE")]
    assert any(r["NAME"] == flags.flag("empdir-override") for r in pay.data["records"])
    c = signed(store, "STUDENT")
    run(c, "ADDLIBLE APPLIB")
    run(c, "OVRDBF FILE(STAFF) TOFILE(APPLIB/PAYROLL)")
    run(c, "CALL PGM(EMPDIR)")
    assert flags.flag("empdir-override") in text(c.handle("ENTER", {"empno": "10099"}))


# -- scoring ----------------------------------------------------------------------------------------------------

def test_a_submission_is_scored_flag_by_flag_and_state_lessons_need_no_submission(store):
    rows = {sid: ok for sid, ok, _ in flags.score(store, {"qsysopr-recon": flags.flag("qsysopr-recon"),
                                                          "qprint-report-leak": "FLAG{000000000000}"}, REG)}
    assert rows["qsysopr-recon"] and not rows["qprint-report-leak"] and not rows["runcmd-qcmdexc"]
    assert len(rows) == 20


def test_the_submission_file_format():
    got = flags.parse_submission("# mine\nQSYSOPR-recon = FLAG{abc}\n\nrunCMD-qcmdexc=done\nnonsense\n")
    assert got == {"qsysopr-recon": "FLAG{abc}", "runcmd-qcmdexc": "done"}


def test_each_state_check_notices_its_win(store):
    done = lambda sid: dict((r[0], r[1]) for r in flags.score(store, {}, REG))[sid]
    assert not done("runcmd-qcmdexc") and not done("payadj-overadopt") and not done("payrun-qtemp") and not done("cpyf-escape")
    c = signed(store, "STUDENT")
    run(c, "ADDLIBLE APPLIB")
    store.objects[("APPLIB", "RUNCMD", "*PGM")]                    # the lesson's exploit is covered in its own tests
    store.profiles["EVIL"] = profiles.Profile(name="EVIL", special_authorities=frozenset({profiles.SpecialAuthority.ALLOBJ}),
                                              owner="QSECOFR")
    assert done("runcmd-qcmdexc")
    pay = store.objects[("APPLIB", "PAYROLL", "*FILE")]
    next(r for r in pay.data["records"] if r["EMPNO"] == 10004)["SALARY"] = 99999
    assert done("payadj-overadopt")
    pay.private["STUDENT"] = Auth.OBJOPR | Auth.READ
    assert done("payrun-qtemp")
    c2 = signed(store, "OPERATOR", "QPADEV0182")
    run(c2, "ADDLIBLE SCRATCH")
    run(c2, "CPYF FROMFILE(APPLIB/PAYROLL) TOFILE(SCRATCH/LOOT) CRTFILE(*YES)")
    assert done("cpyf-escape")


def test_command_line_scores_and_shows(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("SILVERLAKE_STATE_DIR", str(tmp_path))
    sub = tmp_path / "sub.txt"
    sub.write_text(f"qsysopr-recon={flags.flag('qsysopr-recon')}\n")
    assert flags.main(["check", str(sub)]) == 1
    out = capsys.readouterr().out
    assert "[+] qsysopr-recon" in out and "1 of 20" in out
    assert flags.main(["show"]) == 0
    shown = capsys.readouterr().out
    assert flags.flag("qsysopr-recon") in shown and flags.password("OPERATOR") in shown
