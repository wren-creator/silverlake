"""Spool files, output queues and job logs. Layout positions are from the PUB400 capture."""

import pytest

from silverlake.cl import commands
from silverlake.screens.model import Text
from silverlake.screens.signon import SignonController
from silverlake.system import profiles, spool, state


@pytest.fixture
def store(tmp_path):
    s, db = state.open_store(state_dir=tmp_path)
    yield s
    db.close()


def _signed(store, user="QSECOFR", device="QPADEV0001"):
    c = SignonController(device, store)
    c.handle("ENTER", {"user": user, "password": user})
    return c


def _text(s):
    return " | ".join(f.text for f in s.fields if isinstance(f, Text))


def _run(store, user, line):
    out = commands.execute(store, store.get(user), line)
    return out.message.text if out.message else ""


def test_the_seed_has_two_queues_and_two_spool_files(store):
    assert ("QGPL", "QPRINT", "*OUTQ") in store.objects and ("QUSRSYS", "QEZJOBLOG", "*OUTQ") in store.objects
    assert {f.name for f in store.spool} == {"PAYRPT", "QPJOBLOG"}


def test_wrksplf_defaults_to_your_own_files_only(store):
    c = _signed(store, "DEVELOPER")
    s = c.handle("ENTER", {"command": "wrksplf"})
    f = {(x.row, x.col): x for x in s.fields}
    assert f[(0, 26)].text == "Work with All Spooled Files"
    assert [x.name for x in c.view[1].rows] == ["PAYRPT"]                   # not QSECOFR's job log
    assert [(i.row, i.col, i.length) for i in s.inputs()][-1] == (20, 6, 73)
    assert [f[(8, col)].text for col in (1, 6, 18, 30, 42, 54, 60, 69, 75)] == \
        ["Opt", "File", "User", "Queue", "User Data", "Sts", "Pages", "Page", "Copy"]


def test_select_all_lists_what_the_queue_lets_you_list(store):
    c = _signed(store, "STUDENT")
    c.handle("ENTER", {"command": "wrksplf select(*all)"})
    assert {f.name for f in c.view[1].rows} == {"PAYRPT", "QPJOBLOG"}      # public *USE on both queues


def test_a_report_on_a_dspdta_yes_queue_is_readable_by_anyone_who_can_read_the_queue(store):
    out = commands.execute(store, store.get("STUDENT"), "DSPSPLF FILE(PAYRPT) JOB(100231/DEVELOPER/PAYRUN)")
    assert out.view and "PAYROLL REGISTER" in out.view[1].lines[0]


def test_a_job_log_on_a_dspdta_owner_queue_is_not(store):
    out = commands.execute(store, store.get("STUDENT"), "DSPSPLF FILE(QPJOBLOG) JOB(100188/QSECOFR/QPADEV0001)")
    assert out.message and out.message.id == "CPF3492" and out.message.text == "Not authorized to spooled file."


def test_spoolctl_and_jobctl_open_it_and_jobctl_depends_on_oprctl(store):
    line = "DSPSPLF FILE(QPJOBLOG) JOB(100188/QSECOFR/QPADEV0001)"
    assert commands.execute(store, store.get("SPOOLMAN"), line).view            # *SPLCTL
    assert commands.execute(store, store.get("JOBMAN"), line).view              # *JOBCTL, OPRCTL(*YES)
    store.objects[("QUSRSYS", "QEZJOBLOG", "*OUTQ")].data["oprctl"] = "*NO"
    assert commands.execute(store, store.get("JOBMAN"), line).message.id == "CPF3492"
    assert commands.execute(store, store.get("SPOOLMAN"), line).view            # *SPLCTL does not care


def test_dspsplf_errors_use_the_documented_ids(store):
    assert _run(store, "QSECOFR", "DSPSPLF FILE(NOSUCH) JOB(100188/QSECOFR/QPADEV0001)").startswith("File NOSUCH not found")
    out = commands.execute(store, store.get("QSECOFR"), "DSPSPLF FILE(NOSUCH) JOB(100188/QSECOFR/QPADEV0001)")
    assert out.message.id == "CPF3303"


def test_dltsplf_follows_the_control_rule(store):
    assert _run(store, "STUDENT", "DLTSPLF FILE(PAYRPT) JOB(100231/DEVELOPER/PAYRUN)") == "Not authorized to spooled file."
    assert len(store.spool) == 2
    assert "deleted" in _run(store, "DEVELOPER", "DLTSPLF FILE(PAYRPT) JOB(100231/DEVELOPER/PAYRUN)")
    assert [f.name for f in store.spool] == ["QPJOBLOG"]


