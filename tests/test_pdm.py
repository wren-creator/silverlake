"""PDM and the source editor: STRPDM, WRKMBRPDM, STRSEU. The window is items i: row 0 is the beginning marker,
line k of the member is item k + 1 while the window is at the top."""

import pytest

from silverlake.screens.model import Input, Text
from silverlake.screens.signon import SignonController
from silverlake.system import profiles, source


@pytest.fixture
def store():
    return profiles.load()


def signed(store, user="STUDENT", dev="QPADEV0131"):
    c = SignonController(dev, store)
    c.handle("ENTER", {"user": user, "password": user})
    return c


def cmd(c, line):
    s = c.handle("ENTER", {"command": line})
    s.validate()
    return s


def texts(s):
    return [f.text for f in s.fields if isinstance(f, Text)]


def shown(s):
    return [f.value for f in s.fields if isinstance(f, Input) and f.name.startswith("d")]


def line_of(s, needle):
    return next(t for t in texts(s) if needle in t)


def names(s):
    return {f.name for f in s.fields if isinstance(f, Input)}


def seu(c, aid="ENTER", **values):
    s = c.handle(aid, values)
    s.validate()
    return s


def member_lines(store, lib, file, mbr):
    return store.objects[(lib, file, "*FILE")].data["members"][mbr]["lines"]


@pytest.fixture
def stu(store):
    c = signed(store)
    cmd(c, "ADDLIBLE SCRATCH")
    cmd(c, "CRTSRCPF FILE(SCRATCH/QRPGLESRC)")
    return c


def put(store, name, lines, lib="SCRATCH", file="QRPGLESRC", type_="RPGLE"):
    source.put_member(store, store.objects[(lib, file, "*FILE")], name, lines, type_)


def test_the_pdm_menu_has_the_captured_four_lines(store):
    s = cmd(signed(store), "STRPDM")
    t = texts(s)
    assert "Programming Development Manager (PDM)" in t and "1. Work with libraries" in t
    assert "3. Work with members" in t and "9. Work with user-defined options" in t


def test_pdm_menu_options_point_at_the_commands_and_f3_leaves(store):
    c = signed(store)
    cmd(c, "STRPDM")
    assert "WRKMBRPDM" in line_of(seu(c, command="3"), "WRKMBRPDM")
    s = seu(c, "F3")
    assert "Silverlake Main Menu" in texts(s)


def test_wrkmbrpdm_refusals_use_the_captured_wording(store):
    c = signed(store)
    assert "Library NOSUCH was not found." in texts(cmd(c, "WRKMBRPDM FILE(NOSUCH/NOFILE)"))
    assert "You do not have authority to file QRPGLESRC in SRCLIB." in texts(cmd(c, "WRKMBRPDM FILE(SRCLIB/QRPGLESRC)"))
    assert "Library NOSUCH not found." in texts(cmd(c, "STRSEU SRCFILE(NOSUCH/NOFILE) SRCMBR(NOMBR)"))


def test_wrkmbrpdm_lists_members_with_type_and_text(store):
    c = signed(store, "DEVELOPER")
    s = cmd(c, "WRKMBRPDM FILE(SRCLIB/QDDSSRC)")
    assert "Work with Members Using PDM" in texts(s)
    assert "CUSTPF" in texts(s) and "HELLOD" in texts(s) and "Customer physical file" in texts(s)
    assert {"opt0", "opt1", "command", "pos"} <= names(s)


def test_new_member_through_strseu_and_lines_from_nothing(store, stu):
    s = cmd(stu, "STRSEU SRCFILE(SCRATCH/QRPGLESRC) SRCMBR(HELLO) TYPE(RPGLE)")
    assert "Edit" in texts(s) and "SCRATCH/QRPGLESRC" in texts(s)
    # an empty member has no line to open an insert on: the command line adds the first
    s = seu(stu, seu="SAVE")
    assert "Member HELLO saved." in texts(s)
    assert store.objects[("SCRATCH", "QRPGLESRC", "*FILE")].data["members"]["HELLO"]["type"] == "RPGLE"


def open_edit(store, c, name="TEST"):
    s = cmd(c, f"STRSEU SRCFILE(SCRATCH/QRPGLESRC) SRCMBR({name})")
    return s


