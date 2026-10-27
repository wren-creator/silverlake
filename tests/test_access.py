import textwrap

import pytest

from silverlake.screens.model import Input, Text
from silverlake.screens.signon import SignonController
from silverlake.system import profiles
from silverlake.system.authority import (ALL, CHANGE, EXCLUDE, USE, Auth, AuthList, SecuredObject,
                                         SpecialAuthority as SA, UserClass as UC, can_grant,
                                         class_authorities, name_auth, parse_auth,
                                         resolve_object_authority)

EVERY = frozenset(SA)


# -- user class defaults: IBM i 7.5 CRTUSRPRF, USRCLS ---------------------------------

@pytest.mark.parametrize("qsec", [10, 20])
def test_class_defaults_at_level_20_give_the_lower_classes_allobj(qsec):
    assert class_authorities(UC.USER, qsec) == {SA.ALLOBJ, SA.SAVSYS}
    assert class_authorities(UC.SYSOPR, qsec) == {SA.ALLOBJ, SA.SAVSYS, SA.JOBCTL}
    assert class_authorities(UC.PGMR, qsec) == {SA.ALLOBJ, SA.SAVSYS, SA.JOBCTL}
    assert class_authorities(UC.SECADM, qsec) == {SA.ALLOBJ, SA.SAVSYS, SA.SECADM, SA.JOBCTL}


@pytest.mark.parametrize("qsec", [30, 40, 50])
def test_class_defaults_at_level_30_and_up(qsec):
    assert class_authorities(UC.USER, qsec) == set()
    assert class_authorities(UC.PGMR, qsec) == set()
    assert class_authorities(UC.SYSOPR, qsec) == {SA.SAVSYS, SA.JOBCTL}
    assert class_authorities(UC.SECADM, qsec) == {SA.SECADM}


@pytest.mark.parametrize("qsec", [10, 20, 30, 40, 50])
def test_secofr_has_all_eight_at_every_level(qsec):
    assert class_authorities(UC.SECOFR, qsec) == EVERY
    assert len(EVERY) == 8


def test_bad_qsecurity_is_refused():
    with pytest.raises(ValueError):
        class_authorities(UC.USER, 35)


# -- who may give what away -------------------------------------------------------------

def test_cannot_give_what_you_do_not_hold():
    assert not can_grant(frozenset({SA.JOBCTL}), frozenset({SA.SPLCTL}))
    assert can_grant(frozenset({SA.JOBCTL, SA.SPLCTL}), frozenset({SA.SPLCTL}))


def test_giving_secadm_needs_allobj_and_secadm():
    assert not can_grant(frozenset({SA.SECADM}), frozenset({SA.SECADM}))
    assert not can_grant(frozenset({SA.ALLOBJ}), frozenset({SA.SECADM}))
    assert can_grant(frozenset({SA.ALLOBJ, SA.SECADM}), frozenset({SA.SECADM}))


def test_giving_audit_needs_allobj_secadm_and_audit():
    assert not can_grant(frozenset({SA.ALLOBJ, SA.SECADM}), frozenset({SA.AUDIT}))
    assert can_grant(EVERY, frozenset({SA.AUDIT}))


# -- object authority values -------------------------------------------------------------

def test_special_values_expand_to_ibm_detail_sets():
    assert ALL == Auth.OBJOPR | Auth.OBJMGT | Auth.OBJEXIST | Auth.OBJALTER | Auth.OBJREF \
        | Auth.READ | Auth.ADD | Auth.UPD | Auth.DLT | Auth.EXECUTE
    assert CHANGE == Auth.OBJOPR | Auth.READ | Auth.ADD | Auth.UPD | Auth.DLT | Auth.EXECUTE
    assert USE == Auth.OBJOPR | Auth.READ | Auth.EXECUTE
    assert EXCLUDE == Auth.NONE


def test_parse_and_name_round_trip():
    for v in ("*ALL", "*CHANGE", "*USE", "*EXCLUDE"):
        assert name_auth(parse_auth(v)) == v
    assert parse_auth("*OBJOPR *READ") == Auth.OBJOPR | Auth.READ
    assert name_auth(Auth.OBJOPR | Auth.READ) == "*OBJOPR *READ"
    with pytest.raises(ValueError):
        parse_auth("*BOGUS")


# -- resolving authority to an object -------------------------------------------------------

def check(user, special=frozenset(), groups=(), obj=None, autls=None):
    return resolve_object_authority(user, frozenset(special), list(groups), obj, autls)


def test_allobj_beats_a_private_exclude():
    obj = SecuredObject("F", "OWNER", private={"BOB": EXCLUDE}, public=EXCLUDE)
    assert check("BOB", {SA.ALLOBJ}, obj=obj) == ALL
    assert check("BOB", obj=obj) == EXCLUDE


def test_owner_gets_owner_authority():
    obj = SecuredObject("F", "OWNER", public=EXCLUDE)
    assert check("OWNER", obj=obj) == ALL


