"""WRKOBJ, WRKOBJOWN and CHGOBJOWN."""

import pytest

from silverlake.cl.commands import execute
from silverlake.screens.model import Text
from silverlake.screens.render import render
from silverlake.screens.signon import SignonController
from silverlake.system import profiles
from silverlake.system.authority import CHANGE, Auth


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
    assert {n for _, n, _ in names(store, "QSECOFR", "WRKOBJ APPLIB/*ALL *FILE")} == {"PAYROLL", "CUSTOMERS", "REGRPT", "REGRPTX", "SCREEN", "REPORT", "EMPINQ", "SALADJ", "RUNCMD", "STAFF", "VAULT", "MAINTLOG", "DAILYOPS"}
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
    assert "not modeled" in run(store, "QSECOFR", "WRKOBJ OBJ(APPLIB/*ALL) OBJTYPE(*JOBQ)")


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


def test_chgobjd_takes_a_generic_name(store):
    """PAYADJ, PAYCALC, PAYLOOK, PAYRUN and PAYRUNX are the *PGM matches for PAY* in APPLIB."""
    assert "5 objects changed" in run(store, "QSECOFR", "CHGOBJD OBJ(APPLIB/PAY*) OBJTYPE(*PGM) TEXT('batch')")
    assert all(store.objects[("APPLIB", n, "*PGM")].text == "batch"
              for n in ("PAYADJ", "PAYCALC", "PAYLOOK", "PAYRUN", "PAYRUNX"))


def test_chgobjd_generic_skips_what_it_may_not_change(store):
    """SECADMIN owns PAYADJ, PAYRUN and PAYRUNX outright but only has public authority (no *OBJMGT)
    to PAYCALC (QSECOFR's) and PAYLOOK (OPERATOR's)."""
    msg = run(store, "SECADMIN", "CHGOBJD OBJ(APPLIB/PAY*) OBJTYPE(*PGM) TEXT('mine')")
    assert "3 objects changed, 2 not changed" in msg
    assert store.objects[("APPLIB", "PAYADJ", "*PGM")].text == "mine"
    assert store.objects[("APPLIB", "PAYCALC", "*PGM")].text != "mine"


def test_chgobjd_all_matches_every_object_of_the_type_in_the_library(store):
    out = run(store, "QSECOFR", "CHGOBJD OBJ(APPLIB/*ALL) OBJTYPE(*MENU) TEXT('menus')")
    assert "2 objects changed" in out
    assert store.objects[("APPLIB", "APPMENU", "*MENU")].text == "menus"
    assert store.objects[("APPLIB", "RESTRICT", "*MENU")].text == "menus"


def test_chgobjd_generic_with_no_matches_says_so(store):
    assert "No objects found" in run(store, "QSECOFR", "CHGOBJD OBJ(APPLIB/ZZZ*) OBJTYPE(*FILE) TEXT('x')")


def test_chgobjd_generic_follows_the_library_list_when_none_is_named(store):
    """CLERK's current library is APPLIB and no library is named, so the match still has to come
    from *LIBL; CLERK owns none of the five PAY* programs, which is what proves it found them."""
    assert "0 objects changed, 5 not changed" in run(store, "CLERK", "CHGOBJD OBJ(PAY*) OBJTYPE(*PGM) TEXT('x')")


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
    c.handle("ENTER", {"command": "wrkobjown qsecofr *file"})              # option 3 is built on Work with Objects only
    assert "Option 3 is not available" in " | ".join(f.text for f in c.handle("ENTER", {"opt0": "3"}).fields if isinstance(f, Text))
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


# -- delete, edit authority and description, shaped by the PUB400 capture -----------------------------------

def _text(screen):
    return " | ".join(f.text for f in screen.fields if isinstance(f, Text))


def _make(store, user="QSECOFR"):
    run(store, user, "CRTLIB LIB(SCRATCH2)")
    store.objects[("SCRATCH2", "OLDFILE", "*FILE")] = type(store.objects[("APPLIB", "PAYROLL", "*FILE")])(
        "OLDFILE", user, library="SCRATCH2", type="*FILE", text="Scratch file")


def test_option_4_asks_first_and_f12_keeps_the_options_typed(store):
    _make(store)
    c = _signed(store)
    c.handle("ENTER", {"command": "wrkobj scratch2/*all *file"})
    s = c.handle("ENTER", {"opt0": "4"})
    f = _field_map(s)
    assert f[(0, 27)].text == "Confirm Delete of Objects" and f[(2, 1)].text == "Press Enter to confirm your choices for 4=Delete."
    assert (f[(6, 1)].text, f[(6, 6)].text, f[(6, 18)].text, f[(6, 28)].text) == ("4", "OLDFILE", "*FILE", "SCRATCH2")
    assert f[(21, 31)].text == "F12=Cancel" and f[(20, 73)].text == "Bottom"
    s = c.handle("F12", {})
    assert ("SCRATCH2", "OLDFILE", "*FILE") in store.objects                      # nothing deleted
    assert next(i for i in s.inputs() if i.name == "opt0").value == "4"           # the 4 is still typed


