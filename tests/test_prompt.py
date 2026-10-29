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


def test_roll_up_checks_the_required_name_first_and_then_says_already_at_bottom(store):
    c = signed(store)
    f4(c, "CRTSRCPF")
    assert "Parameter FILE required." in texts(c.handle("ROLLUP", {}))          # captured on CRTPF
    assert "Already at bottom of area." in texts(c.handle("ROLLUP", {"FILE": "MYSRC"}))
    f4(signed(store), "CRTBNDRPG")                                                # nothing required: captured
    c = signed(store)
    f4(c, "CRTBNDRPG")
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
    assert "not built" in " ".join(texts(f4(c, "SIGNOFF")))
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


# -- the other commands, from the table ------------------------------------------------------------------

from silverlake.proto import datastream as ds                    # noqa: E402
from silverlake.screens import prompt as _prompt                 # noqa: E402


@pytest.mark.parametrize("cmd", sorted(_prompt.SPECS))
def test_every_captured_prompt_draws_a_valid_screen_on_every_page(store, cmd):
    c = signed(store, "QSECOFR")
    s = f4(c, cmd)
    spec = _prompt.SPECS[cmd]
    assert spec["title"][0] in texts(s)
    if spec["note"]:
        assert spec["note"] in texts(s) and not inputs(s)
        return
    first = {"FILE": "X", "OBJ": "X", "AUTL": "X", "LIB": "X", "PGM": "X"}
    for page in range(len(spec["pages"])):
        s.validate()
        assert spec["pages"][page][1] in texts(s)                                  # Bottom or More...
        assert {n for rows in [spec["pages"][page][0]] for _, _, n, _, _, _ in rows if n} == set(inputs(s))
        if page + 1 < len(spec["pages"]):
            filled = {n: first.get(n, "X") for n in spec["required"]}
            s = c.handle("ROLLUP", filled)


def test_a_required_parameter_is_drawn_brighter_and_roll_up_and_enter_refuse_while_it_is_empty(store):
    c = signed(store, "QSECOFR")
    s = f4(c, "DLTLIB")
    assert at(s, 4, 49).required and not at(s, 5, 49).required                       # LIB is required, ASPDEV is not
    assert "Parameter LIB required." in texts(c.handle("ROLLUP", {}))
    assert "Parameter LIB required." in texts(enter(c))
    from silverlake.screens.render import render
    assert bytes([ds.ATTR_WHITE_UNDERLINE]) in render(s)


def test_roll_up_pages_a_long_prompt_and_roll_down_comes_back(store):
    c = signed(store, "QSECOFR")
    f4(c, "OVRDBF")
    assert "Parameter FILE required." in texts(c.handle("ROLLUP", {}))         # captured: the name first
    two = c.handle("ROLLUP", {"FILE": "CUSTPF"})
    assert "More..." in texts(two) and "FILE" not in inputs(two)
    three = c.handle("ROLLUP", {})
    assert "Bottom" in texts(three)
    assert "Already at bottom of area." in texts(c.handle("ROLLUP", {}))
    back = c.handle("ROLLDOWN", {})
    assert "More..." in texts(back)
    assert "FILE" in inputs(c.handle("ROLLDOWN", {}))
    assert "Already at top of area." in texts(c.handle("ROLLDOWN", {}))


def test_what_was_typed_on_one_page_is_still_there_when_enter_is_pressed_on_another(store):
    c = signed(store, "QSECOFR")
    f4(c, "HLDSPLF")
    c.handle("ROLLUP", {"FILE": "QPJOBLOG"})
    assert _prompt.SPECS["HLDSPLF"]["pages"][1][0]                                   # a second page exists
    s = enter(c)                                                                      # FILE is on the first page
    assert "Parameter FILE required." not in texts(s)


def test_a_command_with_nothing_to_prompt_for_says_so_and_enter_runs_it(store):
    c = signed(store)
    s = f4(c, "CHGPWD")
    assert "No parameters to show; press Enter to run, F3 to exit." in texts(s) and not inputs(s)
    assert "Change Password (CHGPWD)" in texts(s)


def test_a_qualified_name_and_a_list_value_make_the_command_line_the_host_would_take(store):
    c = signed(store, "QSECOFR")
    w = _prompt.Prompt.for_command(c._ctx(), "DSPOBJAUT OBJ(QGPL/QSYS) OBJTYPE(*LIB)")
    assert (w.values["OBJ"], w.values["OBJ@"], w.values["OBJTYPE"]) == ("QSYS", "QGPL", "*LIB")
    assert w._line() == "DSPOBJAUT OBJ(QGPL/QSYS) OBJTYPE(*LIB)"
    w = _prompt.Prompt.for_command(c._ctx(), "WRKSPLF")
    assert w._line() == "WRKSPLF"                                                     # nothing changed, nothing added
    w.values["SELECT"] = "STUDENT"
    assert w._line().startswith("WRKSPLF SELECT(STUDENT ")


