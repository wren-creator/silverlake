"""Password rules (QPWD*), CHGPWD, per-profile PWDEXPITV and the expiry warning."""

from datetime import date, timedelta

import pytest

from silverlake.cl import commands
from silverlake.screens.model import Text
from silverlake.screens.signon import SignonController
from silverlake.system import profiles
from silverlake.system.spool import mask


@pytest.fixture
def store():
    return profiles.load()


def run(store, user, line):
    out = commands.execute(store, store.profiles[user], line)
    return out.message.text if out.message else ""


def texts(screen):
    return " | ".join(f.text for f in screen.fields if isinstance(f, Text))


def test_chgpwd_changes_your_own_password(store):
    assert run(store, "STUDENT", "CHGPWD PASSWORD(student) NEWPASSWORD(fresh1) NEWPASSWORD2(fresh1)") == "Password changed."
    assert store.profiles["STUDENT"].password == "FRESH1"
    assert store.profiles["STUDENT"].password_changed == date.today().isoformat()
    assert store.check_signon("STUDENT", "fresh1").profile is not None


def test_chgpwd_refuses_a_wrong_current_mismatch_and_same(store):
    assert "not correct" in run(store, "STUDENT", "CHGPWD PASSWORD(nope) NEWPASSWORD(a) NEWPASSWORD2(a)")
    assert "do not match" in run(store, "STUDENT", "CHGPWD PASSWORD(student) NEWPASSWORD(a) NEWPASSWORD2(b)")
    assert "different" in run(store, "STUDENT", "CHGPWD PASSWORD(student) NEWPASSWORD(student) NEWPASSWORD2(student)")
    assert store.profiles["STUDENT"].password == "STUDENT"


def test_chgpwd_is_masked_in_the_job_log():
    line = "CHGPWD PASSWORD(old) NEWPASSWORD(new1) NEWPASSWORD2(new1)"
    out = mask(line)
    assert "old" not in out and "new1" not in out


def test_length_digit_adjacent_and_repeat_rules(store):
    s = store.system
    s.qpwdminlen, s.qpwdmaxlen = 6, 8
    assert "at least 6" in run(store, "STUDENT", "CHGPWD PASSWORD(student) NEWPASSWORD(abc) NEWPASSWORD2(abc)")
    assert "no longer than 8" in run(store, "STUDENT", "CHGPWD PASSWORD(student) NEWPASSWORD(abcdefghi) NEWPASSWORD2(abcdefghi)")
    s.qpwdrqddgt = 1
    assert "digit" in run(store, "STUDENT", "CHGPWD PASSWORD(student) NEWPASSWORD(abcdef) NEWPASSWORD2(abcdef)")
    s.qpwdlmtajc = 1
    assert "next to each other" in run(store, "STUDENT", "CHGPWD PASSWORD(student) NEWPASSWORD(abcd12) NEWPASSWORD2(abcd12)")
    s.qpwdlmtrep = 2
    assert "twice in a row" in run(store, "STUDENT", "CHGPWD PASSWORD(student) NEWPASSWORD(abbcd1) NEWPASSWORD2(abbcd1)")
    s.qpwdlmtrep = 1
    assert "repeat a character" in run(store, "STUDENT", "CHGPWD PASSWORD(student) NEWPASSWORD(abcab1) NEWPASSWORD2(abcab1)")
    assert run(store, "STUDENT", "CHGPWD PASSWORD(student) NEWPASSWORD(abcde1) NEWPASSWORD2(abcde1)") == "Password changed."


def test_history_blocks_reuse(store):
    store.system.qpwdrqddif = 8        # remembers 4
    run(store, "STUDENT", "CHGPWD PASSWORD(student) NEWPASSWORD(one1) NEWPASSWORD2(one1)")
    run(store, "STUDENT", "CHGPWD PASSWORD(one1) NEWPASSWORD(two2) NEWPASSWORD2(two2)")
    assert "used before" in run(store, "STUDENT", "CHGPWD PASSWORD(two2) NEWPASSWORD(one1) NEWPASSWORD2(one1)")
    assert "used before" in run(store, "STUDENT", "CHGPWD PASSWORD(two2) NEWPASSWORD(student) NEWPASSWORD2(student)")


def test_rules_also_bind_chgusrprf_and_crtusrprf(store):
    store.system.qpwdminlen = 6
    assert "at least 6" in run(store, "QSECOFR", "CHGUSRPRF USRPRF(STUDENT) PASSWORD(abc)")
    assert store.profiles["STUDENT"].password == "STUDENT"
    assert "at least 6" in run(store, "QSECOFR", "CRTUSRPRF USRPRF(NEWB) PASSWORD(abc)")
    assert "NEWB" not in store.profiles
    assert "created" in run(store, "QSECOFR", "CRTUSRPRF USRPRF(NEWB) PASSWORD(abcdef)")


def test_per_profile_interval_beats_the_system_value(store):
    run(store, "QSECOFR", "CHGUSRPRF USRPRF(STUDENT) PWDEXPITV(10)")
    p = store.profiles["STUDENT"]
    assert p.pwd_expitv == 10 and store.expiry_days(p) == 10
    p.password_changed = (date.today() - timedelta(days=11)).isoformat()
    assert store.password_is_expired(p)
    run(store, "QSECOFR", "CHGUSRPRF USRPRF(STUDENT) PWDEXPITV(*NOMAX)")
    assert not store.password_is_expired(p)
    run(store, "QSECOFR", "CHGUSRPRF USRPRF(STUDENT) PWDEXPITV(*SYSVAL)")
    assert p.pwd_expitv is None
    assert "PWDEXPITV" in run(store, "QSECOFR", "CHGUSRPRF USRPRF(STUDENT) PWDEXPITV(400)")


def test_warning_shows_on_the_first_screen_inside_the_window(store):
    p = store.profiles["STUDENT"]
    store.system.qpwdexpitv = 30
    p.password_changed = (date.today() - timedelta(days=27)).isoformat()
    c = SignonController("QPADEV0071", store)
    s = c.handle("ENTER", {"user": "STUDENT", "password": "student"})
    assert "Password will expire in 3 days." in texts(s)
    p.password_changed = (date.today() - timedelta(days=30)).isoformat()
    assert "expire today" in store.expiry_warning(p)
    p.password_changed = (date.today() - timedelta(days=5)).isoformat()
    assert store.expiry_warning(p) == ""        # outside the window


def test_state_round_trips_the_new_fields(store, tmp_path):
    from silverlake.system import state
    store.system.qpwdminlen = 4
    run(store, "STUDENT", "CHGPWD PASSWORD(student) NEWPASSWORD(abcd) NEWPASSWORD2(abcd)")
    store.profiles["STUDENT"].pwd_expitv = 9
    again = state.from_dict(state.to_dict(store))
    assert again.system.qpwdminlen == 4
    assert again.profiles["STUDENT"].password_history == ["STUDENT"]
    assert again.profiles["STUDENT"].pwd_expitv == 9
