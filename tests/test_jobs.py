"""Jobs and WRKACTJOB. Layout positions are from the PUB400 capture."""

import pytest

from silverlake.screens.model import Text
from silverlake.screens.signon import SignonController
from silverlake.system import profiles
from silverlake.system.jobs import JobTable


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("SILVERLAKE_STATE", str(tmp_path))
    return profiles.load()


def _signed(store, user="QSECOFR", device="QPADEV0001"):
    c = SignonController(device, store)
    c.handle("ENTER", {"user": user, "password": user})
    return c


def _text(s):
    return " | ".join(f.text for f in s.fields if isinstance(f, Text))


def test_the_table_is_seeded_with_subsystems_and_their_jobs():
    t = JobTable()
    names = [j.name for j in t.active()]
    assert "QINTER" in names and "QZDASOINIT" in names and "QTCPIP" in names
    assert [j.name for j in t.active()].index("QUSRWRK") < [j.name for j in t.active()].index("QZSOSIGN")
    assert [j.name for j in t.active("QUSRWRK") if j.type == "SBS"] == ["QUSRWRK"]


def test_a_session_is_an_interactive_job_named_after_its_display(store):
    c = _signed(store, "CLERK", "QPADEV0042")
    jobs = store.jobs.find("QPADEV0042")
    assert len(jobs) == 1 and jobs[0].user == "CLERK" and jobs[0].type == "INT" and jobs[0].subsystem == "QINTER"
    c.close()
    assert store.jobs.find("QPADEV0042") == []                 # a dropped connection ends the job too


def test_job_numbers_are_unique_six_digits(store):
    _signed(store, "CLERK", "QPADEV0001"), _signed(store, "QSECOFR", "QPADEV0002")
    numbers = [j.number for j in store.jobs.jobs]
    assert len(numbers) == len(set(numbers)) and all(len(n) == 6 and n.isdigit() for n in numbers)


def test_wrkactjob_layout_follows_the_capture(store):
    c = _signed(store)
    s = c.handle("ENTER", {"command": "wrkactjob"})
    f = {(x.row, x.col): x for x in s.fields}
    assert f[(0, 29)].text == "Work with Active Jobs" and f[(2, 49)].text == "Active jobs:"
    assert [f[(8, col)].text for col in (1, 6, 21, 33, 39, 46, 62)] == \
        ["Opt", "Subsystem/Job", "User", "Type", "CPU %", "Function", "Status"]
    assert f[(5, 57)].text == "7=Display message" and f[(6, 31)].text == "13=Disconnect ..."
    assert f[(21, 41)].text == "F10=Restart statistics" and f[(22, 60)].text == "F24=More keys"
    ins = [(i.row, i.col, i.length) for i in s.inputs()]
    assert ins[0] == (9, 1, 2) and ins[-1] == (20, 6, 73)


def test_any_user_sees_every_job_including_other_peoples(store):
    _signed(store, "QSECOFR", "QPADEV0001")
    c = _signed(store, "STUDENT", "QPADEV0002")
    c.handle("ENTER", {"command": "wrkactjob"})
    seen = {(j.name, j.user) for j in c.view[1].rows}
    assert ("QPADEV0001", "QSECOFR") in seen and ("QZDASOINIT", "QUSER") in seen    # no *JOBCTL needed to look


def test_own_job_shows_what_it_is_running(store):
    c = _signed(store)
    t = _text(c.handle("ENTER", {"command": "wrkactjob"}))
    assert "CMD-WRKACTJOB" in t and "RUN" in t


def test_sbs_parameter_narrows_the_list_and_a_bad_one_is_refused(store):
    c = _signed(store)
    t = _text(c.handle("ENTER", {"command": "wrkactjob sbs(qusrwrk)"}))
    assert "QUSRWRK" in t and "QSYSWRK" not in t
    c.handle("F12", {})
    assert "Subsystem NOSUCH not found." in _text(c.handle("ENTER", {"command": "wrkactjob sbs(nosuch)"}))


def test_options_are_not_built_yet_and_say_so(store):
    c = _signed(store)
    c.handle("ENTER", {"command": "wrkactjob"})
    assert "Option 4 is not available" in _text(c.handle("ENTER", {"opt0": "4"}))
    assert "Option 9 is not valid" in _text(c.handle("ENTER", {"opt0": "9"}))


def test_wrkactjob_is_a_command_object_so_it_can_be_taken_away(store):
    from silverlake.cl import commands
    commands.execute(store, store.get("QSECOFR"), "RVKOBJAUT OBJ(QSYS/WRKACTJOB) OBJTYPE(*CMD) USER(*PUBLIC) AUT(*USE)")
    c = _signed(store, "STUDENT", "QPADEV0003")
    assert "Not authorized to command WRKACTJOB" in _text(c.handle("ENTER", {"command": "wrkactjob"}))