def test_private_entry_overrides_a_more_generous_public():
    obj = SecuredObject("F", "OWNER", private={"BOB": EXCLUDE}, public=CHANGE)
    assert check("BOB", obj=obj) == EXCLUDE
    assert check("ANNE", obj=obj) == CHANGE


def test_group_authority_applies_and_combines():
    obj = SecuredObject("F", "OWNER", private={"G1": USE, "G2": Auth.UPD}, public=EXCLUDE)
    assert check("BOB", groups=["G1"], obj=obj) == USE
    assert check("BOB", groups=["G1", "G2"], obj=obj) == USE | Auth.UPD
    assert check("BOB", groups=["G3"], obj=obj) == EXCLUDE


def test_authorization_list_stands_in_for_public():
    autl = AuthList("L", {"BOB": USE}, public=EXCLUDE)
    obj = SecuredObject("F", "OWNER", public=None, autl="L")
    assert check("BOB", obj=obj, autls={"L": autl}) == USE
    assert check("ANNE", obj=obj, autls={"L": autl}) == EXCLUDE


# -- the seed file -----------------------------------------------------------------------------

@pytest.fixture(scope="module")
def store():
    return profiles.load()


def test_seed_has_every_class_and_every_special_authority_on_its_own(store):
    classes = {p.user_class for p in store.profiles.values()}
    assert classes == set(UC)
    singles = {next(iter(store.special_authorities(p))) for p in store.profiles.values()
               if p.special_authorities and len(p.special_authorities) == 1}
    assert singles == set(SA)


def test_seed_effective_authorities_follow_the_class_table(store):
    sa = store.special_authorities
    p = store.get
    assert sa(p("QSECOFR")) == EVERY
    assert sa(p("SECADMIN")) == {SA.SECADM}
    assert sa(p("DEVELOPER")) == set()
    assert sa(p("OPERATOR")) == {SA.JOBCTL, SA.SAVSYS}
    assert sa(p("STUDENT")) == set()
    assert sa(p("GUEST")) == set()
    assert sa(p("SVCACCT")) == {SA.ALLOBJ}


def test_qsecurity_20_hands_every_user_allobj():
    st = profiles.load()
    st.system.qsecurity = 20
    assert SA.ALLOBJ in st.special_authorities(st.get("STUDENT"))
    assert st.special_authorities(st.get("GUEST")) == set()   # SPCAUT(*NONE) still means none


def test_seed_objects_resolve_for_the_demo_users(store):
    def auth(user, obj):
        lib = "SRCLIB" if obj == "SRCLIB" else "APPLIB"
        key = ("QSYS", obj, "*LIB") if obj == "SRCLIB" else (lib, obj, "*FILE")
        return store.object_authority(store.get(user), store.objects[key])
    assert auth("QSECOFR", "PAYROLL") == ALL            # *ALLOBJ
    assert auth("SECADMIN", "PAYROLL") == ALL           # on the authorization list
    assert auth("OPERATOR", "PAYROLL") == USE
    assert auth("STUDENT", "PAYROLL") == EXCLUDE        # falls to the list's public
    assert auth("DEVELOPER", "CUSTOMERS") == CHANGE
    assert auth("GUEST", "CUSTOMERS") == EXCLUDE        # private exclude beats public *USE
    assert auth("STUDENT", "CUSTOMERS") == USE
    assert auth("DEVELOPER", "SRCLIB") == ALL           # owner
    assert auth("SVCACCT", "SRCLIB") == ALL             # *ALLOBJ, never named on it


def test_seed_group_membership(store):
    assert store.groups_of(store.get("DEVELOPER")) == ["GRPDEV"]
    assert store.groups_of(store.get("STUDENT")) == []


def test_who_may_create_profiles(store):
    p, may = store.get, store.may_create_or_change
    # *SECADM is required; and the actor must hold whatever they hand out
    assert may(p("SECADMIN"), frozenset())
    assert not may(p("STUDENT"), frozenset())
    assert not may(p("SECADMIN"), frozenset({SA.JOBCTL}))        # does not hold it
    assert not may(p("SECADMIN"), frozenset({SA.SECADM}))        # needs *ALLOBJ too
    assert may(p("QSECOFR"), frozenset(SA))
    assert may(p("DEVADMIN"), frozenset())                       # a programmer with *SECADM


# -- sign-on -------------------------------------------------------------------------------------

def test_signon_outcomes(store):
    ok = store.check_signon("student", "student")
    assert ok.profile.name == "STUDENT" and ok.message is None

    assert store.check_signon("NOSUCH", "x").message.id == "CPF1120"
    assert store.check_signon("STUDENT", "wrong").message.id == "CPF1107"
    assert store.check_signon("STUDENT", "").message.id == "CPF1107"
    assert store.check_signon("NOPWD", "anything").message.id == "CPF1118"
    assert store.check_signon("OLDTEMP", "OLDTEMP").message.id == "CPF1394"
    assert store.check_signon("OLDTEMP", "nope").message.id == "CPF1107"   # password first


