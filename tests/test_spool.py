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
    assert "Not authorized to spooled file." in _text(c.handle("ENTER", {"opt0": "4"}))
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


# -- housekeeping: HLDSPLF, RLSSPLF, options 3 and 6, JOB filter, WRKACTJOB option 8 ----------------------------

def test_hold_and_release_follow_the_control_rule(store):
    job = "JOB(100231/DEVELOPER/PAYRUN)"
    assert _run(store, "STUDENT", f"HLDSPLF FILE(PAYRPT) {job}") == "Not authorized to spooled file."
    assert next(f for f in store.spool if f.name == "PAYRPT").status == "RDY"
    assert "held" in _run(store, "DEVELOPER", f"HLDSPLF FILE(PAYRPT) {job}")
    assert next(f for f in store.spool if f.name == "PAYRPT").status == "HLD"
    assert "released" in _run(store, "SPOOLMAN", f"RLSSPLF FILE(PAYRPT) {job}")           # *SPLCTL
    assert next(f for f in store.spool if f.name == "PAYRPT").status == "RDY"


def test_options_3_and_6_hold_and_release_from_the_list(store):
    c = _signed(store, "DEVELOPER")
    c.handle("ENTER", {"command": "wrksplf"})
    assert "held" in _text(c.handle("ENTER", {"opt0": "3"}))
    assert next(f for f in store.spool if f.name == "PAYRPT").status == "HLD"
    assert "HLD" in _text(c._draw_view())
    assert "released" in _text(c.handle("ENTER", {"opt0": "6"}))
    assert "deleted" in _text(c.handle("ENTER", {"opt0": "4"}))
    assert not any(f.name == "PAYRPT" for f in store.spool)


def test_wrksplf_job_filter_needs_select_all_and_narrows(store):
    assert "JOB can only be given" in _run(store, "QSECOFR", "WRKSPLF JOB(100231/DEVELOPER/PAYRUN)")
    c = _signed(store, "QSECOFR")
    c.handle("ENTER", {"command": "wrksplf select(*all) job(100231/developer/payrun)"})
    assert [f.name for f in c.view[1].rows] == ["PAYRPT"]


def test_an_empty_spool_list_says_so_instead_of_an_empty_screen(store):
    assert _run(store, "STUDENT", "WRKSPLF") == "No spooled files found."


def test_wrkactjob_option_8_opens_that_jobs_spool_files(store):
    c = _signed(store, "QSECOFR")
    c.handle("ENTER", {"command": "wrkactjob"})
    rows = c.view[1].rows
    mine = next(i for i, j in enumerate(rows) if j.name == "QPADEV0001")
    # no spool file yet for a live session, so the list says so and stays on the jobs
    assert "No spooled files found." in _text(c.handle("ENTER", {f"opt{mine}": "8"}))
    store.spool.append(spool.SpoolFile("QSYSPRT", "QSECOFR", "QPADEV0001", rows[mine].number, 1, "QPRINT", "QGPL"))
    s = c.handle("ENTER", {f"opt{mine}": "8"})
    assert c.view[0] == "work" and c.view[1].kind == "spool" and [f.name for f in c.view[1].rows] == ["QSYSPRT"]
    c.handle("F12", {})
    assert c.view is None or c.view[1].kind == "jobs"


def test_f17_and_f18_jump_on_the_owner_list_and_the_edit_screen(store):
    for i in range(12):
        _run(store, "QSECOFR", f"CRTLIB TOPLIB{i:02d}")
    c = _signed(store, "QSECOFR")
    c.handle("ENTER", {"command": "wrkobjown usrprf(qsecofr)"})
    assert c.view[1].pages > 1
    c.handle("F18", {})
    assert c.view[1].page == c.view[1].pages - 1
    c.handle("F17", {})
    assert c.view[1].page == 0
    for u in ("STUDENT", "GUEST", "AUDITOR", "BACKUP", "OPERATOR", "JOBMAN", "SECONLY", "SPOOLMAN", "DEVELOPER", "IOADMIN"):
        _run(store, "QSECOFR", f"GRTOBJAUT OBJ(TOPLIB00) OBJTYPE(*LIB) USER({u}) AUT(*USE)")
    c.handle("F12", {})
    c.handle("ENTER", {"command": "wrkobj qsys/toplib00 *lib"})
    c.handle("ENTER", {"opt0": "2"})
    assert c.view[1].pages > 1
    c.handle("F18", {})
    assert c.view[1].page == c.view[1].pages - 1
    c.handle("F17", {})
    assert c.view[1].page == 0