def test_typing_over_a_line_changes_it_and_file_saves_it(store, stu):
    put(store, "TEST", ["     C                   EVAL      x = 1", "     C                   RETURN"])
    open_edit(store, stu)
    s = seu(stu, d1="     C                   EVAL      x = 2")
    assert member_lines(store, "SCRATCH", "QRPGLESRC", "TEST")[0].endswith("x = 1")      # not saved yet
    s = seu(stu, seu="FILE")
    assert member_lines(store, "SCRATCH", "QRPGLESRC", "TEST")[0].endswith("x = 2")
    assert "Silverlake Main Menu" in texts(s)


def test_insert_opens_blank_lines_and_typing_in_them_adds_lines(store, stu):
    put(store, "TEST", ["one", "two"])
    open_edit(store, stu)
    s = seu(stu, p1="I2")
    assert {"p2", "d2", "p3", "d3"} <= names(s)             # two blank lines, after line one
    seu(stu, d2="between a", d3="between b")
    seu(stu, seu="SAVE")
    assert member_lines(store, "SCRATCH", "QRPGLESRC", "TEST") == ["one", "between a", "between b", "two"]


def test_blank_insert_lines_are_dropped(store, stu):
    put(store, "TEST", ["one", "two"])
    open_edit(store, stu)
    seu(stu, p1="I3")
    seu(stu, seu="SAVE")
    assert member_lines(store, "SCRATCH", "QRPGLESRC", "TEST") == ["one", "two"]


def test_delete_repeat_and_blocks(store, stu):
    put(store, "TEST", ["a", "b", "c", "d", "e"])
    open_edit(store, stu)
    seu(stu, p2="D")                                         # b
    seu(stu, seu="SAVE")
    assert member_lines(store, "SCRATCH", "QRPGLESRC", "TEST") == ["a", "c", "d", "e"]
    seu(stu, p1="R")                                         # repeat a
    seu(stu, seu="SAVE")
    assert member_lines(store, "SCRATCH", "QRPGLESRC", "TEST") == ["a", "a", "c", "d", "e"]
    seu(stu, p3="DD", p4="DD")                               # c and d
    seu(stu, seu="SAVE")
    assert member_lines(store, "SCRATCH", "QRPGLESRC", "TEST") == ["a", "a", "e"]


def test_copy_and_move_place_after_or_before_a_target(store, stu):
    put(store, "TEST", ["a", "b", "c", "d"])
    open_edit(store, stu)
    seu(stu, p1="C", p4="A")                                 # copy a after d
    seu(stu, seu="SAVE")
    assert member_lines(store, "SCRATCH", "QRPGLESRC", "TEST") == ["a", "b", "c", "d", "a"]
    seu(stu, p2="M", p1="B")                                 # move b before a
    seu(stu, seu="SAVE")
    assert member_lines(store, "SCRATCH", "QRPGLESRC", "TEST") == ["b", "a", "c", "d", "a"]


def test_a_block_move_finished_on_a_later_enter(store, stu):
    put(store, "TEST", ["a", "b", "c", "d"])
    open_edit(store, stu)
    s = seu(stu, p1="MM", p2="MM")
    seu(stu, p4="A")
    seu(stu, seu="SAVE")
    assert member_lines(store, "SCRATCH", "QRPGLESRC", "TEST") == ["c", "d", "a", "b"]


def test_find_change_top_and_bottom(store, stu):
    put(store, "TEST", [f"line {i}" for i in range(60)])
    open_edit(store, stu)
    assert "found on line 41" in " ".join(texts(seu(stu, seu="FIND 'line 40'")))
    assert "line 40" in shown(seu(stu))
    assert "End of data" in "".join(texts(seu(stu, seu="BOTTOM")))
    assert "Beginning of data" in "".join(texts(seu(stu, seu="TOP")))
    assert "1 line changed." in texts(seu(stu, seu="CHANGE 'line 3' 'row 3'"))
    seu(stu, seu="SAVE")
    assert member_lines(store, "SCRATCH", "QRPGLESRC", "TEST")[3] == "row 3"
    assert "was not found" in " ".join(texts(seu(stu, seu="FIND 'nothing here'")))


def test_roll_pages_through_a_long_member(store, stu):
    put(store, "TEST", [f"line {i}" for i in range(60)])
    s = open_edit(store, stu)
    assert "line 0" in shown(s) and "line 30" not in shown(s)
    s = seu(stu, "ROLLUP")
    assert "line 0" not in shown(s) and "line 17" in shown(s)
    s = seu(stu, "ROLLDOWN")
    assert "line 0" in shown(s)