def test_the_colors_follow_the_capture(store):
    s = f4(signed(store), "DLTLIB")
    assert at(s, 2, 1).attr == ds.ATTR_BLUE                      # "Type choices" is blue on the real host
    assert at(s, 0, 29).attr == ds.ATTR_WHITE
    assert next(t for t in s.fields if isinstance(t, Text) and t.text == "Bottom").attr == ds.ATTR_WHITE
    assert at(s, 20, 73).text == "Bottom"


def test_a_refusal_redraws_every_missing_required_field_in_reverse_and_puts_the_cursor_on_the_first(store):
    c = signed(store, "QSECOFR")
    s = f4(c, "ADDAUTLE")                                          # AUTL and USER (which has a "+" line) are required
    s = c.handle("ENTER", {})
    s.validate()
    assert "Parameter AUTL required." in texts(s) and s.cursor == "AUTL"
    flagged = {f.name for f in s.fields if isinstance(f, Input) and f.error}
    assert flagged == {"AUTL", "USER", "USER+"}                    # captured: all of the group, not AUT
    from silverlake.screens.render import render
    assert bytes([ds.ATTR_REVERSE_UNDERLINE]) in render(s)
    s = c.handle("ENTER", {"AUTL": "MYLIST"})                      # AUTL is filled in, so only USER is flagged now
    assert "Parameter USER required." in texts(s) and s.cursor == "USER"
    assert {f.name for f in s.fields if isinstance(f, Input) and f.error} == {"USER", "USER+"}


def test_a_refusal_on_another_page_brings_the_page_with_the_missing_name_back(store):
    c = signed(store, "QSECOFR")
    f4(c, "OVRDBF")
    c.handle("ROLLUP", {"FILE": "CUSTPF"})                         # now on page 2
    c.handle("ROLLUP", {})                                         # page 3
    s = c.handle("ENTER", {"FILE": ""})                            # the name is gone: back to the page that holds it
    assert "Parameter FILE required." in texts(s) and "FILE" in inputs(s) and s.cursor == "FILE"


# -- F10=Additional parameters (captured: auth-f10-*) ---------------------------------------------------------

def test_f10_shows_the_additional_parameters_below_the_first_ones_and_drops_the_f10_key(store):
    c = signed(store)
    plain = f4(c, "CHGJOB")
    assert any("F10=Additional parameters" in t for t in texts(plain)) and "Additional Parameters" not in " ".join(texts(plain))
    s = c.handle("F10", {})
    s.validate()
    assert "Additional Parameters" in " ".join(t.strip() for t in texts(s))
    assert set(inputs(plain)) <= set(inputs(s)) and "JOBQ" in inputs(s)               # the first rows repeat, then more
    assert not any("F10=Additional" in t for t in texts(s)) and "More..." in " ".join(texts(s))


def test_f10_keeps_what_was_typed_and_rolls_through_every_captured_page(store):
    c = signed(store)
    f4(c, "CRTUSRPRF")
    c.handle("F10", {"USRPRF": "NEWGUY"})
    pages = 1
    while True:
        s = c.handle("ROLLUP", {})
        s.validate()
        if "Already at bottom of area." in texts(s) or "Parameter USRPRF required." in texts(s):
            break
        pages += 1
    assert pages == 5                                                       # five pages captured, then the bottom
    for _ in range(pages - 1):
        s = c.handle("ROLLDOWN", {})
    assert inputs(s)["USRPRF"] == "NEWGUY"                                  # still there on the first page


def test_f10_a_second_time_and_a_prompt_without_it_say_the_key_is_not_built(store):
    c = signed(store)
    f4(c, "CHGJOB")
    c.handle("F10", {})
    assert "That key is not built here." in texts(c.handle("F10", {}))
    f4(c2 := signed(store), "CRTLIB")                                       # no F10 page for this prompt
    assert "That key is not built here." in texts(c2.handle("F10", {}))


def test_f12_leaves_the_prompt_from_the_f10_view_as_the_host_did(store):
    c = signed(store)
    f4(c, "CHGJOB")
    c.handle("F10", {})
    assert "Silverlake Main Menu" in texts(c.handle("F12", {}))


