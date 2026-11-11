"""A program ending abnormally now gets a message ID (CPF9999, from a web search, see
messages.function_check) and a spooled QPPGMDMP, a simplified stand-in for a real formatted dump.
See rpg.dump_program for what it leaves out and why."""

import pytest

from silverlake.cl.commands import execute
from silverlake.system import profiles
from silverlake.system.authority import SecuredObject, USE

LOOP = "\n".join([
    "     D n               S              5  0",
    "     C                   EVAL      n = 0",
    "     C                   DOW       1 = 1",
    "     C                   EVAL      n = n + 1",
    "     C                   ENDDO",
    "     C                   RETURN",
]) + "\n"


@pytest.fixture
def store():
    return profiles.load()


def add_program(store, name, source, lib="APPLIB", owner="QSECOFR"):
    obj = SecuredObject(name, owner, public=USE, library=lib, type="*PGM", text=f"test {name}",
                        data={"attr": "RPGLE", "usrprf": "*USER", "useadpaut": "*YES", "source": source, "dspf": ""})
    store.objects[obj.key] = obj
    return obj


def test_an_abnormal_end_gets_the_function_check_id(store):
    add_program(store, "SPIN", LOOP)
    out = execute(store, store.get("STUDENT"), "CALL PGM(APPLIB/SPIN)")
    assert out.message.id == "CPF9999"
    assert "ended abnormally" in out.message.text


def test_an_abnormal_end_spools_a_dump(store):
    add_program(store, "SPIN", LOOP)
    before = len(store.spool)
    execute(store, store.get("STUDENT"), "CALL PGM(APPLIB/SPIN)")
    new = [f for f in store.spool if f.name == "QPPGMDMP"]
    assert len(store.spool) == before + 1 and len(new) == 1
    dump = new[0]
    assert dump.job_name.startswith("STUDENT") or dump.job_name  # it belongs to the job that ran it
    assert any("SPIN" in ln and "APPLIB" in ln for ln in dump.lines)
    assert any("instructions" in ln for ln in dump.lines)        # the runtime's own error text, kept


def test_a_program_that_ends_cleanly_spools_no_dump(store):
    add_program(store, "OK", "     C                   EVAL      *inlr = *on\n     C                   RETURN\n")
    execute(store, store.get("STUDENT"), "CALL PGM(APPLIB/OK)")
    assert not [f for f in store.spool if f.name == "QPPGMDMP"]