def test_f3_on_a_changed_member_asks_and_can_discard_or_save(store, stu):
    put(store, "TEST", ["one"])
    open_edit(store, stu)
    seu(stu, d1="changed")
    s = seu(stu, "F3")
    assert "Exit" in texts(s) and "Change/create member . . . . . . . ." in " ".join(texts(s))
    s = seu(stu, "ENTER", save="N", member="TEST", text="", back="N")
    assert member_lines(store, "SCRATCH", "QRPGLESRC", "TEST") == ["one"]
    open_edit(store, stu)
    seu(stu, d1="kept")
    seu(stu, "F3")
    seu(stu, "ENTER", save="Y", member="COPY2", text="Saved as", back="N")
    assert member_lines(store, "SCRATCH", "QRPGLESRC", "COPY2") == ["kept"]
    assert store.objects[("SCRATCH", "QRPGLESRC", "*FILE")].data["members"]["COPY2"]["text"] == "Saved as"


def test_f12_on_the_exit_display_returns_to_editing(store, stu):
    put(store, "TEST", ["one"])
    open_edit(store, stu)
    seu(stu, d1="changed")
    seu(stu, "F3")
    s = seu(stu, "F12")
    assert "Edit" in texts(s)


def test_f3_on_an_unchanged_member_just_leaves(store, stu):
    put(store, "TEST", ["one"])
    open_edit(store, stu)
    assert "Silverlake Main Menu" in texts(seu(stu, "F3"))


def test_browse_shows_the_member_and_changes_nothing(store, stu):
    put(store, "TEST", ["one"])
    s = cmd(stu, "STRSEU SRCFILE(SCRATCH/QRPGLESRC) SRCMBR(TEST) OPTION(5)")
    assert "Browse" in texts(s) and "one" in texts(s) and not shown(s)
    seu(stu, d1="nope", seu="SAVE")
    assert member_lines(store, "SCRATCH", "QRPGLESRC", "TEST") == ["one"]


def test_a_member_is_locked_while_it_is_being_edited(store, stu):
    put(store, "TEST", ["one"])
    open_edit(store, stu)
    other = signed(store, "STUDENT", "QPADEV0132")
    cmd(other, "ADDLIBLE SCRATCH")
    assert "is in use" in " ".join(texts(open_edit(store, other)))
    seu(stu, "F3")
    assert "Edit" in texts(open_edit(store, other))


def test_signing_off_releases_the_lock(store, stu):
    put(store, "TEST", ["one"])
    open_edit(store, stu)
    stu._sign_off()
    assert store.member_locks == {}


def test_a_user_without_authority_to_the_file_cannot_edit_but_may_browse(store, stu):
    put(store, "TEST", ["one"])
    f = store.objects[("SCRATCH", "QRPGLESRC", "*FILE")]
    from silverlake.system.authority import USE
    f.public = USE
    other = signed(store, "OPERATOR")
    cmd(other, "ADDLIBLE SCRATCH")
    s = cmd(other, "STRSEU SRCFILE(SCRATCH/QRPGLESRC) SRCMBR(TEST)")
    assert "You do not have authority to edit member TEST." in " ".join(texts(s))
    assert "Browse" in texts(cmd(other, "STRSEU SRCFILE(SCRATCH/QRPGLESRC) SRCMBR(TEST) OPTION(5)"))


def test_option_14_compiles_by_member_type_into_the_files_library(store):
    c = signed(store, "DEVELOPER")
    cmd(c, "ADDLIBLE SRCLIB")
    cmd(c, "WRKMBRPDM FILE(SRCLIB/QDDSSRC)")
    s = seu(c, opt0="14")                                     # CUSTPF, a PF member, so CRTPF
    assert "File CUSTPF created in library SRCLIB." in texts(s)
    assert ("SRCLIB", "CUSTPF", "*FILE") in store.objects
    s = seu(c, opt1="14")                                     # and HELLOD, a DSPF member, so CRTDSPF
    assert ("SRCLIB", "HELLOD", "*FILE") in store.objects
    seu(c, "F3")
    cmd(c, "WRKMBRPDM FILE(SRCLIB/QRPGLESRC)")
    s = seu(c, opt0="14")
    assert "Program HELLO placed in library SRCLIB." in " ".join(texts(s))
    assert store.objects[("SRCLIB", "HELLO", "*PGM")].owner == "DEVELOPER"


