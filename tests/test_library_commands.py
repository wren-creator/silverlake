"""CRTLIB, DLTLIB, the library list, WRKLIB, DSPOBJAUT, GRTOBJAUT, RVKOBJAUT."""

import pytest

from silverlake.cl.commands import execute
from silverlake.cl.session import Session
from silverlake.screens.model import Text
from silverlake.screens.render import render
from silverlake.screens.signon import SignonController
from silverlake.system import admin, profiles, state
from silverlake.system.authority import ALL, CHANGE, EXCLUDE, USE, Auth
from silverlake.system.authority import SecuredObject

CUST = ("APPLIB", "CUSTOMERS", "*FILE")
QSRC = ("SRCLIB", "QRPGSRC", "*FILE")
PAY = ("APPLIB", "PAYROLL", "*FILE")


@pytest.fixture
def store():
    return profiles.load()


def run(store, user, line, session=None):
    out = execute(store, store.get(user), line, session)
    return out.message.line() if out.message else (out.view[0] if out.view else "")


def texts(screen):
    return " | ".join(f.text for f in screen.fields if isinstance(f, Text))


# -- CRTLIB ------------------------------------------------------------------------------------------

def test_crtlib_defaults(store):
    assert run(store, "STUDENT", "CRTLIB LIB(MYLIB) TEXT('mine')") == "Library MYLIB created."
    lib = store.find_library("MYLIB")
    assert lib.owner == "STUDENT" and lib.public == CHANGE and lib.text == "mine" and lib.type == "*LIB"


def test_crtlib_aut_option_and_positional(store):
    run(store, "STUDENT", "CRTLIB LIB(SECRET) AUT(*EXCLUDE)")
    assert store.find_library("SECRET").public == EXCLUDE
    run(store, "STUDENT", "CRTLIB POSLIB")
    assert store.find_library("POSLIB")


def test_crtlib_refusals(store):
    assert "CPF2111" in run(store, "STUDENT", "CRTLIB APPLIB")
    assert "CPF2166" in run(store, "STUDENT", "CRTLIB 1BAD")
    assert "created" in run(store, "GUEST", "CRTLIB MYLIB")       # no authority check; see objects.py


# -- DLTLIB --------------------------------------------------------------------------------------------

def test_dltlib_needs_use_and_objexist_on_the_library(store):
    assert "CPF2182" in run(store, "STUDENT", "DLTLIB APPLIB")           # *USE only
    assert store.find_library("APPLIB")
    assert "CPF2110" in run(store, "STUDENT", "DLTLIB NOSUCH")


def test_dltlib_system_libraries_and_the_library_list(store):
    assert "CPF2129" in run(store, "QSECOFR", "DLTLIB QGPL")
    s = Session()
    run(store, "STUDENT", "CRTLIB MYLIB")
    run(store, "STUDENT", "ADDLIBLE MYLIB", s)
    assert "CPF2167" in run(store, "STUDENT", "DLTLIB MYLIB", s)
    run(store, "STUDENT", "RMVLIBLE MYLIB", s)
    assert "deleted" in run(store, "STUDENT", "DLTLIB MYLIB", s)


def test_dltlib_takes_its_contents(store):
    run(store, "STUDENT", "CRTLIB MYLIB")
    store.objects[("MYLIB", "F1", "*FILE")] = SecuredObject("F1", "STUDENT", library="MYLIB", type="*FILE")
    assert "deleted" in run(store, "STUDENT", "DLTLIB MYLIB")
    assert not [o for o in store.objects.values() if o.library == "MYLIB"]


def test_dltlib_cannot_delete_what_you_have_no_objexist_to(store):
    run(store, "STUDENT", "CRTLIB MYLIB")
    store.objects[("MYLIB", "THEIRS", "*FILE")] = SecuredObject(
        "THEIRS", "QSECOFR", public=EXCLUDE, library="MYLIB", type="*FILE")
    store.objects[("MYLIB", "MINE", "*FILE")] = SecuredObject("MINE", "STUDENT", library="MYLIB", type="*FILE")
    msg = run(store, "STUDENT", "DLTLIB MYLIB")
    assert "CPF2161" in msg and "CPF2168" in msg
    assert store.find_library("MYLIB") and ("MYLIB", "THEIRS", "*FILE") in store.objects
    assert ("MYLIB", "MINE", "*FILE") not in store.objects            # what could be deleted was


