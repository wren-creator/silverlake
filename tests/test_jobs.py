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


# -- job control: HLDJOB, RLSJOB, ENDJOB, CHGJOB --------------------------------------------------------------

from silverlake.cl import commands


def _run(store, user, line, session=None):
    out = commands.execute(store, store.get(user), line, session)
    return out.message.text if out.message else "", out


def _victim(store, user="STUDENT", device="QPADEV0009"):
    c = _signed(store, user, device)
    return c, store.jobs.find(device)[0]


def test_owner_may_hold_and_release_their_own_job_and_others_may_not(store):
    c, job = _victim(store)
    ref = f"JOB({job.qualified})"
    text, _ = _run(store, "GUEST", f"HLDJOB {ref}")
    assert text == f"Not authorized to control job {job.qualified}."
    assert "held" in _run(store, "STUDENT", f"HLDJOB {ref}")[0] and job.status == "HLD"
    assert "already held" in _run(store, "STUDENT", f"HLDJOB {ref}")[0]
    assert _run(store, "GUEST", f"RLSJOB {ref}")[0].startswith("Not authorized to control job")
    assert "released" in _run(store, "JOBMAN", f"RLSJOB {ref}")[0] and job.status == "DSPW"   # *JOBCTL
    assert "not held" in _run(store, "STUDENT", f"RLSJOB {ref}")[0]


def test_jobctl_is_the_only_special_authority_that_counts(store):
    c, job = _victim(store)
    ref = f"JOB({job.qualified})"
    assert _run(store, "SPOOLMAN", f"HLDJOB {ref}")[0].startswith("Not authorized")     # *SPLCTL is not enough
    assert _run(store, "SVCACCT", f"HLDJOB {ref}")[0].startswith("Not authorized")      # nor is *ALLOBJ on its own
    assert "held" in _run(store, "LEGACY", f"HLDJOB {ref}")[0]                           # *ALLOBJ plus *JOBCTL


def test_hldjob_and_friends_report_what_they_cannot_find_or_do(store):
    assert _run(store, "QSECOFR", "HLDJOB JOB(NOSUCH)")[0].startswith("Job NOSUCH user * job number * not found")
    assert _run(store, "QSECOFR", "HLDJOB JOB(*)")[0] == "Current job not allowed as job name on this command."
    assert "not valid job type" in _run(store, "QSECOFR", "HLDJOB JOB(QINTER)")[0]          # a subsystem monitor
    text, out = _run(store, "QSECOFR", "HLDJOB JOB(NOSUCH)")
    assert out.message.id == "CPF1321"


def test_a_held_job_shows_hld_on_wrkactjob_and_options_3_and_6_work(store):
    c = _signed(store, "QSECOFR", "QPADEV0001")
    other, job = _victim(store, "STUDENT", "QPADEV0009")
    c.handle("ENTER", {"command": "wrkactjob"})
    idx = [j.qualified for j in c.view[1].rows].index(job.qualified)
    page, i = divmod(idx, 9)
    c.view[1].page = page
    assert "held" in _text(c.handle("ENTER", {f"opt{i}": "3"}))
    assert job.status == "HLD" and "HLD" in _text(c._draw_view())
    assert "released" in _text(c.handle("ENTER", {f"opt{i}": "6"})) and job.status == "DSPW"


def test_endjob_ends_another_session_and_it_notices_on_its_next_key(store):
    victim, job = _victim(store, "STUDENT", "QPADEV0009")
    assert _run(store, "GUEST", f"ENDJOB JOB({job.qualified})")[0].startswith("Not authorized")
    assert "ended" in _run(store, "JOBMAN", f"ENDJOB JOB({job.qualified})")[0]
    assert store.jobs.find("QPADEV0009") == []
    s = victim.handle("ENTER", {"command": "dsplibl"})
    assert "Sign On" in _text(s) and victim.profile is None
    assert any(f.job_name == "QPADEV0009" for f in store.spool)                  # it still leaves its job log


def test_endjob_star_ends_your_own_session_and_the_rule_still_applies(store):
    c = _signed(store, "STUDENT", "QPADEV0010")
    s = c.handle("ENTER", {"command": "endjob job(*)"})
    assert "Sign On" in _text(s) and c.profile is None


def test_endjob_option_4_from_wrkactjob_and_a_seeded_job_just_goes(store):
    c = _signed(store, "QSECOFR", "QPADEV0001")
    c.handle("ENTER", {"command": "wrkactjob"})
    rows = c.view[1].rows
    idx = next(i for i, j in enumerate(rows) if j.name == "QSYSSCD")
    c.view[1].page = idx // 9
    assert "ended" in _text(c.handle("ENTER", {f"opt{idx % 9}": "4"}))
    assert store.jobs.find("QSYSSCD") == []


