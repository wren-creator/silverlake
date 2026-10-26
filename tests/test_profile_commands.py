"""CRTUSRPRF, CHGUSRPRF, DSPUSRPRF, DLTUSRPRF and WRKUSRPRF from the command
line: the parser, the authority rules, persistence, and the screens."""

import pytest

from silverlake.cl import parser
from silverlake.cl.commands import execute
from silverlake.screens.model import Text
from silverlake.screens.render import render
from silverlake.screens.signon import SignonController
from silverlake.system import profiles, state
from silverlake.system.authority import Auth, SpecialAuthority as SA


@pytest.fixture
def store():
    return profiles.load()


def run(store, user, line):
    out = execute(store, store.get(user), line)
    return out.message.line() if out.message else ""


def texts(screen):
    return " | ".join(f.text for f in screen.fields if isinstance(f, Text))


# -- parser ----------------------------------------------------------------------

def test_parser_keywords_positionals_and_quotes():
    p = parser.parse("crtusrprf bob 'Mixed Case' spcaut(*jobctl *savsys) text('it''s mine')")
    assert p.command == "CRTUSRPRF"
    assert p.positional == ["BOB", "Mixed Case"]
    assert p.keywords == {"SPCAUT": ["*JOBCTL", "*SAVSYS"], "TEXT": ["it's mine"]}


def test_parser_strips_library_qualifier_and_ignores_blank():
    assert parser.parse("QSYS/DSPUSRPRF STUDENT").command == "DSPUSRPRF"
    assert parser.parse("   ") is None


@pytest.mark.parametrize("line", ["CRTUSRPRF X TEXT('open", "CRTUSRPRF X TEXT(a", "CRTUSRPRF X )",
                                  "CRTUSRPRF X TEXT(a) TEXT(b)", "CRTUSRPRF TEXT(a) X"])
def test_parser_rejects_malformed_lines(line):
    with pytest.raises(parser.ParseError):
        parser.parse(line)


# -- binding and messages ------------------------------------------------------------

def test_unknown_command_and_keyword_and_missing_name(store):
    assert "WRKACTJOB in library *LIBL not found" in run(store, "QSECOFR", "WRKACTJOB")
    assert "Keyword BAD not valid" in run(store, "QSECOFR", "CRTUSRPRF X BAD(1)")
    assert "Required parameter USRPRF" in run(store, "QSECOFR", "CRTUSRPRF")
    assert "SPCAUT not valid" in run(store, "QSECOFR", "CRTUSRPRF X SPCAUT(*NOPE)")
    assert "TOOLONGNAMEX for parameter USRPRF not valid" in run(store, "QSECOFR", "CRTUSRPRF TOOLONGNAMEX")


def test_create_uses_the_command_defaults(store):
    assert "created" in run(store, "QSECOFR", "CRTUSRPRF NEWBIE")
    p = store.get("NEWBIE")
    assert p.password is None and p.status == "*ENABLED" and p.user_class.value == "*USER"
    assert p.special_authorities is None and p.limited_capabilities == "*NO"
    assert p.initial_menu == "MAIN" and p.public_authority == Auth.NONE and p.owner == "QSECOFR"


def test_create_with_options(store):
    run(store, "QSECOFR", "CRTUSRPRF USRPRF(MIKE) PASSWORD('Hunter2') USRCLS(*PGMR) "
                          "SPCAUT(*JOBCTL *SAVSYS) GRPPRF(GRPDEV) LMTCPB(*YES) TEXT('Mike') PWDEXP(*YES)")
    p = store.get("MIKE")
    assert p.password == "Hunter2" and p.password_expired and p.user_class.value == "*PGMR"
    assert store.special_authorities(p) == {SA.JOBCTL, SA.SAVSYS}
    assert p.group_profile == "GRPDEV" and p.limited_capabilities == "*YES" and p.text == "Mike"
    assert store.check_signon("mike", "hunter2").profile is p      # qpwdlvl 0 ignores case


def test_duplicate_and_bad_names(store):
    assert "CPF2214" in run(store, "QSECOFR", "CRTUSRPRF STUDENT")
    assert "not a valid profile name" in run(store, "QSECOFR", "CRTUSRPRF 1BAD")


def test_expired_password_with_none_is_refused(store):
    assert "CPF223F" in run(store, "QSECOFR", "CRTUSRPRF X PWDEXP(*YES)")


def test_missing_group_is_refused_and_nothing_is_created(store):
    assert "CPF2259" in run(store, "QSECOFR", "CRTUSRPRF X GRPPRF(NOSUCH)")
    assert store.get("X") is None


# -- who may do what ------------------------------------------------------------------------------