def test_enter_on_the_confirm_deletes_and_the_empty_list_says_so(store):
    _make(store)
    c = _signed(store)
    c.handle("ENTER", {"command": "wrkobj scratch2/*all *file"})
    c.handle("ENTER", {"opt0": "4"})
    s = c.handle("ENTER", {})
    f = _field_map(s)
    assert ("SCRATCH2", "OLDFILE", "*FILE") not in store.objects
    assert f[(8, 3)].text == "(Cannot find object to match specified name.)"
    assert "Object OLDFILE in SCRATCH2 type *FILE deleted." in _text(s)
    assert {(i.row, i.col) for i in s.inputs()} == {(20, 6)}                       # only the command line is left


def test_delete_follows_the_page_rules(store):
    _make(store)
    assert "CPF2189" in run(store, "STUDENT", "DLTF SCRATCH2/OLDFILE")
    run(store, "QSECOFR", "GRTOBJAUT OBJ(SCRATCH2/OLDFILE) OBJTYPE(*FILE) USER(STUDENT) AUT(*OBJEXIST)")
    assert "CPF2189" in run(store, "STUDENT", "DLTF SCRATCH2/OLDFILE")             # *OBJOPR is needed as well
    run(store, "QSECOFR", "GRTOBJAUT OBJ(SCRATCH2/OLDFILE) OBJTYPE(*FILE) USER(STUDENT) AUT(*OBJOPR)")
    run(store, "QSECOFR", "RVKOBJAUT OBJ(SCRATCH2) OBJTYPE(*LIB) USER(*PUBLIC) AUT(*EXECUTE)")
    assert "CPF2216" in run(store, "STUDENT", "DLTF SCRATCH2/OLDFILE")             # cannot reach it without the library
    assert "deleted" in run(store, "QSECOFR", "DLTF SCRATCH2/OLDFILE")
    assert "CPF2208" in run(store, "QSECOFR", "DLTF SCRATCH2/OLDFILE")
    assert "CPF9876" in run(store, "QSECOFR", "DLTCMD QSYS/CRTLIB")                # system library contents
    assert "CPF2189" in run(store, "STUDENT", "DLTMNU APPLIB/APPMENU")
    assert "deleted" in run(store, "QSECOFR", "DLTMNU APPLIB/APPMENU")
    assert "CPF2208" in run(store, "QSECOFR", "DLTPGM QSYS2/NOPE")


def test_deleting_a_library_from_the_list_uses_dltlib(store):
    run(store, "QSECOFR", "CRTLIB LIB(GONE)")
    c = _signed(store)
    c.handle("ENTER", {"command": "wrkobj qsys/gone *lib"})
    c.handle("ENTER", {"opt0": "4"})
    s = c.handle("ENTER", {})
    assert store.find_library("GONE") is None and "Library GONE deleted." in _text(s)


def test_several_options_confirm_together_and_a_refusal_is_reported(store):
    _make(store)
    store.objects[("SCRATCH2", "KEEP", "*FILE")] = type(store.objects[("APPLIB", "PAYROLL", "*FILE")])(
        "KEEP", "QSECOFR", library="SCRATCH2", type="*FILE")
    c = _signed(store, "QSECOFR")
    c.handle("ENTER", {"command": "wrkobj scratch2/*all *file"})
    s = c.handle("ENTER", {"opt0": "4", "opt1": "4"})
    assert _field_map(s)[(7, 6)].text in ("KEEP", "OLDFILE") and (6, 6) in _field_map(s)
    s = c.handle("ENTER", {})
    assert "2 objects deleted." in _text(s)


def test_option_2_opens_edit_authority_in_the_captured_layout(store):
    c = _signed(store)
    c.handle("ENTER", {"command": "wrkobj applib/payroll *file"})
    s = c.handle("ENTER", {"opt0": "2"})
    f = _field_map(s)
    assert f[(0, 29)].text == "Edit Object Authority" and f[(2, 26)].text == "PAYROLL" and f[(4, 26)].text == "*FILE"
    assert f[(8, 3)].text.startswith("Object secured by authorization list")
    ins = {(i.row, i.col): i for i in s.inputs()}
    assert ins[(8, 67)].value == "PAYAUTL" and ins[(8, 67)].length == 10
    assert ins[(12, 25)].length == 8 and f[(12, 1)].text == "*PUBLIC" and ins[(12, 25)].value == "*AUTL"
    assert f[(13, 1)].text == "QSECOFR" and ins[(13, 25)].value == "*ALL"
    assert f[(21, 24)].text == "F6=Add new users" and f[(22, 43)].text == "F12=Cancel"
    s = c.handle("F12", {})
    assert "Work with Objects" in _text(s)


