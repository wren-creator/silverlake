"""WRKOBJ, WRKOBJOWN and CHGOBJOWN."""

import pytest

from silverlake.cl.commands import execute
from silverlake.screens.model import Text
from silverlake.screens.render import render
from silverlake.screens.signon import SignonController
from silverlake.system import profiles
from silverlake.system.authority import Auth


@pytest.fixture
def store():
    return profiles.load()


def run(store, user, line):
    out = execute(store, store.get(user), line)
    return out.message.line() if out.message else ""


def names(store, user, line):
    out = execute(store, store.get(user), line)
    if out.view is None:
        assert "No objects found" in out.message.line(), out.message.line()
        return []
    return [(o.library, o.name, o.type) for o in out.view[1]]


def test_wrkobj_finds_by_generic_name_and_library(store):
    assert ("APPLIB", "PAYROLL", "*FILE") in names(store, "QSECOFR", "WRKOBJ OBJ(APPLIB/PAY*)")
    assert names(store, "QSECOFR", "WRKOBJ OBJ(APPLIB/PAY*) OBJTYPE(*FILE)") == [("APPLIB", "PAYROLL", "*FILE")]
    assert {n for _, n, _ in names(store, "QSECOFR", "WRKOBJ APPLIB/*ALL *FILE")} == {"PAYROLL", "CUSTOMERS"}
    assert "No objects found" in run(store, "QSECOFR", "WRKOBJ OBJ(APPLIB/ZZ*)")


def test_wrkobj_library_specs(store):
    assert all(lib != "QSYS" for lib, _, _ in names(store, "QSECOFR", "WRKOBJ OBJ(*ALLUSR/*ALL) OBJTYPE(*FILE)"))
    assert ("QSYS", "CRTLIB", "*CMD") in names(store, "QSECOFR", "WRKOBJ OBJ(*ALL/CRTLIB) OBJTYPE(*CMD)")
    assert ("QSYS", "QGPL", "*LIB") in names(store, "QSECOFR", "WRKOBJ OBJ(QSYS/Q*) OBJTYPE(*LIB)")
    assert "CPF9810" in run(store, "QSECOFR", "WRKOBJ OBJ(NOSUCH/*ALL)")
    # *LIBL searches the job's library list only, and APPLIB is not on it for STUDENT
    assert names(store, "STUDENT", "WRKOBJ OBJ(*ALL) OBJTYPE(*FILE)") == []


def test_only_libraries_you_can_use_and_objects_you_have_authority_to(store):
    run(store, "QSECOFR", "RVKOBJAUT OBJ(APPLIB) OBJTYPE(*LIB) USER(*PUBLIC) AUT(*USE)")
    assert "CPF9820" in run(store, "STUDENT", "WRKOBJ OBJ(APPLIB/*ALL)")
    assert all(lib != "APPLIB" for lib, _, _ in names(store, "STUDENT", "WRKOBJ OBJ(*ALL/*ALL) OBJTYPE(*FILE)"))
    # SRCLIB/QRPGSRC is wide open but its library is locked, so it never shows
    assert ("SRCLIB", "QRPGSRC", "*FILE") not in names(store, "STUDENT", "WRKOBJ OBJ(*ALL/*ALL) OBJTYPE(*FILE)")
    # PAYROLL is *EXCLUDE to STUDENT, so even in a usable library it is not shown
    run(store, "QSECOFR", "GRTOBJAUT OBJ(APPLIB) OBJTYPE(*LIB) USER(*PUBLIC) AUT(*USE)")
    assert ("APPLIB", "PAYROLL", "*FILE") not in names(store, "STUDENT", "WRKOBJ OBJ(APPLIB/*ALL) OBJTYPE(*FILE)")
    assert ("APPLIB", "PAYROLL", "*FILE") in names(store, "OPERATOR", "WRKOBJ OBJ(APPLIB/*ALL) OBJTYPE(*FILE)")


def test_wrkobj_rejects_bad_names_and_unmodeled_types(store):
    assert "not valid" in run(store, "QSECOFR", "WRKOBJ OBJ(APPLIB/A*B)")
    assert "not modeled" in run(store, "QSECOFR", "WRKOBJ OBJ(APPLIB/*ALL) OBJTYPE(*DTAARA)")


