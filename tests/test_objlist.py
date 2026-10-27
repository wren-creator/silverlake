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