# -- the library list --------------------------------------------------------------------------------------

def test_default_list_and_addlible_positions(store):
    s = Session()
    assert s.search_order() == ["QSYS", "QSYS2", "QUSRSYS", "QHLPSYS", "QGPL", "QTEMP"]   # as on a real system
    run(store, "QSECOFR", "ADDLIBLE APPLIB", s)
    assert s.user_libs == ["APPLIB", "QGPL", "QTEMP"]
    run(store, "QSECOFR", "ADDLIBLE SCRATCH POSITION(*LAST)", s)
    run(store, "QSECOFR", "ADDLIBLE SRCLIB POSITION(*AFTER APPLIB)", s)
    assert s.user_libs == ["APPLIB", "SRCLIB", "QGPL", "QTEMP", "SCRATCH"]
    run(store, "QSECOFR", "CRTLIB NEWL")
    run(store, "QSECOFR", "ADDLIBLE NEWL POSITION(*BEFORE QGPL)", s)
    assert s.user_libs == ["APPLIB", "SRCLIB", "NEWL", "QGPL", "QTEMP", "SCRATCH"]
    run(store, "QSECOFR", "CRTLIB OTHER")
    run(store, "QSECOFR", "ADDLIBLE OTHER POSITION(*REPLACE SRCLIB)", s)
    assert s.user_libs == ["APPLIB", "OTHER", "NEWL", "QGPL", "QTEMP", "SCRATCH"]


def test_addlible_and_rmvlible_refusals(store):
    s = Session()
    assert "CPF2110" in run(store, "STUDENT", "ADDLIBLE NOSUCH", s)
    assert "CPF2182" in run(store, "STUDENT", "ADDLIBLE SRCLIB", s)          # no authority to the library
    assert "CPF2103" in run(store, "STUDENT", "ADDLIBLE QGPL", s)
    assert "CPF2149" in run(store, "STUDENT", "RMVLIBLE QSYS", s)            # system portion stays
    assert "CPF2149" in run(store, "STUDENT", "ADDLIBLE APPLIB POSITION(*AFTER NOWHERE)", s)
    assert "not valid" in run(store, "STUDENT", "ADDLIBLE APPLIB POSITION(*MIDDLE)", s)
    assert s.user_libs == ["QGPL", "QTEMP"]


def test_unqualified_names_resolve_through_the_library_list(store):
    s = Session()
    assert "CPF2208" in run(store, "STUDENT", "DSPOBJAUT OBJ(CUSTOMERS) OBJTYPE(*FILE)", s)
    run(store, "STUDENT", "ADDLIBLE APPLIB", s)
    assert run(store, "STUDENT", "DSPOBJAUT OBJ(CUSTOMERS) OBJTYPE(*FILE)", s) == "dspobjaut"
    assert run(store, "STUDENT", "DSPOBJAUT OBJ(SCRATCH) OBJTYPE(*LIB)", s) == "dspobjaut"   # libraries are in QSYS


# -- WRKLIB / DSPLIBL ---------------------------------------------------------------------------------------

def names(out_view):
    return [o.name for o in out_view[1]]


def test_wrklib_shows_only_libraries_you_have_some_authority_to(store):
    s = Session()
    student = execute(store, store.get("STUDENT"), "WRKLIB LIB(*ALL)", s).view
    assert "SRCLIB" not in names(student) and "APPLIB" in names(student) and "SCRATCH" in names(student)
    dev = execute(store, store.get("DEVELOPER"), "WRKLIB LIB(*ALL)", s).view
    assert "SRCLIB" in names(dev)                                 # through GRPDEV
    assert "SRCLIB" in names(execute(store, store.get("QSECOFR"), "WRKLIB *ALL", s).view)