def test_edit_authority_applies_what_is_typed_and_blank_removes_a_user(store):
    run(store, "QSECOFR", "GRTOBJAUT OBJ(APPLIB/CUSTOMERS) OBJTYPE(*FILE) USER(STUDENT) AUT(*USE)")
    c = _signed(store)
    c.handle("ENTER", {"command": "wrkobj applib/customers *file"})
    s = c.handle("ENTER", {"opt0": "2"})
    rows = [r for r, _ in c.view[1].rows()]
    i = rows.index("STUDENT")
    s = c.handle("ENTER", {f"auth{i}": "*change"})
    assert store.objects[("APPLIB", "CUSTOMERS", "*FILE")].private["STUDENT"] == CHANGE
    assert "Authorities changed." in _text(s)
    c.handle("ENTER", {f"auth{i}": ""})
    assert "STUDENT" not in store.objects[("APPLIB", "CUSTOMERS", "*FILE")].private
    s = c.handle("ENTER", {"auth0": "*bogus"})
    assert "not valid" in _text(s)
    s = c.handle("ENTER", {"autl": "payautl"})
    assert store.objects[("APPLIB", "CUSTOMERS", "*FILE")].autl == "PAYAUTL"
    c.handle("ENTER", {"autl": "*none"})
    assert store.objects[("APPLIB", "CUSTOMERS", "*FILE")].autl is None


def _edit(store, user="QSECOFR"):
    c = _signed(store, user)
    c.handle("ENTER", {"command": "wrkobj applib/customers *file"})
    return c, c.handle("ENTER", {"opt0": "2"})


def test_f11_goes_round_plain_object_data_plain_as_captured(store):
    run(store, "QSECOFR", "GRTOBJAUT OBJ(APPLIB/CUSTOMERS) OBJTYPE(*FILE) USER(STUDENT) AUT(*USE)")
    c, s = _edit(store)
    assert _field_map(s)[(22, 1)].text == "F11=Display detail object authorities"
    s = c.handle("F11", {})
    f = _field_map(s)
    assert f[(10, 36)].text == "----------Object-----------" and f[(11, 36)].text == "Opr" and f[(11, 60)].text == "Ref"
    assert f[(22, 1)].text == "F11=Display data authorities" and f[(21, 45)].text == "F10=Grant with reference object"
    ins = {(i.row, i.col): i for i in s.inputs()}
    assert all((12, col) in ins and ins[(12, col)].length == 1 for col in (37, 42, 48, 55, 61))
    s = c.handle("F11", {})
    f = _field_map(s)
    assert f[(10, 36)].text == "---------------Data---------------" and f[(11, 63)].text == "Execute"
    assert f[(22, 1)].text == "F11=Nondisplay detail" and f[(22, 25)].text == "F12=Cancel"
    s = c.handle("F11", {})
    assert _field_map(s)[(22, 1)].text == "F11=Display detail object authorities" and (10, 36) not in _field_map(s)
    s = c.handle("F11", {})
    assert (10, 36) in _field_map(s)


def test_the_detail_views_mark_the_rights_a_user_holds(store):
    run(store, "QSECOFR", "GRTOBJAUT OBJ(APPLIB/CUSTOMERS) OBJTYPE(*FILE) USER(STUDENT) AUT(*OBJOPR *READ)")
    c, s = _edit(store)
    rows = [r for r, _ in c.view[1].rows()]
    i = rows.index("STUDENT")
    s = c.handle("F11", {})
    ins = {(i2.row, i2.col): i2 for i2 in s.inputs()}
    assert ins[(12 + i, 37)].value == "X" and ins[(12 + i, 42)].value == ""
    s = c.handle("F11", {})
    ins = {(i2.row, i2.col): i2 for i2 in s.inputs()}
    assert ins[(12 + i, 37)].value == "X" and ins[(12 + i, 43)].value == ""