def test_display_screen_follows_the_capture_and_rolls(store):
    c = _signed(store, "DEVELOPER")
    c.handle("ENTER", {"command": "wrksplf"})
    s = c.handle("ENTER", {"opt0": "5"})
    f = {(x.row, x.col): x for x in s.fields}
    assert f[(0, 30)].text == "Display Spooled File" and f[(1, 21)].text == "PAYRPT"
    assert f[(22, 1)].text.startswith("F3=Exit   F12=Cancel   F19=Left")
    assert [(i.row, i.col, i.length) for i in s.inputs()] == [(2, 21, 8), (3, 21, 30)]
    assert f[(5, 0)].text.strip().startswith("SILVERLAKE TRAINING CO") and f[(21, 73)].text == "Bottom"
    c.handle("F12", {})
    assert c.view[0] == "work"


def test_attributes_screen_follows_the_capture(store):
    c = _signed(store, "DEVELOPER")
    c.handle("ENTER", {"command": "wrksplf"})
    f = {(x.row, x.col): x for x in c.handle("ENTER", {"opt0": "8"}).fields}
    assert f[(0, 23)].text == "Work with Spooled File Attributes" and f[(2, 67)].text == "PAYRPT"
    assert f[(8, 44)].text == "QPRINT" and f[(9, 46)].text == "QGPL" and f[(7, 44)].text == "READY"


def test_options_not_built_say_so_and_a_refused_display_is_refused(store):
    c = _signed(store, "STUDENT")
    c.handle("ENTER", {"command": "wrksplf select(*all)"})
    assert "Option 4 is not available" in _text(c.handle("ENTER", {"opt0": "4"}))
    assert "Option 11 is not valid" in _text(c.handle("ENTER", {"opt0": "11"}))
    c.handle("ENTER", {"opt0": ""})
    rows = [f.name for f in c.view[1].rows]
    jl = rows.index("QPJOBLOG") if c.view[1].page == 0 else 0
    assert "Not authorized to spooled file." in _text(c.handle("ENTER", {f"opt{jl}": "5"}))


def test_signing_off_files_a_job_log_of_what_was_typed(store):
    c = _signed(store, "DEVELOPER", "QPADEV0042")
    c.handle("ENTER", {"command": "dsplibl"})
    c.handle("F3", {})
    c.handle("ENTER", {"command": "crtlib newlib"})
    number = store.jobs.find("QPADEV0042")[0].number
    c.close()
    log = [f for f in store.spool if f.job_number == number][0]
    text = "\n".join(log.lines)
    assert log.name == "QPJOBLOG" and log.user == "DEVELOPER" and log.outq == "QEZJOBLOG" and log.user_data == "QPADEV0042"
    assert "DSPLIBL" in text and "CRTLIB NEWLIB" in text and "Library NEWLIB created." in text


def test_a_password_never_reaches_a_job_log(store):
    c = _signed(store)
    c.handle("ENTER", {"command": "chgusrprf usrprf(student) password(Sup3rSecret!)"})
    number = store.jobs.find("QPADEV0001")[0].number
    c.close()
    text = "\n".join([f for f in store.spool if f.job_number == number][0].lines)
    assert "Sup3rSecret" not in text and "PASSWORD(*****)" in text


def test_spool_files_survive_a_restart_and_job_numbers_do_not_collide(tmp_path):
    s, db = state.open_store(state_dir=tmp_path)
    c = _signed(s, "STUDENT", "QPADEV0007")
    first = s.jobs.find("QPADEV0007")[0].number
    c.close()
    db.close()
    s2, db2 = state.open_store(state_dir=tmp_path)
    assert first in {f.job_number for f in s2.spool}
    c2 = _signed(s2, "STUDENT", "QPADEV0007")
    assert s2.jobs.find("QPADEV0007")[0].number != first
    db2.close()


def test_an_old_state_file_without_queues_gets_them(tmp_path):
    s, db = state.open_store(state_dir=tmp_path)
    for key in (("QGPL", "QPRINT", "*OUTQ"), ("QUSRSYS", "QEZJOBLOG", "*OUTQ")):
        del s.objects[key]
    s.on_change()
    db.close()
    s2, db2 = state.open_store(state_dir=tmp_path)
    assert ("QGPL", "QPRINT", "*OUTQ") in s2.objects
    db2.close()


def test_the_new_commands_are_objects_and_dspobjaut_knows_outq(store):
    assert all(("QSYS", n, "*CMD") in store.objects for n in ("WRKSPLF", "DSPSPLF", "DLTSPLF"))
    out = commands.execute(store, store.get("QSECOFR"), "DSPOBJAUT OBJ(QGPL/QPRINT) OBJTYPE(*OUTQ)")
    assert out.view and out.view[0] == "dspobjaut"
