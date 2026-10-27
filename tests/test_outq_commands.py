"""CRTOUTQ and DLTOUTQ, built from IBM's two command pages."""

import pytest

from silverlake.cl.commands import execute
from silverlake.cl.session import Session
from silverlake.screens.model import Text
from silverlake.screens.signon import SignonController
from silverlake.system import profiles
from silverlake.system.authority import Auth, name_auth
from silverlake.system.spool import SpoolFile


@pytest.fixture
def store():
    return profiles.load()


def run(store, user, line, lib="SCRATCH"):
    out = execute(store, store.get(user), line, Session.for_profile(lib))
    return out.message.line() if out.message else out


def test_create_makes_a_queue_the_creator_owns_with_use_for_everyone(store):
    assert "created in library SCRATCH" in run(store, "STUDENT", "CRTOUTQ OUTQ(SCRATCH/MYQ) TEXT('mine')")
    q = store.objects[("SCRATCH", "MYQ", "*OUTQ")]
    assert q.owner == "STUDENT" and name_auth(q.public) == "*USE"            # the page's default, not the library's
    assert q.text == "mine" and q.data["dspdta"] == "*NO" and q.data["oprctl"] == "*YES" and q.data["autchk"] == "*OWNER"


def test_the_pages_parameters_are_stored(store):
    run(store, "STUDENT", "CRTOUTQ OUTQ(SCRATCH/Q2) DSPDTA(*OWNER) OPRCTL(*NO) AUTCHK(*DTAAUT) AUT(*EXCLUDE)")
    q = store.objects[("SCRATCH", "Q2", "*OUTQ")]
    assert (q.data["dspdta"], q.data["oprctl"], q.data["autchk"]) == ("*OWNER", "*NO", "*DTAAUT")
    assert q.public == Auth.NONE
    assert "not valid" in run(store, "STUDENT", "CRTOUTQ OUTQ(SCRATCH/Q3) DSPDTA(*SOME)")


def test_create_refusals(store):
    run(store, "STUDENT", "CRTOUTQ OUTQ(SCRATCH/DUP)")
    assert "CPF3353" in run(store, "STUDENT", "CRTOUTQ OUTQ(SCRATCH/DUP)")
    assert "CPF3352" in run(store, "STUDENT", "CRTOUTQ OUTQ(QTEMP/X)")
    assert "CPF2402" in run(store, "STUDENT", "CRTOUTQ OUTQ(NOLIB/X)")
    assert "CPF2182" in run(store, "STUDENT", "CRTOUTQ OUTQ(SRCLIB/X)")


def test_a_new_queue_can_be_listed_and_used(store):
    run(store, "STUDENT", "CRTOUTQ OUTQ(SCRATCH/MYQ)")
    c = SignonController("QPADEV0061", store)
    c.handle("ENTER", {"user": "STUDENT", "password": "student"})
    s = c.handle("ENTER", {"command": "wrkoutq outq(scratch/myq)"})
    assert "Work with Output Queue" in " ".join(f.text for f in s.fields if isinstance(f, Text))


def test_only_the_owner_can_delete_a_queue_made_with_defaults(store):
    run(store, "STUDENT", "CRTOUTQ OUTQ(SCRATCH/MYQ) AUT(*CHANGE)")
    # *CHANGE has no *OBJEXIST, so another user with plenty of access still cannot delete it
    assert "CPF2189" in run(store, "GUEST", "DLTOUTQ OUTQ(SCRATCH/MYQ)")
    assert ("SCRATCH", "MYQ", "*OUTQ") in store.objects
    assert "deleted" in run(store, "STUDENT", "DLTOUTQ OUTQ(SCRATCH/MYQ)")
    assert ("SCRATCH", "MYQ", "*OUTQ") not in store.objects


def test_a_queue_with_entries_cannot_be_deleted_until_they_go(store):
    run(store, "STUDENT", "CRTOUTQ OUTQ(SCRATCH/MYQ)")
    store.spool.append(SpoolFile("REPORT", "STUDENT", "JOB", "199999", outq="MYQ", outq_lib="SCRATCH",
                                 lines=["x"], created="2026-10-27T10:00:00"))
    assert "CPF3360" in run(store, "STUDENT", "DLTOUTQ OUTQ(SCRATCH/MYQ)")
    store.spool.clear()
    assert "deleted" in run(store, "STUDENT", "DLTOUTQ OUTQ(SCRATCH/MYQ)")


def test_the_two_system_queues_cannot_be_deleted(store):
    assert "CPF3469" in run(store, "QSECOFR", "DLTOUTQ OUTQ(QGPL/QPRINT)")
    assert "CPF3469" in run(store, "QSECOFR", "DLTOUTQ OUTQ(QUSRSYS/QEZJOBLOG)")


def test_delete_from_work_with_objects_option_4(store):
    run(store, "STUDENT", "CRTOUTQ OUTQ(SCRATCH/MYQ)")
    c = SignonController("QPADEV0062", store)
    c.handle("ENTER", {"user": "STUDENT", "password": "student"})
    s = c.handle("ENTER", {"command": "wrkobj obj(scratch/myq) objtype(*outq)"})
    s = c.handle("ENTER", {"opt0": "4"})
    assert "Confirm Delete" in " ".join(f.text for f in s.fields if isinstance(f, Text))
    c.handle("ENTER", {})
    assert ("SCRATCH", "MYQ", "*OUTQ") not in store.objects


def test_both_are_command_objects(store):
    assert all(("QSYS", n, "*CMD") in store.objects for n in ("CRTOUTQ", "DLTOUTQ"))
