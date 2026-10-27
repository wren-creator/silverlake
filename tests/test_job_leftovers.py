"""Options 17 to 22, the third WRKJOB page, the Change Job prompt, and the F10 and F11 keys on the call
stack, open files and locks displays, from the auth-dspjob3 and auth-dspjob4 captures."""

import pytest

from silverlake.screens.model import Input, Text
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


@pytest.mark.parametrize("opt,title,empty", [
    ("17", "Display Communications Status", "(No communications identifiers are active)"),
    ("19", "Display Job Mutexes", "(Job or thread has no mutexes)"),
    ("21", "Display MLB Attributes", "(No MLB attributes list available)"),
])
def test_dspjob_options_17_19_21_show_the_captured_empty_lists(store, opt, title, empty):
    c = signed(store)
    c.handle("ENTER", {"command": "dspjob"})
    s = c.handle("ENTER", {"selection": opt})
    assert title in text(s) and empty in text(s)
    assert at(s)[(1, 71)] == "SILVERLK"
    assert "Display Job" in text(c.handle("F12", {}))


def test_activation_groups_and_environment_variables_carry_the_captured_rows(store):
    c = signed(store)
    c.handle("ENTER", {"command": "dspjob"})
    f = at(c.handle("ENTER", {"selection": "18"}))
    assert f[(6, 1)] == "*DFTACTGRP" and f[(8, 55)] == "QLGLOCAL" and f[(9, 69)] == "QSYS"
    c.handle("F12", {})
    s = c.handle("ENTER", {"selection": "22"})
    f = at(s)
    assert f[(8, 6)] == "PASE_USRGRP_LIMITED" and f[(8, 34)] == "'N'"
    assert f[(9, 31)] == ">" and f[(11, 71)] == ">"                         # long names and values are cut and marked


def test_threads_and_mutexes_are_worded_for_the_menu_they_came_from(store):
    c = signed(store)
    c.handle("ENTER", {"command": "wrkjob"})
    c.handle("ROLLUP", {})
    assert "Work with Job Mutexes" in text(c.handle("ENTER", {"command": "19"}))
    c.handle("F12", {})
    s = c.handle("ENTER", {"command": "20"})
    assert "Work with Threads" in text(s) and "14=Work with thread mutexes" in text(s)
    tid = at(s)[(10, 7)]
    assert len(tid) == 8 and at(s)[(10, 40)] == "RUN"
    c.handle("F12", {})
    c.handle("ENTER", {"command": "dspjob"})
    assert "Display Threads" in text(c.handle("ENTER", {"selection": "20"}))


def test_a_job_that_is_not_interactive_has_empty_lists(store):
    from silverlake.screens import jobextra
    batch = next(j for j in store.jobs.jobs if j.type != "INT" and j.type != "SBS")
    assert (6, 1) not in at(jobextra.actgrp_screen(batch, "SILVERLK"))
    assert (8, 6) not in at(jobextra.env_screen(batch, "SILVERLK"))


def test_third_wrkjob_page_release_runs_rlsjob_and_45_and_30_are_not_built(store):
    c = signed(store)
    c.handle("ENTER", {"command": "wrkjob"})
    c.handle("ROLLUP", {})
    c.handle("ROLLUP", {})
    assert "Option 45 is not available" in text(c.handle("ENTER", {"command": "45"}))
    assert "Option 30 is not available" in text(c.handle("ENTER", {"command": "30"}))
    assert "not held" in text(c.handle("ENTER", {"command": "43"})).lower() or "released" in text(
        c.handle("ENTER", {"command": "43"})).lower()


def test_f11_flips_the_call_stack_open_files_and_locks_and_f10_opens_record_locks(store):
    c = signed(store)
    c.handle("ENTER", {"command": "dspjob"})
    c.handle("ENTER", {"selection": "11"})
    s = c.handle("F11", {})
    assert at(s)[(5, 32)].startswith("------Activation Group") and at(s)[(7, 62)] == "Yes"
    assert "F11=Display statements" in text(s)
    assert "Statement" in text(c.handle("F11", {}))
    c.handle("F12", {})
    c.handle("ENTER", {"selection": "14"})
    s = c.handle("F11", {})
    assert "USRRCD" in text(s) and "F11=Display descriptions" in text(s)
    assert "*ACTGRPDFN" in text(c.handle("F11", {}))
    c.handle("F12", {})
    c.handle("ENTER", {"selection": "12"})
    s = c.handle("F11", {})
    assert at(s)[(10, 58)] == "Scope" and at(s)[(11, 58)] == "*JOB"
    s = c.handle("F10", {})
    assert "Display Job Record Locks" in text(s) and "(No record locks)" in text(s)
    assert "Display Job Locks" in text(c.handle("F12", {}))


def test_wrkjob_option_40_opens_the_change_job_prompt_and_enter_runs_chgjob(store):
    c = signed(store)
    job = c.session.job
    c.handle("ENTER", {"command": "wrkjob"})
    c.handle("ROLLUP", {})
    s = c.handle("ENTER", {"command": "40"})
    f = at(s)
    assert f[(0, 19)].strip() == "Change Job (CHGJOB)" and f[(4, 49)] == job.name and f[(8, 34)] == "OUTPTY"
    ins = {x.name: x for x in s.fields if isinstance(x, Input)}
    assert ins["JOBPTY"].value == "*SAME" and ins["OUTPTY"].value == "5"
    s = c.handle("ENTER", {"JOBPTY": "*SAME", "OUTPTY": "7", "PRTDEV": "PRT01", "OUTQ": job.user, "OUTQLIB": "QGPL", "RUNPTY": "*SAME"})
    assert "changed" in text(s) and job.attrs["OUTPTY"] == "7"
    assert "Work with Job" in text(s)


def test_the_change_job_prompt_refuses_bad_values_and_ignores_the_unmodeled_fields(store):
    c = signed(store)
    job = c.session.job
    c.handle("ENTER", {"command": "wrkjob"})
    c.handle("ROLLUP", {})
    c.handle("ENTER", {"command": "40"})
    base = {"JOBPTY": "*SAME", "OUTPTY": "5", "PRTDEV": "PRT01", "OUTQ": job.user, "OUTQLIB": "QGPL", "RUNPTY": "*SAME"}
    assert "Change Job (CHGJOB)" in text(c.handle("ENTER", {**base, "OUTPTY": "12"}))
    assert job.attrs["OUTPTY"] == "5"
    assert "not modeled" in text(c.handle("ENTER", {**base, "OUTQ": "ELSEWHERE"}))
    assert "No changes" in text(c.handle("ENTER", base))
    assert "Work with Job" in text(c.handle("F12", {}))


def test_jobs_in_the_job_log_show_the_prompts_chgjob_line(store):
    c = signed(store)
    job = c.session.job
    c.handle("ENTER", {"command": "wrkjob"})
    c.handle("ROLLUP", {})
    c.handle("ENTER", {"command": "40"})
    c.handle("ENTER", {"JOBPTY": "*SAME", "OUTPTY": "6", "PRTDEV": "PRT01", "OUTQ": job.user, "OUTQLIB": "QGPL", "RUNPTY": "*SAME"})
    assert any("CHGJOB" in t and "OUTPTY(6)" in t for _, _, t in job.log)