def test_chgjob_changes_what_the_pages_allow(store):
    c, job = _victim(store)
    assert "changed" in _run(store, "STUDENT", f"CHGJOB JOB({job.qualified}) JOBPTY(3) OUTPTY(4)")[0]
    assert job.attrs["JOBPTY"] == "3" and job.attrs["OUTPTY"] == "4"
    assert _run(store, "GUEST", f"CHGJOB JOB({job.qualified}) JOBPTY(1)")[0].startswith("Not authorized to control")
    assert job.attrs["JOBPTY"] == "3"


def test_chgjob_runpty_and_limits_need_jobctl_even_on_your_own_job(store):
    c, job = _victim(store)
    ref = f"JOB({job.qualified})"
    text, out = _run(store, "STUDENT", f"CHGJOB {ref} RUNPTY(10)")
    assert "not authorized to change parameters" in text and out.message.id == "CPF1337"
    assert job.attrs["RUNPTY"] == "20"
    assert "changed" in _run(store, "JOBMAN", f"CHGJOB {ref} RUNPTY(10)")[0] and job.attrs["RUNPTY"] == "10"
    assert "not valid" in _run(store, "JOBMAN", f"CHGJOB {ref} RUNPTY(500)")[0]
    assert job.attrs["RUNPTY"] == "10"                                                 # a bad value changes nothing
    assert "changed" in _run(store, "JOBMAN", f"CHGJOB {ref} CPUTIME(*NOMAX) PURGE(*NO)")[0]


def test_chgjob_option_2_opens_the_prompt_or_takes_attributes_from_the_command_line(store):
    c = _signed(store, "QSECOFR", "QPADEV0001")
    other, job = _victim(store, "STUDENT", "QPADEV0009")
    c.handle("ENTER", {"command": "wrkactjob"})
    idx = [j.qualified for j in c.view[1].rows].index(job.qualified)
    c.view[1].page = idx // 9
    assert "Change Job (CHGJOB)" in _text(c.handle("ENTER", {f"opt{idx % 9}": "2"}))     # no attributes typed: the prompt
    c.handle("F12", {})
    assert "changed" in _text(c.handle("ENTER", {f"opt{idx % 9}": "2", "command": "JOBPTY(2)"}))
    assert job.attrs["JOBPTY"] == "2"


def test_job_control_commands_are_command_objects(store):
    assert all(("QSYS", n, "*CMD") in store.objects for n in ("HLDJOB", "RLSJOB", "ENDJOB", "CHGJOB"))


# -- DSPJOBLOG and WRKJOB ---------------------------------------------------------------------------------------

def test_dspjoblog_shows_the_live_log_in_the_captured_layout(store):
    c = _signed(store, "STUDENT", "QPADEV0011")
    c.handle("ENTER", {"command": "dsplibl"})
    c.handle("F3", {})
    c.handle("ENTER", {"command": "crtlib nosuch/zz"})
    s = c.handle("ENTER", {"command": "dspjoblog"})
    f = {(x.row, x.col): x for x in s.fields}
    assert f[(0, 31)].text == "Display Job Log" and f[(2, 13)].text == "QPADEV0011" and f[(2, 40)].text == "STUDENT"
    lines = [x.text for x in s.fields if isinstance(x, Text) and x.row >= 4 and x.row <= 17 and x.col == 1]
    assert lines[0] == "3>> DSPLIBL" and lines[-1] == "3>> DSPJOBLOG"          # the command itself is the last line
    assert f[(21, 1)].text.startswith("F3=Exit   F5=Refresh   F10=Display detailed messages")
    assert f[(18, 73)].text == "Bottom" and not s.inputs()


def test_dspjoblog_rules_same_user_or_jobctl_and_allobj_jobs_need_allobj(store):
    plain, pjob = _victim(store, "STUDENT", "QPADEV0012")
    boss, bjob = _victim(store, "QSECOFR", "QPADEV0013")
    ref = lambda j: f"DSPJOBLOG JOB({j.qualified})"
    text, out = _run(store, "GUEST", ref(pjob))
    assert out.message.id == "CPF2441" and text == "Not authorized to display job log."
    assert _run(store, "JOBMAN", ref(pjob))[1].view                               # *JOBCTL reads a plain user's log
    assert _run(store, "JOBMAN", ref(bjob))[1].message.id == "CPF2441"            # but not a job that has *ALLOBJ
    assert _run(store, "LEGACY", ref(bjob))[1].view                               # *ALLOBJ plus *JOBCTL does
    assert _run(store, "SPOOLMAN", ref(pjob))[1].message.id == "CPF2441"          # *SPLCTL is not mentioned


