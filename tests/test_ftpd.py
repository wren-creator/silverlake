"""The FTP server: sign-on through the profile store, listing and getting files under the usual authority."""

import asyncio
import socket

import pytest

from silverlake.net import ftpd, services
from silverlake.system import profiles
from silverlake.system.authority import EXCLUDE


@pytest.fixture
def store():
    return profiles.load()


def login(store, user, password=None):
    s = ftpd.FtpSession(store)
    s.handle(f"USER {user}")
    return s, s.handle(f"PASS {password or user}")


def code(step):
    return step.replies[0][0]


def test_nothing_works_before_sign_on_except_the_greeting_and_sign_on(store):
    s = ftpd.FtpSession(store)
    assert s.greeting().replies[0][0] == 220
    assert code(s.handle("LIST")) == 530 and code(s.handle("RETR APPLIB/PAYROLL")) == 530
    assert code(s.handle("NOOP")) == 200 and code(s.handle("BOGUS")) == 500
    assert code(s.handle("PASS x")) == 503


def test_a_good_password_signs_on_and_a_bad_one_counts_against_the_profile(store):
    assert code(login(store, "STUDENT")[1]) == 230
    for _ in range(store.system.qmaxsign):
        assert code(login(store, "OPERATOR", "wrong")[1]) == 530
    assert store.profiles["OPERATOR"].status != "*ENABLED"
    assert code(login(store, "OPERATOR")[1]) == 530


def test_a_profile_that_cannot_sign_on_is_rejected_without_saying_why(store):
    assert code(login(store, "QSYS", "QSYS")[1]) == 530 and code(login(store, "NOSUCH", "x")[1]) == 530


def test_the_server_says_what_it_is(store):
    s, _ = login(store, "STUDENT")
    assert "OS/400" in s.handle("SYST").replies[0][1] and "V7R4M0" in s.handle("SYST").replies[0][1]
    assert code(s.handle("AUTH TLS")) == 502


def test_a_file_the_profile_may_not_read_is_refused_and_one_it_may_read_comes_back(store):
    s, _ = login(store, "STUDENT")
    refused = s.handle("RETR APPLIB/PAYROLL")
    assert refused.data is None and code(refused) == 550 and "authorized" in refused.replies[0][1].lower()
    s2, _ = login(store, "OPERATOR")
    got = s2.handle("RETR APPLIB/PAYROLL")
    assert got.data and "Chen" in got.data and got.after[0][0] == 226


def test_there_is_no_way_to_write(store):
    s, _ = login(store, "QSECOFR")
    for c in ("STOR APPLIB/X", "DELE APPLIB/PAYROLL", "MKD X", "RMD X", "RNFR X", "RCMD DSPLIBL"):
        assert code(s.handle(c)) == 500


def test_both_naming_formats_reach_the_same_file(store):
    s, _ = login(store, "OPERATOR")
    a = s.handle("RETR APPLIB/PAYROLL").data
    s.handle("NAMEFMT 1")
    b = s.handle("RETR /QSYS.LIB/APPLIB.LIB/PAYROLL.FILE").data
    assert a == b and a
    assert code(s.handle("CWD /QSYS.LIB/APPLIB.LIB")) == 250 and s.handle("LIST").data.find("PAYROLL") >= 0
    assert code(s.handle("CWD /QSYS.LIB/NOPE.LIB")) == 550
    s.handle("NAMEFMT 0")
    assert code(s.handle("CWD APPLIB")) == 250 and "PAYROLL" in s.handle("NLST").data


def test_a_listing_leaves_out_what_the_profile_cannot_see_and_a_locked_library_is_refused(store):
    s, _ = login(store, "STUDENT")
    s.handle("CWD APPLIB")
    names = s.handle("LIST").data
    assert "CUSTOMERS" in names and "VAULT" not in names
    store.objects[("QSYS", "APPLIB", "*LIB")].public = EXCLUDE
    s2, _ = login(store, "STUDENT")
    assert code(s2.handle("CWD APPLIB")) == 250
    assert code(s2.handle("LIST")) == 550


def free_port():
    with socket.socket() as sk:
        sk.bind(("127.0.0.1", 0))
        return sk.getsockname()[1]


def test_a_real_client_can_sign_on_list_and_get_a_file_over_sockets(store):
    import ftplib
    port = free_port()

    def client():
        ftp = ftplib.FTP()
        ftp.connect("127.0.0.1", port, timeout=5)
        ftp.login("OPERATOR", "OPERATOR")
        out = []
        ftp.retrlines("RETR APPLIB/PAYROLL", out.append)
        ftp.quit()
        return out

    async def go():
        servers = await services.start("127.0.0.1", lambda: store, {"SILVERLAKE_HTTPADMIN_PORT": str(free_port()),
                                                                     "SILVERLAKE_FTP_PORT": str(port)})
        try:
            return await asyncio.get_running_loop().run_in_executor(None, client)
        finally:
            for sv in servers:
                sv.close()

    rows = asyncio.run(go())
    assert rows and "Chen" in " ".join(rows)


def test_limited_capability_does_not_stop_ftp_until_the_exit_program_is_registered(store):
    s, ok = login(store, "CLERK")
    assert code(ok) == 230
    s.handle("CWD APPLIB")
    assert "DAILYOPS" in s.handle("LIST").data
    assert "Month end" in s.handle("RETR DAILYOPS").data
    store.objects[("QUSRSYS", "FTPEXIT", "*PGM")].data["registered"] = "yes"
    assert code(s.handle("LIST")) == 550 and code(s.handle("RETR DAILYOPS")) == 550


def test_the_exit_program_leaves_unlimited_profiles_alone(store):
    store.objects[("QUSRSYS", "FTPEXIT", "*PGM")].data["registered"] = "yes"
    s, _ = login(store, "OPERATOR")
    assert s.handle("RETR APPLIB/PAYROLL").data


def test_the_notes_are_for_the_clerk_only(store):
    s, _ = login(store, "STUDENT")
    s.handle("CWD APPLIB")
    assert "DAILYOPS" not in s.handle("LIST").data
    assert code(s.handle("RETR DAILYOPS")) == 550
