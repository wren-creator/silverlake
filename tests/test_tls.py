"""The TLS ports: 5250, the console, FTP (explicit and implicit) and the sign-on server, all on one throwaway
certificate, and not started at all when there is none."""

import asyncio
import ftplib
import socket
import ssl
import struct
from base64 import b64encode

import pytest

from netutil import all_ports, free_port, needs_openssl, tls_dir  # noqa: F401  (tls_dir is a fixture)
from silverlake.net import certs, hostsvr, services
from silverlake.screens.signon import SignonController
from silverlake.system import profiles

REQUEST = bytes(6) + struct.pack(">H", 0xE009) + bytes(10) + struct.pack(">H", 0x7003)
pytestmark = needs_openssl


@pytest.fixture
def store():
    return profiles.load()


def run_with_services(store, env, work):
    async def go():
        servers = await services.start("127.0.0.1", lambda: store, env,
                                       make_controller=lambda display: SignonController(display, store))
        try:
            return await asyncio.get_running_loop().run_in_executor(None, work)
        finally:
            for s in servers:
                s.close()
    return asyncio.run(go())


def test_the_certificate_is_self_signed_for_loopback_and_the_key_is_private(tls_dir):
    cert, key = certs.paths()
    assert cert.exists() and (key.stat().st_mode & 0o777) == 0o600
    assert certs.make() is True                      # second time keeps what is there
    before = cert.read_text()
    assert certs.make() and cert.read_text() == before
    assert certs.make(force=True) and cert.read_text() != before


def test_without_a_certificate_no_tls_port_starts(store, monkeypatch, tmp_path):
    monkeypatch.setenv("SILVERLAKE_TLS_DIR", str(tmp_path / "nothing"))
    env = all_ports()
    tls_port = int(env["SILVERLAKE_HTTPADMIN_TLS_PORT"])

    def probe():
        with pytest.raises(OSError):
            socket.create_connection(("127.0.0.1", tls_port), timeout=1)

    run_with_services(store, env, probe)


def test_the_console_answers_on_the_tls_port_and_shares_state_with_the_plain_one(store, tls_dir):
    env = all_ports()
    tls_port, plain = int(env["SILVERLAKE_HTTPADMIN_TLS_PORT"]), int(env["SILVERLAKE_HTTPADMIN_PORT"])
    cred = b64encode(b"STUDENT:STUDENT").decode()
    body = "name=ZZTLS&description=hello"

    def talk(port, tls, raw):
        s = socket.create_connection(("127.0.0.1", port), timeout=3)
        if tls:
            s = certs.client_context().wrap_socket(s, server_hostname="localhost")
        s.sendall(raw)
        out = b""
        while chunk := s.recv(4096):
            out += chunk
        s.close()
        return out

    def work():
        post = talk(tls_port, True, (f"POST /HTTPAdmin/servers HTTP/1.0\r\nAuthorization: Basic {cred}\r\n"
                                     f"Content-Length: {len(body)}\r\n\r\n{body}").encode())
        page = talk(plain, False, f"GET /HTTPAdmin/servers HTTP/1.0\r\nAuthorization: Basic {cred}\r\n\r\n".encode())
        return post, page

    post, page = run_with_services(store, env, work)
    assert post.startswith(b"HTTP/1.0 302") and b"ZZTLS" in page


@pytest.mark.filterwarnings("ignore::DeprecationWarning")
def test_the_tls_port_refuses_an_old_protocol_and_a_client_that_does_not_trust_the_certificate(store, tls_dir):
    env = all_ports()
    port = int(env["SILVERLAKE_HTTPADMIN_TLS_PORT"])

    def work():
        untrusting = ssl.create_default_context()
        with pytest.raises(ssl.SSLError):
            untrusting.wrap_socket(socket.create_connection(("127.0.0.1", port), timeout=3), server_hostname="localhost")
        old = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        old.check_hostname = False
        old.verify_mode = ssl.CERT_NONE
        old.maximum_version = ssl.TLSVersion.TLSv1_1
        with pytest.raises((ssl.SSLError, OSError)):
            old.wrap_socket(socket.create_connection(("127.0.0.1", port), timeout=3))

    run_with_services(store, env, work)


