"""DSPLIBL and DSPOBJAUT follow the real PUB400 layouts: positions, page size, Top and Bottom."""

import pytest

from silverlake.screens.model import Text
from silverlake.screens.signon import SignonController
from silverlake.system import profiles


@pytest.fixture
def ctl():
    store = profiles.load()
    c = SignonController("QPADEV0001", store)
    c.handle("ENTER", {"user": "QSECOFR", "password": "QSECOFR"})
    return c


def runs(screen):
    return {(f.row, f.col): f.text for f in screen.fields if isinstance(f, Text)}


def test_dsplibl_matches_the_captured_positions(ctl):
    r = runs(ctl.handle("ENTER", {"command": "dsplibl"}))
    assert r[(0, 12)].strip() == "Display Library List"
    assert r[(1, 61)] == "System:"
    assert (r[(8, 6)], r[(8, 18)], r[(8, 28)], r[(8, 40)]) == ("Library", "Type", "Device", "Text")
    assert r[(9, 6)] == "QSYS" and r[(9, 18)] == "SYS"          # rows start at 9
    assert r[(21, 67)] == "      Bottom"                         # padded run, as captured
    assert [r[(22, c)] for c in (1, 11, 24, 34)] == ["F3=Exit", "F12=Cancel", "F17=Top", "F18=Bottom"]


def test_dsplibl_pages_twelve_rows_and_f17_f18_jump(ctl):
    for i in range(14):
        ctl.handle("ENTER", {"command": f"crtlib LIB(LIB{i:02d})"})
        ctl.handle("ENTER", {"command": f"addlible LIB{i:02d}"})
    first = runs(ctl.handle("ENTER", {"command": "dsplibl"}))
    assert first[(21, 67)].strip() == "More..."
    assert (20, 6) in first and (21, 6) not in first              # 12 rows, 9 through 20
    bottom = runs(ctl.handle("F18", {}))
    assert bottom[(21, 67)].strip() == "Bottom" and (9, 6) in bottom
    assert runs(ctl.handle("F17", {}))[(9, 6)] == "QSYS"


def test_dspobjaut_matches_the_captured_layout(ctl):
    r = runs(ctl.handle("ENTER", {"command": "dspobjaut OBJ(QGPL) OBJTYPE(*LIB)"}))
    assert r[(2, 1)] == "Object . . . . . . . :" and r[(2, 26)] == "QGPL"
    assert r[(3, 28)] == "QSYS" and r[(4, 26)] == "*LIB" and r[(4, 67)] == "*SYSBAS"
    assert r[(6, 67)] == "*NONE"
    assert (r[(9, 1)], r[(9, 13)], r[(9, 25)]) == ("User", "Group", "Authority")
    assert r[(10, 1)] and (10, 25) in r                          # rows start at 10
    assert r[(18, 67)].strip() in ("Bottom", "More...")
    assert r[(21, 1)] == "F3=Exit" and r[(22, 1)] == "F18=Bottom"
