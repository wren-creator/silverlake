"""Record level locking: a CHAIN in a file opened U or C holds the record until UPDATE, DELETE, the
next read, or the job ends, and a second job's CHAIN on the same record while that lock is held is
refused. See docs/rpg.md, 'Record level locking'."""

import pytest

from silverlake.screens.model import Text
from silverlake.screens.signon import SignonController
from silverlake.system import profiles
from silverlake.system.authority import USE, SecuredObject

PAYLOCK_DDS = "\n".join([
    "     A          R PAYREC",
    "     A            EMPNO          5S 0",
    "     A            NAME          20",
    "     A            DEPT           4",
    "     A            SALARY         7S 0",
    "     A          K EMPNO",
]) + "\n"


def _set(line: str, start: int, text: str) -> str:
    end = start - 1 + len(text)
    if len(line) < end:
        line = line.ljust(end)
    return line[: start - 1] + text + line[end:]


def fline(name, ftype="I", desig="F", fmt="E", keyed=False, device="DISK") -> str:
    s = _set(" " * 5 + "F", 7, name)
    s = _set(s, 17, ftype)
    s = _set(s, 18, desig)
    s = _set(s, 22, fmt)
    if keyed:
        s = _set(s, 34, "K")
    s = _set(s, 36, device)
    return s


def cline(opcode, factor1="", factor2="", result="", ind_hi="") -> str:
    s = " " * 5 + "C"
    if factor1:
        s = _set(s, 12, factor1)
    s = _set(s, 26, opcode)
    if factor2:
        s = _set(s, 36, factor2)
    if result:
        s = _set(s, 50, result)
    if ind_hi:
        s = _set(s, 71, ind_hi)
    return s


def _program(usage: str) -> str:
    lines = [
        fline("EMPINQ", "C", "F", "E", device="WORKSTN"),
        fline("PAYLOCK", usage, "F", "E", keyed=True, device="DISK"),
        cline("EXFMT", factor2="PAYLOOK"),
        cline("CHAIN", factor1="EMPNO", factor2="PAYLOCK", ind_hi="71"),
        cline("EXFMT", factor2="PAYLOOK"),
        cline("EVAL", factor2="*inlr = *on"),
        cline("RETURN"),
    ]
    return "\n".join(lines) + "\n"


@pytest.fixture
def store():
    return profiles.load()


def signed(store, dev, user="STUDENT"):
    c = SignonController(dev, store)
    c.handle("ENTER", {"user": user, "password": user})
    return c


def run(c, line):
    return c.handle("ENTER", {"command": line})


def text(s):
    return " | ".join(f.text for f in s.fields if isinstance(f, Text))


def _seed_file(store):
    obj = SecuredObject("PAYLOCK", "STUDENT", public=USE, library="APPLIB", type="*FILE",
                        data={"attr": "PF", "dds": PAYLOCK_DDS,
                              "records": [{"EMPNO": 10003, "NAME": "ALICE", "DEPT": "ACCT", "SALARY": 50000}]})
    store.objects[obj.key] = obj


def _seed_program(store, name: str, usage: str):
    obj = SecuredObject(name, "STUDENT", public=USE, library="APPLIB", type="*PGM",
                        data={"attr": "RPGLE", "usrprf": "*USER", "useadpaut": "*NO",
                              "source": _program(usage), "dspf": ""})
    store.objects[obj.key] = obj


def _chain_and_hold(store, dev):
    """Starts LOCKT, keys in the employee, and leaves the job sitting on the second EXFMT, with the
    record chained (and, for a U or C file, locked)."""
    c = signed(store, dev)
    run(c, "ADDLIBLE APPLIB")
    run(c, "CALL PGM(LOCKT)")
    s = c.handle("ENTER", {"empno": "10003"})
    return c, s


def test_a_chain_for_update_locks_the_record_for_another_job(store):
    _seed_file(store)
    _seed_program(store, "LOCKT", "U")
    a, s = _chain_and_hold(store, "QPADEV0151")
    assert "ALICE" in text(s)
    b = signed(store, "QPADEV0152")
    run(b, "ADDLIBLE APPLIB")
    run(b, "CALL PGM(LOCKT)")
    s2 = b.handle("ENTER", {"empno": "10003"})
    assert "ended abnormally" in text(s2) and "locked by another job" in text(s2)


def test_the_lock_releases_when_the_holding_job_ends(store):
    _seed_file(store)
    _seed_program(store, "LOCKT", "U")
    a, _ = _chain_and_hold(store, "QPADEV0153")
    a.handle("ENTER", {})                                       # second EXFMT: *inlr on, RETURN -- job ends
    b = signed(store, "QPADEV0154")
    run(b, "ADDLIBLE APPLIB")
    run(b, "CALL PGM(LOCKT)")
    s2 = b.handle("ENTER", {"empno": "10003"})
    assert "ALICE" in text(s2) and "ended abnormally" not in text(s2)


def test_an_update_releases_the_lock_before_the_job_ends(store):
    _seed_file(store)
    source = "\n".join([
        fline("EMPINQ", "C", "F", "E", device="WORKSTN"),
        fline("PAYLOCK", "U", "F", "E", keyed=True, device="DISK"),
        cline("EXFMT", factor2="PAYLOOK"),
        cline("CHAIN", factor1="EMPNO", factor2="PAYLOCK", ind_hi="71"),
        cline("UPDATE", factor2="PAYLOCK"),
        cline("EXFMT", factor2="PAYLOOK"),
        cline("EVAL", factor2="*inlr = *on"),
        cline("RETURN"),
    ]) + "\n"
    obj = SecuredObject("LOCKU", "STUDENT", public=USE, library="APPLIB", type="*PGM",
                        data={"attr": "RPGLE", "usrprf": "*USER", "useadpaut": "*NO", "source": source, "dspf": ""})
    store.objects[obj.key] = obj
    a = signed(store, "QPADEV0155")
    run(a, "ADDLIBLE APPLIB")
    run(a, "CALL PGM(LOCKU)")
    a.handle("ENTER", {"empno": "10003"})                       # CHAIN, UPDATE, then the second EXFMT: still paused
    b = signed(store, "QPADEV0156")
    run(b, "ADDLIBLE APPLIB")
    _seed_program(store, "LOCKT", "U")
    run(b, "CALL PGM(LOCKT)")
    s2 = b.handle("ENTER", {"empno": "10003"})
    assert "ALICE" in text(s2) and "ended abnormally" not in text(s2)


def test_a_read_only_chain_never_locks(store):
    _seed_file(store)
    _seed_program(store, "LOCKI", "I")
    c = signed(store, "QPADEV0157")
    run(c, "ADDLIBLE APPLIB")
    run(c, "CALL PGM(LOCKI)")
    c.handle("ENTER", {"empno": "10003"})
    c2 = signed(store, "QPADEV0158")
    run(c2, "ADDLIBLE APPLIB")
    run(c2, "CALL PGM(LOCKI)")
    s2 = c2.handle("ENTER", {"empno": "10003"})
    assert "ALICE" in text(s2) and "ended abnormally" not in text(s2)
