"""Running RPG IV programs on the rpgle runtime: CALL, the screens, keys, errors, calls between
programs, and DSPPGM (from the auth-callpgm capture)."""

import pytest

from silverlake.screens.model import Input, Text
from silverlake.screens.signon import SignonController
from silverlake.system import profiles, rpg, state
from silverlake.system.authority import EXCLUDE, USE, SecuredObject


@pytest.fixture
def store():
    return profiles.load()


def signed(store, user="STUDENT", device="QPADEV0041"):
    c = SignonController(device, store)
    c.handle("ENTER", {"user": user, "password": user})
    return c


def at(s):
    return {(f.row, f.col): f.text for f in s.fields if isinstance(f, Text)}


def text(s):
    return " | ".join(f.text for f in s.fields if isinstance(f, Text))


def add_program(store, name, source, dspf="", lib="APPLIB", owner="QSECOFR", public=USE, **data):
    obj = SecuredObject(name, owner, public=public, library=lib, type="*PGM", text=f"test {name}",
                        data={"attr": "RPGLE", "usrprf": "*USER", "useadpaut": "*YES", "source": source,
                              "dspf": dspf, **data})
    store.objects[obj.key] = obj
    return obj


LOOP = "\n".join([
    "     D n               S              5  0",
    "     C                   DOW       *in01 = *off",
    "     C                   EVAL      n = n + 1",
    "     C                   ENDDO",
]) + "\n"


def test_the_seeded_programs_are_real_objects_with_source(store):
    for name in ("ADVENTURE", "SALESRPT"):
        obj = store.objects[("APPLIB", name, "*PGM")]
        assert rpg.is_rpg(obj) and "WORKSTN" in obj.data["source"]
    for name in ("SCREEN", "REPORT"):                       # their display files are objects of their own
        assert store.objects[("APPLIB", name, "*FILE")].data["attr"] == "DSPF"


def test_call_runs_the_program_and_its_screen_lands_where_the_dds_put_it(store):
    c = signed(store)
    s = c.handle("ENTER", {"command": "CALL PGM(APPLIB/SALESRPT)"})
    f = at(s)
    assert f[(0, 28)] == "REGIONAL SALES REPORT"                      # DDS row 1, column 29
    assert f[(5, 2)] == "North America" and f[(5, 29)] == "01200"      # calculated by the program
    assert f[(11, 29)] == "005665"
    assert [(i.name, i.row, i.col) for i in s.fields if isinstance(i, Input)] == [("cmd", 13, 23)]


def test_every_screen_a_seeded_program_shows_is_a_valid_5250_screen(store):
    c = signed(store)
    for prog, first in (("SALESRPT", {}), ("ADVENTURE", {"cmd": "M"})):
        s = c.handle("ENTER", {"command": f"CALL PGM(APPLIB/{prog})"})
        s.validate()
        if first:
            c.handle("ENTER", first).validate()
        c._sign_off()
        c.handle("ENTER", {"user": "STUDENT", "password": "STUDENT"})


def test_enter_ends_a_program_that_ends_and_the_menu_comes_back(store):
    c = signed(store)
    c.handle("ENTER", {"command": "CALL PGM(APPLIB/SALESRPT)"})
    s = c.handle("ENTER", {})
    assert "Silverlake Main Menu" in text(s) and c.view is None


def test_a_program_that_wants_input_gets_it_and_a_key_it_declared(store):
    c = signed(store)
    s = c.handle("ENTER", {"command": "CALL PGM(APPLIB/ADVENTURE)"})
    assert "ADVENTURE" in text(s) and "a dark forest" in text(s)
    s = c.handle("ENTER", {"cmd": "M"})
    assert "COMBAT" in text(s) or "forest" in text(s) or "goblin" in text(s)
    assert "Silverlake Main Menu" in text(c.handle("F3", {}))           # the display file asks for F3 (CF03)


def test_a_key_the_display_file_never_named_is_refused_where_it_stands(store):
    c = signed(store)
    c.handle("ENTER", {"command": "CALL PGM(APPLIB/ADVENTURE)"})
    s = c.handle("F12", {})
    assert "Function key not allowed." in text(s) and "ADVENTURE" in text(s)
    assert c.view is not None


def test_letters_in_a_number_field_never_reach_the_program(store):
    prog = "\n".join([
        "     FNUMS      CF   E             WORKSTN",
        "     D qty             S              3  0",
        "     C                   EXFMT     NUMS",
        "     C                   EVAL      *inlr = *on",
        "     C                   RETURN",
    ]) + "\n"
    dds = "\n".join(["     A          R NUMS", "     A                                  1  2'Qty'",
                     "     A            QTY            3  0B  1 10"]) + "\n"
    add_program(store, "NUMS", prog, dds)
    c = signed(store)
    c.handle("ENTER", {"command": "CALL PGM(APPLIB/NUMS)"})
    s = c.handle("ENTER", {"qty": "ab"})
    assert "takes numbers only" in text(s) and c.view is not None
    assert "Silverlake Main Menu" in text(c.handle("ENTER", {"qty": "12"}))