def test_without_secadm_you_cannot_create_or_change(store):
    for user in ("STUDENT", "DEVELOPER", "AUDITOR"):
        assert "CPF2292" in run(store, user, "CRTUSRPRF X")
        assert "CPF2292" in run(store, user, "CHGUSRPRF STUDENT TEXT(x)")


def test_secadmin_cannot_pass_on_secadm_or_audit(store):
    assert "CPF2269" in run(store, "SECADMIN", "CRTUSRPRF X SPCAUT(*SECADM)")
    assert "CPF2269" in run(store, "SECADMIN", "CRTUSRPRF X USRCLS(*SECADM)")   # the class carries *SECADM
    assert "CPF2291" in run(store, "SECADMIN", "CRTUSRPRF Y SPCAUT(*ALLOBJ)")


def test_secofr_can_give_anything(store):
    assert "created" in run(store, "QSECOFR", "CRTUSRPRF ADM SPCAUT(*SECADM *AUDIT *ALLOBJ)")


def test_secadm_only_user_cannot_touch_profiles_it_has_no_authority_to(store):
    # DEVADMIN holds *SECADM but owns nothing and was granted nothing.
    assert "CPF2228" in run(store, "DEVADMIN", "CHGUSRPRF STUDENT STATUS(*DISABLED)")
    assert store.get("STUDENT").status == "*ENABLED"
    # It can still create, and then owns, what it creates.
    assert "created" in run(store, "DEVADMIN", "CRTUSRPRF MINE")
    assert store.get("MINE").owner == "DEVADMIN"
    assert "changed" in run(store, "DEVADMIN", "CHGUSRPRF MINE TEXT('mine')")


def test_group_needs_change_and_objmgt_to_the_group_profile(store):
    assert "CPF2217" in run(store, "DEVADMIN", "CRTUSRPRF X GRPPRF(GRPDEV)")
    assert "created" in run(store, "SECADMIN", "CRTUSRPRF X GRPPRF(GRPDEV)")


def test_change_only_touches_what_was_named(store):
    before = store.get("DEVELOPER").group_profile
    assert "changed" in run(store, "SECADMIN", "CHGUSRPRF DEVELOPER STATUS(*DISABLED)")
    p = store.get("DEVELOPER")
    assert p.status == "*DISABLED" and p.group_profile == before and p.password == "DEVELOPER"
    assert "changed" in run(store, "SECADMIN", "CHGUSRPRF DEVELOPER GRPPRF(*NONE) SUPGRPPRF(GRPDEV)")
    assert p.group_profile is None and p.supplemental_groups == ["GRPDEV"]
    assert "changed" in run(store, "SECADMIN", "CHGUSRPRF DEVELOPER STATUS(*SAME)")


def test_change_cannot_add_authorities_the_actor_lacks(store):
    assert "CPF2291" in run(store, "SECADMIN", "CHGUSRPRF STUDENT SPCAUT(*ALLOBJ)")
    assert store.special_authorities(store.get("STUDENT")) == frozenset()
    assert "CPF2204" in run(store, "SECADMIN", "CHGUSRPRF NOSUCH TEXT(x)")


def test_changing_class_to_one_that_adds_authorities_is_checked(store):
    assert "CPF2269" in run(store, "SECADMIN", "CHGUSRPRF STUDENT USRCLS(*SECADM)")
    assert "CPF2291" in run(store, "SECADMIN", "CHGUSRPRF STUDENT USRCLS(*SYSOPR)")   # *JOBCTL, *SAVSYS not held
    assert "changed" in run(store, "SECADMIN", "CHGUSRPRF STUDENT USRCLS(*PGMR)")     # adds nothing at level 40


# -- display ---------------------------------------------------------------------------------------------

def test_display_needs_read_to_the_profile(store):
    assert execute(store, store.get("QSECOFR"), "DSPUSRPRF STUDENT").view[0] == "dspusrprf"
    assert execute(store, store.get("STUDENT"), "DSPUSRPRF STUDENT").view[0] == "dspusrprf"   # itself
    assert "CPF2217" in run(store, "STUDENT", "DSPUSRPRF DEVELOPER")
    assert "CPF2204" in run(store, "QSECOFR", "DSPUSRPRF NOSUCH")


def test_display_only_knows_basic_and_screen_output(store):
    assert "TYPE" in run(store, "QSECOFR", "DSPUSRPRF STUDENT TYPE(*ALL)")
    assert "OUTPUT" in run(store, "QSECOFR", "DSPUSRPRF STUDENT OUTPUT(*PRINT)")


# -- work with -------------------------------------------------------------------------------------------

