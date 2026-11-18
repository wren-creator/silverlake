"""CHGPF, RGZPFM and CLRPFM: authority-gated commands over a physical file. None of this was
captured; the authority each needs is from IBM's command pages (CHGPF) and a web search quoting
their help text (RGZPFM, CLRPFM), not pages read in full. See docs/rpg.md."""

import pytest

from silverlake.screens.model import Text
from silverlake.screens.signon import SignonController
from silverlake.system import profiles


@pytest.fixture
def store():
    return profiles.load()


def signed(store, user="STUDENT", dev="QPADEV0161"):
    c = SignonController(dev, store)
    c.handle("ENTER", {"user": user, "password": user})
    c.handle("ENTER", {"command": "ADDLIBLE APPLIB"})
    c.handle("ENTER", {"command": "ADDLIBLE SCRATCH"})
    return c


def run(c, line):
    s = c.handle("ENTER", {"command": line})
    s.validate()
    return s


def text(s):
    return " | ".join(f.text for f in s.fields if isinstance(f, Text))


def recs(store, lib, name):
    return store.objects[(lib, name, "*FILE")].data["records"]


# STAFF is public *USE: object-operational, read, execute -- no *OBJMGT, *OBJALTER or *DLT.

def test_chgpf_needs_more_than_use(store):
    c = signed(store)
    assert "Not authorized" in text(run(c, "CHGPF FILE(APPLIB/STAFF)"))


def test_rgzpfm_needs_more_than_use(store):
    c = signed(store)
    assert "Not authorized" in text(run(c, "RGZPFM FILE(APPLIB/STAFF)"))


def test_clrpfm_needs_more_than_use(store):
    c = signed(store)
    assert "Not authorized" in text(run(c, "CLRPFM FILE(APPLIB/STAFF)"))


def test_the_owner_may_change_reorganize_and_clear_their_own_copy(store):
    c = signed(store, "OPERATOR")                           # PAYAUTL gives OPERATOR *USE on PAYROLL
    run(c, "CPYF FROMFILE(APPLIB/PAYROLL) TOFILE(SCRATCH/MYPAY) CRTFILE(*YES)")
    assert len(recs(store, "SCRATCH", "MYPAY")) == 7

    s = run(c, "CHGPF FILE(SCRATCH/MYPAY)")
    assert "changed" in text(s)

    s = run(c, "RGZPFM FILE(SCRATCH/MYPAY)")
    assert "reorganized" in text(s)
    assert len(recs(store, "SCRATCH", "MYPAY")) == 7          # nothing to compact, nothing lost

    s = run(c, "CLRPFM FILE(SCRATCH/MYPAY)")
    assert "7 records cleared" in text(s)
    assert recs(store, "SCRATCH", "MYPAY") == []


def test_chgpf_rgzpfm_clrpfm_refuse_a_display_file(store):
    c = signed(store)
    for cmd in ("CHGPF FILE(APPLIB/EMPINQ)", "RGZPFM FILE(APPLIB/EMPINQ)", "CLRPFM FILE(APPLIB/EMPINQ)"):
        assert "not a physical file" in text(run(c, cmd)).lower() or "Not authorized" in text(run(c, cmd))


def test_a_nonexistent_file_is_refused(store):
    c = signed(store)
    for cmd in ("CHGPF FILE(APPLIB/NOSUCH)", "RGZPFM FILE(APPLIB/NOSUCH)", "CLRPFM FILE(APPLIB/NOSUCH)"):
        assert "not found" in text(run(c, cmd)).lower()
