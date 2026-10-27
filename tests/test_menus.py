"""Menus, GO, the menu stack, limited capabilities, CALL QCMD, and CHGPRF."""

import pytest

from silverlake.cl.commands import execute
from silverlake.cl.session import MAX_MENUS, Session
from silverlake.screens.model import Input, Text
from silverlake.screens.render import render
from silverlake.screens.signon import SignonController
from silverlake.system import menus, profiles, state
from silverlake.system.objects import SecuredObject


@pytest.fixture
def store():
    return profiles.load()


def texts(screen):
    return " | ".join(f.text for f in screen.fields if isinstance(f, Text))


def sign_on(store, user, **fields):
    c = SignonController("QPADEV0001", store)
    s = c.handle("ENTER", {"user": user, "password": user, **fields})
    return c, s


def cmd(c, line):
    return c.handle("ENTER", {"command": line})


def run(store, user, line):
    out = execute(store, store.get(user), line)
    return out.message.line() if out.message else ""


def add_menu(store, library, name, items, title="Test menu"):
    store.objects[(library, name, "*MENU")] = SecuredObject(
        library=library, name=name, type="*MENU", owner="QSYS", public=profiles.USE,
        data={"title": title, "items": items})


# -- the menu data -------------------------------------------------------------------------------------------

def test_option_one_and_zero_one_are_the_same():
    m = menus.parse({"title": "T", "items": [{"opt": "1", "text": "a", "cmd": "DSPLIBL"}]})
    assert m.find("01") is m.find("1") and m.find("1") is not None
    assert m.find("2") is None and m.find("") is None


@pytest.mark.parametrize("data", [
    {"title": "", "items": []},
    {"title": "x" * 41, "items": []},
    {"title": "T", "items": [{"opt": "100", "text": "a", "cmd": "X"}]},
    {"title": "T", "items": [{"opt": "1", "text": "a", "cmd": "X"}, {"opt": "1", "text": "b", "cmd": "X"}]},
    {"title": "T", "items": [{"opt": "1", "text": "a", "cmd": ""}]},
    {"title": "T", "items": [{"opt": str(i), "text": "a", "cmd": "X"} for i in range(1, 15)]},
])
def test_bad_menus_are_rejected(data):
    with pytest.raises(menus.MenuError):
        menus.parse(data)


def test_every_seed_menu_parses(store):
    found = [k for k in store.objects if k[2] == "*MENU"]
    assert ("QSYS", "MAIN", "*MENU") in found
    for key in found:
        menus.parse(store.objects[key].data, key[1])


# -- the screens ---------------------------------------------------------------------------------------------

def test_menu_geometry_follows_a_real_main_menu(store):
    c, s = sign_on(store, "STUDENT")
    assert "Selection or command" in texts(s)
    cmdfield = next(i for i in s.inputs() if i.name == "command")
    assert (cmdfield.row, cmdfield.col, cmdfield.length) == (19, 6, 153)
    assert not cmdfield.monocase


def test_every_profile_gets_screens_that_fit(store):
    for name, p in list(store.profiles.items()):
        if not p.password or p.status != "*ENABLED":
            continue
        c, s = sign_on(store, name)
        render(s)
        render(cmd(c, "x" * 200))
        render(cmd(c, "go menu(*libl/nothere)"))


# -- option dispatch, GO and the stack -----------------------------------------------------------------------

def test_an_option_runs_its_command(store):
    c, _ = sign_on(store, "STUDENT")
    cmd(c, "1")                                  # option 1 is DSPLIBL
    assert c.view is not None and c.view[0] == "plist"
    assert "Silverlake Main Menu" in texts(c.handle("ENTER", {}))
    cmd(c, "01")                                 # 01 is the same option
    assert c.view is not None


def test_go_pushes_a_menu_and_f12_cancels(store):
    c, _ = sign_on(store, "STUDENT")
    s = cmd(c, "go applib/appmenu")
    assert c.session.menu_stack[-1] == ("APPLIB", "APPMENU")
    assert "APPMENU" in texts(s)
    s = c.handle("F12", {})
    assert c.session.menu_stack == [("QSYS", "MAIN")] and "Silverlake Main Menu" in texts(s)
    c.handle("F12", {})                          # nothing earlier: stays put
    assert c.session.menu_stack == [("QSYS", "MAIN")]