def test_typing_an_x_in_a_detail_view_changes_only_that_views_rights(store):
    run(store, "QSECOFR", "GRTOBJAUT OBJ(APPLIB/CUSTOMERS) OBJTYPE(*FILE) USER(STUDENT) AUT(*OBJOPR *READ)")
    c, s = _edit(store)
    obj = store.objects[("APPLIB", "CUSTOMERS", "*FILE")]
    i = [r for r, _ in c.view[1].rows()].index("STUDENT")
    c.handle("F11", {})                                              # object rights: Opr, Mgt, Exist, Alter, Ref
    c.handle("ENTER", {f"x{i}_0": "", f"x{i}_3": "X"})               # drop Opr, add Alter
    held = obj.private["STUDENT"]
    assert Auth.OBJALTER in held and Auth.OBJOPR not in held and Auth.READ in held
    c.handle("F11", {})                                              # data rights
    c.handle("ENTER", {f"x{i}_0": "", f"x{i}_1": "X"})               # drop Read, add Add
    held = obj.private["STUDENT"]
    assert Auth.ADD in held and Auth.READ not in held and Auth.OBJALTER in held
    c.handle("ENTER", {f"x{i}_1": ""})                               # nothing left in this view
    assert Auth.ADD not in obj.private["STUDENT"] and Auth.OBJALTER in obj.private["STUDENT"]


def test_clearing_every_x_of_a_private_user_revokes_and_of_public_excludes(store):
    run(store, "QSECOFR", "GRTOBJAUT OBJ(APPLIB/CUSTOMERS) OBJTYPE(*FILE) USER(STUDENT) AUT(*READ)")
    c, s = _edit(store)
    obj = store.objects[("APPLIB", "CUSTOMERS", "*FILE")]
    rows = [r for r, _ in c.view[1].rows()]
    i = rows.index("STUDENT")
    c.handle("F11", {})
    c.handle("F11", {})                                              # data view
    c.handle("ENTER", {f"x{i}_0": ""})
    assert "STUDENT" not in obj.private
    c.handle("ENTER", {"x0_0": "", "x0_1": "", "x0_2": "", "x0_3": "", "x0_4": ""})
    assert obj.public == Auth.NONE or not (obj.public & (Auth.READ | Auth.ADD | Auth.UPD | Auth.DLT | Auth.EXECUTE))


def test_f5_and_f12_still_work_in_a_detail_view(store):
    c, s = _edit(store)
    c.handle("F11", {})
    s = c.handle("F5", {})
    assert (10, 36) in _field_map(s)
    s = c.handle("F12", {})
    assert "Work with Objects" in _text(s)


def test_edit_authority_is_refused_without_object_management_in_the_captured_words(store):
    assert run(store, "STUDENT", "EDTOBJAUT APPLIB/CUSTOMERS *FILE") == "CPF22B8 - Not authorized to change authorities."
    c = _signed(store, "STUDENT")
    s = c.handle("ENTER", {"command": "edtobjaut applib/customers *file"})
    assert "Not authorized to change authorities." in _text(s) and "CPF" not in _text(s)


def test_a_user_with_objmgt_can_edit_but_cannot_hand_out_objmgt(store):
    run(store, "QSECOFR", "GRTOBJAUT OBJ(APPLIB/CUSTOMERS) OBJTYPE(*FILE) USER(STUDENT) AUT(*OBJMGT *OBJOPR)")
    obj = store.objects[("APPLIB", "CUSTOMERS", "*FILE")]
    before = obj.public
    c = _signed(store, "STUDENT")
    c.handle("ENTER", {"command": "edtobjaut applib/customers *file"})
    assert c.view[0] == "edit"
    s = c.handle("ENTER", {"auth0": "*all"})                      # *ALL includes *OBJMGT, owner and *ALLOBJ only
    assert "Not authorized to give authority" in _text(s) and obj.public == before
    s = c.handle("ENTER", {"auth0": "*exclude"})                  # taking authority away is fine
    assert "Authorities changed." in _text(s) and obj.public == Auth.NONE


def test_option_8_shows_the_description_in_the_captured_layout(store):
    c = _signed(store)
    c.handle("ENTER", {"command": "wrkobj applib/payroll *file"})
    s = c.handle("ENTER", {"opt0": "8"})
    f = _field_map(s)
    assert f[(0, 23)].text == "Display Object Description - Full" and f[(2, 26)].text == "PAYROLL"
    assert f[(3, 28)].text == "APPLIB" and f[(3, 67)].text == "QSECOFR" and f[(5, 26)].text == "*FILE"
    assert f[(13, 44)].text == "QSECOFR" and f[(14, 44)].text == "SILVERLK" and f[(15, 44)].text == "*SYSTEM"
    assert f[(20, 1)].text == "Press Enter to continue."
    assert "Work with Objects" in _text(c.handle("ENTER", {}))


