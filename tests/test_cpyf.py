"""CPYF and DSPPFM: the authority each needs, what a copy keeps and does not keep, and the display."""

import pytest

from silverlake.screens.model import Input, Text
from silverlake.screens.signon import SignonController
from silverlake.system import profiles
from silverlake.system.authority import Auth


@pytest.fixture
def store():
    return profiles.load()


def signed(store, user="STUDENT", dev="QPADEV0151"):
    c = SignonController(dev, store)
    c.handle("ENTER", {"user": user, "password": user})
    c.handle("ENTER", {"command": "ADDLIBLE APPLIB"})
    c.handle("ENTER", {"command": "ADDLIBLE SCRATCH"})
    return c


def run(c, line):
    s = c.handle("ENTER", {"command": line})
    s.validate()
    return s


def text(s):
    return " | ".join(f.text for f in s.fields if isinstance(f, Text))


def recs(store, lib, name):
    return store.objects[(lib, name, "*FILE")].data["records"]


def test_a_basic_user_cannot_copy_a_file_they_cannot_use(store):
    c = signed(store)
    s = run(c, "CPYF FROMFILE(APPLIB/PAYROLL) TOFILE(SCRATCH/MYPAY) CRTFILE(*YES)")
    assert "Not authorized" in text(s) and ("SCRATCH", "MYPAY", "*FILE") not in store.objects


def test_use_on_the_source_is_enough_to_copy_it_out_and_the_copy_is_wide_open(store):
    c = signed(store, "OPERATOR")                           # PAYAUTL gives OPERATOR *USE
    s = run(c, "CPYF FROMFILE(APPLIB/PAYROLL) TOFILE(SCRATCH/MYPAY) CRTFILE(*YES)")
    assert "6 records copied" in text(s) and "created in library SCRATCH" in text(s)
    copy = store.objects[("SCRATCH", "MYPAY", "*FILE")]
    assert copy.owner == "OPERATOR" and copy.autl is None             # not on PAYAUTL
    student = store.profiles["STUDENT"]
    assert Auth.READ in store.authority_to_object(student, copy)      # anyone with the library's create authority reads it
    assert recs(store, "SCRATCH", "MYPAY")[2]["SALARY"] == 72000


def test_the_copy_in_qtemp_belongs_to_the_job_and_goes_with_it(store):
    c = signed(store, "OPERATOR")
    run(c, "CPYF FROMFILE(APPLIB/PAYROLL) TOFILE(QTEMP/LOOT) CRTFILE(*YES)")
    assert ("QTEMP", "LOOT", "*FILE") in store.objects
    c._sign_off()
    assert ("QTEMP", "LOOT", "*FILE") not in store.objects


def test_crtfile_needs_authority_to_add_to_the_library(store):
    c = signed(store, "OPERATOR")
    s = run(c, "CPYF FROMFILE(APPLIB/PAYROLL) TOFILE(SRCLIB/X) CRTFILE(*YES)")
    assert "not authorized" in text(s).lower()


def test_an_existing_target_is_not_touched_without_a_member_option(store):
    c = signed(store, "OPERATOR")
    run(c, "CPYF FROMFILE(APPLIB/PAYROLL) TOFILE(SCRATCH/MYPAY) CRTFILE(*YES)")
    s = run(c, "CPYF FROMFILE(APPLIB/PAYROLL) TOFILE(SCRATCH/MYPAY)")
    assert "already has records" in text(s)
    assert len(recs(store, "SCRATCH", "MYPAY")) == 6


def test_replace_and_add_and_updadd(store):
    c = signed(store, "OPERATOR")
    run(c, "CPYF FROMFILE(APPLIB/PAYROLL) TOFILE(SCRATCH/MYPAY) CRTFILE(*YES)")
    run(c, "CPYF FROMFILE(APPLIB/PAYROLL) TOFILE(SCRATCH/MYPAY) MBROPT(*ADD)")
    s = run(c, "CPYF FROMFILE(APPLIB/PAYROLL) TOFILE(SCRATCH/MYPAY) MBROPT(*ADD)")
    assert "same key" in text(s) and len(recs(store, "SCRATCH", "MYPAY")) == 6      # a unique key refuses duplicates
    run(c, "CPYF FROMFILE(APPLIB/PAYROLL) TOFILE(SCRATCH/MYPAY) MBROPT(*REPLACE) NBRRCDS(2)")
    assert len(recs(store, "SCRATCH", "MYPAY")) == 2
    s = run(c, "CPYF FROMFILE(APPLIB/PAYROLL) TOFILE(SCRATCH/MYPAY) MBROPT(*UPDADD)")
    assert "6 records copied" in text(s) and len(recs(store, "SCRATCH", "MYPAY")) == 6


