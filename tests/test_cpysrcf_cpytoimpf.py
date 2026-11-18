"""CPYSRCF (source members between source files) and CPYTOIMPF (a database file to a delimited IFS
stream file). Neither was captured; see docs/rpg.md."""

import pytest

from silverlake.cl import commands
from silverlake.cl.session import Session
from silverlake.system import profiles, source


@pytest.fixture
def store():
    return profiles.load()


def run(store, user, line, session=None):
    s = session or Session.for_profile(store.get(user).current_library)
    return commands.execute(store, store.get(user), line, s)


def said(out):
    return out.message.text if out.message else ""


def sess(store, user="STUDENT", *libs):
    s = Session.for_profile(store.get(user).current_library)
    s.user_libs += list(libs)
    return s


def src_file(store, user, name, s):
    assert "created" in said(run(store, user, f"CRTSRCPF FILE(SCRATCH/{name})", s))
    return store.objects[("SCRATCH", name, "*FILE")]


# -- CPYSRCF -----------------------------------------------------------------------------------------

def test_copies_one_named_member(store):
    s = sess(store, "STUDENT", "SCRATCH")
    frm = src_file(store, "STUDENT", "FROMFILE", s)
    source.put_member(store, frm, "HELLO", ["     C     EVAL      x = 1"], "RPGLE", "greeting")
    src_file(store, "STUDENT", "TOFILE", s)
    out = run(store, "STUDENT", "CPYSRCF FROMFILE(SCRATCH/FROMFILE) TOFILE(SCRATCH/TOFILE) FROMMBR(HELLO)", s)
    assert "1 member(s) copied" in said(out)
    to = store.objects[("SCRATCH", "TOFILE", "*FILE")]
    assert source.member(to, "HELLO")["text"] == "greeting"


def test_tombr_renames_the_copy(store):
    s = sess(store, "STUDENT", "SCRATCH")
    frm = src_file(store, "STUDENT", "FROMFILE", s)
    source.put_member(store, frm, "HELLO", ["x"], "RPGLE")
    to = src_file(store, "STUDENT", "TOFILE", s)
    run(store, "STUDENT", "CPYSRCF FROMFILE(SCRATCH/FROMFILE) TOFILE(SCRATCH/TOFILE) FROMMBR(HELLO) TOMBR(GREET)", s)
    assert source.member(to, "GREET") is not None and source.member(to, "HELLO") is None


def test_frommbr_all_copies_every_member_under_its_own_name(store):
    s = sess(store, "STUDENT", "SCRATCH")
    frm = src_file(store, "STUDENT", "FROMFILE", s)
    source.put_member(store, frm, "A", ["1"], "RPGLE")
    source.put_member(store, frm, "B", ["2"], "RPGLE")
    to = src_file(store, "STUDENT", "TOFILE", s)
    out = run(store, "STUDENT", "CPYSRCF FROMFILE(SCRATCH/FROMFILE) TOFILE(SCRATCH/TOFILE) FROMMBR(*ALL)", s)
    assert "2 member(s) copied" in said(out)
    assert source.member(to, "A") is not None and source.member(to, "B") is not None


def test_mbropt_add_skips_a_member_that_already_exists(store):
    s = sess(store, "STUDENT", "SCRATCH")
    frm = src_file(store, "STUDENT", "FROMFILE", s)
    source.put_member(store, frm, "HELLO", ["1"], "RPGLE", "new")
    to = src_file(store, "STUDENT", "TOFILE", s)
    source.put_member(store, to, "HELLO", ["0"], "RPGLE", "old")
    out = run(store, "STUDENT", "CPYSRCF FROMFILE(SCRATCH/FROMFILE) TOFILE(SCRATCH/TOFILE) FROMMBR(HELLO) "
                                "MBROPT(*ADD)", s)
    assert "No members copied" in said(out)
    assert source.member(to, "HELLO")["text"] == "old"


def test_a_member_not_found_is_refused(store):
    s = sess(store, "STUDENT", "SCRATCH")
    src_file(store, "STUDENT", "FROMFILE", s)
    src_file(store, "STUDENT", "TOFILE", s)
    out = run(store, "STUDENT", "CPYSRCF FROMFILE(SCRATCH/FROMFILE) TOFILE(SCRATCH/TOFILE) FROMMBR(NOSUCH)", s)
    assert "not found" in said(out)


def test_needs_write_authority_to_the_to_file(store):
    s = sess(store, "STUDENT", "SCRATCH", "APPLIB")
    frm = src_file(store, "STUDENT", "FROMFILE", s)
    source.put_member(store, frm, "HELLO", ["1"], "RPGLE")
    out = run(store, "STUDENT", "CPYSRCF FROMFILE(SCRATCH/FROMFILE) TOFILE(APPLIB/QRPGLESRC) FROMMBR(HELLO)", s)
    assert "do not have authority" in said(out) or "not found" in said(out)


# -- CPYTOIMPF -----------------------------------------------------------------------------------------

def test_copies_records_as_delimited_lines(store):
    s = sess(store, "OPERATOR", "APPLIB")                   # PAYAUTL gives OPERATOR *USE on PAYROLL
    out = run(store, "OPERATOR", "CPYTOIMPF FROMFILE(APPLIB/PAYROLL) TOFILE('/home/OPERATOR/payroll.csv')", s)
    assert "records copied" in said(out)
    text = store.ifs["/home/OPERATOR/payroll.csv"].content
    assert text.endswith("\r\n") and '"' in text                 # *CRLF and *DBLQUOTE are the defaults
    first = text.split("\r\n")[0]
    assert "," in first


def test_strdlm_none_leaves_character_fields_unquoted(store):
    s = sess(store, "OPERATOR", "APPLIB")
    run(store, "OPERATOR", "CPYTOIMPF FROMFILE(APPLIB/PAYROLL) TOFILE('/home/OPERATOR/payroll.csv') "
                           "RCDDLM(*LF) STRDLM(*NONE)", s)
    text = store.ifs["/home/OPERATOR/payroll.csv"].content
    assert '"' not in text and "\n" in text and "\r\n" not in text


def test_needs_use_on_the_from_file(store):
    s = sess(store, "STUDENT", "APPLIB")
    out = run(store, "STUDENT", "CPYTOIMPF FROMFILE(APPLIB/PAYROLL) TOFILE('/home/STUDENT/x.csv')", s)
    assert "Not authorized" in said(out)
    assert "/home/STUDENT/x.csv" not in store.ifs