def test_password_case_follows_qpwdlvl():
    st = profiles.load()
    assert st.check_signon("STUDENT", "StUdEnT").profile is not None      # level 0 ignores case
    st.system.qpwdlvl = 2
    assert st.check_signon("STUDENT", "StUdEnT").profile is None
    st.profiles["STUDENT"].password = "StUdEnT"
    assert st.check_signon("STUDENT", "StUdEnT").profile is not None


def test_only_the_message_id_we_saw_is_marked_verified():
    from silverlake.system import messages
    assert messages.user_not_found("X").source == messages.VERIFIED
    assert messages.password_not_correct("X").source == messages.RECALLED


# -- the controller ----------------------------------------------------------------------------------

def texts(screen):
    return " | ".join(f.text for f in screen.fields if isinstance(f, Text))


def test_controller_flow_signon_home_signoff(store):
    c = SignonController("QPADEV0001", store)
    s = c.handle("ENTER", {"user": "devadmin", "password": "wrong"})
    assert "CPF1107" in texts(s) and next(i for i in s.inputs() if i.name == "user").value == "DEVADMIN"

    s = c.handle("ENTER", {"user": "DEVADMIN", "password": "devadmin"})
    t = texts(s)
    assert "Silverlake Main Menu" in t
    assert any(isinstance(f, Input) and f.name == "command" for f in s.fields)

    assert "WRKACTJOB in library *LIBL not found" in texts(c.handle("ENTER", {"command": "wrkactjob"}))
    assert "Silverlake Main Menu" in texts(c.handle("F3", {}))     # F3 on the initial menu does nothing
    assert "Sign On" in texts(c.handle("ENTER", {"command": "signoff"}))
    assert "Sign On" in texts(c.handle("ENTER", {}))      # signed off, back to sign-on


def test_blank_user_just_redraws(store):
    c = SignonController("QPADEV0001", store)
    t = texts(c.handle("ENTER", {"user": "  ", "password": "x"}))
    assert "CPF" not in t and "Sign On" in t


# -- seed validation ------------------------------------------------------------------------------------

def load_text(tmp_path, body):
    path = tmp_path / "p.toml"
    path.write_text(textwrap.dedent(body))
    return profiles.load(path)


@pytest.mark.parametrize("body, why", [
    ('[system]\nqsecurity = 35\n', "qsecurity"),
    ('[system]\nqpwdlvl = 9\n', "qpwdlvl"),
    ('[[profile]]\nname = "A"\nuser_class = "*BOSS"\n', "user_class"),
    ('[[profile]]\nname = "A"\nspecial_authorities = ["*ROOT"]\n', "special_authorities"),
    ('[[profile]]\nname = "A"\nstatus = "*GONE"\n', "status"),
    ('[[profile]]\nname = "TOOLONGNAME1"\n', "1 to 10"),
    ('[[profile]]\nname = "A"\n[[profile]]\nname = "a"\n', "duplicate"),
    ('[[profile]]\nname = "A"\ngroup_profile = "NOPE"\n', "does not exist"),
])
def test_bad_seeds_are_refused_with_a_reason(tmp_path, body, why):
    with pytest.raises(profiles.SeedError, match=why):
        load_text(tmp_path, body)


def test_missing_seed_file(tmp_path):
    with pytest.raises(profiles.SeedError):
        profiles.load(tmp_path / "nope.toml")


def test_custom_seed_assigns_any_combination(tmp_path):
    st = load_text(tmp_path, '''
        [system]
        qsecurity = 30
        [[profile]]
        name = "MIXED"
        user_class = "*SYSOPR"
        special_authorities = ["*SPLCTL", "*AUDIT"]
        password = "x"
    ''')
    assert st.special_authorities(st.get("MIXED")) == {SA.SPLCTL, SA.AUDIT}


# -- every profile gets a screen that fits -----------------------------------------------------------

def test_base_screen_renders_for_every_seed_profile(store):
    """Every profile signs on to a screen that fits, with a long message on it."""
    from silverlake.screens.render import render
    for profile in store.profiles.values():
        if not profile.password or profile.status != "*ENABLED":
            continue
        c = SignonController("QPADEV0001", store)
        s = c.handle("ENTER", {"user": profile.name, "password": profile.password})
        if not any(isinstance(f, Input) and f.name == "command" for f in s.fields):
            continue            # *SIGNOFF style profiles land back on sign-on
        s = c.handle("ENTER", {"command": "x" * 200})
        s.validate()
        assert render(s)


def test_wrap_keeps_every_line_inside_the_value_column():
    from silverlake.screens.home import VALUE_WIDTH, wrap
    long = " ".join(a.value for a in SA)
    lines = wrap(long)
    assert len(lines) > 1 and all(len(line) <= VALUE_WIDTH for line in lines)
    assert " ".join(lines) == long
    assert wrap("") == [""] and wrap("one") == ["one"]