def test_wrkusrprf_lists_only_what_you_have_authority_to(store):
    everyone = execute(store, store.get("QSECOFR"), "WRKUSRPRF").view[1]
    assert len(everyone) == len(store.profiles)
    assert [p.name for p in execute(store, store.get("STUDENT"), "WRKUSRPRF").view[1]] == ["STUDENT"]
    generic = execute(store, store.get("QSECOFR"), "WRKUSRPRF DEV*").view[1]
    assert [p.name for p in generic] == ["DEVADMIN", "DEVELOPER"]


# -- delete ------------------------------------------------------------------------------------------------

def test_delete_needs_secadm_and_authority_to_the_profile(store):
    run(store, "QSECOFR", "CRTUSRPRF TEMP")
    assert "CPF2229" in run(store, "STUDENT", "DLTUSRPRF TEMP")
    assert "CPF2229" in run(store, "DEVADMIN", "DLTUSRPRF TEMP")
    assert "deleted" in run(store, "QSECOFR", "DLTUSRPRF TEMP")
    assert store.get("TEMP") is None


def test_protected_profiles_cannot_be_deleted(store):
    for name in ("QSECOFR", "QDFTOWN"):
        assert "CPF2203" in run(store, "QSECOFR", f"DLTUSRPRF {name}")
        assert store.get(name)


def test_owner_of_objects_is_not_deleted_by_default(store):
    assert "CPF2215" in run(store, "QSECOFR", "DLTUSRPRF STUDENT")
    assert store.get("STUDENT") and store.find_library("SCRATCH").owner == "STUDENT"


def test_ownobjopt_chgown_moves_objects_and_cleans_references(store):
    assert "deleted" in run(store, "QSECOFR", "DLTUSRPRF DEVELOPER OWNOBJOPT(*CHGOWN QSECOFR)")
    assert store.find_library("SRCLIB").owner == "QSECOFR"
    assert "DEVELOPER" not in store.objects[("APPLIB", "CUSTOMERS", "*FILE")].private


def test_ownobjopt_dlt_removes_owned_objects(store):
    assert "deleted" in run(store, "QSECOFR", "DLTUSRPRF STUDENT OWNOBJOPT(*DLT)")
    assert store.find_library("SCRATCH") is None


def test_chgown_needs_a_real_new_owner(store):
    assert "CPF2204" in run(store, "QSECOFR", "DLTUSRPRF STUDENT OWNOBJOPT(*CHGOWN NOSUCH)")
    assert "needs the name" in run(store, "QSECOFR", "DLTUSRPRF STUDENT OWNOBJOPT(*CHGOWN)")
    assert store.get("STUDENT")


def test_deleting_a_group_removes_it_from_its_members(store):
    run(store, "QSECOFR", "DLTUSRPRF GRPDEV")
    assert store.get("DEVELOPER").group_profile is None
    assert "GRPDEV" not in store.find_library("SRCLIB").private


def test_deleting_the_owner_of_profiles_hands_them_to_qdftown(store):
    run(store, "QSECOFR", "CRTUSRPRF BOSS SPCAUT(*SECADM)")
    run(store, "BOSS", "CRTUSRPRF KID")
    assert store.get("KID").owner == "BOSS"
    run(store, "QSECOFR", "DLTUSRPRF BOSS")
    assert store.get("KID").owner == "QDFTOWN"


def test_cannot_delete_a_profile_someone_is_signed_on_under(store):
    c = SignonController("QPADEV0001", store)
    c.handle("ENTER", {"user": "STUDENT", "password": "STUDENT"})
    assert "CPF2215" in run(store, "QSECOFR", "DLTUSRPRF STUDENT OWNOBJOPT(*DLT)")
    c.close()
    assert "deleted" in run(store, "QSECOFR", "DLTUSRPRF STUDENT OWNOBJOPT(*DLT)")


# -- persistence -------------------------------------------------------------------------------------------

def test_changes_survive_a_restart_and_reset_wipes_them(tmp_path):
    st, db = state.open_store(state_dir=tmp_path)
    run(st, "QSECOFR", "CRTUSRPRF KEEPER PASSWORD(abc) SPCAUT(*JOBCTL)")
    run(st, "QSECOFR", "DLTUSRPRF OLDTEMP")
    run(st, "QSECOFR", "DLTUSRPRF STUDENT OWNOBJOPT(*DLT)")
    db.close()

    again, db2 = state.open_store(state_dir=tmp_path)
    assert again.get("KEEPER").password == "ABC"      # unquoted values are upper-cased
    assert again.special_authorities(again.get("KEEPER")) == {SA.JOBCTL}
    assert again.get("OLDTEMP") is None and again.find_library("SCRATCH") is None
    assert state.to_dict(again) == state.to_dict(st)
    db2.close()

    import shutil
    shutil.rmtree(tmp_path)                       # what reset.sh does
    fresh, db3 = state.open_store(state_dir=tmp_path)
    assert fresh.get("KEEPER") is None and fresh.get("STUDENT") and fresh.get("OLDTEMP")
    db3.close()


