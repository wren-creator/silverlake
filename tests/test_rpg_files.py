"""DISK files for RPG programs: *FILE objects with a record layout and records, authority checked at open
and on every operation against whoever the call stack holds, and changes kept in the objects."""

import pytest

from silverlake.screens.model import Text
from silverlake.screens.signon import SignonController
from silverlake.system import profiles, state
from silverlake.system.authority import EXCLUDE, USE, SecuredObject

PROBE = "\n".join([
    "     FPAYROLL   {u}F   E           K DISK",
    "     C                   EVAL      empno = 10003",
    "     C     empno         CHAIN     PAYROLL                            71",
    "{body}",
    "     C                   EVAL      *inlr = *on",
    "     C                   RETURN",
]) + "\n"


@pytest.fixture
def store():
    return profiles.load()


def signed(store, user="STUDENT"):
    c = SignonController("QPADEV0071", store)
    c.handle("ENTER", {"user": user, "password": user})
    c.handle("ENTER", {"command": "ADDLIBLE APPLIB"})
    return c


def text(s):
    return " | ".join(f.text for f in s.fields if isinstance(f, Text))


def joblog(c):
    return " | ".join(t for _, _, t in c.session.joblog)


def probe(store, name, owner="STUDENT", usrprf="*USER", usage="I", body=""):
    src = PROBE.format(u=usage, body=body)
    obj = SecuredObject(name, owner, public=USE, library="APPLIB", type="*PGM",
                        data={"attr": "RPGLE", "usrprf": usrprf, "useadpaut": "*YES", "source": src, "dspf": ""})
    store.objects[obj.key] = obj
    return obj


def payroll(store):
    return store.objects[("APPLIB", "PAYROLL", "*FILE")]


def salary(store, empno):
    return next(r["SALARY"] for r in payroll(store).data["records"] if r["EMPNO"] == empno)


def test_seeded_files_carry_a_layout_and_records(store):
    for name in ("PAYROLL", "CUSTOMERS"):
        data = store.objects[("APPLIB", name, "*FILE")].data
        assert data["attr"] == "PF" and " R " in data["dds"] and data["records"]


def test_a_user_cannot_open_the_payroll_file_directly(store):
    probe(store, "SNOOP")
    c = signed(store)
    c.handle("ENTER", {"command": "CALL PGM(SNOOP)"})
    assert "Not authorized to use object PAYROLL in library APPLIB type *FILE." in joblog(c)


def test_the_same_read_works_through_a_program_that_adopts_an_owner_who_may(store):
    probe(store, "READIT", owner="OPERATOR", usrprf="*OWNER")
    c = signed(store)
    s = c.handle("ENTER", {"command": "CALL PGM(READIT)"})
    assert "ended abnormally" not in text(s)


def test_payroll_lookup_shows_a_record_to_a_basic_user_and_changes_nothing(store):
    c = signed(store)
    c.handle("ENTER", {"command": "CALL PGM(PAYLOOK)"})
    s = c.handle("ENTER", {"empno": "10003"})
    assert "Chen, Priya" in text(s) and "0072000" in text(s)
    s = c.handle("ENTER", {"empno": "99999"})
    assert "No such employee" in text(s)
    assert salary(store, 10003) == 72000


def test_an_owner_who_may_only_read_cannot_be_used_to_update(store):
    body = "\n".join(["     C                   EVAL      salary = 1", "     C                   UPDATE    PAYREC"])
    probe(store, "RAISE", owner="OPERATOR", usrprf="*OWNER", usage="U", body=body)
    c = signed(store)
    s = c.handle("ENTER", {"command": "CALL PGM(RAISE)"})
    assert "Not authorized" in text(s)
    assert salary(store, 10003) == 72000


def test_the_vulnerable_adjust_program_gives_anyone_a_raise_and_it_sticks(store):
    c = signed(store)
    c.handle("ENTER", {"command": "CALL PGM(PAYADJ)"})
    s = c.handle("ENTER", {"empno": "10004", "newsal": "999999"})
    assert "Salary changed" in text(s)
    assert salary(store, 10004) == 999999


def test_the_fix_is_who_may_call_it(store):
    store.objects[("APPLIB", "PAYADJ", "*PGM")].public = EXCLUDE
    store.objects[("APPLIB", "PAYADJ", "*PGM")].private["OPERATOR"] = USE
    c = signed(store)
    assert "Not authorized" in text(c.handle("ENTER", {"command": "CALL PGM(PAYADJ)"}))
    assert salary(store, 10004) == 65000


def test_adoption_ends_when_the_program_does(store):
    c = signed(store)
    c.handle("ENTER", {"command": "CALL PGM(PAYLOOK)"})
    c.handle("F3", {})
    probe(store, "SNOOP")
    assert "Not authorized" in text(c.handle("ENTER", {"command": "CALL PGM(SNOOP)"}))


def test_a_program_called_by_one_that_adopts_reaches_the_file_when_use_adopted_authority_is_yes(store):
    probe(store, "INNER")                               # runs as the user, USEADPAUT *YES, opens PAYROLL
    outer = SecuredObject("OUTER", "OPERATOR", public=USE, library="APPLIB", type="*PGM",
                          data={"attr": "RPGLE", "usrprf": "*OWNER", "useadpaut": "*YES", "dspf": "",
                                "source": "     C                   CALL      'APPLIB/INNER'\n"
                                          "     C                   EVAL      *inlr = *on\n     C                   RETURN\n"})
    store.objects[outer.key] = outer
    c = signed(store)
    assert "ended abnormally" not in text(c.handle("ENTER", {"command": "CALL PGM(OUTER)"}))
    store.objects[("APPLIB", "INNER", "*PGM")].data["useadpaut"] = "*NO"
    assert "Not authorized" in text(c.handle("ENTER", {"command": "CALL PGM(OUTER)"}))


def test_a_file_that_is_not_there_says_so_before_the_program_starts(store):
    del store.objects[("APPLIB", "PAYROLL", "*FILE")]
    probe(store, "SNOOP")
    c = signed(store)
    assert "PAYROLL" in text(c.handle("ENTER", {"command": "CALL PGM(SNOOP)"}))


def test_records_survive_a_save_and_load(store):
    c = signed(store)
    c.handle("ENTER", {"command": "CALL PGM(PAYADJ)"})
    c.handle("ENTER", {"empno": "10004", "newsal": "70000"})
    again = state.from_dict(state.to_dict(store))
    assert next(r["SALARY"] for r in again.objects[("APPLIB", "PAYROLL", "*FILE")].data["records"]
                if r["EMPNO"] == 10004) == 70000