def test_wrkobjown(store):
    mine = names(store, "QSECOFR", "WRKOBJOWN")
    assert all(o in names(store, "QSECOFR", "WRKOBJOWN USRPRF(*CURRENT)") for o in mine)
    assert ("APPLIB", "PAYROLL", "*FILE") in names(store, "QSECOFR", "WRKOBJOWN USRPRF(*CURRENT) OBJTYPE(*FILE)")
    assert "CPF2204" in run(store, "QSECOFR", "WRKOBJOWN USRPRF(NOBODY)")
    assert "CPF2217" in run(store, "STUDENT", "WRKOBJOWN USRPRF(QSECOFR)")


def test_chgobjown_moves_the_owner_and_revokes_or_keeps_the_old_one(store):
    obj = store.objects[("APPLIB", "CUSTOMERS", "*FILE")]
    old = obj.owner
    assert "changed" in run(store, "QSECOFR", "CHGOBJOWN OBJ(APPLIB/CUSTOMERS) OBJTYPE(*FILE) NEWOWN(STUDENT)")
    assert obj.owner == "STUDENT" and old not in obj.private
    assert "changed" in run(store, "QSECOFR", "CHGOBJOWN APPLIB/CUSTOMERS *FILE DEVELOPER CUROWNAUT(*SAME)")
    assert obj.owner == "DEVELOPER" and "STUDENT" in obj.private and "DEVELOPER" not in obj.private


def test_chgobjown_authority_rules(store):
    assert "CPF2204" in run(store, "QSECOFR", "CHGOBJOWN APPLIB/CUSTOMERS *FILE NOBODY")
    assert "CPF2208" in run(store, "QSECOFR", "CHGOBJOWN APPLIB/NOPE *FILE STUDENT")
    # STUDENT holds no *OBJEXIST on the file
    assert "CPF2230" in run(store, "STUDENT", "CHGOBJOWN APPLIB/CUSTOMERS *FILE STUDENT")
    # give STUDENT the object authority, but not authority to the profile of its present owner
    run(store, "QSECOFR", "GRTOBJAUT OBJ(APPLIB/CUSTOMERS) OBJTYPE(*FILE) USER(STUDENT) AUT(*ALL)")
    assert "CPF2233" in run(store, "STUDENT", "CHGOBJOWN APPLIB/CUSTOMERS *FILE STUDENT")
    # a user may always add to and manage their own profile, so a new owner of STUDENT clears CPF2232
    assert "CPF2232" in run(store, "STUDENT", "CHGOBJOWN APPLIB/CUSTOMERS *FILE DEVELOPER")


def test_screens_render(store):
    c = SignonController("QPADEV0001", store)
    c.handle("ENTER", {"user": "QSECOFR", "password": "QSECOFR"})
    s = c.handle("ENTER", {"command": "wrkobj *allusr/*all"})
    assert "Work with Objects" in " | ".join(f.text for f in s.fields if isinstance(f, Text))
    render(s)
    c.handle("ENTER", {})
    render(c.handle("ENTER", {"command": "wrkobjown usrprf(qsecofr)"}))
    assert c.view is not None


def test_commands_are_objects_so_a_site_can_lock_them(store):
    run(store, "QSECOFR", "RVKOBJAUT OBJ(QSYS/CHGOBJOWN) OBJTYPE(*CMD) USER(*PUBLIC) AUT(*USE)")
    assert "Not authorized to command CHGOBJOWN" in run(store, "STUDENT", "CHGOBJOWN A/B *FILE C")


# -- rename and change description ------------------------------------------------------------------------

def test_rnmobj_renames_and_follows_the_page_rules(store):
    assert "renamed" in run(store, "QSECOFR", "RNMOBJ OBJ(APPLIB/CUSTOMERS) OBJTYPE(*FILE) NEWOBJ(CLIENTS)")
    assert ("APPLIB", "CLIENTS", "*FILE") in store.objects and ("APPLIB", "CUSTOMERS", "*FILE") not in store.objects
    assert "CPF2132" in run(store, "QSECOFR", "RNMOBJ APPLIB/CLIENTS *FILE PAYROLL")
    assert "CPF9876" in run(store, "QSECOFR", "RNMOBJ QSYS/CRTLIB *CMD CRTLIB2")
    assert "CPF2166" in run(store, "QSECOFR", "RNMOBJ QSYS/QGPL *LIB APPLIB2")
    assert "CPF2166" in run(store, "QSECOFR", "RNMOBJ QSYS/APPLIB *LIB QGPL")
    assert "CPF2208" in run(store, "QSECOFR", "RNMOBJ APPLIB/NOPE *FILE X")


