"""OVRDBF and QTEMP, and the two seeded lessons they make: a caller who redirects a file an adopting program
opens (EMPDIR, fixed by EMPDIRX), and a caller who puts a program of their own ahead of the one an adopting
program calls by name (PAYRUN, fixed by PAYRUNX)."""

import pytest

from silverlake.screens.model import Text
from silverlake.screens.signon import SignonController
from silverlake.system import profiles, source
from silverlake.system.authority import EXCLUDE, USE, SecuredObject

PAYSNOOP = "\n".join([
    "     FEMPINQ    CF   E             WORKSTN",
    "     FPAYROLL   IF   E           K DISK",
    "     C                   EXFMT     PAYLOOK",
    "     C     EMPNO         CHAIN     PAYROLL                            71",
    "     C                   EXFMT     PAYLOOK",
    "     C                   EVAL      *inlr = *on",
    "     C                   RETURN",
]) + "\n"


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


def joblog(c):
    return " | ".join(t for _, _, t in c.session.joblog)


def test_a_normal_user_cannot_read_payroll_but_may_call_the_directory(store):
    c = signed(store)
    run(c, "ADDLIBLE APPLIB")
    s = run(c, "CALL PGM(EMPDIR)")
    s = c.handle("ENTER", {"empno": "10003"})
    assert "Chen, Priya" in text(s) and "0000000" in text(s)       # salary is zero in STAFF


def test_an_override_redirects_the_file_an_adopting_program_opens(store):
    c = signed(store)
    run(c, "ADDLIBLE APPLIB")
    run(c, "OVRDBF FILE(STAFF) TOFILE(APPLIB/PAYROLL)")
    run(c, "CALL PGM(EMPDIR)")
    s = c.handle("ENTER", {"empno": "10003"})
    assert "Chen, Priya" in text(s) and "0072000" in text(s)       # OPERATOR's authority read the payroll
    assert "File STAFF overridden to APPLIB/PAYROLL." in joblog(c)


def test_the_override_alone_gives_a_normal_user_nothing(store):
    c = signed(store)
    run(c, "ADDLIBLE APPLIB")
    run(c, "OVRDBF FILE(PAYROLL) TOFILE(APPLIB/STAFF)")
    probe = SecuredObject("SNOOP", "STUDENT", public=USE, library="APPLIB", type="*PGM",
                          data={"attr": "RPGLE", "usrprf": "*USER", "useadpaut": "*YES", "source": PAYSNOOP,
                                "dspf": ""})
    store.objects[probe.key] = probe
    s = run(c, "CALL PGM(SNOOP)")
    s = c.handle("ENTER", {"empno": "10003"})
    assert "0072000" not in text(s)


def test_an_override_to_a_file_the_owner_cannot_read_is_refused_at_open(store):
    c = signed(store)
    run(c, "ADDLIBLE APPLIB")
    payroll = store.objects[("APPLIB", "PAYROLL", "*FILE")]
    payroll.autl, payroll.public = None, EXCLUDE            # OPERATOR, the adopted owner, no longer reaches it
    run(c, "OVRDBF FILE(STAFF) TOFILE(APPLIB/PAYROLL)")
    assert "Not authorized" in text(run(c, "CALL PGM(EMPDIR)"))


def test_the_fixed_directory_is_refused_the_file_its_owner_cannot_reach(store):
    c = signed(store)
    run(c, "ADDLIBLE APPLIB")
    run(c, "OVRDBF FILE(STAFF) TOFILE(APPLIB/PAYROLL)")
    s = run(c, "CALL PGM(EMPDIRX)")
    assert "Not authorized" in text(s) and "0072000" not in text(s)
    run(c, "DLTOVR FILE(STAFF)")
    s = run(c, "CALL PGM(EMPDIRX)")
    assert "PAYLOOK" in text(s) or "Employee" in text(s)           # without the override it still works


def test_dltovr_removes_an_override_and_a_later_one_replaces_an_earlier(store):
    c = signed(store)
    run(c, "OVRDBF FILE(A) TOFILE(APPLIB/STAFF)")
    run(c, "OVRDBF FILE(A) TOFILE(APPLIB/PAYROLL)")
    assert c.session.overrides["A"]["to"] == "APPLIB/PAYROLL"
    run(c, "OVRDBF FILE(B) TOFILE(APPLIB/STAFF) SECURE(*YES)")
    run(c, "OVRDBF FILE(B) TOFILE(APPLIB/PAYROLL)")
    assert c.session.overrides["B"]["to"] == "APPLIB/STAFF"          # secured, so the later one is ignored
    run(c, "DLTOVR FILE(A)")
    assert "A" not in c.session.overrides and "B" in c.session.overrides
    run(c, "DLTOVR FILE(*ALL)")
    assert not c.session.overrides


