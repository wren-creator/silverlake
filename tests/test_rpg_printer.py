"""Printer files: a program that prints leaves a spooled file of its job on the printer file's output queue,
and the queue's rules decide who can read it."""

import pytest

from silverlake.screens.signon import SignonController
from silverlake.system import profiles, spool
from silverlake.system.authority import EXCLUDE, SecuredObject, USE


@pytest.fixture
def store():
    return profiles.load()


def signed(store, user):
    c = SignonController("QPADEV0091", store)
    c.handle("ENTER", {"user": user, "password": user})
    c.handle("ENTER", {"command": "ADDLIBLE APPLIB"})
    return c


def joblog(c):
    return " | ".join(t for _, _, t in c.session.joblog)


def printed(store, name):
    return [f for f in store.spool if f.name == name]


def test_a_register_run_by_payroll_staff_lands_on_the_queue_as_their_file(store):
    c = signed(store, "OPERATOR")
    c.handle("ENTER", {"command": "CALL PGM(REGRPT)"})
    [f] = printed(store, "REGRPT")
    assert (f.user, f.outq_lib, f.outq, f.status) == ("OPERATOR", "QGPL", "QPRINT", "RDY")
    assert f.job_name == c.session.job.name and f.job_number == c.session.job.number
    text = "\n".join(f.lines)
    assert "PAYROLL REGISTER" in text and "Chen, Priya" in text and "653,001" in text


def test_the_default_queue_lets_a_basic_user_read_the_report(store):
    OPERATOR, STUDENT = store.get("OPERATOR"), store.get("STUDENT")
    c = signed(store, "OPERATOR")
    c.handle("ENTER", {"command": "CALL PGM(REGRPT)"})
    [f] = printed(store, "REGRPT")
    assert spool.can_display(store, STUDENT, f)               # QPRINT is DSPDTA(*YES): the leak


def test_the_fixed_version_prints_to_a_queue_that_hides_the_contents(store):
    c = signed(store, "OPERATOR")
    c.handle("ENTER", {"command": "CALL PGM(REGRPTX)"})
    [f] = printed(store, "REGRPTX")
    assert (f.outq_lib, f.outq) == ("APPLIB", "PAYOUTQ")
    assert spool.can_display(store, store.get("OPERATOR"), f)
    assert not spool.can_display(store, store.get("STUDENT"), f)


def test_a_user_who_cannot_read_payroll_prints_nothing(store):
    c = signed(store, "STUDENT")
    c.handle("ENTER", {"command": "CALL PGM(REGRPT)"})
    assert printed(store, "REGRPT") == []
    assert "Not authorized to use object PAYROLL" in joblog(c)


def test_a_printer_file_needs_use_authority(store):
    pf = store.objects[("APPLIB", "REGRPT", "*FILE")]
    pf.public = EXCLUDE
    c = signed(store, "OPERATOR")
    c.handle("ENTER", {"command": "CALL PGM(REGRPT)"})
    assert printed(store, "REGRPT") == []
    assert "Not authorized to use object REGRPT" in joblog(c)


def test_a_queue_that_is_gone_stops_the_program_before_it_prints(store):
    del store.objects[("QGPL", "QPRINT", "*OUTQ")]
    c = signed(store, "OPERATOR")
    c.handle("ENTER", {"command": "CALL PGM(REGRPT)"})
    assert printed(store, "REGRPT") == []
    assert "QGPL/QPRINT" in joblog(c)


def test_a_second_run_in_the_same_job_is_the_next_file_number(store):
    c = signed(store, "OPERATOR")
    c.handle("ENTER", {"command": "CALL PGM(REGRPT)"})
    c.handle("ENTER", {"command": "CALL PGM(REGRPT)"})
    assert sorted(f.file_no for f in printed(store, "REGRPT")) == [1, 2]


def test_the_spooled_file_belongs_to_the_user_not_to_an_owner_the_program_adopts(store):
    src = store.objects[("APPLIB", "REGRPT", "*PGM")].data["source"]
    adopt = SecuredObject("REGADOPT", "SECADMIN", public=USE, library="APPLIB", type="*PGM",
                          data={"attr": "RPGLE", "usrprf": "*OWNER", "useadpaut": "*YES", "source": src})
    store.objects[adopt.key] = adopt
    c = signed(store, "STUDENT")
    c.handle("ENTER", {"command": "CALL PGM(REGADOPT)"})
    [f] = printed(store, "REGRPT")
    assert f.user == "STUDENT"


def test_a_file_that_is_not_a_printer_file_is_refused(store):
    src = store.objects[("APPLIB", "REGRPT", "*PGM")].data["source"].replace("dcl-f regrpt printer", "dcl-f customers printer")
    obj = SecuredObject("BADPRT", "QSECOFR", public=USE, library="APPLIB", type="*PGM",
                        data={"attr": "RPGLE", "usrprf": "*USER", "useadpaut": "*YES", "source": src})
    store.objects[obj.key] = obj
    c = signed(store, "OPERATOR")
    c.handle("ENTER", {"command": "CALL PGM(BADPRT)"})
    assert "is not a printer file" in joblog(c)


def _set(line: str, start: int, text: str) -> str:
    end = start - 1 + len(text)
    if len(line) < end:
        line = line.ljust(end)
    return line[: start - 1] + text + line[end:]


def _fline(name, ftype, device, keywords="") -> str:
    s = _set(" " * 5 + "F", 7, name)
    s = _set(s, 17, ftype)
    s = _set(s, 18, "F")
    s = _set(s, 22, "E")
    s = _set(s, 36, device)
    if keywords:
        s = _set(s, 44, keywords)
    return s


