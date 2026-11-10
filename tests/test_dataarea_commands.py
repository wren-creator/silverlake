"""CRTDTAARA, CHGDTAARA, DLTDTAARA, CRTUSRSPC and DLTUSRSPC."""

import pytest

from silverlake.cl.commands import execute
from silverlake.cl.session import Session
from silverlake.system import profiles
from silverlake.system.authority import Auth, name_auth


@pytest.fixture
def store():
    return profiles.load()


def run(store, user, line, lib="SCRATCH"):
    out = execute(store, store.get(user), line, Session.for_profile(lib))
    return out.message.line() if out.message else out


def test_create_with_len_and_value(store):
    assert "created in library SCRATCH" in run(store, "STUDENT", "CRTDTAARA DTAARA(SCRATCH/MYAREA) LEN(10)")
    a = store.objects[("SCRATCH", "MYAREA", "*DTAARA")]
    assert a.owner == "STUDENT" and a.data["value"] == " " * 10 and a.data["length"] == 10


def test_len_defaults_to_the_length_of_value(store):
    run(store, "STUDENT", "CRTDTAARA DTAARA(SCRATCH/MYAREA) VALUE('hello')")
    a = store.objects[("SCRATCH", "MYAREA", "*DTAARA")]
    assert a.data["value"] == "hello" and a.data["length"] == 5


def test_value_is_padded_and_truncated_to_len(store):
    run(store, "STUDENT", "CRTDTAARA DTAARA(SCRATCH/MYAREA) LEN(3) VALUE('hello')")
    assert store.objects[("SCRATCH", "MYAREA", "*DTAARA")].data["value"] == "hel"
    run(store, "STUDENT", "CRTDTAARA DTAARA(SCRATCH/PADDED) LEN(5) VALUE('hi')")
    assert store.objects[("SCRATCH", "PADDED", "*DTAARA")].data["value"] == "hi   "


def test_neither_len_nor_value_is_refused(store):
    assert "Give LEN" in run(store, "STUDENT", "CRTDTAARA DTAARA(SCRATCH/MYAREA)")


def test_type_other_than_char_is_refused(store):
    assert "not modeled" in run(store, "STUDENT", "CRTDTAARA DTAARA(SCRATCH/MYAREA) TYPE(*DEC) LEN(10)")


def test_create_refusals(store):
    run(store, "STUDENT", "CRTDTAARA DTAARA(SCRATCH/DUP) LEN(5)")
    assert "already exists" in run(store, "STUDENT", "CRTDTAARA DTAARA(SCRATCH/DUP) LEN(5)")
    assert "CPF2402" in run(store, "STUDENT", "CRTDTAARA DTAARA(NOLIB/X) LEN(5)")
    assert "CPF2182" in run(store, "STUDENT", "CRTDTAARA DTAARA(SRCLIB/X) LEN(5)")


def test_create_in_qtemp_is_job_local(store):
    from silverlake.screens.signon import SignonController

    c = SignonController("QPADEV0072", store)
    c.handle("ENTER", {"user": "STUDENT", "password": "student"})
    c.handle("ENTER", {"command": "CRTDTAARA DTAARA(QTEMP/TMP) LEN(5)"})
    assert ("QTEMP", "TMP", "*DTAARA") in store.objects
    c._sign_off()
    assert ("QTEMP", "TMP", "*DTAARA") not in store.objects       # gone with the job


def test_change_requires_change_authority(store):
    run(store, "STUDENT", "CRTDTAARA DTAARA(SCRATCH/MYAREA) LEN(10) AUT(*USE)")
    assert "CPF2189" in run(store, "GUEST", "CHGDTAARA DTAARA(SCRATCH/MYAREA) VALUE('nope')")
    assert "changed" in run(store, "STUDENT", "CHGDTAARA DTAARA(SCRATCH/MYAREA) VALUE('newval')")
    a = store.objects[("SCRATCH", "MYAREA", "*DTAARA")]
    assert a.data["value"] == "newval".ljust(10)