def test_f3_returns_to_where_go_was_typed_with_rtnpnt_yes(store):
    c, _ = sign_on(store, "STUDENT")
    cmd(c, "go applib/appmenu")
    cmd(c, "go applib/restrict")
    assert len(c.session.menu_stack) == 3
    c.handle("F3", {})                                      # back to the menu the second GO was typed on
    assert c.session.menu_stack == [("QSYS", "MAIN"), ("APPLIB", "APPMENU")]
    c.handle("F3", {})
    assert c.session.menu_stack == [("QSYS", "MAIN")]


def test_rtnpnt_no_leaves_no_return_point(store):
    c, _ = sign_on(store, "STUDENT")
    cmd(c, "go applib/appmenu rtnpnt(*no)")
    assert c.session.return_points == []
    c.handle("F3", {})
    assert c.session.menu_stack[-1] == ("APPLIB", "APPMENU")   # F3 had nowhere to go


def test_f3_on_the_initial_menu_does_nothing(store):
    c, _ = sign_on(store, "STUDENT")
    assert "Silverlake Main Menu" in texts(c.handle("F3", {}))
    assert c.profile is not None


def test_the_stack_is_ten_deep(store):
    s = Session()
    for i in range(MAX_MENUS + 3):
        s.push_menu(("L", f"M{i}"), True)
    assert len(s.menu_stack) == MAX_MENUS
    assert s.menu_stack[0] == ("L", "M3")             # the oldest were pushed out
    assert all(0 <= i < MAX_MENUS for i, _ in s.return_points)


def test_unknown_and_unauthorized_menus(store):
    c, _ = sign_on(store, "STUDENT")
    assert "not found" in texts(cmd(c, "go nosuchmenu"))
    run(store, "QSECOFR", "RVKOBJAUT OBJ(APPLIB/APPMENU) OBJTYPE(*MENU) USER(*PUBLIC) AUT(*USE)")
    assert "authorized" in texts(cmd(c, "go applib/appmenu")).lower()
    assert c.session.menu_stack == [("QSYS", "MAIN")]


# -- limited capabilities ------------------------------------------------------------------------------------

def test_lmtcpb_yes_blocks_the_command_line_but_not_menu_options(store):
    c, s = sign_on(store, "CLERK")
    assert "RESTRICT" in texts(s)
    assert "cannot be run from a command line" in texts(cmd(c, "wrkusrprf"))
    assert c.view is None
    cmd(c, "1")                                          # a menu option still runs
    assert c.profile is not None


def test_the_deliberate_hole_option_nine_opens_command_entry(store):
    c, _ = sign_on(store, "CLERK")
    s = cmd(c, "9")
    assert "Command Entry" in texts(s)
    s = cmd(c, "dsplibl")                                 # free commands now, LMTCPB or not
    assert c.view is not None
    c.handle("ENTER", {})
    s = c.handle("F3", {})                                # back to the menu
    assert "Selection or command" in texts(s)


def test_locking_qcmd_closes_the_hole(store):
    run(store, "QSECOFR", "RVKOBJAUT OBJ(QSYS/QCMD) OBJTYPE(*PGM) USER(*PUBLIC) AUT(*USE)")
    c, _ = sign_on(store, "CLERK")
    s = cmd(c, "9")
    assert "Command Entry" not in texts(s)
    assert c.session.mode == "menu"


def test_command_entry_f3_goes_back_to_the_menu_it_came_from(store):
    c, _ = sign_on(store, "STUDENT")
    assert "Command Entry" in texts(cmd(c, "call qcmd"))
    assert "Selection or command" in texts(c.handle("F3", {}))
    assert c.session.mode == "menu"


def test_command_entry_with_no_menu_signs_off_on_f3(store):
    store.get("STUDENT").initial_program = "QCMD"
    store.get("STUDENT").initial_menu = "*SIGNOFF"
    c, s = sign_on(store, "STUDENT")
    assert "Command Entry" in texts(s)
    assert "Sign On" in texts(c.handle("F3", {})) and c.profile is None


