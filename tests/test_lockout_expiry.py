"""Sign-on lockout (QMAXSIGN) and password expiry (PWDEXP, QPWDEXPITV)."""

from datetime import date, timedelta

import pytest

from silverlake.screens.model import Input, Text
from silverlake.screens.signon import SignonController
from silverlake.system import admin, profiles, state


@pytest.fixture
def store():
    return profiles.load()


def texts(screen):
    return " | ".join(f.text for f in screen.fields if isinstance(f, Text))


def test_third_bad_password_disables_the_profile(store):
    assert store.check_signon("STUDENT", "x").message.id == "CPF1107"
    assert store.check_signon("STUDENT", "x").message.id == "CPF1107"
    assert store.profiles["STUDENT"].status == "*ENABLED"
    assert store.check_signon("STUDENT", "x").message.id == "CPF1107"
    assert store.profiles["STUDENT"].status == "*DISABLED"
    # now even the right password is refused
    assert store.check_signon("STUDENT", "student").message.id == "CPF1394"


def test_a_good_sign_on_resets_the_count(store):
    for _ in range(2):
        store.check_signon("STUDENT", "x")
    assert store.check_signon("STUDENT", "student").profile is not None
    for _ in range(2):
        store.check_signon("STUDENT", "x")
    assert store.profiles["STUDENT"].status == "*ENABLED"


def test_nomax_never_locks(store):
    store.system.qmaxsign = 0
    for _ in range(50):
        store.check_signon("STUDENT", "x")
    assert store.profiles["STUDENT"].status == "*ENABLED"


def test_device_only_action_does_not_disable_the_profile(store):
    store.system.qmaxsgnacn = 1
    for _ in range(10):
        store.check_signon("STUDENT", "x")
    assert store.profiles["STUDENT"].status == "*ENABLED"


def test_unknown_user_is_not_counted_or_created(store):
    for _ in range(5):
        assert store.check_signon("NOSUCH", "x").message.id == "CPF1120"
    assert store.get("NOSUCH") is None and "NOSUCH" not in store.bad_signons


def test_lockout_survives_a_restart(tmp_path):
    db = state.StateDB(tmp_path / "s.sqlite")
    st = profiles.load()
    st.on_change = lambda: db.write(st)
    for _ in range(3):
        st.check_signon("STUDENT", "x")
    again = state.from_dict(db.read())
    assert again.profiles["STUDENT"].status == "*DISABLED"
    assert again.system.qmaxsign == 3


def test_secadm_reenables_and_the_count_starts_over(store):
    for _ in range(3):
        store.check_signon("STUDENT", "x")
    qsecofr = store.get("QSECOFR")
    assert admin.change(store, qsecofr, "STUDENT", {"status": "*ENABLED"}).ok
    store.check_signon("STUDENT", "x")
    store.check_signon("STUDENT", "x")
    assert store.profiles["STUDENT"].status == "*ENABLED"


def test_expired_flag_forces_a_change(store):
    store.profiles["STUDENT"].password_expired = True
    r = store.check_signon("STUDENT", "student")
    assert r.profile is not None and r.must_change_password


def test_interval_ages_a_password(store):
    p = store.profiles["STUDENT"]
    store.system.qpwdexpitv = 30
    p.password_changed = (date.today() - timedelta(days=31)).isoformat()
    assert store.check_signon("STUDENT", "student").must_change_password
    p.password_changed = (date.today() - timedelta(days=30)).isoformat()
    assert not store.check_signon("STUDENT", "student").must_change_password


def test_no_change_date_never_ages(store):
    store.system.qpwdexpitv = 1
    assert store.profiles["STUDENT"].password_changed is None
    assert not store.check_signon("STUDENT", "student").must_change_password


def test_change_password_rules(store):
    p = store.profiles["STUDENT"]
    ch = store.change_password
    assert ch(p, "wrong", "new1", "new1").id == "CPF1107"
    assert "required" in ch(p, "student", "", "").text
    assert "do not match" in ch(p, "student", "new1", "new2").text
    assert "different" in ch(p, "student", "student", "student").text
    assert "longer than 10" in ch(p, "student", "x" * 11, "x" * 11).text
    assert ch(p, "student", "newpass", "newpass") is None
    assert p.password == "newpass" and p.password_changed == date.today().isoformat()


def test_signon_screen_flow_through_change_password(store):
    store.profiles["STUDENT"].password_expired = True
    c = SignonController("QPADEV0001", store)
    s = c.handle("ENTER", {"user": "STUDENT", "password": "student"})
    assert "Change Password" in texts(s) and c.profile is None
    assert {i.name for i in s.inputs()} >= {"current", "new", "verify"}
    assert all(i.hidden for i in s.inputs())

    s = c.handle("ENTER", {"current": "student", "new": "a", "verify": "b"})
    assert "do not match" in texts(s) and c.profile is None

    s = c.handle("ENTER", {"current": "student", "new": "fresh1", "verify": "fresh1"})
    assert c.profile is not None and "Main Menu" in texts(s)
    assert not store.profiles["STUDENT"].password_expired


def test_f3_on_change_password_goes_back_to_sign_on(store):
    store.profiles["STUDENT"].password_expired = True
    c = SignonController("QPADEV0001", store)
    c.handle("ENTER", {"user": "STUDENT", "password": "student"})
    s = c.handle("F3", {})
    assert "Sign On" in texts(s) and c.profile is None and c.pending_password is None
    assert store.profiles["STUDENT"].password_expired


def test_new_profile_gets_a_change_date(store):
    q = store.get("QSECOFR")
    assert admin.create(store, q, "NEWBIE", {
        **{k: None for k in ()}, "user_class": store.profiles["STUDENT"].user_class, "special": None,
        "password": "pw", "status": "*ENABLED", "password_expired": False, "limited_capabilities": "*NO",
        "group_profile": None, "supplemental_groups": [], "initial_program": "*NONE", "initial_menu": "MAIN",
        "current_library": "*CRTDFT", "text": "", "public_authority": store.profiles["STUDENT"].public_authority,
    }).ok
    assert store.profiles["NEWBIE"].password_changed == date.today().isoformat()