def test_rnmobj_needs_objmgt_and_update_on_the_library(store):
    # STUDENT has nothing on PAYROLL, and APPLIB gives the public only *USE
    assert "CPF2189" in run(store, "STUDENT", "RNMOBJ APPLIB/PAYROLL *FILE X")
    run(store, "QSECOFR", "GRTOBJAUT OBJ(APPLIB/CUSTOMERS) OBJTYPE(*FILE) USER(STUDENT) AUT(*ALL)")
    assert "CPF2182" in run(store, "STUDENT", "RNMOBJ APPLIB/CUSTOMERS *FILE CLIENTS")  # no *UPD on APPLIB
    run(store, "QSECOFR", "GRTOBJAUT OBJ(APPLIB) OBJTYPE(*LIB) USER(STUDENT) AUT(*CHANGE)")
    run(store, "QSECOFR", "RVKOBJAUT OBJ(APPLIB/CUSTOMERS) OBJTYPE(*FILE) USER(STUDENT) AUT(*OBJMGT)")
    assert "CPF2189" in run(store, "STUDENT", "RNMOBJ APPLIB/CUSTOMERS *FILE CLIENTS")
    run(store, "QSECOFR", "GRTOBJAUT OBJ(APPLIB/CUSTOMERS) OBJTYPE(*FILE) USER(STUDENT) AUT(*ALL)")
    assert "renamed" in run(store, "STUDENT", "RNMOBJ APPLIB/CUSTOMERS *FILE CLIENTS")


def test_renaming_a_library_takes_its_contents_and_the_profiles_pointing_at_it(store):
    assert store.get("CLERK").current_library == "APPLIB"
    assert "renamed" in run(store, "QSECOFR", "RNMOBJ OBJ(QSYS/APPLIB) OBJTYPE(*LIB) NEWOBJ(APPS)")
    assert ("APPS", "PAYROLL", "*FILE") in store.objects and not any(k[0] == "APPLIB" for k in store.objects)
    assert store.get("CLERK").current_library == "APPS"


def test_chgobjd_changes_text(store):
    assert "changed" in run(store, "QSECOFR", "CHGOBJD OBJ(APPLIB/PAYROLL) OBJTYPE(*FILE) TEXT('Payroll, locked')")
    assert store.objects[("APPLIB", "PAYROLL", "*FILE")].text == "Payroll, locked"
    assert run(store, "QSECOFR", "CHGOBJD APPLIB/PAYROLL *FILE") == "Object not changed."
    assert "CPF2189" in run(store, "STUDENT", "CHGOBJD APPLIB/PAYROLL *FILE TEXT('x')")


# -- the work lists on the screen ---------------------------------------------------------------------------

def _signed(store, user="QSECOFR"):
    c = SignonController("QPADEV0001", store)
    c.handle("ENTER", {"user": user, "password": user})
    return c


def _field_map(screen):
    return {(f.row, f.col): f for f in screen.fields}


def test_wrkobj_layout_follows_the_capture(store):
    c = _signed(store)
    s = c.handle("ENTER", {"command": "wrkobj applib/*all *file"})
    f = _field_map(s)
    assert f[(0, 31)].text == "Work with Objects" and f[(3, 47)].text == "5=Display authority"
    assert f[(6, 52)].text == "Text" and f[(19, 1)].text == "Parameters for options 5, 7 and 13 or command"
    inputs = {(i.row, i.col): i for i in s.inputs()}
    assert (7, 1) in inputs and inputs[(7, 1)].length == 2
    assert (20, 6) in inputs and inputs[(20, 6)].length == 73
    assert f[(7, 6)].text == "CUSTOMERS" and f[(7, 18)].text == "*FILE" and f[(7, 28)].text == "APPLIB"


def test_wrkobjown_layout_follows_the_capture(store):
    c = _signed(store)
    s = c.handle("ENTER", {"command": "wrkobjown usrprf(qsecofr) objtype(*lib)"})
    f = _field_map(s)
    assert f[(2, 32)].text == "QSECOFR" and f[(6, 27)].text == "9=Change owner" and f[(9, 42)].text == "Type"
    assert f[(10, 64)].text == "*SYSBAS" and f[(10, 52)].text == "PROD"
    ins = {(i.row, i.col): i for i in s.inputs()}
    assert (10, 2) in ins and ins[(10, 2)].length == 1 and ins[(10, 2)].monocase and (20, 6) in ins


def test_wrkautl_layout_has_the_create_row(store):
    c = _signed(store)
    s = c.handle("ENTER", {"command": "wrkautl"})
    inputs = {(i.row, i.col): i for i in s.inputs()}
    assert (7, 1) in inputs and (7, 6) in inputs and inputs[(7, 6)].length == 10 and (8, 1) in inputs
    assert _field_map(s)[(8, 6)].text == "PAYAUTL"