def test_round_trip_keeps_every_seed_field(tmp_path):
    seed = profiles.load()
    st, db = state.open_store(state_dir=tmp_path)
    db.close()
    again, db2 = state.open_store(state_dir=tmp_path)
    assert state.to_dict(again) == state.to_dict(seed)
    db2.close()


# -- the session ---------------------------------------------------------------------------------------------

def signed_on(store, user):
    c = SignonController("QPADEV0001", store)
    c.handle("ENTER", {"user": user, "password": user})
    return c


def test_command_line_reports_completion_and_error_messages(store):
    c = signed_on(store, "SECADMIN")
    assert "User profile ZOE created." in texts(c.handle("ENTER", {"command": "crtusrprf zoe"}))
    assert "CPF2214" in texts(c.handle("ENTER", {"command": "crtusrprf zoe"}))
    assert "CPF2217" in texts(c.handle("ENTER", {"command": "dspusrprf qsecofr"}))


def test_signoff_command_and_sessions_are_counted(store):
    c = signed_on(store, "STUDENT")
    assert store.active == {"STUDENT": 1}
    assert "Sign On" in texts(c.handle("ENTER", {"command": "signoff"}))
    assert store.active == {}
    c = signed_on(store, "STUDENT")
    c.close()
    c.close()                                    # closing twice must not go negative
    assert store.active == {}


def test_dspusrprf_screen_and_back(store):
    c = signed_on(store, "QSECOFR")
    s = c.handle("ENTER", {"command": "dspusrprf developer"})
    t = texts(s)
    assert "Display User Profile" in t and "GRPDEV" in t and "SECADMIN" in t     # owner shown
    assert not s.inputs()
    assert "Selection or command" in texts(c.handle("ENTER", {}))
    c.handle("ENTER", {"command": "dspusrprf developer"})
    assert "Selection or command" in texts(c.handle("F3", {}))
    assert c.profile is not None                  # F3 here leaves the display, not the session


def test_wrkusrprf_option_5_and_paging(store):
    c = signed_on(store, "QSECOFR")
    s = c.handle("ENTER", {"command": "wrkusrprf"})
    assert "Work with User Profiles" in texts(s) and "More..." in texts(s)
    names = [f.text for f in s.fields if isinstance(f, Text) and f.col == 7 and f.row >= 5]
    assert names == sorted(store.profiles)[:15]
    page2 = texts(c.handle("ROLLUP", {}))
    assert "Bottom" in page2 and sorted(store.profiles)[15] in page2
    assert "More..." in texts(c.handle("ROLLDOWN", {}))
    d = c.handle("ENTER", {"opt2": "5"})                      # third row on page one
    assert "Display User Profile" in texts(d) and sorted(store.profiles)[2] in texts(d)
    assert "Work with User Profiles" in texts(c.handle("ENTER", {}))   # back to the list
    assert "Option 9 is not valid" in texts(c.handle("ENTER", {"opt0": "9"}))
    assert "Selection or command" in texts(c.handle("F12", {}))


def test_wrkusrprf_option_5_rechecks_authority(store):
    run(store, "QSECOFR", "CRTUSRPRF AAA")                       # sorts first
    c = signed_on(store, "QSECOFR")
    c.handle("ENTER", {"command": "wrkusrprf"})
    run(store, "QSECOFR", "DLTUSRPRF AAA")                       # gone while the list is on screen
    assert "CPF2204" in texts(c.handle("ENTER", {"opt0": "5"}))


# -- rendering -----------------------------------------------------------------------------------------------------

def test_every_new_screen_renders_for_every_profile(store):
    for name in store.profiles:
        c = SignonController("QPADEV0001", store)
        c.profile = store.get(name)
        render(c.handle("ENTER", {"command": f"dspusrprf {name}"}))
    c = signed_on(store, "QSECOFR")
    render(c.handle("ENTER", {"command": "wrkusrprf"}))
    render(c.handle("ROLLUP", {}))


def test_dsp_values_wrap_inside_the_screen(store):
    render(signed_on(store, "QSECOFR").handle("ENTER", {"command": "dspusrprf qsecofr"}))
    p = store.get("QSECOFR")
    p.supplemental_groups = ["GRPDEV"] * 15
    render(signed_on(store, "QSECOFR").handle("ENTER", {"command": "dspusrprf qsecofr"}))
