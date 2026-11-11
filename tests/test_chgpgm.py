"""CHGPGM, from IBM's page (read in full, not a capture): USRPRF and USEADPAUT need the program's owner,
or *ALLOBJ with *SECADM; *OBJMGT and *USE are needed regardless. See rpg.change_program for what the
real page says that this does not model (the program must be re-created; here the change is immediate)."""

import pytest

from silverlake.cl.commands import execute
from silverlake.system import profiles


@pytest.fixture
def store():
    return profiles.load()


def run(store, user, line):
    return execute(store, store.get(user), line).message


def test_the_owner_may_change_usrprf_and_useadpaut(store):
    obj = store.objects[("APPLIB", "PAYLOOK", "*PGM")]
    assert obj.owner == "OPERATOR" and obj.data["usrprf"] == "*OWNER"
    msg = run(store, "OPERATOR", "CHGPGM PGM(APPLIB/PAYLOOK) USRPRF(*USER) USEADPAUT(*NO)")
    assert "changed" in msg.text
    assert obj.data["usrprf"] == "*USER" and obj.data["useadpaut"] == "*NO"


def test_a_non_owner_without_allobj_and_secadm_cannot_change_adoption(store):
    obj = store.objects[("APPLIB", "PAYLOOK", "*PGM")]
    before = obj.data["usrprf"]
    msg = run(store, "STUDENT", "CHGPGM PGM(APPLIB/PAYLOOK) USRPRF(*USER)")
    assert "Not authorized" in msg.text and obj.data["usrprf"] == before


def test_allobj_and_secadm_together_may_change_a_program_they_do_not_own(store):
    obj = store.objects[("APPLIB", "PAYLOOK", "*PGM")]
    msg = run(store, "QSECOFR", "CHGPGM PGM(APPLIB/PAYLOOK) USRPRF(*USER)")
    assert "changed" in msg.text and obj.data["usrprf"] == "*USER"


def test_same_changes_nothing(store):
    obj = store.objects[("APPLIB", "PAYLOOK", "*PGM")]
    before = dict(obj.data)
    msg = run(store, "QSECOFR", "CHGPGM PGM(APPLIB/PAYLOOK)")
    assert "changed" in msg.text and obj.data["usrprf"] == before["usrprf"] and obj.data["useadpaut"] == before["useadpaut"]


def test_text_can_change_without_touching_adoption(store):
    obj = store.objects[("APPLIB", "ADVENTURE", "*PGM")]
    msg = run(store, "QSECOFR", "CHGPGM PGM(APPLIB/ADVENTURE) TEXT('a new description')")
    assert "changed" in msg.text and obj.text == "a new description"


def test_a_basic_user_without_objmgt_cannot_change_even_just_the_text(store):
    # *USE alone (what a basic profile has to ADVENTURE) is not *OBJMGT, which CHGPGM needs regardless
    # of which parameter is changing.
    msg = run(store, "STUDENT", "CHGPGM PGM(APPLIB/ADVENTURE) TEXT('nope')")
    assert "Not authorized" in msg.text


def test_a_program_in_qsys_cannot_be_changed(store):
    msg = run(store, "QSECOFR", "CHGPGM PGM(QSYS/QCMD) TEXT(x)")
    assert msg.id == "CPF0544" and "cannot be changed" in msg.text


def test_a_bad_useadpaut_value_is_refused(store):
    msg = run(store, "QSECOFR", "CHGPGM PGM(APPLIB/ADVENTURE) USEADPAUT(*MAYBE)")
    assert "USEADPAUT not valid" in msg.text


def test_chgpgm_needs_the_program_to_exist(store):
    msg = run(store, "QSECOFR", "CHGPGM PGM(APPLIB/NOSUCH) TEXT(x)")
    assert "not found" in msg.text