def test_dspjoblog_not_found_ended_and_no_log(store):
    assert _run(store, "QSECOFR", "DSPJOBLOG JOB(NOSUCH)")[1].message.id == "CPF1070"
    assert _run(store, "QSECOFR", "DSPJOBLOG JOB(100188/QSECOFR/QPADEV0001)")[1].message.id == "CPF2443"   # seeded, ended
    sysjob = next(j for j in store.jobs.jobs if j.name == "QTCPIP")
    assert _run(store, "QSECOFR", f"DSPJOBLOG JOB({sysjob.qualified})")[1].message.id == "CPF2523"


def test_joblog_keys_roll_refresh_and_jump(store):
    c = _signed(store, "STUDENT", "QPADEV0014")
    for _ in range(20):
        c.handle("ENTER", {"command": "dsplibl"})
        c.handle("F3", {})
    c.handle("ENTER", {"command": "dspjoblog"})
    assert c.view[2] == 0
    c.handle("ROLLUP", {})
    assert c.view[2] == 14
    c.handle("F18", {})
    assert c.view[2] > 0
    c.handle("F17", {})
    assert c.view[2] == 0
    assert "F10 is not available" in _text(c.handle("F10", {}))
    c.handle("F12", {})
    assert c.view is None


def test_wrkjob_layout_follows_the_capture_and_takes_a_selection_on_the_command_line(store):
    c = _signed(store, "STUDENT", "QPADEV0015")
    s = c.handle("ENTER", {"command": "wrkjob"})
    f = {(x.row, x.col): x for x in s.fields}
    assert f[(0, 33)].text == "Work with Job" and f[(2, 8)].text == "QPADEV0015" and f[(2, 31)].text == "STUDENT"
    assert f[(6, 6)].text == "1. Display job status attributes" and f[(11, 5)].text.startswith("10. Display job log")
    assert [(i.row, i.col, i.length) for i in s.inputs()] == [(20, 6, 153)]
    assert "Option 30 is not available" in _text(c.handle("ENTER", {"command": "30"}))
    assert "Option 99 is not valid" in _text(c.handle("ENTER", {"command": "99"}))
    s = c.handle("ENTER", {"command": "10"})
    assert {(x.row, x.col): x for x in s.fields}[(0, 31)].text == "Display Job Log"
    c.handle("F12", {})
    assert c.view[0] == "wrkjobview"
    s = c.handle("ENTER", {"command": "13"})                                   # own job: the library list
    assert "User Library List" in _text(s) or "Library List" in _text(s)


def test_wrkjob_option_4_lists_that_jobs_spool_files_and_a_command_runs(store):
    from silverlake.system import spool
    c = _signed(store, "QSECOFR", "QPADEV0001")
    job = store.jobs.find("QPADEV0001")[0]
    store.spool.append(spool.SpoolFile("QSYSPRT", "QSECOFR", job.name, job.number, 1, "QPRINT", "QGPL"))
    c.handle("ENTER", {"command": "wrkjob"})
    s = c.handle("ENTER", {"command": "4"})
    assert c.view[0] == "work" and [f.name for f in c.view[1].rows] == ["QSYSPRT"]
    c.handle("F12", {})
    assert c.view[0] == "wrkjobview"
    s = c.handle("ENTER", {"command": "dltlib nosuch"})                     # a command typed on the menu runs
    assert c.view[0] == "wrkjobview" and "NOSUCH" in _text(s)
    assert _run(store, "QSECOFR", "WRKJOB JOB(NOSUCH)")[1].message.id == "CPF1070"


def test_wrkjob_needs_the_same_user_or_jobctl(store):
    plain, pjob = _victim(store, "STUDENT", "QPADEV0016")
    out = commands.execute(store, store.get("GUEST"), f"WRKJOB JOB({pjob.qualified})")
    assert out.message.id == "CPF1071" and out.message.text == f"No authority to job {pjob.qualified}."
    assert commands.execute(store, store.get("JOBMAN"), f"WRKJOB JOB({pjob.qualified})").view
    assert commands.execute(store, store.get("SPOOLMAN"), f"WRKJOB JOB({pjob.qualified})").message.id == "CPF1071"


def test_wrkactjob_option_5_opens_work_with_job(store):
    c = _signed(store, "QSECOFR", "QPADEV0001")
    other, job = _victim(store, "STUDENT", "QPADEV0017")
    c.handle("ENTER", {"command": "wrkactjob"})
    idx = [j.qualified for j in c.view[1].rows].index(job.qualified)
    c.view[1].page = idx // 9
    s = c.handle("ENTER", {f"opt{idx % 9}": "5"})
    assert c.view[0] == "wrkjobview" and {(x.row, x.col): x for x in s.fields}[(2, 8)].text == "QPADEV0017"
    c.handle("F12", {})
    assert c.view[0] == "work"


def test_new_commands_are_objects(store):
    assert all(("QSYS", n, "*CMD") in store.objects for n in ("DSPJOBLOG", "WRKJOB", "DSPJOB"))