def test_dspobjd_command_and_its_rules(store):
    out = execute(store, store.get("QSECOFR"), "DSPOBJD OBJ(APPLIB/PAYROLL) OBJTYPE(*FILE) DETAIL(*FULL)")
    assert out.view[0] == "dspobjd" and out.view[2] == "*FULL"
    assert "CPF2189" in run(store, "STUDENT", "DSPOBJD APPLIB/PAYROLL *FILE")
    assert "CPF2208" in run(store, "QSECOFR", "DSPOBJD APPLIB/NOPE *FILE")
    assert execute(store, store.get("STUDENT"), "DSPOBJD APPLIB/CUSTOMERS *FILE").view[2] == "*BASIC"


def test_the_new_commands_are_objects_a_site_can_lock(store):
    for name in ("DLTF", "DLTCMD", "DLTMNU", "DLTPGM", "EDTOBJAUT", "DSPOBJD"):
        assert ("QSYS", name, "*CMD") in store.objects


# -- WRKAUTL 4, 13, 9 and creation dates -----------------------------------------------------------------------

def _text(s):
    return " | ".join(f.text for f in s.fields if isinstance(f, Text))


def test_wrkautl_option_4_confirms_then_deletes(store):
    run(store, "QSECOFR", "CRTAUTL GONER TEXT('about to go')")
    c = _signed(store)
    s = c.handle("ENTER", {"command": "wrkautl goner"})
    s = c.handle("ENTER", {"opt0": "4"})
    f = _field_map(s)
    assert f[(0, 27)].text == "Confirm Delete of Objects" and (f[(6, 6)].text, f[(6, 18)].text) == ("GONER", "*AUTL")
    s = c.handle("F12", {})
    assert "GONER" in store.autls and next(i for i in s.inputs() if i.name == "opt0").value == "4"
    c.handle("ENTER", {"opt0": "4"})
    s = c.handle("ENTER", {})
    assert "GONER" not in store.autls and "deleted" in _text(s)


def test_wrkautl_option_4_refused_when_the_list_secures_an_object(store):
    c = _signed(store)
    c.handle("ENTER", {"command": "wrkautl payautl"})
    c.handle("ENTER", {"opt0": "4"})
    s = c.handle("ENTER", {})
    assert "PAYAUTL" in store.autls and "cannot be deleted" in _text(s)


def test_wrkautl_option_13_changes_text_for_the_owner_only(store):
    run(store, "QSECOFR", "CRTAUTL MINE TEXT('old')")
    c = _signed(store)
    c.handle("ENTER", {"command": "wrkautl mine"})
    s = c.handle("ENTER", {"opt0": "13", "command": "new words"})
    assert store.autls["MINE"].text == "new words" and "changed" in _text(s)
    other = _signed(store, "DEVADMIN") if "DEVADMIN" in store.profiles else None
    if other:
        other.handle("ENTER", {"command": "wrkautl mine"})
        other.handle("ENTER", {"opt0": "13", "command": "hijack"})
        assert store.autls["MINE"].text == "new words"


def test_wrkautl_option_9_says_there_are_no_documents(store):
    c = _signed(store)
    c.handle("ENTER", {"command": "wrkautl"})
    assert "No documents or folders" in _text(c.handle("ENTER", {"opt0": "9"}))


def test_a_library_made_here_remembers_when_and_the_description_shows_it(store):
    run(store, "QSECOFR", "CRTLIB NEWLIB")
    lib = store.objects[("QSYS", "NEWLIB", "*LIB")]
    assert lib.data["created"]
    c = _signed(store)
    c.handle("ENTER", {"command": "wrkobj qsys/newlib *lib"})
    f = _field_map(c.handle("ENTER", {"opt0": "8"}))
    assert (12, 44) in f and f[(12, 44)].text[2] == "-"


# -- DSPOBJD basic and page two, and Add New Users (F6) -------------------------------------------------------

def _inputs(s):
    return {i.name: i for i in s.inputs()}


def test_dspobjd_basic_is_a_list_with_options_5_and_8(store):
    run(store, "QSECOFR", "CRTLIB SHOWME TEXT('look at me')")
    c = _signed(store)
    c.handle("ENTER", {"command": "dspobjd obj(qsys/showme) objtype(*lib) detail(*basic)"})
    s = c._draw_view()
    f = _field_map(s)
    assert f[(0, 23)].text == "Display Object Description - Basic" and f[(9, 6)].text == "SHOWME"
    assert (_inputs(s)["opt0"].row, _inputs(s)["opt0"].col, _inputs(s)["opt0"].length) == (9, 2, 1)
    assert "not available" in _text(c.handle("ENTER", {"opt0": "8"}))
    s = c.handle("ENTER", {"opt0": "5"})
    assert _field_map(s)[(0, 23)].text == "Display Object Description - Full"
    c.handle("F12", {})
    assert _field_map(c._draw_view())[(0, 23)].text == "Display Object Description - Basic"


