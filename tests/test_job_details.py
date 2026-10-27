"""The job screens that were not built: page two of the menus, page two of the status and definition
pages, and options 11, 12, 14, 15 and 16 (call stack, locks, open files, overrides, commitment control)."""

import pytest

from silverlake.screens.model import Text
from silverlake.screens.signon import SignonController
from silverlake.system import profiles


@pytest.fixture
def store():
    return profiles.load()


def signed(store, user="STUDENT", device="QPADEV0031"):
    c = SignonController(device, store)
    c.handle("ENTER", {"user": user, "password": user})
    return c


def text(s):
    return " | ".join(f.text for f in s.fields if isinstance(f, Text))


def at(s):
    return {(f.row, f.col): f.text for f in s.fields if isinstance(f, Text)}


def test_dspjob_page_two_matches_the_capture_and_rolls_back(store):
    c = signed(store)
    c.handle("ENTER", {"command": "dspjob"})
    s = c.handle("ROLLUP", {})
    f = at(s)
    assert f[(6, 5)] == "17. Display communications status, if active"
    assert f[(8, 5)] == "19. Display mutexes, if active" and f[(13, 5)] == "30. All of the above"
    assert f[(18, 67)] == "      Bottom" and (15, 5) not in f             # no 40, 41, 42 on Display Job
    assert at(c.handle("ROLLDOWN", {}))[(6, 6)] == "1. Display job status attributes"
    c.handle("ROLLUP", {})
    assert "Option 40 is not valid" in text(c.handle("ENTER", {"selection": "40"}))


def test_wrkjob_page_two_adds_change_end_and_hold(store):
    c = signed(store)
    c.handle("ENTER", {"command": "wrkjob"})
    f = at(c.handle("ROLLUP", {}))
    assert f[(8, 5)] == "19. Work with mutexes, if active"
    assert [f[(r, 5)] for r in (15, 16, 17)] == ["40. Change job", "41. End job", "42. Hold job"]
    assert f[(18, 67)] == "     More..."                                   # a third page exists
    third = at(c.handle("ROLLUP", {}))
    assert third[(6, 5)] == "43. Release job" and third[(8, 5)].startswith("45. Work with Java")
    assert third[(18, 67)] == "      Bottom"
    assert at(c.handle("ROLLUP", {}))[(18, 67)] == "      Bottom"             # nowhere further to go


def test_wrkjob_option_42_holds_and_41_ends_the_job(store):
    c = signed(store)
    c.handle("ENTER", {"command": "wrkjob"})
    c.handle("ROLLUP", {})
    s = c.handle("ENTER", {"command": "42"})
    assert c.session.job.status == "HLD" or c.session.job.held_from
    assert "17." in text(s) or "42." in text(s)
    c.handle("ENTER", {"command": "41"})
    assert c.session.job.ending


def test_status_and_definition_page_two(store):
    c = signed(store)
    c.handle("ENTER", {"command": "dspjob"})
    c.handle("ENTER", {"selection": "1"})
    f = at(c.handle("ROLLUP", {}))
    assert f[(4, 1)].startswith("Controlled end requested") and f[(4, 49)] == "NO"
    assert f[(5, 49)] == "SILVERLK" and f[(19, 67)] == "      Bottom"
    assert at(c.handle("ROLLDOWN", {}))[(4, 1)].startswith("Status of job")
    c.handle("F12", {})
    f = at(c.handle("ENTER", {"selection": "2"}))
    assert f[(19, 67)] == "     More..."
    f = at(c.handle("ROLLUP", {}))
    assert f[(4, 1)].startswith("Printer device") and f[(8, 55)] == "*YMD"
    assert f[(14, 55)] in ("*MON", "*TUE", "*WED", "*THU", "*FRI", "*SAT", "*SUN")
    assert f[(19, 67)] == "      Bottom"


def test_call_stack_open_files_overrides_and_commitment(store):
    c = signed(store)
    c.handle("ENTER", {"command": "dspjob"})
    f = at(c.handle("ENTER", {"selection": "11"}))
    assert f[(0, 31)] == "Display Call Stack" and f[(7, 7)].startswith("QCMD") and f[(11, 7)].startswith("QUICMD")
    c.handle("F12", {})
    f = at(c.handle("ENTER", {"selection": "14"}))
    assert f[(0, 20)].strip() == "Display Open Files" and f[(8, 1)] == "QDUI80" and f[(8, 23)] == "QPADEV0031"
    assert f[(3, 51)].strip() == "2"
    c.handle("F12", {})
    assert "(No file overrides)" in text(c.handle("ENTER", {"selection": "15"}))
    c.handle("F12", {})
    assert "(No commitment definitions are active)" in text(c.handle("ENTER", {"selection": "16"}))
    assert at(c.handle("F16", {}))[(0, 34)] == "Display Job"                 # back to the job menu


def test_locks_show_what_the_session_holds(store):
    c = signed(store)
    c.handle("ENTER", {"command": "addlible APPLIB"})
    c.handle("ENTER", {"command": "dspjob"})
    s = c.handle("ENTER", {"selection": "12"})
    f = at(s)
    assert f[(0, 12)].strip() == "Display Job Locks" and f[(4, 15)] == "ACTIVE"
    shown = [(f[(r, 6)], f[(r, 30)], f[(r, 41)]) for r in range(11, 20) if (r, 6) in f]
    assert ("QSYS", "*LIB", "*SHRRD") in shown and ("QGPL", "*LIB", "*SHRRD") in shown
    assert ("MAIN", "*MENU", "*SHRNUP") in shown or ("QDUI80", "*FILE-DSP", "*SHRNUP") in shown
    assert [r[0] for r in shown] == sorted(r[0] for r in shown)           # sorted by object, as captured
    assert all(f[(r, 51)] == "HELD" for r in range(11, 20) if (r, 6) in f)


def test_work_with_job_locks_is_the_wrkjob_flavor(store):
    c = signed(store)
    c.handle("ENTER", {"command": "wrkjob"})
    f = at(c.handle("ENTER", {"command": "12"}))
    assert f[(0, 12)].strip() == "Work with Job Locks"


def test_another_jobs_detail_screens_follow_the_same_rule_as_its_menu(store):
    victim = signed(store, "STUDENT", "QPADEV0041")
    spy = signed(store, "STUDENT", "QPADEV0042")
    spy.handle("ENTER", {"command": f"dspjob job({victim.session.job.qualified})"})
    s = spy.handle("ENTER", {"selection": "12"})
    assert "Display Job Locks" in text(s) and "QPADEV0041" in text(s)
    # a system job holds nothing here, and says so by showing an empty list
    sysjob = next(j for j in store.jobs.active() if j.name == "QSYSSCD")
    assert sysjob.info is None


def test_unbuilt_page_two_options_say_so(store):
    c = signed(store)
    c.handle("ENTER", {"command": "dspjob"})
    c.handle("ROLLUP", {})
    assert "Option 30 is not available" in text(c.handle("ENTER", {"selection": "30"}))
