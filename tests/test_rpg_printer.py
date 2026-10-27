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