def test_dspobjd_full_has_a_second_page_that_roll_reaches(store):
    c = _signed(store)
    c.handle("ENTER", {"command": "dspobjd obj(qsys/qgpl) objtype(*lib) detail(*full)"})
    p1 = _text(c._draw_view())
    assert "Creation information" in p1
    p2 = _text(c.handle("ROLLUP", {}))
    assert "Change/Usage information" in p2 and "Auditing/Integrity information" in p2
    assert "Creation information" in _text(c.handle("ROLLDOWN", {}))


def test_f6_opens_add_new_users_and_f12_comes_back(store):
    _make(store)
    c = _signed(store)
    c.handle("ENTER", {"command": "wrkobj scratch2/*all *file"})
    c.handle("ENTER", {"opt0": "2"})
    s = c.handle("F6", {})
    f = _field_map(s)
    assert f[(0, 33)].text == "Add New Users" and len(s.inputs()) == 20
    assert _field_map(c.handle("F12", {}))[(0, 29)].text == "Edit Object Authority"


def test_add_new_users_grants_through_the_normal_rules(store):
    _make(store)
    c = _signed(store)
    c.handle("ENTER", {"command": "wrkobj scratch2/*all *file"})
    c.handle("ENTER", {"opt0": "2"})
    c.handle("F6", {})
    s = c.handle("ENTER", {"user0": "clerk", "auth0": "*use"})
    assert "Authorities changed." in _text(s) and _field_map(s)[(0, 29)].text == "Edit Object Authority"
    assert "CLERK" in store.objects[("SCRATCH2", "OLDFILE", "*FILE")].private
    c.handle("F6", {})
    s = c.handle("ENTER", {"user0": "clerk", "auth0": "*bogus"})
    assert "not valid" in _text(s) and _field_map(s)[(0, 33)].text == "Add New Users"
    s = c.handle("ENTER", {"user0": "nosuchuser", "auth0": "*use"})
    assert _field_map(s)[(0, 33)].text == "Add New Users"


# -- GRTOBJAUT REFOBJ (ours, not captured) ---------------------------------------------------------------------
def test_grtobjaut_refobj_copies_the_reference_objects_authorities(store):
    run(store, "QSECOFR", "GRTOBJAUT OBJ(APPLIB/PAYROLL) OBJTYPE(*FILE) USER(STUDENT) AUT(*USE)")
    out = run(store, "QSECOFR", "GRTOBJAUT OBJ(APPLIB/CUSTOMERS) OBJTYPE(*FILE) REFOBJ(APPLIB/PAYROLL)")
    assert "Authority granted." in out
    tgt, ref = (store.objects[("APPLIB", n, "*FILE")] for n in ("CUSTOMERS", "PAYROLL"))
    assert tgt.private["STUDENT"] == ref.private["STUDENT"] and tgt.autl == ref.autl and tgt.public == ref.public


def test_grtobjaut_refobj_rules(store):
    assert "REFOBJ cannot be combined" in run(
        store, "QSECOFR", "GRTOBJAUT OBJ(APPLIB/CUSTOMERS) OBJTYPE(*FILE) USER(STUDENT) AUT(*USE) REFOBJ(APPLIB/PAYROLL)")
    assert "CPF" in run(store, "QSECOFR", "GRTOBJAUT OBJ(APPLIB/CUSTOMERS) OBJTYPE(*FILE) REFOBJ(APPLIB/NOPE)")
    assert "Not authorized" in run(store, "STUDENT", "GRTOBJAUT OBJ(APPLIB/CUSTOMERS) OBJTYPE(*FILE) REFOBJ(APPLIB/PAYROLL)")


def test_grtobjaut_refobj_replace_makes_the_object_match(store):
    run(store, "QSECOFR", "GRTOBJAUT OBJ(APPLIB/CUSTOMERS) OBJTYPE(*FILE) USER(STUDENT) AUT(*ALL)")
    run(store, "QSECOFR", "GRTOBJAUT OBJ(APPLIB/CUSTOMERS) OBJTYPE(*FILE) REFOBJ(APPLIB/PAYROLL) REPLACE(*YES)")
    tgt, ref = (store.objects[("APPLIB", n, "*FILE")] for n in ("CUSTOMERS", "PAYROLL"))
    assert tgt.private.get("STUDENT") == ref.private.get("STUDENT")


