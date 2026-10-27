"""Display files as objects: found by the F-spec name through the library list, shared between programs,
needing *USE, and changeable without touching the program."""

import pytest

from silverlake.screens.model import Input, Text
from silverlake.screens.signon import SignonController
from silverlake.system import profiles
from silverlake.system.authority import EXCLUDE


@pytest.fixture
def store():
    return profiles.load()


def signed(store, user="STUDENT"):
    c = SignonController("QPADEV0101", store)
    c.handle("ENTER", {"user": user, "password": user})
    return c


def texts(s):
    return [f.text for f in s.fields if isinstance(f, Text)]


def joblog(c):
    return " | ".join(t for _, _, t in c.session.joblog)


def test_two_programs_share_one_display_file_object(store):
    # RUNCMD and RUNCMDX both open a display file named RUNCMD: one object, one layout.
    dspf = [o for o in store.objects.values() if o.name == "RUNCMD" and o.type == "*FILE"]
    assert len(dspf) == 1 and dspf[0].data["attr"] == "DSPF"
    shown = []
    for prog in ("RUNCMD", "RUNCMDX"):
        c = signed(store)
        s = c.handle("ENTER", {"command": f"CALL PGM(APPLIB/{prog})"})
        shown.append(texts(s))
    assert shown[0] == shown[1] and "COMMAND HELPER" in shown[0]


def test_changing_the_display_file_changes_the_screen_for_every_program_that_uses_it(store):
    obj = store.objects[("APPLIB", "RUNCMD", "*FILE")]
    obj.data["dds"] = obj.data["dds"].replace("COMMAND HELPER", "SUPPORT TOOL  ")
    for prog in ("RUNCMD", "RUNCMDX"):
        c = signed(store)
        assert "SUPPORT TOOL" in " ".join(texts(c.handle("ENTER", {"command": f"CALL PGM(APPLIB/{prog})"})))


def test_a_display_file_needs_use_authority(store):
    store.objects[("APPLIB", "EMPINQ", "*FILE")].public = EXCLUDE
    c = signed(store, "OPERATOR")
    c.handle("ENTER", {"command": "ADDLIBLE APPLIB"})
    c.handle("ENTER", {"command": "CALL PGM(PAYLOOK)"})
    assert "Not authorized to use object EMPINQ" in joblog(c)


def test_a_missing_display_file_stops_the_program(store):
    del store.objects[("APPLIB", "SCREEN", "*FILE")]
    c = signed(store)
    c.handle("ENTER", {"command": "CALL PGM(APPLIB/ADVENTURE)"})
    assert "SCREEN" in joblog(c) and "not found" in joblog(c)


def test_a_file_that_is_not_a_display_file_is_refused(store):
    store.objects[("APPLIB", "SCREEN", "*FILE")].data["attr"] = "PF"
    c = signed(store)
    c.handle("ENTER", {"command": "CALL PGM(APPLIB/ADVENTURE)"})
    assert "is not a display file" in joblog(c)


def test_the_programs_own_library_is_tried_when_it_is_not_on_the_list(store):
    c = signed(store)                                   # APPLIB is not on STUDENT's list
    s = c.handle("ENTER", {"command": "CALL PGM(APPLIB/SALESRPT)"})
    assert "REGIONAL SALES REPORT" in texts(s)
    assert any(isinstance(f, Input) for f in s.fields)