def _cline(opcode, factor2="") -> str:
    s = " " * 5 + "C"
    if factor2:
        s = _set(s, 36, factor2)
    s = _set(s, 26, opcode)
    return s


def _pausing_print_source() -> str:
    """A program that writes a HEADING record to REGRPT (needs no fields: it's all constants and the
    auto page number), then pauses on EXFMT before ending -- so the spool file it just created can be
    caught mid-run, still OPN, before the program closes it."""
    return "\n".join([
        _fline("EMPINQ", "C", "WORKSTN"),
        _fline("REGRPT", "O", "PRINTER"),
        _cline("WRITE", "HEADING"),
        _cline("EXFMT", "PAYLOOK"),
        _cline("EVAL", "*inlr = *on"),
        _cline("RETURN"),
    ]) + "\n"


def _seed_pausing_print_program(store, name="PAUSEPRT"):
    obj = SecuredObject(name, "OPERATOR", public=USE, library="APPLIB", type="*PGM",
                        data={"attr": "RPGLE", "usrprf": "*USER", "useadpaut": "*NO",
                              "source": _pausing_print_source(), "dspf": ""})
    store.objects[obj.key] = obj


def test_a_spool_file_stays_opn_while_the_program_still_owns_it(store):
    _seed_pausing_print_program(store)
    c = signed(store, "OPERATOR")
    c.handle("ENTER", {"command": "CALL PGM(PAUSEPRT)"})
    [f] = printed(store, "REGRPT")
    assert f.status == "OPN"
    c.handle("ENTER", {})
    [f] = printed(store, "REGRPT")
    assert f.status == "RDY"


def test_crtprtf_pagesize_and_copies_flow_to_the_printer_file(store):
    from silverlake.cl import commands
    from silverlake.cl.session import Session
    from silverlake.system import source

    s = Session.for_profile(store.get("STUDENT").current_library)
    s.user_libs += ["SCRATCH"]
    commands.execute(store, store.get("STUDENT"), "CRTSRCPF FILE(SCRATCH/QDDSSRC)", s)
    f = store.objects[("SCRATCH", "QDDSSRC", "*FILE")]
    source.put_member(store, f, "RPT", ["     A          R LINE", "     A            NAME          20A  O     2"])
    out = commands.execute(store, store.get("STUDENT"), "CRTPRTF FILE(SCRATCH/RPT) SRCFILE(SCRATCH/QDDSSRC) PAGESIZE(40) COPIES(3)", s)
    assert out.message.text == "File RPT created in library SCRATCH."
    obj = store.objects[("SCRATCH", "RPT", "*FILE")]
    assert obj.data["page_length"] == 40
    assert obj.data["copies"] == 3


def test_crtprtf_pagesize_dft_leaves_no_override(store):
    from silverlake.cl import commands
    from silverlake.cl.session import Session
    from silverlake.system import source

    s = Session.for_profile(store.get("STUDENT").current_library)
    s.user_libs += ["SCRATCH"]
    commands.execute(store, store.get("STUDENT"), "CRTSRCPF FILE(SCRATCH/QDDSSRC)", s)
    f = store.objects[("SCRATCH", "QDDSSRC", "*FILE")]
    source.put_member(store, f, "RPT", ["     A          R LINE", "     A            NAME          20A  O     2"])
    commands.execute(store, store.get("STUDENT"), "CRTPRTF FILE(SCRATCH/RPT) SRCFILE(SCRATCH/QDDSSRC)", s)
    obj = store.objects[("SCRATCH", "RPT", "*FILE")]
    assert "page_length" not in obj.data and obj.data["copies"] == 1


def test_chgprtf_changes_page_size_copies_and_outq(store):
    c = signed(store, "QSECOFR")
    c.handle("ENTER", {"command": "CHGPRTF FILE(REGRPT) PAGESIZE(40) COPIES(2) OUTQ(QPRINT)"})
    obj = store.objects[("APPLIB", "REGRPT", "*FILE")]
    assert obj.data["page_length"] == 40
    assert obj.data["copies"] == 2
    assert obj.data["outq"] == "QGPL/QPRINT"


def test_chgprtf_pagesize_dft_clears_a_previous_override(store):
    c = signed(store, "QSECOFR")
    c.handle("ENTER", {"command": "CHGPRTF FILE(REGRPT) PAGESIZE(40)"})
    c.handle("ENTER", {"command": "CHGPRTF FILE(REGRPT) PAGESIZE(*DFT)"})
    assert "page_length" not in store.objects[("APPLIB", "REGRPT", "*FILE")].data


def test_chgprtf_needs_at_least_one_attribute(store):
    c = signed(store, "QSECOFR")
    c.handle("ENTER", {"command": "CHGPRTF FILE(REGRPT)"})
    assert "at least one attribute" in joblog(c)


def test_chgprtf_needs_authority_to_the_file(store):
    c = signed(store, "STUDENT")
    c.handle("ENTER", {"command": "CHGPRTF FILE(REGRPT) PAGESIZE(40)"})
    assert "Not authorized" in joblog(c)
    assert "page_length" not in store.objects[("APPLIB", "REGRPT", "*FILE")].data


def test_chgprtf_pagesize_changes_the_report_the_program_prints(store):
    c = signed(store, "QSECOFR")
    c.handle("ENTER", {"command": "CHGPRTF FILE(REGRPT) PAGESIZE(5)"})
    c2 = signed(store, "OPERATOR")
    c2.handle("ENTER", {"command": "CALL PGM(REGRPT)"})
    [f] = printed(store, "REGRPT")
    text = "\n".join(f.lines)
    assert text.count("PAYROLL REGISTER") > 1  # a 5-line page overflows well before all 7 employees print