def test_option_14_on_a_member_that_cannot_be_compiled(store, stu):
    put(store, "NOTES", ["some text"], type_="TXT")
    cmd(stu, "WRKMBRPDM FILE(SCRATCH/QRPGLESRC)")
    assert "cannot be compiled" in " ".join(texts(seu(stu, opt0="14")))


def test_delete_asks_first_and_f12_keeps_the_member(store, stu):
    put(store, "A", ["x"])
    put(store, "B", ["y"])
    cmd(stu, "WRKMBRPDM FILE(SCRATCH/QRPGLESRC)")
    s = seu(stu, opt0="4", opt1="4")
    assert "Confirm Delete of Members" in texts(s)
    seu(stu, "F12")
    assert set(store.objects[("SCRATCH", "QRPGLESRC", "*FILE")].data["members"]) == {"A", "B"}
    seu(stu, opt0="4")
    s = seu(stu)
    assert "1 member deleted." in " ".join(texts(s))
    assert set(store.objects[("SCRATCH", "QRPGLESRC", "*FILE")].data["members"]) == {"B"}


def test_copy_rename_and_change_text_read_their_value_from_the_command_line(store, stu):
    put(store, "A", ["x"])
    cmd(stu, "WRKMBRPDM FILE(SCRATCH/QRPGLESRC)")
    seu(stu, opt0="3", command="A2")
    seu(stu, opt0="7", command="A3")
    m = store.objects[("SCRATCH", "QRPGLESRC", "*FILE")].data["members"]
    assert set(m) == {"A2", "A3"} and m["A3"]["lines"] == ["x"]
    seu(stu, opt0="13", command="New words")
    assert store.objects[("SCRATCH", "QRPGLESRC", "*FILE")].data["members"]["A2"]["text"] == "New words"


def test_position_to_scrolls_the_list(store, stu):
    for n in "ABCDEFGHIJKLMNOP":
        put(store, n, ["x"])
    cmd(stu, "WRKMBRPDM FILE(SCRATCH/QRPGLESRC)")
    s = seu(stu, pos="M")
    assert "M" in texts(s) and "A" not in texts(s)


def test_a_generic_member_name_filters_the_list(store, stu):
    for n in ("ABC", "ABD", "XYZ"):
        put(store, n, ["x"])
    s = cmd(stu, "WRKMBRPDM FILE(SCRATCH/QRPGLESRC) MBR(AB*)")
    assert "ABC" in texts(s) and "XYZ" not in texts(s)


def test_a_command_typed_on_the_pdm_line_runs(store, stu):
    cmd(stu, "WRKMBRPDM FILE(SCRATCH/QRPGLESRC)")
    s = seu(stu, command="CRTSRCPF FILE(SCRATCH/QDDSSRC)")
    assert "File QDDSSRC created in library SCRATCH." in " ".join(texts(s))
    assert ("SCRATCH", "QDDSSRC", "*FILE") in store.objects


def test_the_whole_loop_write_compile_run(store, stu):
    cmd(stu, "CRTSRCPF FILE(SCRATCH/QDDSSRC)")
    cmd(stu, "STRSEU SRCFILE(SCRATCH/QDDSSRC) SRCMBR(SCR) TYPE(DSPF)")
    put_dds = ["     A          R FMT", "     A                                  1  2'FROM THE EDITOR'"]
    seu(stu, seu="SAVE")
    f = store.objects[("SCRATCH", "QDDSSRC", "*FILE")]
    source.put_member(store, f, "SCR", put_dds, "DSPF")
    seu(stu, seu="CANCEL")
    cmd(stu, "CRTDSPF FILE(SCRATCH/SCR) SRCFILE(SCRATCH/QDDSSRC)")
    put(store, "SHOW", ["     FSCR       CF   E             WORKSTN", "     C                   EXFMT     FMT",
                        "     C                   EVAL      *inlr = *on", "     C                   RETURN"])
    cmd(stu, "CRTBNDRPG PGM(SCRATCH/SHOW) SRCFILE(SCRATCH/QRPGLESRC)")
    s = cmd(stu, "CALL PGM(SCRATCH/SHOW)")
    assert "FROM THE EDITOR" in texts(s)
