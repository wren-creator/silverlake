"""DSPPGMREF: from IBM's page (read in full, not a capture), the files a *PGM's F-specs name. See
rpg.program_references for what is built (*FILE only) and what is left out (*PGM, *DTAARA, *SRVPGM)."""

import pytest

from silverlake.cl.commands import execute
from silverlake.system import profiles
from silverlake.system.authority import EXCLUDE, USE, SecuredObject


@pytest.fixture
def store():
    return profiles.load()


def run(store, user, line):
    return execute(store, store.get(user), line)


def test_dsppgmref_lists_the_files_a_program_declares(store):
    out = run(store, "STUDENT", "DSPPGMREF PGM(APPLIB/PAYLOOK)")
    assert out.view is not None and out.view[0] == "dsppgmref"
    names = {row[0] for row in out.view[2]}
    assert names == {"EMPINQ", "PAYROLL"}
    uses = {row[0]: row[2] for row in out.view[2]}
    assert uses["PAYROLL"] == "Input"       # PAYLOOK only reads it


def test_dsppgmref_lists_a_display_file_too(store):
    out = run(store, "STUDENT", "DSPPGMREF PGM(APPLIB/ADVENTURE)")
    assert out.view[0] == "dsppgmref" and out.view[2] == [("SCREEN", "*FILE", "Combined")]


def test_dsppgmref_on_a_program_with_no_files_is_an_empty_list(store):
    obj = SecuredObject("NOFILES", "QSECOFR", public=USE, library="APPLIB", type="*PGM",
                        data={"attr": "RPGLE", "source": "     C                   RETURN\n"})
    store.objects[obj.key] = obj
    out = run(store, "STUDENT", "DSPPGMREF PGM(APPLIB/NOFILES)")
    assert out.view[0] == "dsppgmref" and out.view[2] == []


def test_dsppgmref_needs_objopr_to_the_program(store):
    obj = SecuredObject("LOCKED", "QSECOFR", public=EXCLUDE, library="APPLIB", type="*PGM",
                        data={"attr": "RPGLE", "source": "     C                   RETURN\n"})
    store.objects[obj.key] = obj
    out = run(store, "STUDENT", "DSPPGMREF PGM(APPLIB/LOCKED)")
    assert out.view is None and "Not authorized" in out.message.text


def test_dsppgmref_on_a_program_that_is_not_there(store):
    out = run(store, "STUDENT", "DSPPGMREF PGM(APPLIB/NOSUCH)")
    assert out.view is None and "not found" in out.message.text


def test_dsppgmref_needs_the_pgm_parameter(store):
    out = run(store, "STUDENT", "DSPPGMREF")
    assert "Required parameter PGM" in out.message.text
