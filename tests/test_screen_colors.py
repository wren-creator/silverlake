"""Colors follow the PUB400 captures: labels, values, list rows and numbered options are green, titles,
column headings and the More... and Bottom markers are white, prompts and key lines are blue. Turquoise
is only the sign-on screen's own information block."""

import pytest

from silverlake.proto import datastream as ds
from silverlake.screens.model import Text
from silverlake.screens.signon import SignonController
from silverlake.system import state


@pytest.fixture
def store(tmp_path):
    s, db = state.open_store(state_dir=tmp_path)
    yield s
    db.close()


def _screens(store):
    c = SignonController("QPADEV0001", store)
    c.handle("ENTER", {"user": "QSECOFR", "password": "QSECOFR"})
    for line in ("WRKOBJ OBJ(QGPL/*ALL) OBJTYPE(*LIB)", "WRKACTJOB", "DSPMSG MSGQ(*SYSOPR)", "WRKSPLF SELECT(*ALL)",
                 "DSPJOBLOG", "DSPJOB", "WRKJOB", "DSPAUTL AUTL(QPWFSERVER)", "WRKUSRPRF", "DSPLIBL", "WRKLIB LIB(*ALL)"):
        yield line, c.handle("ENTER", {"command": line})
        while c.view is not None:
            c.handle("F12", {})


def test_no_screen_but_signon_uses_turquoise_and_markers_are_white(store):
    seen = 0
    for line, s in _screens(store):
        for t in (x for x in s.fields if isinstance(x, Text)):
            seen += 1
            assert t.attr != ds.ATTR_TURQUOISE, (line, t.text)
            if t.text in ("More...", "Bottom"):
                assert t.attr == ds.ATTR_WHITE, (line, t.text)
    assert seen > 200


def test_list_rows_and_header_values_are_green_and_keys_are_blue(store):
    c = SignonController("QPADEV0001", store)
    c.handle("ENTER", {"user": "QSECOFR", "password": "QSECOFR"})
    f = {(x.row, x.col): x for x in c.handle("ENTER", {"command": "wrkactjob"}).fields if isinstance(x, Text)}
    assert f[(9, 6)].attr == ds.ATTR_GREEN and f[(2, 10)].attr == ds.ATTR_GREEN        # a job row, the CPU % value
    assert f[(8, 6)].attr == ds.ATTR_WHITE and f[(0, 29)].attr == ds.ATTR_WHITE         # column heading, title
    assert any(x.attr == ds.ATTR_BLUE and x.text.startswith("F3=Exit") for x in f.values())