def test_wrklib_patterns(store):
    s = Session()
    def w(line):
        return names(execute(store, store.get("QSECOFR"), line, s).view)
    assert w("WRKLIB") == ["QGPL", "QHLPSYS", "QSYS", "QSYS2", "QTEMP", "QUSRSYS"]   # *LIBL
    assert "QSYS" not in w("WRKLIB LIB(*ALLUSR)") and "APPLIB" in w("WRKLIB LIB(*ALLUSR)")
    assert w("WRKLIB LIB(S*)") == ["SCRATCH", "SRCLIB"]
    assert w("WRKLIB LIB(*USRLIBL)") == ["QGPL", "QTEMP"]
    assert "No libraries" in run(store, "QSECOFR", "WRKLIB LIB(ZZ*)", s)
    assert "not valid" in run(store, "QSECOFR", "WRKLIB LIB(*MID*)", s)


def test_dsplibl_view(store):
    out = execute(store, store.get("STUDENT"), "DSPLIBL", Session.for_profile("SCRATCH"))
    assert out.view[0] == "dsplibl"
    assert out.view[1].entries() == [("QSYS", "SYS"), ("QSYS2", "SYS"), ("QUSRSYS", "SYS"), ("QHLPSYS", "SYS"),
                                     ("SCRATCH", "CUR"), ("QGPL", "USR"), ("QTEMP", "USR")]   # the real order


# -- DSPOBJAUT -----------------------------------------------------------------------------------------------

def rows(store, user, line, s=None):
    out = execute(store, store.get(user), line, s)
    assert out.view and out.view[0] == "dspobjaut", out.message.line() if out.message else out
    return out.view[2]


def test_dspobjaut_shows_the_whole_list_to_whoever_can_manage_it(store):
    r = rows(store, "QSECOFR", "DSPOBJAUT OBJ(APPLIB/CUSTOMERS) OBJTYPE(*FILE)")
    assert r == [("QSECOFR", "*ALL"), ("DEVELOPER", "*CHANGE"), ("GUEST", "*EXCLUDE"), ("*PUBLIC", "*USE")]
    # Anyone else sees only themselves.
    assert rows(store, "STUDENT", "DSPOBJAUT OBJ(APPLIB/CUSTOMERS) OBJTYPE(*FILE)") == [("*PUBLIC", "*USE")]
    assert rows(store, "DEVELOPER", "DSPOBJAUT OBJ(APPLIB/CUSTOMERS) OBJTYPE(*FILE)") == [("DEVELOPER", "*CHANGE")]


def test_dspobjaut_shows_auth_list_as_public(store):
    r = rows(store, "QSECOFR", "DSPOBJAUT OBJ(APPLIB/PAYROLL) OBJTYPE(*FILE)")
    assert r[-1] == ("*PUBLIC", "*AUTL")


def test_dspobjaut_message_ladder(store):
    assert "CPF2209" in run(store, "STUDENT", "DSPOBJAUT OBJ(NOLIB/X) OBJTYPE(*FILE)")
    assert "CPF2216" in run(store, "STUDENT", "DSPOBJAUT OBJ(SRCLIB/QRPGSRC) OBJTYPE(*FILE)")   # library locked
    assert "CPF2208" in run(store, "STUDENT", "DSPOBJAUT OBJ(APPLIB/NOPE) OBJTYPE(*FILE)")
    assert "CPF2207" in run(store, "STUDENT", "DSPOBJAUT OBJ(APPLIB/PAYROLL) OBJTYPE(*FILE)")   # in reach, no authority
    assert "CPF2207" in run(store, "GUEST", "DSPOBJAUT OBJ(APPLIB/CUSTOMERS) OBJTYPE(*FILE)")


def test_dspobjaut_on_a_library_object(store):
    r = rows(store, "QSECOFR", "DSPOBJAUT OBJ(SRCLIB) OBJTYPE(*LIB)")
    assert r == [("DEVELOPER", "*ALL"), ("GRPDEV", "*CHANGE"), ("*PUBLIC", "*EXCLUDE")]


