"""Source files, members and the compile commands: CRTSRCPF, CRTBNDRPG, CRTPF, CRTDSPF, CRTPRTF."""

import pytest

from silverlake.cl import commands
from silverlake.cl.session import Session
from silverlake.screens.model import Text
from silverlake.screens.signon import SignonController
from silverlake.system import profiles, rpg, source
from silverlake.system.authority import CHANGE, EXCLUDE, USE


@pytest.fixture
def store():
    return profiles.load()


def run(store, user, line, session=None):
    s = session or Session.for_profile(store.get(user).current_library)
    return commands.execute(store, store.get(user), line, s)


def said(out):
    return out.message.text if out.message else ""


def sess(store, user="STUDENT", *libs):
    s = Session.for_profile(store.get(user).current_library)
    s.user_libs += list(libs)
    return s


def src_file(store, user="STUDENT", spec="SCRATCH/QRPGLESRC", s=None):
    s = s or sess(store, user, "SCRATCH")
    assert "created" in said(run(store, user, f"CRTSRCPF FILE({spec})", s))
    return store.objects[("SCRATCH", spec.split("/")[1], "*FILE")], s


HELLO = ["     C                   EVAL      x = 1", "     C                   EVAL      *inlr = *on",
         "     C                   RETURN"]


def test_crtsrcpf_makes_a_source_file_with_the_captured_defaults(store):
    f, _ = src_file(store)
    assert f.data["attr"] == "PF-SRC" and f.data["rcdlen"] == 92 and f.data["members"] == {}
    assert f.owner == "STUDENT" and source.width(f) == 80


def test_crtsrcpf_can_add_a_member_and_refuses_a_file_that_exists(store):
    s = sess(store, "STUDENT", "SCRATCH")
    assert "created" in said(run(store, "STUDENT", "CRTSRCPF FILE(SCRATCH/QRPGLESRC) MBR(FIRST)", s))
    assert "FIRST" in store.objects[("SCRATCH", "QRPGLESRC", "*FILE")].data["members"]
    assert "already exists" in said(run(store, "STUDENT", "CRTSRCPF FILE(SCRATCH/QRPGLESRC)", s))


def test_crtsrcpf_needs_authority_to_the_library(store):
    out = run(store, "GUEST", "CRTSRCPF FILE(APPLIB/QRPGLESRC)")
    assert "Not authorized" in said(out) and ("APPLIB", "QRPGLESRC", "*FILE") not in store.objects
    assert "not found" in said(run(store, "STUDENT", "CRTSRCPF FILE(NOSUCH/QRPGLESRC)"))


def test_a_member_compiles_to_a_program_that_belongs_to_the_compiler(store):
    f, s = src_file(store)
    source.put_member(store, f, "HELLO", HELLO, "RPGLE", "Say hello")
    out = run(store, "STUDENT", "CRTBNDRPG PGM(SCRATCH/HELLO) SRCFILE(SCRATCH/QRPGLESRC) USRPRF(*OWNER)", s)
    assert "Program HELLO placed in library SCRATCH. 00 highest severity." in said(out)
    p = store.objects[("SCRATCH", "HELLO", "*PGM")]
    assert p.owner == "STUDENT" and p.text == "Say hello"          # *SRCMBRTXT is the default
    assert p.data["usrprf"] == "*OWNER" and p.data["useadpaut"] == "*YES" and rpg.is_rpg(p)


def test_adopting_a_program_you_compiled_only_adopts_yourself(store):
    f, s = src_file(store)
    source.put_member(store, f, "HELLO", HELLO)
    run(store, "STUDENT", "CRTBNDRPG PGM(SCRATCH/HELLO) SRCFILE(SCRATCH/QRPGLESRC) USRPRF(*OWNER)", s)
    assert rpg.adopted_owners(store, ["SCRATCH/HELLO"]) == ["STUDENT"]
    assert store.adopting(store.get("STUDENT"), ["STUDENT"]).adopted == ()


def test_the_default_member_is_the_program_name_and_pgm_defaults_to_the_member(store):
    f, s = src_file(store)
    source.put_member(store, f, "HELLO", HELLO)
    assert "placed" in said(run(store, "STUDENT", "CRTBNDRPG PGM(SCRATCH/HELLO) SRCFILE(SCRATCH/QRPGLESRC)", s))
    assert "placed" in said(run(store, "STUDENT", "CRTBNDRPG SRCFILE(SCRATCH/QRPGLESRC) SRCMBR(HELLO) PGM(SCRATCH/AGAIN)", s))
    assert "Parameter PGM required." in said(run(store, "STUDENT", "CRTBNDRPG SRCFILE(SCRATCH/QRPGLESRC)", s))