def test_option_5_shows_authority_and_comes_back_to_the_list(store):
    c = _signed(store)
    c.handle("ENTER", {"command": "wrkobj applib/*all *file"})
    s = c.handle("ENTER", {"opt0": "5"})                       # CUSTOMERS
    assert "Display Object Authority" in " | ".join(f.text for f in s.fields if isinstance(f, Text))
    s = c.handle("ENTER", {})
    assert "Work with Objects" in " | ".join(f.text for f in s.fields if isinstance(f, Text))


def test_option_7_uses_the_command_line_for_the_new_name_and_refreshes_the_list(store):
    c = _signed(store)
    c.handle("ENTER", {"command": "wrkobj applib/*all *file"})
    s = c.handle("ENTER", {"opt0": "7"})
    assert "Type the new name" in " | ".join(f.text for f in s.fields if isinstance(f, Text))
    s = c.handle("ENTER", {"opt0": "7", "command": "clients"})
    t = " | ".join(f.text for f in s.fields if isinstance(f, Text))
    assert "CLIENTS" in t and "renamed" in t and ("APPLIB", "CLIENTS", "*FILE") in store.objects


def test_option_13_changes_the_text(store):
    c = _signed(store)
    c.handle("ENTER", {"command": "wrkobj applib/customers *file"})
    s = c.handle("ENTER", {"opt0": "13", "command": "Who we sell to"})
    assert store.objects[("APPLIB", "CUSTOMERS", "*FILE")].text == "Who we sell to"
    assert "Who we sell to" in " | ".join(f.text for f in s.fields if isinstance(f, Text))


def test_wrkobjown_option_9_changes_the_owner(store):
    c = _signed(store)
    c.handle("ENTER", {"command": "wrkobjown usrprf(qsecofr) objtype(*file)"})
    names = [r.name for r in c.view[1].rows]
    s = c.handle("ENTER", {"opt0": "9", "command": "student"})
    assert store.objects[next(k for k in store.objects if k[1] == names[0])].owner == "STUDENT"


def test_unbuilt_options_say_so_and_bad_ones_are_invalid(store):
    c = _signed(store)
    c.handle("ENTER", {"command": "wrkobj applib/*all *file"})
    assert "Option 4 is not available" in " | ".join(f.text for f in c.handle("ENTER", {"opt0": "4"}).fields if isinstance(f, Text))
    assert "Option 6 is not valid" in " | ".join(f.text for f in c.handle("ENTER", {"opt0": "6"}).fields if isinstance(f, Text))


def test_wrkautl_options(store):
    c = _signed(store)
    c.handle("ENTER", {"command": "wrkautl"})
    s = c.handle("ENTER", {"opt0": "5"})
    assert "Display Authorization List" in " | ".join(f.text for f in s.fields if isinstance(f, Text))
    c.handle("ENTER", {})
    s = c.handle("ENTER", {"opt0": "8"})
    t = " | ".join(f.text for f in s.fields if isinstance(f, Text))
    assert "PAYROLL" in t and "Display Authorization List Objects" in t
    c.handle("ENTER", {})
    s = c.handle("ENTER", {"optnew": "1", "newname": "fresh"})
    assert "FRESH" in store.autls and "FRESH" in " | ".join(f.text for f in s.fields if isinstance(f, Text))
    assert "needs a name" in " | ".join(f.text for f in c.handle("ENTER", {"optnew": "1"}).fields if isinstance(f, Text))


def test_a_command_on_the_list_command_line_runs_and_the_list_stays(store):
    c = _signed(store)
    c.handle("ENTER", {"command": "wrkautl"})
    s = c.handle("ENTER", {"command": "crtautl zzlist"})
    assert "ZZLIST" in store.autls and "ZZLIST" in " | ".join(f.text for f in s.fields if isinstance(f, Text))
    c.handle("F12", {})
    assert c.view is None


def test_paging_and_f3_on_a_work_list(store):
    for i in range(25):
        run(store, "QSECOFR", f"CRTAUTL L{i:02d}")
    c = _signed(store)
    s = c.handle("ENTER", {"command": "wrkautl"})
    assert "More..." in " | ".join(f.text for f in s.fields if isinstance(f, Text))
    s = c.handle("ROLLUP", {})
    assert c.view[1].page == 1
    c.handle("ROLLDOWN", {})
    assert c.view[1].page == 0
    assert "Main Menu" in " | ".join(f.text for f in c.handle("F3", {}).fields if isinstance(f, Text))
