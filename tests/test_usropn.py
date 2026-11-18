"""USROPN: a DISK file that is not opened at program start, needs an explicit OPEN statement, and
can be overridden by the program itself (through QCMDEXC) after it starts and before OPEN runs --
something an ordinary F-spec can't do, since every other file opens before the first statement.
See docs/rpg.md, 'Overrides and QTEMP'."""

import pytest

from silverlake.screens.model import Text
from silverlake.screens.signon import SignonController
from silverlake.system import profiles
from silverlake.system.authority import USE, SecuredObject

PAYROLL_DDS = "\n".join([
    "     A* one employee per record, shared by SHADOW1 and SHADOW2.",
    "",
    "     A          R PAYREC",
    "     A            EMPNO          5S 0",
    "     A            NAME          20",
    "     A            DEPT           4",
    "     A            SALARY         7S 0",
    "     A          K EMPNO",
]) + "\n"

OVRDBF_CMD = "OVRDBF FILE(SHADOW1) TOFILE(APPLIB/SHADOW2)"


def _set(line: str, start: int, text: str) -> str:
    """Places text at 1-based column start, padding the line out if it isn't long enough yet."""
    end = start - 1 + len(text)
    if len(line) < end:
        line = line.ljust(end)
    return line[: start - 1] + text + line[end:]


def fline(name, ftype="I", desig="F", fmt="E", keyed=False, device="DISK", keywords="") -> str:
    s = _set(" " * 5 + "F", 7, name)
    s = _set(s, 17, ftype)
    s = _set(s, 18, desig)
    s = _set(s, 22, fmt)
    if keyed:
        s = _set(s, 34, "K")
    s = _set(s, 36, device)
    if keywords:
        s = _set(s, 44, keywords)
    return s


def dline(name, length, dec=None) -> str:
    s = _set(" " * 5 + "D", 7, name)
    s = _set(s, 24, "S")
    s = _set(s, 33, str(length))
    if dec is not None:
        s = _set(s, 41, str(dec))
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


def _program(open_file: bool, override: bool) -> str:
    lines = [
        fline("EMPINQ", "C", "F", "E", device="WORKSTN"),
        fline("SHADOW1", "I", "F", "E", keyed=True, device="DISK", keywords="USROPN"),
    ]
    if override:
        lines += [dline("CMD", 60), dline("LEN", 15, 0)]
    lines.append(cline("EXFMT", factor2="PAYLOOK"))
    if override:
        lines.append(cline("EVAL", factor2=f"cmd = '{OVRDBF_CMD}'"))
        lines.append(cline("EVAL", factor2=f"len = {len(OVRDBF_CMD)}"))
        lines.append(cline("CALL", factor2="'QCMDEXC'"))
        lines.append(cline("PARM", result="CMD"))
        lines.append(cline("PARM", result="LEN"))
    if open_file:
        lines.append(cline("OPEN", factor2="SHADOW1"))
    lines.append(cline("CHAIN", factor1="EMPNO", factor2="SHADOW1", ind_hi="71"))
    lines.append(cline("EXFMT", factor2="PAYLOOK"))
    lines.append(cline("EVAL", factor2="*inlr = *on"))
    lines.append(cline("RETURN"))
    return "\n".join(lines) + "\n"


@pytest.fixture
def store():
    return profiles.load()


def signed(store, user="STUDENT", dev="QPADEV0141"):
    c = SignonController(dev, store)
    c.handle("ENTER", {"user": user, "password": user})
    return c


def run(c, line):
    return c.handle("ENTER", {"command": line})


def text(s):
    return " | ".join(f.text for f in s.fields if isinstance(f, Text))


def _seed_shadow_files(store, name_one="SHADOW-ONE", name_two="SHADOW-TWO"):
    for fname, empname in (("SHADOW1", name_one), ("SHADOW2", name_two)):
        obj = SecuredObject(fname, "STUDENT", public=USE, library="APPLIB", type="*FILE",
                            data={"attr": "PF", "dds": PAYROLL_DDS,
                                  "records": [{"EMPNO": 10003, "NAME": empname, "DEPT": "ACCT", "SALARY": 50000}]})
        store.objects[obj.key] = obj


def _seed_program(store, name: str, source: str):
    obj = SecuredObject(name, "STUDENT", public=USE, library="APPLIB", type="*PGM",
                        data={"attr": "RPGLE", "usrprf": "*USER", "useadpaut": "*NO", "source": source, "dspf": ""})
    store.objects[obj.key] = obj


def test_a_usropn_file_is_not_open_until_an_open_statement_runs(store):
    _seed_shadow_files(store)
    _seed_program(store, "NOOPEN", _program(open_file=False, override=False))
    c = signed(store)
    run(c, "ADDLIBLE APPLIB")
    run(c, "CALL PGM(NOOPEN)")
    s = c.handle("ENTER", {"empno": "10003"})
    assert "not open" in text(s).lower()


def test_open_applies_an_override_the_program_made_after_it_started(store):
    _seed_shadow_files(store)
    _seed_program(store, "USROPNT", _program(open_file=True, override=True))
    c = signed(store)
    run(c, "ADDLIBLE APPLIB")
    run(c, "CALL PGM(USROPNT)")
    s = c.handle("ENTER", {"empno": "10003"})
    body = text(s)
    assert "SHADOW-TWO" in body and "SHADOW-ONE" not in body
    assert "File SHADOW1 overridden to APPLIB/SHADOW2." in " | ".join(t for _, _, t in c.session.joblog)


def test_open_without_an_override_reads_the_named_file(store):
    _seed_shadow_files(store)
    _seed_program(store, "USROPNN", _program(open_file=True, override=False))
    c = signed(store)
    run(c, "ADDLIBLE APPLIB")
    run(c, "CALL PGM(USROPNN)")
    s = c.handle("ENTER", {"empno": "10003"})
    assert "SHADOW-ONE" in text(s)
