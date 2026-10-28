"""The SQL runner: authority first, then the statement, and nothing but the files it names."""

import pytest

from silverlake.cl.session import Session
from silverlake.system import pase, profiles, sql


@pytest.fixture
def store():
    return profiles.load()


def go(store, user, statement, libs=("APPLIB",)):
    session = Session.for_profile(store.profiles[user].current_library)
    for lib in libs:
        if lib not in session.search_order():
            session.user_libraries.append(lib) if hasattr(session, "user_libraries") else None
    return sql.run(store, store.profiles[user], session, statement)


def test_select_reads_the_rows_of_a_file_the_profile_may_read(store):
    r = go(store, "OPERATOR", "SELECT EMPNO, NAME FROM APPLIB.PAYROLL WHERE DEPT = 'OPS' ORDER BY EMPNO")
    assert r.columns == ["EMPNO", "NAME"] and r.rows[0][1] == "Chen, Priya" and r.count == len(r.rows) >= 1
    out = sql.render(r)
    assert out[0].startswith("EMPNO") and out[1].startswith("-----") and out[-1].endswith("record(s) selected.")


def test_the_rows_stay_behind_the_authority_the_file_carries(store):
    r = go(store, "STUDENT", "SELECT * FROM APPLIB.PAYROLL")
    assert r.error.startswith("SQL0551") and "PAYROLL" in r.error
    assert go(store, "QSECOFR", "SELECT COUNT(*) AS N FROM APPLIB.PAYROLL").rows[0][0] >= 5


def test_a_missing_file_or_library_is_not_found(store):
    assert go(store, "OPERATOR", "SELECT * FROM APPLIB.NOSUCH").error.startswith("SQL0204")
    assert go(store, "OPERATOR", "SELECT * FROM NOLIB.PAYROLL").error.startswith("SQL0204")


def test_update_insert_and_delete_need_their_own_authority_and_write_back(store):
    assert go(store, "OPERATOR", "UPDATE APPLIB.PAYROLL SET SALARY = 1 WHERE EMPNO = 10004").error.startswith("SQL0551")
    r = go(store, "QSECOFR", "UPDATE APPLIB.PAYROLL SET SALARY = 99999 WHERE EMPNO = 10004")
    assert r.kind == "change" and r.count == 1 and sql.render(r) == ["  1 record(s) changed."]
    rows = store.objects[("APPLIB", "PAYROLL", "*FILE")].data["records"]
    assert next(x for x in rows if x["EMPNO"] == 10004)["SALARY"] == 99999
    n = len(store.objects[("APPLIB", "PAYROLL", "*FILE")].data["records"])
    assert go(store, "QSECOFR", "DELETE FROM APPLIB.PAYROLL WHERE EMPNO = 10005").count == 1
    assert len(store.objects[("APPLIB", "PAYROLL", "*FILE")].data["records"]) == n - 1
    assert go(store, "QSECOFR", "INSERT INTO APPLIB.PAYROLL VALUES (20001, 'New, Hire', 'ENG', 1)").count == 1


def test_a_refused_statement_changes_nothing(store):
    before = list(store.objects[("APPLIB", "PAYROLL", "*FILE")].data["records"])
    go(store, "OPERATOR", "DELETE FROM APPLIB.PAYROLL")
    assert store.objects[("APPLIB", "PAYROLL", "*FILE")].data["records"] == before


def test_only_the_four_statements_and_only_one_at_a_time(store):
    for stmt in ("DROP TABLE APPLIB.PAYROLL", "PRAGMA table_info(PAYROLL)", "ATTACH DATABASE 'x' AS y",
                 "CREATE TABLE T (A INT)"):
        assert go(store, "QSECOFR", stmt).error.startswith("SQL0104"), stmt
    assert go(store, "QSECOFR", "SELECT 1 FROM APPLIB.PAYROLL; DELETE FROM APPLIB.PAYROLL").error.startswith("SQL0104")
    assert go(store, "QSECOFR", "SELECT name FROM sqlite_master").error.startswith("SQL0204")   # no such file
    assert go(store, "QSECOFR", "SELECT * FROM").error.startswith("SQL0104")
    assert go(store, "QSECOFR", "").error.startswith("SQL0104")


def test_call_qcmdexc_runs_cl_as_the_same_profile(store):
    ok = go(store, "QSECOFR", "CALL QSYS2.QCMDEXC('CRTLIB LIB(SQLLIB)')")
    assert ok.kind == "command" and store.find_library("SQLLIB")
    denied = go(store, "STUDENT", "CALL QSYS2.QCMDEXC('CRTUSRPRF USRPRF(EVIL) PASSWORD(X) SPCAUT(*ALLOBJ)')")
    assert "EVIL" not in store.profiles and sql.render(denied)


def test_db2_in_the_shell_prints_the_result(store):
    sh = pase.Shell(store, store.profiles["OPERATOR"])
    out = sh.run('db2 "select name from applib.payroll where empno = 10003"')
    assert out[0] == "NAME" and "Chen, Priya" in out[2] and out[-1].endswith("record(s) selected.")
    assert pase.Shell(store, store.profiles["STUDENT"]).run('db2 "select * from applib.payroll"')[0].startswith("SQL0551")
    assert sh.run("db2") == ['db2: usage: db2 "SQL statement"']
    assert sh.run('echo "select 1 from applib.payroll" > q') == []


def test_a_runaway_statement_is_stopped(store):
    r = go(store, "QSECOFR", "WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM c) SELECT COUNT(*) FROM c, APPLIB.PAYROLL")
    assert r.error.startswith("SQL0104")
    assert go(store, "QSECOFR", "SELECT zeroblob(2000000000) FROM APPLIB.PAYROLL").error.startswith("SQL0104")
