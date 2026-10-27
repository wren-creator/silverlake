"""Options 1, 2, 4, 7 and 9 on the spooled file lists, built from the auth-splopts capture."""

import pytest

from silverlake.screens.model import Input, Text
from silverlake.screens.signon import SignonController
from silverlake.system import profiles


@pytest.fixture
def store():
    return profiles.load()


def signed(store, user="QSECOFR", device="QPADEV0061"):
    c = SignonController(device, store)
    c.handle("ENTER", {"user": user, "password": user})
    return c


def text(s):
    return " | ".join(f.text for f in s.fields if isinstance(f, Text))


def at(s):
    return {(f.row, f.col): f.text for f in s.fields if isinstance(f, Text)}


def inputs(s):
    return {f.name: f for f in s.fields if isinstance(f, Input)}


def test_option_9_shows_the_printing_status_and_f12_goes_back(store):
    c = signed(store)
    c.handle("ENTER", {"command": "wrkoutq outq(qgpl/qprint)"})
    s = c.handle("ENTER", {"opt0": "9"})
    t = at(s)
    assert t[(0, 27)] == "Work with Printing Status"
    assert "This file is not associated with a started printer." in text(s)
    assert "Work with Output Queue" in text(c.handle("F12", {}))


def test_option_7_says_there_are_no_messages(store):
    c = signed(store)
    c.handle("ENTER", {"command": "wrksplf select(*all)"})
    s = c.handle("ENTER", {"opt0": "7"})
    assert "No messages for file" in text(s) and "Work with All Spooled Files" in text(s)


def test_option_1_prompts_and_nothing_is_sent(store):
    c = signed(store)
    c.handle("ENTER", {"command": "wrksplf select(*all)"})
    s = c.handle("ENTER", {"opt0": "1"})
    assert at(s)[(0, 19)].strip().startswith("Send Network Spooled File") or "SNDNETSPLF" in text(s)
    assert {"tousrid", "address", "dtafmt"} <= set(inputs(s))
    assert "Nothing was sent" in text(c.handle("ENTER", {}))
    assert "Work with All Spooled Files" in text(c.handle("F12", {}))


def test_option_2_changes_copies_and_form_type(store):
    c = signed(store)
    c.handle("ENTER", {"command": "wrksplf select(*all)"})
    f = c.view[1].rows[0]
    s = c.handle("ENTER", {"opt0": "2"})
    assert "CHGSPLFA" in text(s)
    s = c.handle("ENTER", {"dev": "*OUTQ", "prtseq": "*SAME", "formtype": "INVOICE", "copies": "3", "restart": "*STRPAGE"})
    assert "changed" in text(s) and "Work with All Spooled Files" in text(s)
    assert f.copies == 3 and f.form_type == "INVOICE"


def test_option_2_refuses_a_bad_copy_count_and_stays_on_the_prompt(store):
    c = signed(store)
    c.handle("ENTER", {"command": "wrksplf select(*all)"})
    c.handle("ENTER", {"opt0": "2"})
    s = c.handle("ENTER", {"dev": "*OUTQ", "prtseq": "*SAME", "formtype": "*STD", "copies": "0", "restart": "*STRPAGE"})
    assert "Change Spooled File Attributes" in text(s)


def test_option_2_is_refused_for_someone_elses_file(store):
    c = signed(store, "STUDENT")
    c.handle("ENTER", {"command": "wrksplf select(*all)"})
    assert "Not authorized to spooled file." in text(c.handle("ENTER", {"opt0": "2"}))


def test_option_4_deletes_the_file_from_the_list(store):
    c = signed(store)
    c.handle("ENTER", {"command": "wrksplf select(*all)"})
    n = len(store.spool)
    assert "deleted" in text(c.handle("ENTER", {"opt0": "4"}))
    assert len(store.spool) == n - 1