def test_ovrdbf_with_a_bad_scope_is_refused(store):
    c = signed(store)
    assert "OVRSCOPE" in text(run(c, "OVRDBF FILE(A) TOFILE(APPLIB/STAFF) OVRSCOPE(*NOPE)"))


def test_an_override_belongs_to_one_job(store):
    c = signed(store)
    run(c, "OVRDBF FILE(STAFF) TOFILE(APPLIB/PAYROLL)")
    d = signed(store, "STUDENT", "QPADEV0142")
    assert not d.session.overrides


# -- QTEMP -----------------------------------------------------------------------------------------

def test_what_a_job_makes_in_qtemp_only_that_job_sees_and_it_goes_at_sign_off(store):
    c = signed(store)
    run(c, "CRTSRCPF FILE(QTEMP/QRPGLESRC)")
    assert ("QTEMP", "QRPGLESRC", "*FILE") in store.objects
    d = signed(store, "OPERATOR", "QPADEV0142")
    obj = store.objects[("QTEMP", "QRPGLESRC", "*FILE")]
    from silverlake.system import objects
    assert objects.visible(obj, c.session.search_order()) and not objects.visible(obj, d.session.search_order())
    c._sign_off()
    assert ("QTEMP", "QRPGLESRC", "*FILE") not in store.objects


def test_qtemp_comes_before_a_library_added_last(store):
    c = signed(store)
    run(c, "ADDLIBLE APPLIB *LAST")
    order = c.session.search_order()
    assert order.index("QTEMP") < order.index("APPLIB")


GRAB = [
    "     D c1              S             25    INZ('GRTOBJAUT APPLIB/PAYROLL ')",
    "     D c2              S             18    INZ('*FILE STUDENT *USE')",
    "     D cl              S             80",
    "     D len             S             15  0 INZ(43)",
    "     C                   EVAL      cl = c1 + c2",
    "     C                   CALL      'QCMDEXC'",
    "     C                   PARM                    cl",
    "     C                   PARM                    len",
    "     C                   EVAL      *inlr = *on",
    "     C                   RETURN",
]


def hijack(store, c):
    """The attacker's own PAYCALC in QTEMP: it gives the attacker *USE on the payroll file, which only works
    with the authority PAYRUN hands down. It does not declare PAYROLL, because compiling that needs authority."""
    run(c, "CRTSRCPF FILE(QTEMP/QRPGLESRC)")
    f = store.objects[("QTEMP", "QRPGLESRC", "*FILE")]
    source.put_member(store, f, "PAYCALC", GRAB, "RPGLE")
    return run(c, "CRTBNDRPG PGM(QTEMP/PAYCALC) SRCFILE(QTEMP/QRPGLESRC)")


def can_read_payroll(store, user="STUDENT"):
    from silverlake.system.authority import Auth
    return Auth.READ in store.authority_to_object(store.profiles[user], store.objects[("APPLIB", "PAYROLL", "*FILE")])


def test_a_program_in_qtemp_runs_in_place_of_the_one_an_adopting_program_calls_by_name(store):
    c = signed(store)
    run(c, "ADDLIBLE APPLIB *LAST")
    assert "placed in library QTEMP" in text(hijack(store, c))
    assert not can_read_payroll(store)
    run(c, "CALL PGM(PAYRUN)")
    assert can_read_payroll(store)                                  # SECADMIN's authority went to the attacker's code
    assert "GRTOBJAUT" in joblog(c)


def test_the_fixed_pay_run_calls_its_own_paycalc(store):
    c = signed(store)
    run(c, "ADDLIBLE APPLIB *LAST")
    hijack(store, c)
    s = run(c, "CALL PGM(PAYRUNX)")
    assert "ended abnormally" not in text(s) and not can_read_payroll(store)


def test_the_hijacked_program_has_no_special_power_when_the_user_calls_it_directly(store):
    c = signed(store)
    run(c, "ADDLIBLE APPLIB *LAST")
    hijack(store, c)
    run(c, "CALL PGM(QTEMP/PAYCALC)")
    assert not can_read_payroll(store)


def test_another_job_calling_the_pay_run_never_reaches_the_attackers_program(store):
    c = signed(store)
    run(c, "ADDLIBLE APPLIB *LAST")
    hijack(store, c)
    d = signed(store, "STUDENT", "QPADEV0142")
    run(d, "ADDLIBLE APPLIB *LAST")
    run(d, "CALL PGM(PAYRUN)")
    assert not can_read_payroll(store)
