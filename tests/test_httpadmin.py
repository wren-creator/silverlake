"""The web console: sign-in through the profile store, the evaluated description, and the fix."""

from base64 import b64encode

import pytest

from silverlake import flags, scenarios
from silverlake.net import httpadmin, textview
from silverlake.net.httpadmin import Request, State
from silverlake.system import profiles

REG = scenarios.registry()
INJECT = 'name=ZZTEST&description=%3C%21--%23exec+cmd%3D%22{cmd}%22+--%3E'


@pytest.fixture
def store():
    return profiles.load()


def auth(user="STUDENT", password=None):
    return {"authorization": "Basic " + b64encode(f"{user}:{password or user}".encode()).decode()}


def get(store, state, url, headers=None):
    return httpadmin.handle(Request("GET", url, auth() if headers is None else headers), store, state)


def post_description(store, state, cmd, headers=None):
    body = INJECT.format(cmd=cmd.replace(" ", "+").replace("(", "%28").replace(")", "%29"))
    return httpadmin.handle(Request("POST", "/HTTPAdmin/servers", auth() if headers is None else headers, body), store, state)


def test_the_console_wants_a_profile_and_the_password_must_be_right(store):
    state = State()
    assert get(store, state, "/HTTPAdmin", {}).status == 401
    assert "WWW-Authenticate" in get(store, state, "/HTTPAdmin", {}).headers
    assert get(store, state, "/HTTPAdmin", auth("STUDENT", "wrong")).status == 401
    assert get(store, state, "/HTTPAdmin", {"authorization": "Basic !!!"}).status == 401
    assert get(store, state, "/HTTPAdmin").status == 200
    assert get(store, state, "/").status == 302 and get(store, state, "/other").status == 404


def test_bad_passwords_over_http_count_against_the_profile(store):
    state = State()
    for _ in range(store.system.qmaxsign):
        get(store, state, "/HTTPAdmin", auth("STUDENT", "nope"))
    assert store.profiles["STUDENT"].status != "*ENABLED"
    assert get(store, state, "/HTTPAdmin", auth("STUDENT")).status == 401


def test_a_profile_that_cannot_sign_on_cannot_use_the_console(store):
    assert get(store, State(), "/HTTPAdmin", auth("QTMHHTTP", "x")).status == 401


def test_a_description_runs_a_command_as_the_web_profile_until_the_fix(store):
    state = State()
    assert post_description(store, state, "DSPMSG MSGQ(QTMHHTTP)").status == 302
    page = get(store, state, "/HTTPAdmin/servers").body
    assert flags.flag("httpadmin-ssi-injection") in page
    assert "ZZTEST" in page and "Payroll web front end" in page


def test_the_same_command_is_refused_to_the_person_who_sent_it(store):
    student = store.profiles["STUDENT"]
    out = textview.run(store, student, "DSPMSG MSGQ(QTMHHTTP)")
    assert flags.flag("httpadmin-ssi-injection") not in out and "not authorized" in out.lower()


def test_the_fix_escapes_the_description_and_runs_nothing(store):
    scenarios.apply(store, REG["httpadmin-ssi-injection"], "secure")
    state = State()
    post_description(store, state, "DSPMSG MSGQ(QTMHHTTP)")
    page = get(store, state, "/HTTPAdmin/servers").body
    assert flags.flag("httpadmin-ssi-injection") not in page
    assert "&lt;!--#exec" in page
    assert "SJ11643" in get(store, state, "/HTTPAdmin/about").body


def test_the_about_page_says_the_fix_is_missing(store):
    assert "not installed" in get(store, State(), "/HTTPAdmin/about").body


def test_a_directive_can_only_do_what_the_web_profile_may(store):
    state = State()
    post_description(store, state, "CRTUSRPRF USRPRF(EVIL) PASSWORD(EVIL) USRCLS(*SECOFR)")
    get(store, state, "/HTTPAdmin/servers")
    assert "EVIL" not in store.profiles


def test_a_command_that_needs_a_screen_says_so(store):
    state = State()
    post_description(store, state, "WRKOBJ OBJ(QSYS/*ALL)")
    assert "needs a screen" in get(store, state, "/HTTPAdmin/servers").body


def test_create_checks_the_name(store):
    state = State()
    bad = httpadmin.handle(Request("POST", "/HTTPAdmin/servers", auth(), "name=1bad&description=x"), store, state)
    assert bad.status == 400
    post_description(store, state, "DSPLIBL")
    again = httpadmin.handle(Request("POST", "/HTTPAdmin/servers", auth(), "name=zztest&description=x"), store, state)
    assert again.status == 409