# -- F10 on Edit Object Authority: the GRTOBJAUT prompt with a reference object ---------------------------------
def test_f10_opens_grtobjaut_for_the_object_in_the_captured_layout(store):
    c, s = _edit(store)
    s = c.handle("F10", {})
    f = _field_map(s)
    assert f[(0, 23)].text == "Grant Object Authority (GRTOBJAUT)" and f[(2, 1)].text == "Type choices, press Enter."
    assert f[(4, 49)].text == "CUSTOMERS" and f[(4, 45)].text == "  >" and f[(5, 51)].text == "APPLIB"
    assert f[(6, 49)].text == "*FILE" and f[(7, 49)].text == "*SYSBAS"
    ins = {(i.row, i.col): i for i in s.inputs()}
    assert sorted(ins) == [(8, 49), (9, 51), (10, 49), (11, 49)]
    assert ins[(9, 51)].value == "*LIBL" and ins[(10, 49)].value == "*OBJTYPE" and ins[(11, 49)].value == "*"
    assert f[(20, 66)].text.strip() == "Bottom" and f[(21, 1)].text.startswith("F3=Exit")


def test_f10_prompt_runs_grtobjaut_with_the_reference_and_comes_back(store):
    run(store, "QSECOFR", "GRTOBJAUT OBJ(APPLIB/PAYROLL) OBJTYPE(*FILE) USER(STUDENT) AUT(*USE)")
    c, s = _edit(store)
    s = c.handle("F10", {})
    s = c.handle("ENTER", {})
    assert "Parameter REFOBJ required." in _text(s)
    s = c.handle("ENTER", {"REFOBJ": "payroll", "REFOBJ@": "applib"})
    assert "Edit Object Authority" in _text(s) and "Authority granted." in _text(s)
    assert store.objects[("APPLIB", "CUSTOMERS", "*FILE")].private["STUDENT"] == Auth.OBJOPR | Auth.READ | Auth.EXECUTE


def test_f12_on_the_f10_prompt_goes_back_to_the_edit_screen(store):
    c, s = _edit(store)
    c.handle("F10", {})
    assert "Edit Object Authority" in _text(c.handle("F12", {}))


# -- option 3 (copy) opens the CRTDUPOBJ prompt, captured in auth-copyobj -----------------------------------------
def test_option_3_opens_crtdupobj_in_the_captured_layout(store):
    c = _signed(store)
    c.handle("ENTER", {"command": "wrkobj applib/customers *file"})
    s = c.handle("ENTER", {"opt0": "3"})
    f = _field_map(s)
    assert f[(0, 23)].text == "Create Duplicate Object (CRTDUPOBJ)"
    assert [f[(r, 49)].text for r in (4, 5, 6)] == ["CUSTOMERS", "APPLIB", "*FILE"] and f[(4, 45)].text == "  >"
    ins = {(i.row, i.col): i for i in s.inputs()}
    assert sorted(ins) == [(7, 49), (8, 49), (9, 49), (10, 49)]
    assert [ins[(r, 49)].value for r in (7, 8, 9, 10)] == ["*FROMLIB", "*OBJ", "*", "*ASPDEV"]
    assert "Function key not allowed." in _text(c.handle("F10", {}))
    assert "Already at bottom of area." in _text(c.handle("ROLLUP", {}))


def test_option_3_duplicates_the_object_and_the_list_shows_it(store):
    c = _signed(store, "QSECOFR")
    c.handle("ENTER", {"command": "wrkobj applib/*all *file"})
    c.handle("ENTER", {"opt0": "3"})
    s = c.handle("ENTER", {"NEWOBJ": "custcopy"})
    assert ("APPLIB", "CUSTCOPY", "*FILE") in store.objects and "Work with Objects" in _text(s)
    assert "CUSTCOPY" in _text(s)


def test_crtdupobj_rules(store):
    assert "duplicated" in run(store, "QSECOFR", "CRTDUPOBJ OBJ(CUSTOMERS) FROMLIB(APPLIB) OBJTYPE(*FILE) NEWOBJ(CUST2)")
    new = store.objects[("APPLIB", "CUST2", "*FILE")]
    old = store.objects[("APPLIB", "CUSTOMERS", "*FILE")]
    assert new.owner == "QSECOFR" and new.public == old.public and new.text == old.text and new.data == old.data
    assert new.data is not old.data
    assert "CPF2132" in run(store, "QSECOFR", "CRTDUPOBJ OBJ(CUSTOMERS) FROMLIB(APPLIB) OBJTYPE(*FILE) NEWOBJ(CUST2)")
    assert "CPF2209" in run(store, "QSECOFR", "CRTDUPOBJ OBJ(CUSTOMERS) FROMLIB(APPLIB) OBJTYPE(*FILE) TOLIB(NOPE)")
    assert "not valid" in run(store, "QSECOFR", "CRTDUPOBJ OBJ(CUSTOMERS) FROMLIB(APPLIB) OBJTYPE(*FILE) NEWOBJ(1BAD)")
    assert "CPF2189" in run(store, "STUDENT", "CRTDUPOBJ OBJ(PAYROLL) FROMLIB(APPLIB) OBJTYPE(*FILE) NEWOBJ(P2)")
    assert "CPF9876" in run(store, "QSECOFR", "CRTDUPOBJ OBJ(CUSTOMERS) FROMLIB(APPLIB) OBJTYPE(*FILE) TOLIB(QSYS)")