# -- GRTOBJAUT -----------------------------------------------------------------------------------------------------

def test_grant_adds_and_replace_sets(store):
    run(store, "QSECOFR", "GRTOBJAUT OBJ(APPLIB/CUSTOMERS) OBJTYPE(*FILE) USER(STUDENT) AUT(*OBJMGT)")
    assert store.objects[CUST].private["STUDENT"] == Auth.OBJMGT
    run(store, "QSECOFR", "GRTOBJAUT OBJ(APPLIB/CUSTOMERS) OBJTYPE(*FILE) USER(STUDENT) AUT(*READ *UPD)")
    assert store.objects[CUST].private["STUDENT"] == Auth.OBJMGT | Auth.READ | Auth.UPD      # added
    run(store, "QSECOFR", "GRTOBJAUT OBJ(APPLIB/CUSTOMERS) OBJTYPE(*FILE) USER(STUDENT) AUT(*USE) REPLACE(*YES)")
    assert store.objects[CUST].private["STUDENT"] == USE
    run(store, "QSECOFR", "GRTOBJAUT OBJ(APPLIB/CUSTOMERS) OBJTYPE(*FILE) USER(STUDENT) AUT(*EXCLUDE)")
    assert store.objects[CUST].private["STUDENT"] == EXCLUDE                                   # always replaces


def test_grant_to_public_and_several_users(store):
    run(store, "QSECOFR", "GRTOBJAUT APPLIB/CUSTOMERS *FILE USER(*PUBLIC OPERATOR) AUT(*CHANGE)")
    o = store.objects[CUST]
    assert o.public == CHANGE and o.private["OPERATOR"] == CHANGE


def test_who_may_grant(store):
    # STUDENT has no *OBJMGT on CUSTOMERS.
    assert "CPF2223" in run(store, "STUDENT", "GRTOBJAUT APPLIB/CUSTOMERS *FILE USER(STUDENT) AUT(*ALL)")
    # The owner of a library can manage it; a user given *OBJMGT can manage but not pass on *OBJMGT.
    run(store, "QSECOFR", "GRTOBJAUT APPLIB/CUSTOMERS *FILE USER(STUDENT) AUT(*OBJMGT *READ)")
    assert "Authority granted" in run(store, "STUDENT", "GRTOBJAUT APPLIB/CUSTOMERS *FILE USER(OPERATOR) AUT(*USE)")
    assert "CPF2223" in run(store, "STUDENT", "GRTOBJAUT APPLIB/CUSTOMERS *FILE USER(OPERATOR) AUT(*OBJMGT)")
    assert Auth.OBJMGT not in store.objects[CUST].private["OPERATOR"]
    # *ALLOBJ without any entry may.
    assert "Authority granted" in run(store, "SVCACCT", "GRTOBJAUT APPLIB/CUSTOMERS *FILE USER(OPERATOR) AUT(*OBJMGT)")


def test_granting_a_user_authority_to_a_locked_library_opens_what_is_inside(store):
    """The escalation path the library gate invites: the file was never locked,
    the library was. Anyone who can manage the library can open it to anyone."""
    s = Session()
    assert "CPF2216" in run(store, "STUDENT", "DSPOBJAUT OBJ(SRCLIB/QRPGSRC) OBJTYPE(*FILE)", s)
    run(store, "DEVELOPER", "GRTOBJAUT OBJ(SRCLIB) OBJTYPE(*LIB) USER(STUDENT) AUT(*USE)", s)
    assert store.authority_to_object(store.get("STUDENT"), store.objects[QSRC]) == CHANGE
    assert rows(store, "STUDENT", "DSPOBJAUT OBJ(SRCLIB/QRPGSRC) OBJTYPE(*FILE)", s)