def test_a_change_command_shows_the_signed_on_profiles_current_values_not_the_captured_ones(store):
    c = signed(store)
    f4(c, "CHGPRF")
    s = c.handle("F10", {})
    values = inputs(s)
    assert values["CURLIB"] == store.get("STUDENT").current_library
    from silverlake.screens.promptspecs import SPECS
    assert not any(w in repr(SPECS) for w in ("WREN01", "Hoff,Britley", "pub400.com", "PRT01", "PUB400SYS"))


# -- F24, the other key line (captured on CRTPF: auth-f13) ----------------------------------------------------

MORE = "F9=All parameters   F11=Choices   F14=Command string   F24=More keys"


def test_f24_swaps_the_key_lines_for_the_one_the_host_showed_and_a_second_turns_it_back(store):
    c = signed(store)
    plain = f4(c, "CRTPF")
    s = c.handle("F24", {})
    s.validate()
    assert MORE in texts(s) and not any("F3=Exit" in t for t in texts(s))
    assert at(s, 21, 1).attr == at(plain, 21, 1).attr and not any(f.row == 22 for f in s.fields)   # one line, row 21
    assert inputs(s) == inputs(plain)
    assert texts(c.handle("F24", {})) == texts(plain)                                              # ours


def test_the_keys_on_the_other_line_say_they_are_not_built_and_do_not_run_the_command(store):
    c = signed(store)
    f4(c, "CRTPF")
    c.handle("F24", {})
    for key in ("F9", "F11", "F14"):
        s = c.handle(key, {"FILE": "NEWF", "SRCMBR": "X"})
        assert "That key is not built here." in texts(s), key
        assert inputs(s)["FILE"] == "NEWF"                                   # typed text kept, nothing ran
    assert store.find_library("SCRATCH") is not None and not source_exists(store, "NEWF")


def source_exists(store, name):
    return any(o.name == name for o in store.objects.values())


# -- F13, How to use this display (captured: auth-f13-help, auth-f13-helpall) ---------------------------------

def page_text(s):
    return " ".join(texts(s))


def test_f13_opens_the_help_and_f3_and_f12_both_go_back_to_the_prompt_with_what_was_typed(store):
    for back in ("F3", "F12"):
        c = signed(store)
        f4(c, "CRTPF")
        s = c.handle("F13", {"FILE": "KEEPME"})
        s.validate()
        assert texts(s)[:2] == ["Help", "                 Prompt Display - Help"] and "More..." in page_text(s)
        assert not [f for f in s.fields if isinstance(f, Input) and not f.hidden]      # nothing to type into
        s = c.handle(back, {})
        assert "Create Physical File (CRTPF)" in texts(s) and inputs(s)["FILE"] == "KEEPME"


def test_the_help_has_fifteen_pages_and_says_bottom_on_the_last(store):
    c = signed(store)
    f4(c, "CHGJOB")
    c.handle("F13", {})
    pages = 1
    while True:
        s = c.handle("ROLLUP", {})
        s.validate()
        if "Already at bottom of area." in texts(s):
            break
        pages += 1
        assert ("Bottom" in page_text(s)) == (pages == 15) and ("More..." in page_text(s)) == (pages < 15)
    assert pages == 15


def test_the_help_is_the_same_text_for_every_prompt_even_one_with_nothing_to_prompt_for(store):
    first = None
    for cmd in ("CRTPF", "CHGPWD", "WRKSPLF"):
        c = signed(store)
        f4(c, cmd)
        s = c.handle("F13", {})
        first = first or page_text(s)
        assert page_text(s) == first


def test_the_other_keys_on_the_help(store):
    c = signed(store)
    f4(c, "CRTPF")
    c.handle("F13", {})
    assert "Already at top of area." in texts(c.handle("ROLLDOWN", {}))           # ours
    assert "Wrong cursor position." in texts(c.handle("F10", {}))                   # captured with the cursor in the corner
    for key in ("F14", "ENTER", "F24"):
        assert "That key is not built here." in texts(c.handle(key, {})), key
    assert "Help" in texts(c.handle("ROLLUP", {}))                                  # still on the help, and nothing ran


def test_the_help_text_comes_from_the_capture_with_its_colors(store):
    from silverlake.screens.promptspecs import HELP
    c = signed(store)
    f4(c, "CRTPF")
    s = c.handle("F13", {})
    drawn = {(f.row, f.col): (f.attr, f.text) for f in s.fields if isinstance(f, Text)}
    for row, col, attr, text in HELP["pages"][0]:
        assert drawn[(row, col)] == (attr, text)
    assert len(HELP["pages"]) == 15 and HELP["cursor"] == (1, 1)