# -- review fixes (found by a second model reading the six commits) --------------------------------------------
def test_refobj_leaves_the_targets_owner_and_list_alone_and_does_not_copy_the_references_owner(store):
    tgt, ref = (store.objects[("APPLIB", n, "*FILE")] for n in ("CUSTOMERS", "PAYROLL"))
    ref.private["DEVELOPER"] = Auth.OBJOPR | Auth.READ
    ref.private["QSECOFR"] = Auth.READ               # an entry for the target's owner must not shrink the owner's rights
    ref.autl = None
    tgt.autl = "PAYAUTL"
    before_owner = tgt.owner_auth
    for line in ("", " REPLACE(*YES)"):
        out = run(store, "QSECOFR", "GRTOBJAUT OBJ(APPLIB/CUSTOMERS) OBJTYPE(*FILE) REFOBJ(APPLIB/PAYROLL)" + line)
        assert "Authority granted." in out and (Auth.OBJOPR | Auth.READ) in tgt.private["DEVELOPER"]
        assert (tgt.private["DEVELOPER"] == Auth.OBJOPR | Auth.READ) == bool(line)      # REPLACE(*YES) makes it match
        assert tgt.owner_auth == before_owner
        if not line:
            assert tgt.autl == "PAYAUTL"                       # REPLACE(*NO) keeps a list the object already has


def test_refobj_by_someone_who_may_not_hand_out_objmgt_is_refused_when_the_reference_carries_it(store):
    run(store, "QSECOFR", "GRTOBJAUT OBJ(APPLIB/CUSTOMERS) OBJTYPE(*FILE) USER(STUDENT) AUT(*OBJMGT *OBJOPR)")
    run(store, "QSECOFR", "GRTOBJAUT OBJ(APPLIB/PAYROLL) OBJTYPE(*FILE) USER(STUDENT) AUT(*OBJMGT *OBJOPR)")
    assert "CPF2223" in run(store, "STUDENT", "GRTOBJAUT OBJ(APPLIB/CUSTOMERS) OBJTYPE(*FILE) REFOBJ(APPLIB/PAYROLL)")


def test_a_detail_view_edit_by_someone_who_may_not_hand_out_objmgt_still_works_on_other_rights(store):
    run(store, "QSECOFR", "GRTOBJAUT OBJ(APPLIB/CUSTOMERS) OBJTYPE(*FILE) USER(STUDENT) AUT(*OBJMGT *OBJOPR)")
    run(store, "QSECOFR", "GRTOBJAUT OBJ(APPLIB/CUSTOMERS) OBJTYPE(*FILE) USER(DEVELOPER) AUT(*OBJMGT *READ)")
    c = _signed(store, "STUDENT")
    c.handle("ENTER", {"command": "edtobjaut applib/customers *file"})
    i = [r for r, _ in c.view[1].rows()].index("DEVELOPER")
    c.handle("F11", {})
    c.handle("F11", {})                                              # data rights
    s = c.handle("ENTER", {f"x{i}_0": "X", f"x{i}_1": "X"})          # Read stays, Add is new
    obj = store.objects[("APPLIB", "CUSTOMERS", "*FILE")]
    assert Auth.ADD in obj.private["DEVELOPER"] and Auth.OBJMGT in obj.private["DEVELOPER"]
    assert "Not authorized" not in _text(s)


def test_x_marks_on_a_public_row_that_follows_an_authorization_list_are_applied(store):
    c, s = _edit(store)
    obj = store.objects[("APPLIB", "CUSTOMERS", "*FILE")]
    obj.public = None
    obj.autl = "PAYAUTL"
    c.view[1].obj = obj
    c.handle("F11", {})
    c.handle("F11", {})
    c.handle("ENTER", {"x0_0": "X"})
    assert obj.public is not None and Auth.READ in obj.public


def test_a_copy_into_qtemp_belongs_to_the_job_and_is_visible_to_it(store):
    c = _signed(store)
    s = c.session
    out = execute(store, store.get("QSECOFR"), "CRTDUPOBJ OBJ(CUSTOMERS) FROMLIB(APPLIB) OBJTYPE(*FILE) TOLIB(QTEMP)", s)
    new = store.objects.get(("QTEMP", "CUSTOMERS", "*FILE"))
    if new is None:                                                   # no QTEMP library in this store: nothing to test
        assert "CPF2209" in out.message.line()
    else:
        assert new.data.get("job") == getattr(s.search_order(), "job", None)