# -- DSPJOB ------------------------------------------------------------------------------------------------------

def test_dspjob_menu_follows_the_capture_with_a_two_character_selection(store):
    c = _signed(store, "STUDENT", "QPADEV0021")
    s = c.handle("ENTER", {"command": "dspjob"})
    f = {(x.row, x.col): x for x in s.fields}
    assert f[(0, 34)].text == "Display Job" and f[(2, 8)].text == "QPADEV0021" and f[(2, 31)].text == "STUDENT"
    assert f[(9, 6)].text == "4. Display spooled files" and f[(12, 5)].text == "11. Display call stack, if active"
    assert f[(19, 1)].text == "Selection" and [(i.row, i.col, i.length) for i in s.inputs()] == [(20, 6, 2)]
    assert f[(22, 1)].text == "F3=Exit" and f[(22, 11)].text == "F12=Cancel" and (18, 67) in f
    assert "Option 99 is not valid" in _text(c.handle("ENTER", {"selection": "99"}))
    assert "Option 30 is not available" in _text(c.handle("ENTER", {"selection": "30"}))
    assert "17. Display communications status" in _text(c.handle("ROLLUP", {}))      # page two, built
    assert c.view[0] == "dspjobview"


def test_dspjob_pages_show_the_jobs_own_attributes_and_f16_returns_to_the_menu(store):
    c = _signed(store, "QSECOFR", "QPADEV0022")
    c.handle("ENTER", {"command": "chgjob runpty(30)"})
    c.handle("ENTER", {"command": "dspjob"})
    s = c.handle("ENTER", {"selection": "1"})
    f = {(x.row, x.col): x for x in s.fields}
    assert f[(0, 25)].text == "Display Job Status Attributes" and f[(4, 49)].text == "ACTIVE"
    assert (f[(5, 49)].text, f[(14, 49)].text, f[(16, 49)].text) == ("QSECOFR", "QINTER", "INTER")
    assert f[(22, 37)].text == "F16=Job menu" and f[(20, 1)].text == "Press Enter to continue." and (19, 67) in f
    c.handle("ENTER", {})                                                      # Enter goes back one level
    assert c.view[0] == "dspjobview"
    s = c.handle("ENTER", {"selection": "2"})
    f = {(x.row, x.col): x for x in s.fields}
    assert f[(0, 12)].text.strip() == "Display Job Definition Attributes" and f[(10, 55)].text == "5" and f[(16, 55)].text == "*SECLVL"
    c.handle("F12", {})
    s = c.handle("ENTER", {"selection": "3"})
    f = {(x.row, x.col): x for x in s.fields}
    assert f[(0, 12)].text.strip() == "Display Job Run Attributes" and f[(4, 55)].text == "30" and (19, 67) not in f   # CHGJOB shows here
    c.handle("F16", {})
    assert c.view[0] == "dspjobview" and not c.parents
    c.handle("F3", {})
    assert c.view is None


def test_dspjob_options_4_and_10_and_13_work_and_follow_the_same_rules_as_wrkjob(store):
    from silverlake.system import spool
    c = _signed(store, "STUDENT", "QPADEV0023")
    job = store.jobs.find("QPADEV0023")[0]
    store.spool.append(spool.SpoolFile("QSYSPRT", "STUDENT", job.name, job.number, 1, "QPRINT", "QGPL"))
    c.handle("ENTER", {"command": "dspjob"})
    c.handle("ENTER", {"selection": "4"})
    assert c.view[0] == "work" and [f.name for f in c.view[1].rows] == ["QSYSPRT"]
    c.handle("F12", {})
    assert {(x.row, x.col): x for x in c.handle("ENTER", {"selection": "10"}).fields}[(0, 31)].text == "Display Job Log"
    c.handle("F12", {})
    assert "Library List" in _text(c.handle("ENTER", {"selection": "13"}))
    plain, pjob = _victim(store, "STUDENT", "QPADEV0024")
    assert commands.execute(store, store.get("GUEST"), f"DSPJOB JOB({pjob.qualified})").message.id == "CPF1071"
    assert commands.execute(store, store.get("JOBMAN"), f"DSPJOB JOB({pjob.qualified})").view
    assert _run(store, "QSECOFR", "DSPJOB JOB(NOSUCH)")[1].message.id == "CPF1070"


def test_wrkjob_options_1_to_3_open_the_same_pages(store):
    c = _signed(store, "STUDENT", "QPADEV0025")
    c.handle("ENTER", {"command": "wrkjob"})
    assert {(x.row, x.col): x for x in c.handle("ENTER", {"command": "3"}).fields}[(0, 12)].text.strip() == "Display Job Run Attributes"
    c.handle("F16", {})
    assert c.view[0] == "wrkjobview"