def test_the_target_needs_add_and_replace_needs_delete(store):
    c = signed(store, "OPERATOR")
    run(c, "CPYF FROMFILE(APPLIB/PAYROLL) TOFILE(SCRATCH/MYPAY) CRTFILE(*YES)")
    copy = store.objects[("SCRATCH", "MYPAY", "*FILE")]
    copy.owner = "QSECOFR"
    copy.public = Auth.OBJOPR | Auth.READ | Auth.ADD
    s = run(c, "CPYF FROMFILE(APPLIB/PAYROLL) TOFILE(SCRATCH/MYPAY) MBROPT(*REPLACE)")
    assert "Not authorized" in text(s)
    assert len(recs(store, "SCRATCH", "MYPAY")) == 6


def test_different_layouts_need_a_format_option(store):
    c = signed(store, "OPERATOR")
    s = run(c, "CPYF FROMFILE(APPLIB/PAYROLL) TOFILE(APPLIB/CUSTOMERS) MBROPT(*ADD)")
    assert "Not authorized" in text(s)                       # OPERATOR may not add to CUSTOMERS, checked first
    run(c, "CPYF FROMFILE(APPLIB/STAFF) TOFILE(SCRATCH/S2) CRTFILE(*YES)")
    s = run(c, "CPYF FROMFILE(APPLIB/CUSTOMERS) TOFILE(SCRATCH/S2) MBROPT(*ADD)")
    assert "do not match" in text(s)
    s = run(c, "CPYF FROMFILE(APPLIB/CUSTOMERS) TOFILE(SCRATCH/S2) MBROPT(*ADD) FMTOPT(*NOCHK) NBRRCDS(1)")
    assert "1 records copied" in text(s)


def test_a_file_cannot_be_copied_onto_itself_and_source_files_are_refused(store):
    c = signed(store, "OPERATOR")
    assert "same file" in text(run(c, "CPYF FROMFILE(APPLIB/STAFF) TOFILE(APPLIB/STAFF) MBROPT(*ADD)"))
    d = signed(store, "DEVELOPER", "QPADEV0152")
    assert "not a physical file" in text(run(d, "CPYF FROMFILE(SRCLIB/QRPGLESRC) TOFILE(SCRATCH/X) CRTFILE(*YES)"))


def test_dsppfm_shows_records_to_whoever_may_use_the_file(store):
    c = signed(store, "OPERATOR")
    s = run(c, "DSPPFM FILE(APPLIB/PAYROLL)")
    t = text(s)
    assert "Display Physical File Member" in t and "Alvarez, Marta" in t and "0098000" in t
    s = c.handle("F3", {})
    assert "Silverlake Main Menu" in text(s)


def test_dsppfm_is_refused_without_use(store):
    c = signed(store)
    assert "Not authorized" in text(run(c, "DSPPFM FILE(APPLIB/PAYROLL)"))


def test_dsppfm_control_jumps_and_f20_shifts(store):
    c = signed(store, "OPERATOR")
    run(c, "DSPPFM FILE(APPLIB/PAYROLL)")
    s = c.handle("ENTER", {"control": "4"})
    assert "Record . . . . . :   4" in text(s)
    s = c.handle("F20", {})
    assert "Column  . . . . . :   72" in text(s)
    assert "Control must be" in text(c.handle("ENTER", {"control": "zz"}))


def test_dsppfm_on_a_missing_file_says_so(store):
    c = signed(store)
    assert "not found" in text(run(c, "DSPPFM FILE(APPLIB/NOSUCH)"))