@pytest.mark.parametrize("lmt,field,refused", [
    ("*NO", "program", False), ("*NO", "library", False), ("*NO", "menu", False),
    ("*PARTIAL", "program", True), ("*PARTIAL", "library", True), ("*PARTIAL", "menu", False),
    ("*YES", "program", True), ("*YES", "library", True), ("*YES", "menu", True),
])
def test_signon_overrides_follow_limited_capabilities(store, lmt, field, refused):
    store.get("STUDENT").limited_capabilities = lmt
    value = {"program": "QCMD", "library": "APPLIB", "menu": "APPMENU"}[field]
    store.get("STUDENT").current_library = "*CRTDFT"
    c, s = sign_on(store, "STUDENT", **{field: value})
    if refused:
        assert c.profile is None and "Sign On" in texts(s) and "cannot be changed" in texts(s)
        assert store.active == {}
    else:
        assert c.profile is not None


def test_signon_menu_override_lands_on_that_menu(store):
    store.get("STUDENT").limited_capabilities = "*NO"
    c, s = sign_on(store, "STUDENT", menu="applib/appmenu")
    assert c.session.menu_stack == [("APPLIB", "APPMENU")] and "APPMENU" in texts(s)


def test_initial_program_qcmd_starts_command_entry_and_others_refuse(store):
    store.get("STUDENT").initial_program = "QCMD"
    c, s = sign_on(store, "STUDENT")
    assert "Command Entry" in texts(s)
    store2 = profiles.load()
    store2.get("STUDENT").initial_program = "PAYROLL"
    c2, s2 = sign_on(store2, "STUDENT")
    assert c2.profile is None and "not found" in texts(s2)


def test_initial_menu_signoff_signs_straight_off(store):
    store.get("STUDENT").initial_menu = "*SIGNOFF"
    c, s = sign_on(store, "STUDENT")
    assert c.profile is None and "Sign On" in texts(s) and store.active == {}


def test_initial_menu_not_found_falls_to_command_entry_with_the_reason(store):
    store.get("STUDENT").initial_menu = "NOSUCH"
    c, s = sign_on(store, "STUDENT")
    assert "Command Entry" in texts(s) and "not found" in texts(s)


# -- CHGPRF --------------------------------------------------------------------------------------------------

def test_chgprf_rules(store):
    assert "Nothing to change" in run(store, "STUDENT", "CHGPRF")
    assert "changed" in run(store, "STUDENT", "CHGPRF INLMNU(APPLIB/APPMENU)").lower()
    assert store.get("STUDENT").initial_menu == "APPLIB/APPMENU"
    assert "CPF2294" in run(store, "CLERK", "CHGPRF INLPGM(QCMD)")
    store.get("STUDENT").limited_capabilities = "*PARTIAL"
    assert "changed" in run(store, "STUDENT", "CHGPRF INLMNU(MAIN)").lower()
    assert store.get("STUDENT").initial_menu == "MAIN"
    assert "CPF2294" in run(store, "STUDENT", "CHGPRF INLPGM(QCMD)")
    assert "CPF2297" in run(store, "STUDENT", "CHGPRF CURLIB(APPLIB)")
    assert "CPF2295" in run(store, "CLERK", "CHGPRF INLMNU(MAIN)")


def test_chgprf_needs_use_to_the_menu_and_persists(store):
    run(store, "QSECOFR", "RVKOBJAUT OBJ(APPLIB/APPMENU) OBJTYPE(*MENU) USER(*PUBLIC) AUT(*USE)")
    assert "authorized" in run(store, "STUDENT", "CHGPRF INLMNU(APPLIB/APPMENU)").lower()
    run(store, "STUDENT", "CHGPRF INLMNU(MAIN)")
    again = state.from_dict(state.to_dict(store))
    assert again.get("STUDENT").initial_menu == "MAIN"
    assert ("APPLIB", "APPMENU", "*MENU") in again.objects
