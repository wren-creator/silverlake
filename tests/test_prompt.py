"""F4 on the five compile and create commands: the captured layouts, prefilling from what was typed, the
command line the fields make, and what a refused or finished command does to the display."""

import pytest

from silverlake.screens.model import Input, Text
from silverlake.screens.signon import SignonController
from silverlake.system import profiles, source


@pytest.fixture
def store():
    return profiles.load()


def signed(store, user="STUDENT", dev="QPADEV0161"):
    c = SignonController(dev, store)
    c.handle("ENTER", {"user": user, "password": user})
    c.handle("ENTER", {"command": "ADDLIBLE SCRATCH"})
    return c


def f4(c, line=""):
    s = c.handle("F4", {"command": line})
    s.validate()
    return s


def enter(c, **v):
    s = c.handle("ENTER", v)
    s.validate()
    return s


def texts(s):
    return [f.text for f in s.fields if isinstance(f, Text)]


def inputs(s):
    return {f.name: f.value for f in s.fields if isinstance(f, Input)}


def at(s, row, col):
    return next(f for f in s.fields if f.row == row and f.col == col)


def test_crtbndrpg_prompt_has_the_captured_rows_and_defaults(store):
    s = f4(signed(store), "CRTBNDRPG")
    assert "Create Bound RPG Program (CRTBNDRPG)" in texts(s) and "Type choices, press Enter." in texts(s)
    assert "Program  . . . . . . . . . . . . PGM" in texts(s) and "Default activation group . . . . DFTACTGRP" in texts(s)
    v = inputs(s)
    assert (v["PGM"], v["PGM@"], v["SRCFILE"], v["SRCFILE@"], v["SRCMBR"]) == ("*CTLSPEC", "*CURLIB", "QRPGLESRC", "*LIBL", "*PGM")
    assert (v["GENLVL"], v["TEXT"], v["DFTACTGRP"]) == ("10", "*SRCMBRTXT", "*YES")
    assert at(s, 4, 49).name == "PGM" and at(s, 5, 51).name == "PGM@" and at(s, 9, 49).length == 50
    assert "Bottom" in texts(s) and "F3=Exit   F4=Prompt   F5=Refresh   F10=Additional parameters   F12=Cancel" in texts(s)


@pytest.mark.parametrize("cmd,title,names", [
    ("CRTPF", "Create Physical File (CRTPF)", {"RCDLEN", "FILETYPE", "MBR"}),
    ("CRTDSPF", "Create Display File (CRTDSPF)", {"DEV"}),
    ("CRTPRTF", "Create Printer File (CRTPRTF)", {"DEV", "DEVTYPE"}),
    ("CRTSRCPF", "Create Source Physical File (CRTSRCPF)", {"RCDLEN", "MBR"})])
def test_the_other_four_prompts_draw(store, cmd, title, names):
    s = f4(signed(store), cmd)
    assert title in texts(s) and names <= set(inputs(s))


def test_what_was_typed_fills_the_fields(store):
    s = f4(signed(store), "CRTPF FILE(SCRATCH/CUST) SRCFILE(SRCLIB/QDDSSRC) TEXT('Customers')")
    v = inputs(s)
    assert (v["FILE"], v["FILE@"], v["SRCFILE"], v["SRCFILE@"], v["TEXT"]) == ("CUST", "SCRATCH", "QDDSSRC", "SRCLIB", "Customers")


def test_enter_with_no_name_says_parameter_required(store):
    c = signed(store)
    f4(c, "CRTPF")
    assert "Parameter FILE required." in texts(enter(c))


def test_a_file_with_no_source_and_a_stream_file_are_laid_out_and_refused(store):
    c = signed(store)
    f4(c, "CRTPF")
    assert "not built" in " ".join(texts(enter(c, FILE="X", RCDLEN="80")))
    f4(c, "CRTBNDRPG")
    assert "not built" in " ".join(texts(enter(c, PGM="X", SRCSTMF="/home/x.rpgle")))


def test_roll_up_says_already_at_bottom(store):
    c = signed(store)
    f4(c, "CRTSRCPF")
    assert "Already at bottom of area." in texts(c.handle("ROLLUP", {}))


def test_enter_runs_the_command_and_a_finished_one_leaves_the_prompt(store):
    c = signed(store)
    f4(c, "CRTSRCPF")
    s = enter(c, FILE="MYSRC")
    assert "File MYSRC created in library" in " ".join(texts(s)) and "Silverlake Main Menu" in texts(s)
    assert any(k[1] == "MYSRC" for k in store.objects)
    assert any("CRTSRCPF FILE(MYSRC)" in t for _, _, t in c.session.joblog)


def test_a_refused_command_stays_on_the_prompt_with_its_message(store):
    c = signed(store)
    f4(c, "CRTBNDRPG")
    s = enter(c, PGM="NOPE", SRCFILE="QRPGLESRC")
    assert "Create Bound RPG Program (CRTBNDRPG)" in texts(s) and any("Unable to open member" in t for t in texts(s))


def test_only_what_is_not_the_default_goes_on_the_line_and_the_library_when_it_is_named(store):
    c = signed(store)
    f4(c, "CRTSRCPF")
    enter(c, FILE="LISTED", **{"FILE@": "SCRATCH"}, TEXT="my files")
    assert any("CRTSRCPF FILE(SCRATCH/LISTED) TEXT('my files')" == t for _, k, t in c.session.joblog if k == "command")


def test_f12_and_f3_leave_and_f5_resets(store):
    c = signed(store)
    f4(c, "CRTPF FILE(X)")
    s = c.handle("F5", {})
    assert inputs(s)["FILE"] == ""
    assert "Silverlake Main Menu" in texts(c.handle("F12", {}))


def test_a_command_without_a_prompt_says_so_and_blank_f4_does_nothing(store):
    c = signed(store)
    assert "not built" in " ".join(texts(f4(c, "WRKOBJ")))
    assert "Silverlake Main Menu" in texts(f4(c, ""))


def test_f4_in_pdm_with_option_14_prompts_the_compile_filled_in(store):
    c = signed(store, "DEVELOPER")
    c.handle("ENTER", {"command": "ADDLIBLE SRCLIB"})
    c.handle("ENTER", {"command": "WRKMBRPDM FILE(SRCLIB/QRPGLESRC)"})
    s = c.handle("F4", {"opt0": "14"})
    s.validate()
    v = inputs(s)
    assert "Create Bound RPG Program (CRTBNDRPG)" in texts(s)
    assert (v["PGM"], v["SRCFILE"], v["SRCFILE@"], v["SRCMBR"]) == ("HELLO", "QRPGLESRC", "SRCLIB", "HELLO")


def test_f4_on_the_pdm_command_line_prompts_the_typed_command(store):
    c = signed(store, "DEVELOPER")
    c.handle("ENTER", {"command": "WRKMBRPDM FILE(SRCLIB/QDDSSRC)"})
    s = c.handle("F4", {"command": "CRTPF"})
    assert "Create Physical File (CRTPF)" in texts(s)
    assert "Work with Members Using PDM" in texts(c.handle("F12", {}))      # back to the member list