def test_ftp_upgrades_with_auth_tls_and_protects_the_data_connection_with_prot_p(store, tls_dir):
    env = all_ports()
    port = int(env["SILVERLAKE_FTP_PORT"])

    def work():
        ftp = ftplib.FTP_TLS(context=certs.client_context())
        ftp.connect("127.0.0.1", port, timeout=5)
        ftp.auth()
        ftp.login("OPERATOR", "OPERATOR")
        ftp.prot_p()
        rows = []
        ftp.retrlines("RETR APPLIB/PAYROLL", rows.append)
        ftp.quit()
        return rows

    assert "Chen" in " ".join(run_with_services(store, env, work))


def test_ftp_on_the_implicit_tls_port_is_tls_from_the_first_byte(store, tls_dir):
    env = all_ports()
    port = int(env["SILVERLAKE_FTP_TLS_PORT"])

    def work():
        raw = socket.create_connection(("127.0.0.1", port), timeout=3)
        s = certs.client_context().wrap_socket(raw, server_hostname="localhost")
        greeting = s.recv(200)
        s.sendall(b"USER OPERATOR\r\nPASS OPERATOR\r\nSYST\r\n")
        out = b""
        while b"215" not in out:
            out += s.recv(200)
        s.close()
        return greeting, out

    greeting, out = run_with_services(store, env, work)
    assert greeting.startswith(b"220") and b"230" in out and b"OS/400" in out


def test_ftp_without_a_certificate_says_auth_is_not_available(store, monkeypatch, tmp_path):
    from silverlake.net import ftpd
    s = ftpd.FtpSession(store)
    assert s.handle("AUTH TLS").replies[0][0] == 502
    assert s.handle("PBSZ 0").replies[0][0] == 503             # no security environment yet
    s.tls_available = True
    assert s.handle("AUTH TLS").replies[0][0] == 234 and s.handle("AUTH TLS").upgrade is True
    assert s.handle("AUTH NONSENSE").replies[0][0] == 504
    s.user = "X"
    s.secure = True
    assert s.handle("AUTH TLS").replies[0][0] == 503


def test_ftp_pbsz_and_prot_need_the_security_environment_first(store):
    from silverlake.net import ftpd
    s = ftpd.FtpSession(store)
    s.handle("USER STUDENT")
    s.handle("PASS STUDENT")
    assert s.handle("PBSZ 0").replies[0][0] == 503 and s.handle("PROT P").replies[0][0] == 503
    s.secure = True
    assert s.handle("PBSZ 0").replies[0][0] == 200 and s.handle("PROT P").replies[0][0] == 200 and s.prot_private
    assert s.handle("PROT C").replies[0][0] == 200 and not s.prot_private
    assert s.handle("PROT X").replies[0][0] == 504
    assert "AUTH TLS" not in s.handle("FEAT").replies[0][1]
    s.tls_available = True
    assert "AUTH TLS" in s.handle("FEAT").replies[0][1]


def test_the_signon_server_answers_over_tls_and_the_mapper_names_that_port(store, tls_dir):
    env = all_ports()
    mapper, tls_port = int(env["SILVERLAKE_MAPPER_PORT"]), int(env["SILVERLAKE_SIGNON_TLS_PORT"])

    def work():
        m = socket.create_connection(("127.0.0.1", mapper), timeout=3)
        m.sendall(b"as-signon-s")
        named = m.recv(10)
        m.close()
        s = certs.client_context().wrap_socket(socket.create_connection(("127.0.0.1", tls_port), timeout=3),
                                               server_hostname="localhost")
        s.sendall(REQUEST)
        out = b""
        while chunk := s.recv(4096):
            out += chunk
        s.close()
        return named, out

    named, out = run_with_services(store, env, work)
    assert struct.unpack(">I", named[1:5])[0] == tls_port
    assert hostsvr.parse_signon_reply(out)["release"] == "V7R4M0"


def test_5250_over_tls_starts_the_normal_negotiation(store, tls_dir):
    env = all_ports()
    port = int(env["SILVERLAKE_TLS_PORT"])

    def work():
        s = certs.client_context().wrap_socket(socket.create_connection(("127.0.0.1", port), timeout=3),
                                               server_hostname="localhost")
        first = s.recv(64)
        s.close()
        return first

    first = run_with_services(store, env, work)
    assert first[:2] == bytes([0xFF, 0xFD])                    # IAC DO, the telnet negotiation opens