def test_a_member_that_cannot_be_opened_says_what_the_real_compiler_said(store):
    s = sess(store, "STUDENT", "SCRATCH")
    assert said(run(store, "STUDENT", "CRTBNDRPG PGM(NOSUCH/NOPGM) SRCFILE(NOSUCH/QRPGLESRC)", s)) == \
        "Unable to open member NOPGM of file QRPGLESRC in library NOSUCH."
    src_file(store, s=s)
    assert "Unable to open member NOPE of file QRPGLESRC" in said(
        run(store, "STUDENT", "CRTBNDRPG PGM(SCRATCH/NOPE) SRCFILE(SCRATCH/QRPGLESRC)", s))


def test_a_compile_with_errors_makes_no_program_and_prints_a_listing(store):
    f, s = src_file(store)
    source.put_member(store, f, "BAD", ["     C                   BOGUS"])
    out = run(store, "STUDENT", "CRTBNDRPG PGM(SCRATCH/BAD) SRCFILE(SCRATCH/QRPGLESRC)", s)
    assert "Compilation failed. Program BAD not created in library SCRATCH." == said(out)
    assert ("SCRATCH", "BAD", "*PGM") not in store.objects
    [lst] = [x for x in store.spool if x.name == "QSYSPRT"]
    assert lst.user == "STUDENT" and (lst.outq_lib, lst.outq) == ("QGPL", "QPRINT") and lst.user_data == "BAD"
    text = "\n".join(lst.lines)
    assert "BOGUS" in text and "Unsupported RPG opcode" in text and "Compilation failed" in text


def test_a_file_the_program_declares_has_to_exist_to_compile(store):
    f, s = src_file(store)
    source.put_member(store, f, "NEEDS", ["     FNOSUCHF   IF   E           K DISK", *HELLO])
    out = run(store, "STUDENT", "CRTBNDRPG PGM(SCRATCH/NEEDS) SRCFILE(SCRATCH/QRPGLESRC)", s)
    assert "Compilation failed" in said(out)
    assert "File NOSUCHF was not found" in "\n".join(next(x for x in store.spool if x.name == "QSYSPRT").lines)


def test_a_successful_compile_prints_a_listing_too(store):
    f, s = src_file(store)
    source.put_member(store, f, "HELLO", HELLO)
    run(store, "STUDENT", "CRTBNDRPG PGM(SCRATCH/HELLO) SRCFILE(SCRATCH/QRPGLESRC)", s)
    [lst] = [x for x in store.spool if x.name == "QSYSPRT"]
    assert "placed in library SCRATCH" in "\n".join(lst.lines) and "EVAL      x = 1" in "\n".join(lst.lines)


def test_replacing_a_program_makes_the_compiler_the_owner_and_keeps_the_authorities(store):
    f, s = src_file(store)
    source.put_member(store, f, "PAYADJ", HELLO)
    s2 = sess(store, "STUDENT", "SCRATCH", "APPLIB")
    out = run(store, "STUDENT", "CRTBNDRPG PGM(APPLIB/PAYADJ) SRCFILE(SCRATCH/QRPGLESRC)", s2)
    assert "Not authorized" in said(out)                       # APPLIB is not STUDENT's to add to
    store.objects[("APPLIB", "PAYADJ", "*PGM")].private["STUDENT"] = CHANGE
    store.find_library("APPLIB").public = CHANGE
    out = run(store, "STUDENT", "CRTBNDRPG PGM(APPLIB/PAYADJ) SRCFILE(SCRATCH/QRPGLESRC)", s2)
    assert "Not authorized" in said(out)                       # CHANGE has no *OBJEXIST
    store.objects[("APPLIB", "PAYADJ", "*PGM")].private["STUDENT"] = CHANGE | profiles.Auth.OBJEXIST
    assert "placed" in said(run(store, "STUDENT", "CRTBNDRPG PGM(APPLIB/PAYADJ) SRCFILE(SCRATCH/QRPGLESRC)", s2))
    p = store.objects[("APPLIB", "PAYADJ", "*PGM")]
    assert p.owner == "STUDENT" and p.public == USE and p.private["STUDENT"] & profiles.Auth.OBJEXIST


def test_a_source_file_needs_use_authority(store):
    f, s = src_file(store)
    source.put_member(store, f, "HELLO", HELLO)
    f.public = EXCLUDE
    store.objects[("SCRATCH", "QRPGLESRC", "*FILE")] = f
    out = run(store, "OPERATOR", "CRTBNDRPG PGM(SCRATCH/HELLO) SRCFILE(SCRATCH/QRPGLESRC)", sess(store, "OPERATOR", "SCRATCH"))
    assert "Unable to open member" in said(out)