def test_change_missing_data_area(store):
    assert "not found" in run(store, "STUDENT", "CHGDTAARA DTAARA(SCRATCH/NOSUCH) VALUE('x')")


def test_only_the_owner_can_delete_a_data_area_made_with_use(store):
    run(store, "STUDENT", "CRTDTAARA DTAARA(SCRATCH/MYAREA) LEN(10) AUT(*CHANGE)")
    assert "CPF2189" in run(store, "GUEST", "DLTDTAARA DTAARA(SCRATCH/MYAREA)")
    assert ("SCRATCH", "MYAREA", "*DTAARA") in store.objects
    assert "deleted" in run(store, "STUDENT", "DLTDTAARA DTAARA(SCRATCH/MYAREA)")
    assert ("SCRATCH", "MYAREA", "*DTAARA") not in store.objects


def test_data_area_is_usable_from_pase(store):
    """CHGDTAARA and the PASE datarea utility agree on the same value."""
    from silverlake.system import pase

    run(store, "STUDENT", "CRTDTAARA DTAARA(SCRATCH/SHARED) LEN(10) VALUE('fromcl')")
    shell = pase.Shell(store, store.get("STUDENT"))
    list(shell.login())
    out = shell.run("qsh -c 'datarea -r /QSYS.LIB/SCRATCH.LIB/SHARED.DTAARA'")
    assert out == ["fromcl"]


def test_create_user_space(store):
    assert "created in library SCRATCH" in run(store, "STUDENT", "CRTUSRSPC USRSPC(SCRATCH/MYSPACE) SIZE(100)")
    sp = store.objects[("SCRATCH", "MYSPACE", "*USRSPC")]
    assert sp.owner == "STUDENT" and sp.data["size"] == 100 and sp.data["value"] == " " * 100


def test_user_space_size_is_required(store):
    assert "Required parameter SIZE" in run(store, "STUDENT", "CRTUSRSPC USRSPC(SCRATCH/MYSPACE)")


def test_user_space_create_refusals(store):
    run(store, "STUDENT", "CRTUSRSPC USRSPC(SCRATCH/DUP) SIZE(10)")
    assert "already exists" in run(store, "STUDENT", "CRTUSRSPC USRSPC(SCRATCH/DUP) SIZE(10)")
    assert "CPF2402" in run(store, "STUDENT", "CRTUSRSPC USRSPC(NOLIB/X) SIZE(10)")


def test_only_the_owner_can_delete_a_user_space_made_with_use(store):
    run(store, "STUDENT", "CRTUSRSPC USRSPC(SCRATCH/MYSPACE) SIZE(10) AUT(*CHANGE)")
    assert "CPF2189" in run(store, "GUEST", "DLTUSRSPC USRSPC(SCRATCH/MYSPACE)")
    assert "deleted" in run(store, "STUDENT", "DLTUSRSPC USRSPC(SCRATCH/MYSPACE)")
    assert ("SCRATCH", "MYSPACE", "*USRSPC") not in store.objects


def test_a_new_data_area_can_be_listed_and_deleted_from_work_with_objects(store):
    from silverlake.screens.model import Text
    from silverlake.screens.signon import SignonController

    run(store, "STUDENT", "CRTDTAARA DTAARA(SCRATCH/MYAREA) LEN(10)")
    c = SignonController("QPADEV0071", store)
    c.handle("ENTER", {"user": "STUDENT", "password": "student"})
    s = c.handle("ENTER", {"command": "wrkobj obj(scratch/myarea) objtype(*dtaara)"})
    assert "Work with Objects" in " ".join(f.text for f in s.fields if isinstance(f, Text))
    s = c.handle("ENTER", {"opt0": "4"})
    assert "Confirm Delete" in " ".join(f.text for f in s.fields if isinstance(f, Text))
    c.handle("ENTER", {})
    assert ("SCRATCH", "MYAREA", "*DTAARA") not in store.objects


def test_all_five_are_command_objects(store):
    assert all(("QSYS", n, "*CMD") in store.objects
              for n in ("CRTDTAARA", "CHGDTAARA", "DLTDTAARA", "CRTUSRSPC", "DLTUSRSPC"))