def test_a_runaway_loop_is_stopped_and_the_server_keeps_going(store):
    add_program(store, "SPIN", LOOP)
    c = signed(store)
    s = c.handle("ENTER", {"command": "CALL PGM(APPLIB/SPIN)"})
    assert "ended abnormally" in text(s) and "instructions" in text(s)
    assert c.view is None


def test_a_program_that_does_not_parse_says_so_and_does_not_start(store):
    add_program(store, "BROKEN", "     C                   NOSUCHOP  x\n")
    c = signed(store)
    assert "ended abnormally" in text(c.handle("ENTER", {"command": "CALL PGM(APPLIB/BROKEN)"}))


def test_a_program_that_is_not_there_gets_the_captured_wording(store):
    c = signed(store)
    assert "Program NOSUCHPGM in library *LIBL not found." in text(c.handle("ENTER", {"command": "CALL PGM(NOSUCHPGM)"}))
    assert "Program NOPE in library APPLIB not found." in text(c.handle("ENTER", {"command": "CALL PGM(APPLIB/NOPE)"}))


def test_a_program_you_may_not_use_is_refused_by_authority(store):
    add_program(store, "SECRET", LOOP, public=EXCLUDE)
    c = signed(store)
    assert "Not authorized" in text(c.handle("ENTER", {"command": "CALL PGM(APPLIB/SECRET)"}))


def test_a_program_can_call_another_and_its_screen_shows_through(store):
    sales = store.objects[("APPLIB", "SALESRPT", "*PGM")].data       # a short name: factor 2 holds fourteen characters
    add_program(store, "SR", sales["source"])
    caller = "\n".join(["     C                   CALL      'APPLIB/SR'",
                        "     C                   EVAL      *inlr = *on", "     C                   RETURN"]) + "\n"
    add_program(store, "OUTER", caller)
    c = signed(store)
    s = c.handle("ENTER", {"command": "CALL PGM(APPLIB/OUTER)"})
    assert "REGIONAL SALES REPORT" in text(s)
    assert "Silverlake Main Menu" in text(c.handle("ENTER", {}))


def test_an_unqualified_call_uses_the_library_list_like_the_real_thing(store):
    caller = "\n".join(["     C                   CALL      'SALESRPT'", "     C                   RETURN"]) + "\n"
    add_program(store, "OUTER", caller)
    c = signed(store)
    s = c.handle("ENTER", {"command": "CALL PGM(APPLIB/OUTER)"})
    assert "ended abnormally" in text(s) and "Object SALESRPT in library *LIBL" in text(s)   # APPLIB is not on this list


def test_a_call_cannot_reach_a_program_the_caller_may_not_use(store):
    caller = "\n".join(["     C                   CALL      'APPLIB/SEC'", "     C                   RETURN"]) + "\n"
    add_program(store, "OUTER", caller)
    add_program(store, "SEC", LOOP, public=EXCLUDE)
    c = signed(store)
    s = c.handle("ENTER", {"command": "CALL PGM(APPLIB/OUTER)"})
    assert "ended abnormally" in text(s) and "Not authorized to use object SEC" in text(s)


def test_signing_off_with_a_program_on_the_screen_closes_it(store):
    c = signed(store)
    c.handle("ENTER", {"command": "CALL PGM(APPLIB/ADVENTURE)"})
    run = c.view[1]
    c.store.jobs.jobs  # the job is still there
    c._sign_off()
    assert run.done and c.profile is None


def test_source_and_attributes_survive_a_save_and_load(store):
    again = state.from_dict(state.to_dict(store))
    obj = again.objects[("APPLIB", "ADVENTURE", "*PGM")]
    assert obj.data["attr"] == "RPGLE" and "WORKSTN" in obj.data["source"]
    assert "R MAIN" in again.objects[("APPLIB", "SCREEN", "*FILE")].data["dds"]


def test_dsppgm_shows_the_two_captured_pages(store):
    c = signed(store)
    s = c.handle("ENTER", {"command": "DSPPGM PGM(APPLIB/ADVENTURE)"})
    f = at(s)
    assert f[(0, 26)] == "Display Program Information" and f[(2, 28)] == "ADVENTURE" and f[(3, 28)] == "QSECOFR"
    assert f[(14, 56)] == "*USER" and f[(15, 56)] == "*YES" and f[(19, 67)].strip() == "More..."
    s2 = c.handle("ROLLUP", {})
    assert at(s2)[(6, 3)].startswith("Text description") and at(s2)[(19, 67)].strip() == "Bottom"
    assert "Silverlake Main Menu" in text(c.handle("F12", {}))


def test_dsppgm_needs_the_program_to_exist(store):
    c = signed(store)
    assert "not found" in text(c.handle("ENTER", {"command": "DSPPGM PGM(NOPE)"}))
