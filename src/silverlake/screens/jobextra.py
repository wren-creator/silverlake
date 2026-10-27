"""The detail displays behind Display Job and Work with Job options 17 to 22 and the Change Job prompt,
laid out from the auth-dspjob3 and auth-dspjob4 captures of the profile's own job on PUB400. Silverlake
has no communications, no threads beyond the one, no media libraries and no PASE, so these show the
captured shape with the list empty or with the one row every interactive job had. A job that is not
interactive gets empty lists. Keys and options the real displays offer but nothing here can do are not
drawn (F11 on communications and environment variables, every option column, F22)."""

from ..proto import datastream as ds
from .model import Input, Screen, Text
from .worklists import _job_head, _more

_g = lambda r, c, t: Text(r, c, t, ds.ATTR_GREEN)
_w = lambda r, c, t: Text(r, c, t, ds.ATTR_WHITE)
_b = lambda r, c, t: Text(r, c, t, ds.ATTR_BLUE)


def _pad12(title: str) -> str:
    """Titles the host sends as a run starting at column 12, padded so the text sits centered."""
    return " " * ((80 - len(title)) // 2 - 12) + title


def thread_id(job) -> str:
    """The one thread every job here has: a stable id of our own, in the captured eight digit form."""
    return f"{0x300 + int(job.number) % 0x400:08X}"


def _frame(rows: list, message: str) -> Screen:
    if message:
        rows.append(Text(23, 1, message[:77], ds.ATTR_WHITE))
    return Screen(rows)


def comm_screen(job, system_name: str, message: str = "") -> Screen:
    rows = _job_head(job, system_name, "Display Communications Status", 25) + [
        _b(4, 1, "Type options, press Enter."), _b(5, 3, "5=Display"),
        _w(7, 6, "---------Communications---------"), _w(7, 40, "--------Number of Operations---------"),
        _w(8, 1, "Opt"), _w(8, 6, "Identifier"), _w(8, 24, "Method"), _w(8, 45, "Output"), _w(8, 59, "Input"),
        _w(8, 72, "Other"), _g(11, 3, "(No communications identifiers are active)"), _more(20, True),
        _b(21, 1, "F3=Exit"), _b(21, 11, "F5=Refresh"), _b(21, 49, "F12=Cancel"), _b(21, 62, "F16=Job menu"),
        _b(22, 1, "F17=Top"), _b(22, 11, "F18=Bottom")]
    return _frame(rows, message)


ACT_GROUPS = [("*DFTACTGRP", "0000000000000001", "Yes", "", ""), ("*DFTACTGRP", "0000000000000002", "Yes", "", ""),
              ("QLGLOCAL", "0000000000000011", "No", "QLGLOCAL", "QSYS"), ("QSQCLI", "0000000000000012", "No", "QSQCLI", "QSYS")]


def actgrp_screen(job, system_name: str, message: str = "") -> Screen:
    rows = _job_head(job, system_name, "Display Activation Group", 28) + [
        _w(4, 1, "-------Activation Group-------"), _w(5, 1, "Name"), _w(5, 15, "Number"),
        _w(5, 35, "In Use Indicator"), _w(5, 55, "Program"), _w(5, 69, "Library")]
    for i, (name, num, used, prog, lib) in enumerate(ACT_GROUPS if job.type == "INT" else []):
        rows += [_g(6 + i, 1, name), _g(6 + i, 15, num), _g(6 + i, 38, used)]
        if prog:
            rows += [_g(6 + i, 55, prog), _g(6 + i, 69, lib)]
    rows += [_more(19, True), _b(20, 1, "Press Enter to continue."), _b(22, 1, "F3=Exit"), _b(22, 11, "F5=Refresh"),
             _b(22, 24, "F12=Cancel"), _b(22, 37, "F16=Job menu"), _b(22, 52, "F17=Top"), _b(22, 62, "F18=Bottom")]
    return _frame(rows, message)


def mutex_screen(job, system_name: str, message: str = "", work: bool = False) -> Screen:
    title = "Work with Job Mutexes" if work else "Display Job Mutexes"
    rows = _job_head(job, system_name, _pad12(title), 12) + [
        _g(3, 1, "Thread:"), _g(3, 11, thread_id(job)), _b(5, 1, "Type options, press Enter."),
        _b(6, 3, "5=Work with mutex" if work else "5=Display mutex"), _w(8, 9, "Mutex"),
        _w(9, 1, "Opt"), _w(9, 9, "Status"), _w(9, 26, "Mutex"), _g(11, 3, "(Job or thread has no mutexes)"),
        _more(21, True), _b(22, 1, "F3=Exit"), _b(22, 11, "F5=Refresh"), _b(22, 24, "F12=Cancel"), _b(22, 37, "F16=Job menu")]
    return _frame(rows, message)


def threads_screen(job, system_name: str, message: str = "", work: bool = False) -> Screen:
    title = "Work with Threads" if work else "Display Threads"
    rows = _job_head(job, system_name, _pad12(title), 12) + [_b(4, 1, "Type options, press Enter.")]
    if work:
        rows += [_b(5, 3, "3=Hold"), _b(5, 12, "5=Display attributes"), _b(5, 35, "6=Release"), _b(5, 47, "10=Display call stack"),
                 _b(6, 3, "11=Work with thread locks"), _b(6, 35, "14=Work with thread mutexes")]
    else:
        rows += [_b(5, 3, "5=Display attributes"), _b(5, 26, "10=Display call stack"),
                 _b(5, 50, "11=Display thread locks"), _b(6, 3, "14=Display thread mutexes")]
    rows += [_w(8, 51, "Total"), _w(8, 65, "Aux"), _w(8, 74, "Run"), _w(9, 1, "Opt"), _w(9, 7, "Thread"),
             _w(9, 18, "Name"), _w(9, 37, "Status"), _w(9, 52, "CPU"), _w(9, 65, "I/O"), _w(9, 71, "Priority"),
             Input(10, 1, 2, "opt0")]
    rows += [_g(10, 7, thread_id(job)), _g(10, 40, "RUN"), _g(10, 51, "0,010"), _g(10, 66, "74"), _g(10, 76, "20"),
             _more(20, True), _b(21, 1, "F3=Exit"), _b(21, 11, "F5=Refresh")]
    rows += ([_b(21, 42, "F12=Cancel"), _b(21, 55, "F16=Job menu"), _b(21, 70, "F17=Top"), _b(22, 1, "F18=Bottom")] if work else
             [_b(21, 24, "F12=Cancel"), _b(21, 37, "F16=Job menu"), _b(21, 52, "F17=Top"), _b(21, 62, "F18=Bottom")])
    return _frame(rows, message)


def mlb_screen(job, system_name: str, message: str = "") -> Screen:
    rows = _job_head(job, system_name, "Display MLB Attributes", 29) + [
        _w(4, 16, "Resource"), _w(4, 33, "Initial"), _w(4, 46, "End of volume"), _w(5, 1, "Library"),
        _w(5, 16, "Allocation"), _w(5, 34, "Mount"), _w(5, 50, "Mount"), _w(6, 1, "Device"), _w(6, 16, "priority"),
        _w(6, 32, "Wait time"), _w(6, 48, "Wait time"), _g(8, 3, "(No MLB attributes list available)"),
        _more(20, True), _b(21, 1, "F3=Exit"), _b(21, 11, "F5=Refresh"), _b(21, 24, "F12=Cancel"),
        _b(21, 37, "F16=Job menu"), _b(21, 52, "F17=Top"), _b(21, 62, "F18=Bottom")]
    return _frame(rows, message)


ENV_VARS = [("PASE_USRGRP_LIMITED", "'N'"), ("QIBM_PASE_USE_PRESTART_JOB", "'Y'"), ("QIBM_MULTI_THREADED", "'Y'"),
            ("JAVA_HOME", "'/QopenSys/QIBM/ProdData/JavaVM/jdk80/64bit'"), ("LANG", "'/QSYS.LIB/EN_US.LOCALE'")]


def env_screen(job, system_name: str, message: str = "") -> Screen:
    """The captured variables. Real jobs get them from the system; here they are fixed, until there is a PASE."""
    rows = _job_head(job, system_name, "Display Environment Variables", 25) + [
        _b(4, 1, "Type options, press Enter."), _b(5, 3, "5=Display details"),
        _w(7, 1, "Opt"), _w(7, 6, "Name"), _w(7, 34, "Value")]
    for i, (name, value) in enumerate(ENV_VARS if job.type == "INT" else []):
        r = 8 + i
        rows += [Input(r, 2, 1, f"opt{i}"), _g(r, 6, name[:24]), _g(r, 34, value[:36])]
        if len(name) > 24:
            rows.append(_g(r, 31, ">"))
        if len(value) > 36:
            rows.append(_g(r, 71, ">"))
    rows += [_more(20, True), _b(21, 1, "F3=Exit"), _b(21, 11, "F5=Refresh"), _b(21, 45, "F12=Cancel"),
             _b(21, 58, "F16=Job menu"), _b(22, 1, "F17=Top"), _b(22, 11, "F18=Bottom")]
    return _frame(rows, message)


def reclocks_screen(job, system_name: str, message: str = "") -> Screen:
    """Display Job Record Locks. No file is ever open for update here, so no record is ever locked."""
    rows = _job_head(job, system_name, "Display Job Record Locks", 28) + [
        _g(4, 1, "Position to . . . . . . . ."), Input(4, 31, 10, "pos"),
        _g(5, 1, "Library . . . . . . . . . ."), Input(5, 31, 10, "lib"),
        _b(7, 1, "Type options, press Enter."), _b(8, 3, "5=Display member record locks"), _w(10, 58, "Record"),
        _w(11, 1, "Option"), _w(11, 10, "File"), _w(11, 23, "Library"), _w(11, 36, "Member"), _w(11, 58, "Number"),
        _w(11, 67, "Status"), _g(13, 3, "(No record locks)"), _more(21, True),
        _b(22, 1, "F3=Exit"), _b(22, 11, "F5=Refresh"), _b(22, 24, "F12=Cancel"), _b(22, 37, "F16=Job menu")]
    return _frame(rows, message)


def chgjob_screen(job, message: str = "", values: dict[str, str] | None = None) -> Screen:
    """The Change Job prompt, first page (option 40 on Work with Job). JOBPTY and RUNPTY show *SAME and
    OUTPTY shows the job's own, as captured. F4, F10 (additional parameters), F13 and F24 are not built."""
    v = {"JOBPTY": "*SAME", "OUTPTY": job.attrs["OUTPTY"], "PRTDEV": "PRT01", "OUTQ": job.user, "OUTQLIB": "QGPL",
         "RUNPTY": "*SAME", **(values or {})}
    rows: list = [_w(0, 19, "           Change Job (CHGJOB)"), _b(2, 1, "Type choices, press Enter."),
                  _g(4, 1, "Job name . . . . . . . . . . . ."), _g(4, 34, "JOB"), _g(4, 45, "  >"), _g(4, 49, job.name),
                  _g(5, 1, "  User . . . . . . . . . . . . ."), _g(5, 45, "  >"), _g(5, 51, job.user),
                  _g(6, 1, "  Number . . . . . . . . . . . ."), _g(6, 45, "  >"), _g(6, 51, job.number)]
    for r, label, kw, name, col, width in (
            (7, "Job priority (on JOBQ) . . . . .", "JOBPTY", "JOBPTY", 49, 5),
            (8, "Output priority (on OUTQ)  . . .", "OUTPTY", "OUTPTY", 49, 5),
            (9, "Print device . . . . . . . . . .", "PRTDEV", "PRTDEV", 49, 10),
            (10, "Output queue . . . . . . . . . .", "OUTQ", "OUTQ", 49, 10),
            (11, "  Library  . . . . . . . . . . .", None, "OUTQLIB", 51, 10),
            (12, "Run priority . . . . . . . . . .", "RUNPTY", "RUNPTY", 49, 6)):
        rows.append(_g(r, 1, label))
        if kw:
            rows.append(_g(r, 34, kw))
        rows.append(Input(r, col, width, name, value=v[name]))
    rows += [_w(20, 66, "Bottom".rjust(13)), _b(21, 1, "F3=Exit   F5=Refresh   F12=Cancel")]
    return _frame(rows, message)