def test_grant_refusals(store):
    assert "CPF2290" in run(store, "QSECOFR", "GRTOBJAUT APPLIB/CUSTOMERS *FILE USER(STUDENT) AUT(*EXCLUDE *READ)")
    assert "CPF22A0" in run(store, "QSECOFR", "GRTOBJAUT APPLIB/CUSTOMERS *FILE USER(STUDENT) AUT(*AUTL)")
    assert "CPF2283" in run(store, "QSECOFR", "GRTOBJAUT APPLIB/CUSTOMERS *FILE AUTL(NOLIST)")
    assert "User profile NOBODY not found" in run(store, "QSECOFR", "GRTOBJAUT APPLIB/CUSTOMERS *FILE USER(NOBODY)")
    assert "USER(*ALL)" in run(store, "QSECOFR", "GRTOBJAUT APPLIB/CUSTOMERS *FILE USER(*ALL)")
    assert "Either USER or AUTL" in run(store, "QSECOFR", "GRTOBJAUT APPLIB/CUSTOMERS *FILE")
    assert "CPF2208" in run(store, "QSECOFR", "GRTOBJAUT APPLIB/NOPE *FILE USER(STUDENT)")
    assert "*AUTL needs an authorization list" in run(
        store, "QSECOFR", "GRTOBJAUT APPLIB/CUSTOMERS *FILE USER(*PUBLIC) AUT(*AUTL)")


def test_grant_authorization_list(store):
    run(store, "QSECOFR", "GRTOBJAUT APPLIB/CUSTOMERS *FILE USER(*PUBLIC) AUT(*AUTL) AUTL(PAYAUTL)")
    o = store.objects[CUST]
    assert o.autl == "PAYAUTL" and o.public is None
    assert store.authority_to_object(store.get("OPERATOR"), o) == USE            # on the list
    assert store.authority_to_object(store.get("STUDENT"), o) == EXCLUDE         # list public


def test_setting_an_authorization_list_needs_ownership_or_all(store):
    run(store, "QSECOFR", "GRTOBJAUT APPLIB/CUSTOMERS *FILE USER(STUDENT) AUT(*OBJMGT *READ)")
    assert "CPF2223" in run(store, "STUDENT", "GRTOBJAUT APPLIB/CUSTOMERS *FILE AUTL(PAYAUTL)")
    run(store, "QSECOFR", "GRTOBJAUT APPLIB/CUSTOMERS *FILE USER(STUDENT) AUT(*ALL)")
    assert "Authorization list set" in run(store, "STUDENT", "GRTOBJAUT APPLIB/CUSTOMERS *FILE AUTL(PAYAUTL)")


# -- RVKOBJAUT -----------------------------------------------------------------------------------------------------------

def test_revoke_removes_only_what_is_named(store):
    run(store, "QSECOFR", "RVKOBJAUT OBJ(APPLIB/CUSTOMERS) OBJTYPE(*FILE) USER(DEVELOPER) AUT(*UPD *DLT)")
    assert store.objects[CUST].private["DEVELOPER"] == CHANGE & ~(Auth.UPD | Auth.DLT)


def test_revoking_everything_removes_the_entry_so_the_user_falls_through(store):
    # GUEST has a private *EXCLUDE that beats *PUBLIC *USE. Revoke the entry and public applies again.
    assert store.authority_to_object(store.get("GUEST"), store.objects[CUST]) == EXCLUDE
    run(store, "QSECOFR", "RVKOBJAUT APPLIB/CUSTOMERS *FILE USER(GUEST) AUT(*EXCLUDE)")
    assert "GUEST" not in store.objects[CUST].private
    assert store.authority_to_object(store.get("GUEST"), store.objects[CUST]) == USE
    run(store, "QSECOFR", "RVKOBJAUT APPLIB/CUSTOMERS *FILE USER(DEVELOPER) AUT(*ALL)")
    assert "DEVELOPER" not in store.objects[CUST].private


def test_revoke_all_users_and_public(store):
    run(store, "QSECOFR", "RVKOBJAUT APPLIB/CUSTOMERS *FILE USER(*ALL) AUT(*ALL)")
    assert store.objects[CUST].private == {}
    run(store, "QSECOFR", "RVKOBJAUT APPLIB/CUSTOMERS *FILE USER(*PUBLIC) AUT(*USE)")
    assert store.objects[CUST].public == EXCLUDE
    assert "CPF22A4" in run(store, "QSECOFR", "RVKOBJAUT APPLIB/CUSTOMERS *FILE USER(*PUBLIC) AUT(*EXCLUDE)")


