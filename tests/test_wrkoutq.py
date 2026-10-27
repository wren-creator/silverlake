"""WRKOUTQ, laid out from the PUB400 captures of Work with Output Queue."""

import pytest

from silverlake.screens.model import Input, Text
from silverlake.screens.signon import SignonController
from silverlake.system import profiles
from silverlake.system.authority import Auth


@pytest.fixture
def store():
    return profiles.load()


def signed(store, user="STUDENT", device="QPADEV0051"):
    c = SignonController(device, store)
    c.handle("ENTER", {"user": user, "password": user})
    return c


def at(s):
    return {(f.row, f.col): f.text for f in s.fields if isinstance(f, Text)}


def text(s):
    return " | ".join(f.text for f in s.fields if isinstance(f, Text))


def test_a_queue_that_is_not_there_gets_the_captured_wording_whatever_is_missing(store):
    c = signed(store)
    assert "Output queue NOQUEUE in library SLNOSUCH not found." in text(
        c.handle("ENTER", {"command": "wrkoutq outq(slnosuch/noqueue)"}))              # no such library
    assert "Output queue NOQUEUE in library QGPL not found." in text(
        c.handle("ENTER", {"command": "wrkoutq outq(qgpl/noqueue)"}))                  # no such queue
    assert "Output queue NOQUEUE in library *LIBL not found." in text(
        c.handle("ENTER", {"command": "wrkoutq noqueue"}))


def test_the_layout_follows_the_capture(store):
    c = signed(store)
    s = c.handle("ENTER", {"command": "wrkoutq outq(qgpl/qprint)"})
    f = at(s)
    assert f[(0, 29)] == "Work with Output Queue"
    assert (f[(2, 1)], f[(2, 10)], f[(2, 25)], f[(2, 36)], f[(2, 51)], f[(2, 61)]) == (
        "Queue:", "QPRINT", "Library:", "QGPL", "Status:", "RLS")
    assert [f[(5, col)] for col in (3, 12, 23, 32, 43, 55, 67)] == [
        "1=Send", "2=Change", "3=Hold", "4=Delete", "5=Display", "6=Release", "7=Messages"]
    assert f[(6, 3)] == "8=Attributes" and f[(6, 23)] == "9=Work with printing status"
    assert [f[(8, col)] for col in (1, 6, 18, 30, 42, 48, 56, 64, 76)] == [
        "Opt", "File", "User", "User Data", "Sts", "Pages", "Copies", "Form Type", "Pty"]
    assert f[(9, 6)] and (9, 42) in f and f[(9, 64)] == "*STD" and f[(9, 77)] == "5"   # rows start at 9
    assert f[(18, 67)] == "      Bottom"
    assert f[(19, 1)] == "Parameters for options 1, 2, 3 or command" and f[(20, 1)] == "===>"
    inputs = [(i.row, i.col, i.length) for i in s.inputs()]
    assert inputs[0] == (9, 2, 1) and inputs[-1] == (20, 6, 73)


def test_whoever_may_list_the_queue_sees_every_file_with_its_user_and_job(store):
    """The recon point from the capture: the job log queue hides what is inside, not who is in it."""
    c = signed(store)
    s = c.handle("ENTER", {"command": "wrkoutq outq(qusrsys/qezjoblog)"})
    f = at(s)
    users = {f[(r, 18)] for r in range(9, 18) if (r, 18) in f}
    assert users - {"STUDENT"}, "a basic profile should see other people's job logs listed"
    assert all(f[(r, 6)] == "QPJOBLOG" for r in range(9, 18) if (r, 6) in f)
    # the contents are another matter: the display rule (DSPDTA *OWNER) still refuses someone else's log
    other = next(i for i in range(9, 18) if f.get((i, 18)) not in (None, "STUDENT"))
    s = c.handle("ENTER", {f"opt{other - 9}": "5"})
    assert "Not authorized to spooled file." in text(s)


def test_a_queue_you_may_not_read_is_refused(store):
    c = signed(store, "QSECOFR")
    c.handle("ENTER", {"command": "rvkobjaut obj(qgpl/qprint) objtype(*outq) user(*public) aut(*all)"})
    s = signed(store, "STUDENT", "QPADEV0052").handle("ENTER", {"command": "wrkoutq outq(qgpl/qprint)"})
    assert "Not authorized to output queue QPRINT." in text(s)
    assert Auth.READ not in store.objects[("QGPL", "QPRINT", "*OUTQ")].public


def test_hold_and_release_from_the_queue_list(store):
    c = signed(store, "QSECOFR")
    s = c.handle("ENTER", {"command": "wrkoutq outq(qgpl/qprint)"})
    name = at(s)[(9, 6)]
    s = c.handle("ENTER", {"opt0": "3"})
    assert at(s)[(9, 42)] == "HLD"
    s = c.handle("ENTER", {"opt0": "6"})
    assert at(s)[(9, 42)] == "RDY"
    assert "Option 4 is not available" in text(c.handle("ENTER", {"opt0": "4"}))
    assert "Option 11 is not valid" in text(c.handle("ENTER", {"opt0": "11"}))


def test_option_5_displays_a_file_and_f12_comes_back_to_the_queue(store):
    c = signed(store)
    c.handle("ENTER", {"command": "wrkoutq outq(qgpl/qprint)"})
    s = c.handle("ENTER", {"opt0": "5"})
    assert "Display Spooled File" in text(s)
    assert "Work with Output Queue" in text(c.handle("F12", {}))


def test_all_queues_is_not_built_and_says_so(store):
    c = signed(store)
    assert "not available in Silverlake yet" in text(c.handle("ENTER", {"command": "wrkoutq"}))


def test_the_command_is_an_object_like_the_others(store):
    assert ("QSYS", "WRKOUTQ", "*CMD") in store.objects
