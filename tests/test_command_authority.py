"""Commands are objects: running one takes *USE to its *CMD object in QSYS."""

import sqlite3

import pytest

from silverlake.cl import commands
from silverlake.cl.commands import execute
from silverlake.system import commandobjs, messages, profiles, state
from silverlake.system.authority import EXCLUDE, USE


@pytest.fixture
def store():
    return profiles.load()


def run(store, user, line):
    out = execute(store, store.get(user), line)
    return out.message.line() if out.message else (out.view[0] if out.view else "")


REFUSED = "Not authorized to command CRTLIB in library *LIBL."          # wording seen on PUB400


def lock(store, cmd="CRTLIB"):
    assert "Authority revoked" in run(
        store, "QSECOFR", f"RVKOBJAUT OBJ(QSYS/{cmd}) OBJTYPE(*CMD) USER(*PUBLIC) AUT(*USE)")


def test_the_dispatcher_and_the_command_objects_stay_in_step():
    assert set(commands.COMMANDS) == set(commandobjs.COMMAND_NAMES)


def test_every_command_is_a_qsys_object_open_to_the_public_by_default(store):
    for name in set(commands.COMMANDS) - commandobjs.CLOSED:
        o = store.objects[("QSYS", name, "*CMD")]
        assert (o.owner, o.public, o.library) == ("QSYS", USE, "QSYS"), name


def test_a_locked_command_is_refused_with_the_wording_a_real_system_gave(store):
    assert "created" in run(store, "STUDENT", "CRTLIB LIB(OPEN1)")
    lock(store)
    assert run(store, "STUDENT", "CRTLIB LIB(CLOSED1)") == REFUSED
    assert store.find_library("CLOSED1") is None                       # and it did not run
    m = messages.not_authorized_to_command("CRTLIB")
    assert m.source == messages.VERIFIED_TEXT and m.id == ""           # the message line shows no ID


def test_the_refusal_comes_before_parameters_are_looked_at(store):
    lock(store)
    assert run(store, "STUDENT", "CRTLIB") == REFUSED                  # no LIB given, still the authority error
    assert run(store, "STUDENT", "CRTLIB BOGUS(1)") == REFUSED


def test_who_still_gets_through_a_locked_command(store):
    lock(store)
    assert "created" in run(store, "QSECOFR", "CRTLIB LIB(BYALLOBJ)")          # *ALLOBJ
    assert "created" in run(store, "SVCACCT", "CRTLIB LIB(BYSVC)")              # *ALLOBJ, no entry anywhere
    assert run(store, "DEVELOPER", "CRTLIB LIB(NOPE1)") == REFUSED
    run(store, "QSECOFR", "GRTOBJAUT OBJ(QSYS/CRTLIB) OBJTYPE(*CMD) USER(DEVELOPER) AUT(*USE)")
    assert "created" in run(store, "DEVELOPER", "CRTLIB LIB(BYGRANT)")           # a private grant
    assert run(store, "GUEST", "CRTLIB LIB(NOPE2)") == REFUSED


def test_group_authority_opens_a_locked_command(store):
    lock(store)
    run(store, "QSECOFR", "GRTOBJAUT OBJ(QSYS/CRTLIB) OBJTYPE(*CMD) USER(GRPDEV) AUT(*USE)")
    assert "created" in run(store, "DEVELOPER", "CRTLIB LIB(BYGROUP)")           # DEVELOPER is in GRPDEV
    assert run(store, "STUDENT", "CRTLIB LIB(NOPE3)") == REFUSED


def test_a_private_exclude_beats_a_public_use(store):
    run(store, "QSECOFR", "GRTOBJAUT OBJ(QSYS/CRTLIB) OBJTYPE(*CMD) USER(GUEST) AUT(*EXCLUDE)")
    assert run(store, "GUEST", "CRTLIB LIB(NOPE4)") == REFUSED
    assert "created" in run(store, "STUDENT", "CRTLIB LIB(FINE1)")


def test_locking_one_command_leaves_the_others_alone(store):
    lock(store)
    assert run(store, "STUDENT", "DSPLIBL") == "dsplibl"
    assert "CPF2110" in run(store, "STUDENT", "DLTLIB LIB(NOSUCH)")             # ran, and said the library is not there


def test_the_command_objects_can_be_inspected_like_any_other(store):
    out = execute(store, store.get("STUDENT"), "DSPOBJAUT OBJ(QSYS/CRTLIB) OBJTYPE(*CMD)")
    assert out.view[2] == [("*PUBLIC", "*USE")]
    full = execute(store, store.get("QSECOFR"), "DSPOBJAUT OBJ(CRTLIB) OBJTYPE(*CMD)").view[2]   # via the library list
    assert full[0] == ("QSYS", "*ALL") and full[-1] == ("*PUBLIC", "*USE")


def test_nothing_ordinary_runs_when_the_library_holding_the_commands_is_locked(store):
    run(store, "QSECOFR", "RVKOBJAUT OBJ(QSYS) OBJTYPE(*LIB) USER(*PUBLIC) AUT(*USE)")
    assert "Not authorized to command" in run(store, "STUDENT", "DSPLIBL")
    assert run(store, "QSECOFR", "DSPLIBL") == "dsplibl"


def test_locking_a_command_survives_a_restart(tmp_path):
    st, db = state.open_store(state_dir=tmp_path)
    lock(st)
    db.close()
    again, db2 = state.open_store(state_dir=tmp_path)
    assert run(again, "STUDENT", "CRTLIB LIB(NOPE5)") == REFUSED
    assert again.objects[("QSYS", "CRTLIB", "*CMD")].public == EXCLUDE
    db2.close()


def test_a_state_saved_before_a_command_existed_gets_its_object(tmp_path):
    st, db = state.open_store(state_dir=tmp_path)
    del st.objects[("QSYS", "WRKLIB", "*CMD")]
    st.on_change()
    db.close()
    again, db2 = state.open_store(state_dir=tmp_path)
    assert again.objects[("QSYS", "WRKLIB", "*CMD")].public == USE
    db2.close()


def test_an_old_state_file_without_the_data_column_is_upgraded(tmp_path):
    st, db = state.open_store(state_dir=tmp_path)
    db.close()
    con = sqlite3.connect(tmp_path / state.DB_NAME)
    con.executescript(
        "ALTER TABLE objects RENAME TO objects_new; "
        "CREATE TABLE objects (library TEXT NOT NULL, name TEXT NOT NULL, type TEXT NOT NULL, "
        "owner TEXT NOT NULL, owner_auth TEXT NOT NULL, public TEXT NOT NULL, autl TEXT, "
        "text TEXT NOT NULL DEFAULT '', PRIMARY KEY (library, name, type)); "
        "INSERT INTO objects SELECT library, name, type, owner, owner_auth, public, autl, text FROM objects_new; "
        "DROP TABLE objects_new;")
    con.commit()
    con.close()
    again, db2 = state.open_store(state_dir=tmp_path)
    assert again.find_library("APPLIB")
    again.on_change()                                                     # and it can write again
    db2.close()