PF = ["     A          R PEOPLE", "     A            ID             5S 0", "     A            NAME          20A",
      "     A          K ID"]


def test_crtpf_builds_a_file_from_a_dds_member(store):
    f, s = src_file(store, spec="SCRATCH/QDDSSRC")
    source.put_member(store, f, "PEOPLE", PF, "PF", "People")
    out = run(store, "STUDENT", "CRTPF FILE(SCRATCH/PEOPLE) SRCFILE(SCRATCH/QDDSSRC)", s)
    assert said(out) == "File PEOPLE created in library SCRATCH."
    o = store.objects[("SCRATCH", "PEOPLE", "*FILE")]
    assert o.data["attr"] == "PF" and o.data["records"] == [] and "PEOPLE" in o.data["dds"] and o.text == "People"
    assert "already exists" in said(run(store, "STUDENT", "CRTPF FILE(SCRATCH/PEOPLE) SRCFILE(SCRATCH/QDDSSRC)", s))


def test_crtdspf_and_crtprtf_keep_their_dds_and_a_printer_file_gets_the_default_queue(store):
    f, s = src_file(store, spec="SCRATCH/QDDSSRC")
    source.put_member(store, f, "SCR", ["     A          R FMT", "     A                                  1  2'HI'"])
    assert "created" in said(run(store, "STUDENT", "CRTDSPF FILE(SCRATCH/SCR) SRCFILE(SCRATCH/QDDSSRC)", s))
    assert store.objects[("SCRATCH", "SCR", "*FILE")].data["attr"] == "DSPF"
    source.put_member(store, f, "RPT", ["     A          R LINE", "     A            NAME          20A  O     2"])
    assert "created" in said(run(store, "STUDENT", "CRTPRTF FILE(SCRATCH/RPT) SRCFILE(SCRATCH/QDDSSRC)", s))
    assert store.objects[("SCRATCH", "RPT", "*FILE")].data["outq"] == "QGPL/QPRINT"


def test_a_dds_member_with_a_broken_key_is_not_built_and_lists_the_error(store):
    f, s = src_file(store, spec="SCRATCH/QDDSSRC")
    source.put_member(store, f, "BADPF", ["     A          R R1", "     A            ID             5S 0",
                                          "     A          K MISSING"])
    out = run(store, "STUDENT", "CRTPF FILE(SCRATCH/BADPF) SRCFILE(SCRATCH/QDDSSRC)", s)
    assert said(out) == "File BADPF not created in library SCRATCH."
    assert ("SCRATCH", "BADPF", "*FILE") not in store.objects
    assert "MISSING" in "\n".join(next(x for x in store.spool if x.name == "QSYSPRT").lines)


def test_a_file_without_source_is_not_built(store):
    assert "without DDS" in said(run(store, "STUDENT", "CRTPF FILE(SCRATCH/X) SRCFILE(*NONE)"))


def test_the_seeded_members_compile_and_the_program_runs(store):
    c = SignonController("QPADEV0121", store)
    c.handle("ENTER", {"user": "DEVELOPER", "password": "DEVELOPER"})
    for cmd in ("ADDLIBLE SRCLIB", "ADDLIBLE SCRATCH", "CRTDSPF FILE(SCRATCH/HELLOD) SRCFILE(SRCLIB/QDDSSRC)",
                "CRTPF FILE(SCRATCH/CUSTPF) SRCFILE(SRCLIB/QDDSSRC)",
                "CRTBNDRPG PGM(SCRATCH/HELLO) SRCFILE(SRCLIB/QRPGLESRC)"):
        c.handle("ENTER", {"command": cmd})
    s = c.handle("ENTER", {"command": "CALL PGM(SCRATCH/HELLO)"})
    assert "Hello," in [f.text for f in s.fields if isinstance(f, Text)]


def test_members_survive_a_save_and_load(store):
    from silverlake.system import state
    f, _ = src_file(store)
    source.put_member(store, f, "HELLO", HELLO, "RPGLE", "Say hello")
    again = state.from_dict(state.to_dict(store))
    m = again.objects[("SCRATCH", "QRPGLESRC", "*FILE")].data["members"]["HELLO"]
    assert m["lines"] == HELLO and m["type"] == "RPGLE" and m["text"] == "Say hello"


def test_lines_are_cut_to_the_width_of_the_record(store):
    f, _ = src_file(store)
    source.put_member(store, f, "LONG", ["x" * 200])
    assert len(f.data["members"]["LONG"]["lines"][0]) == 80