def test_revoke_rules(store):
    assert "CPF2224" in run(store, "STUDENT", "RVKOBJAUT APPLIB/CUSTOMERS *FILE USER(DEVELOPER)")
    assert store.objects[CUST].private["DEVELOPER"] == CHANGE
    assert "CPF22A5" in run(store, "QSECOFR", "RVKOBJAUT APPLIB/CUSTOMERS *FILE AUTL(PAYAUTL)")
    assert "CPF22A0" in run(store, "QSECOFR", "RVKOBJAUT APPLIB/CUSTOMERS *FILE USER(STUDENT) AUT(*AUTL)")
    assert "User profile NOBODY" in run(store, "QSECOFR", "RVKOBJAUT APPLIB/CUSTOMERS *FILE USER(NOBODY)")


def test_revoke_authorization_list(store):
    assert "removed from object" in run(store, "QSECOFR", "RVKOBJAUT APPLIB/PAYROLL *FILE AUTL(PAYAUTL)")
    o = store.objects[PAY]
    assert o.autl is None and o.public == EXCLUDE


# -- binding -------------------------------------------------------------------------------------------------------------------

def test_binder_refusals(store):
    assert "Required parameter OBJTYPE" in run(store, "QSECOFR", "DSPOBJAUT OBJ(APPLIB/CUSTOMERS)")
    assert "Required parameter OBJ" in run(store, "QSECOFR", "GRTOBJAUT")
    assert "not modeled yet" in run(store, "QSECOFR", "DSPOBJAUT OBJ(APPLIB/CUSTOMERS) OBJTYPE(*PGM)")
    assert "Generic names" in run(store, "QSECOFR", "GRTOBJAUT OBJ(APPLIB/*ALL) OBJTYPE(*FILE) USER(STUDENT)")
    assert "Generic names" in run(store, "QSECOFR", "GRTOBJAUT OBJ(APPLIB/CUS*) OBJTYPE(*FILE) USER(STUDENT)")
    assert "AUT not valid" in run(store, "QSECOFR", "GRTOBJAUT APPLIB/CUSTOMERS *FILE STUDENT AUT(*BOGUS)")
    assert "OUTPUT" in run(store, "QSECOFR", "DSPOBJAUT APPLIB/CUSTOMERS *FILE OUTPUT(*PRINT)")


# -- persistence ------------------------------------------------------------------------------------------------------------------

def test_library_and_authority_changes_survive_a_restart(tmp_path):
    st, db = state.open_store(state_dir=tmp_path)
    run(st, "STUDENT", "CRTLIB LIB(KEPT) TEXT('kept')")
    run(st, "QSECOFR", "GRTOBJAUT APPLIB/CUSTOMERS *FILE USER(STUDENT) AUT(*CHANGE)")
    run(st, "QSECOFR", "RVKOBJAUT APPLIB/CUSTOMERS *FILE USER(GUEST) AUT(*EXCLUDE)")
    db.close()
    again, db2 = state.open_store(state_dir=tmp_path)
    assert again.find_library("KEPT").owner == "STUDENT"
    assert again.objects[CUST].private["STUDENT"] == CHANGE and "GUEST" not in again.objects[CUST].private
    assert state.to_dict(again) == state.to_dict(st)
    db2.close()


# -- the session and screens -----------------------------------------------------------------------------------------------------------

def signed_on(store, user):
    c = SignonController("QPADEV0001", store)
    c.handle("ENTER", {"user": user, "password": user})
    return c


