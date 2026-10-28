"""Lesson ftp-console-cleartext (require TLS for FTP and the console), and the TLS 1.3 only option."""

import socket
import ssl
from base64 import b64encode

import pytest

from netutil import all_ports, needs_openssl, tls_dir  # noqa: F401  (tls_dir is a fixture)
from silverlake import flags, scenarios
from silverlake.net import certs, ftpd, httpadmin
from silverlake.net.httpadmin import Request, State
from silverlake.system import profiles
from test_tls import run_with_services

REG = scenarios.registry()
LESSON = REG["ftp-console-cleartext"]


@pytest.fixture
def store():
    return profiles.load()


def basic(user="STUDENT"):
    return {"authorization": "Basic " + b64encode(f"{user}:{user}".encode()).decode()}


def test_the_range_starts_with_clear_text_sign_on_taken_by_ftp_and_the_console(store):
    assert store.system.require_tls == "no"
    s = ftpd.FtpSession(store)
    assert s.handle("USER STUDENT").replies[0][0] == 331 and s.handle("PASS STUDENT").replies[0][0] == 230
    assert httpadmin.handle(Request("GET", "/HTTPAdmin", basic()), store, State(), secure=False).status == 200


def test_requiring_tls_stops_the_password_before_it_is_sent(store):
    scenarios.apply(store, LESSON, "secure")
    assert store.system.require_tls == "yes"
    s = ftpd.FtpSession(store)
    refused = s.handle("USER STUDENT")
    assert refused.replies[0][0] == 534 and "AUTH TLS" in refused.replies[0][1]
    assert s.handle("PASS STUDENT").replies[0][0] == 503, "no USER was accepted, so there is nothing to answer"
    s.secure = True                                         # after AUTH TLS, or on the implicit port
    assert s.handle("USER STUDENT").replies[0][0] == 331 and s.handle("PASS STUDENT").replies[0][0] == 230

    plain = httpadmin.handle(Request("GET", "/HTTPAdmin", basic()), store, State(), secure=False)
    assert plain.status == 403 and "WWW-Authenticate" not in plain.headers
    assert httpadmin.handle(Request("GET", "/HTTPAdmin", basic()), store, State(), secure=True).status == 200


def test_bad_attempts_on_a_clear_connection_do_not_count_once_tls_is_required(store):
    scenarios.apply(store, LESSON, "secure")
    for _ in range(store.system.qmaxsign + 1):
        httpadmin.handle(Request("GET", "/HTTPAdmin", {"authorization": "Basic " + b64encode(b"OPERATOR:nope").decode()}),
                         store, State(), secure=False)
    assert store.profiles["OPERATOR"].status == "*ENABLED"


def test_the_answer_is_a_fact_that_follows_the_state(store):
    assert LESSON.flag["kind"] == "fact"
    assert flags.FACTS["cleartext_signon_services"](store) == "ftp,httpadmin"
    assert flags.score(store, {LESSON.id: "ftp,httpadmin"}, REG)[0:0] == []
    row = lambda sub: [r for r in flags.score(store, sub, REG) if r[0] == LESSON.id][0]
    assert row({LESSON.id: "ftp,httpadmin"})[1] and not row({LESSON.id: "none"})[1] and not row({})[1]
    scenarios.apply(store, LESSON, "secure")
    assert row({LESSON.id: "none"})[1] and not row({LESSON.id: "ftp,httpadmin"})[1]


def test_a_saved_state_keeps_the_setting_and_an_older_one_defaults_to_no(store):
    from silverlake.system import state
    scenarios.apply(store, LESSON, "secure")
    assert state.from_dict(state.to_dict(store)).system.require_tls == "yes"
    old = state.to_dict(profiles.load())
    del old["system"]["require_tls"]
    assert state.from_dict(old).system.require_tls == "no"


@needs_openssl
def test_on_the_wire_the_clear_console_port_refuses_and_the_tls_port_serves(store, tls_dir):
    scenarios.apply(store, LESSON, "secure")
    env = all_ports()
    plain, secure = int(env["SILVERLAKE_HTTPADMIN_PORT"]), int(env["SILVERLAKE_HTTPADMIN_TLS_PORT"])
    cred = b64encode(b"STUDENT:STUDENT").decode()

    def talk(port, tls):
        s = socket.create_connection(("127.0.0.1", port), timeout=3)
        if tls:
            s = certs.client_context().wrap_socket(s, server_hostname="localhost")
        s.sendall(f"GET /HTTPAdmin HTTP/1.0\r\nAuthorization: Basic {cred}\r\n\r\n".encode())
        out = b""
        while chunk := s.recv(4096):
            out += chunk
        s.close()
        return out

    clear, protected = run_with_services(store, env, lambda: (talk(plain, False), talk(secure, True)))
    assert clear.startswith(b"HTTP/1.0 403") and b"WWW-Authenticate" not in clear
    assert protected.startswith(b"HTTP/1.0 200")


def test_the_minimum_tls_version_is_1_2_unless_told_1_3_and_a_typo_is_an_error():
    assert certs.minimum_version({}) == ssl.TLSVersion.TLSv1_2
    assert certs.minimum_version({"SILVERLAKE_TLS_MIN": "1.3"}) == ssl.TLSVersion.TLSv1_3
    for bad in ("1.1", "tls1.3", "1"):
        with pytest.raises(ValueError):
            certs.minimum_version({"SILVERLAKE_TLS_MIN": bad})


@needs_openssl
def test_tls_1_3_only_refuses_a_client_that_stops_at_1_2(store, tls_dir, monkeypatch):
    monkeypatch.setenv("SILVERLAKE_TLS_MIN", "1.3")
    env = all_ports()
    port = int(env["SILVERLAKE_HTTPADMIN_TLS_PORT"])

    def attempt(maximum):
        ctx = certs.client_context()
        ctx.maximum_version = maximum
        try:
            with ctx.wrap_socket(socket.create_connection(("127.0.0.1", port), timeout=3), server_hostname="localhost") as s:
                return s.version()
        except (ssl.SSLError, OSError):
            return None

    assert run_with_services(store, env, lambda: (attempt(ssl.TLSVersion.TLSv1_2), attempt(ssl.TLSVersion.TLSv1_3))) \
        == (None, "TLSv1.3")