def test_library_list_is_per_session(store):
    a, b = signed_on(store, "STUDENT"), signed_on(store, "OPERATOR")
    a.handle("ENTER", {"command": "addlible applib"})
    assert a.session.user_libs == ["APPLIB", "QGPL", "QTEMP"] and b.session.user_libs == ["QGPL", "QTEMP"]
    a.handle("ENTER", {"command": "signoff"})
    c = signed_on(store, "STUDENT")
    assert c.session.user_libs == ["QGPL", "QTEMP"]                  # a new job starts fresh


def test_views_render_page_and_go_back(store):
    c = signed_on(store, "QSECOFR")
    assert "Display Library List" in texts(c.handle("ENTER", {"command": "dsplibl"}))
    assert "Selection or command" in texts(c.handle("ENTER", {}))
    s = c.handle("ENTER", {"command": "wrklib lib(*all)"})
    assert "Work with Libraries" in texts(s) and "APPLIB" in texts(s) and "Bottom" in texts(s)
    assert "Selection or command" in texts(c.handle("F12", {}))
    s = c.handle("ENTER", {"command": "dspobjaut applib/customers *file"})
    t = texts(s)
    assert "Display Object Authority" in t and "DEVELOPER" in t and "*PUBLIC" in t and "*USE" in t
    render(s)
    assert "Selection or command" in texts(c.handle("F3", {}))
    assert c.profile is not None


def test_a_long_list_pages(store):
    for i in range(20):
        run(store, "QSECOFR", f"CRTLIB LIB(LIB{i:02d})")
    c = signed_on(store, "QSECOFR")
    first = texts(c.handle("ENTER", {"command": "wrklib lib(LIB*)"}))
    assert "More..." in first and "LIB00" in first and "LIB19" not in first
    second = texts(c.handle("ROLLUP", {}))
    assert "Bottom" in second and "LIB19" in second
    assert "More..." in texts(c.handle("ROLLDOWN", {}))
    render(c.handle("ROLLUP", {}))


def test_every_view_renders_for_every_profile(store):
    for name in store.profiles:
        c = SignonController("QPADEV0001", store)
        c.profile = store.get(name)
        for line in ("dsplibl", "wrklib lib(*all)", "dspobjaut applib/customers *file"):
            c.view = None
            s = c.handle("ENTER", {"command": line})
            render(s)


# -- facts read off a real IBM i (PUB400, DSPOBJAUT and DSPLIBL as a basic user) ----------------------------------

def test_the_system_libraries_match_what_a_real_system_showed(store):
    qsys, qgpl = store.find_library("QSYS"), store.find_library("QGPL")
    assert (qsys.owner, qsys.public) == ("QSYS", USE)
    assert (qgpl.owner, qgpl.public) == ("QSYS", CHANGE)
    assert store.get("QSYS").password is None and "QSYS" in admin.PROTECTED


def test_a_basic_user_asking_about_qsys_gets_one_public_row(store):
    """Seen on a real system: DSPOBJAUT OBJ(QSYS) OBJTYPE(*LIB) as an ordinary user lists only *PUBLIC *USE."""
    assert rows(store, "STUDENT", "DSPOBJAUT OBJ(QSYS) OBJTYPE(*LIB)") == [("*PUBLIC", "*USE")]
    assert rows(store, "STUDENT", "DSPOBJAUT OBJ(QGPL) OBJTYPE(*LIB)") == [("*PUBLIC", "*CHANGE")]
    full = rows(store, "QSECOFR", "DSPOBJAUT OBJ(QSYS) OBJTYPE(*LIB)")
    assert full[0] == ("QSYS", "*ALL") and full[-1] == ("*PUBLIC", "*USE")


def test_a_user_with_an_entry_sees_their_own_not_public(store):
    assert rows(store, "DEVELOPER", "DSPOBJAUT OBJ(SRCLIB) OBJTYPE(*LIB)") == [      # an owner can manage, so sees all
        ("DEVELOPER", "*ALL"), ("GRPDEV", "*CHANGE"), ("*PUBLIC", "*EXCLUDE")]
    assert rows(store, "DEVELOPER", "DSPOBJAUT OBJ(APPLIB/CUSTOMERS) OBJTYPE(*FILE)") == [("DEVELOPER", "*CHANGE")]
