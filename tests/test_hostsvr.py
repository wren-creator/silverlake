"""The server mapper and the sign-on server: what a client sees before it has signed on."""

import asyncio
import socket
import struct

import pytest

from silverlake import flags, scenarios
from silverlake.net import hostsvr, services
from silverlake.system import profiles
from netutil import all_ports, free_port

REG = scenarios.registry()
REQUEST = bytes(6) + struct.pack(">H", 0xE009) + bytes(10) + struct.pack(">H", 0x7003)


@pytest.fixture
def store():
    return profiles.load()


def test_the_mapper_names_the_signon_port_and_refuses_what_it_does_not_know():
    table = dict(hostsvr.DEFAULT_PORTS)
    assert hostsvr.mapper_reply("as-signon", table) == bytes([0x2B]) + struct.pack(">I", 8476)
    assert hostsvr.mapper_reply("as-signon\r\n", table)[0] == 0x2B
    assert hostsvr.mapper_reply("as-nothing", table) == bytes([0x2D])


def test_the_exchange_reply_carries_release_level_and_password_level(store):
    reply = hostsvr.signon_reply(store)
    assert struct.unpack(">I", reply[:4])[0] == len(reply)
    assert struct.unpack(">H", reply[18:20])[0] == 0xF003
    assert hostsvr.parse_signon_reply(reply) == {"release": "V7R4M0", "datastream_level": 15, "password_level": 0}


def test_the_password_level_on_the_wire_follows_the_system_value(store):
    store.system.qpwdlvl = 3
    assert hostsvr.parse_signon_reply(hostsvr.signon_reply(store))["password_level"] == 3


def test_only_the_exchange_request_gets_an_answer():
    assert hostsvr.is_exchange_request(REQUEST)
    assert not hostsvr.is_exchange_request(b"hello") and not hostsvr.is_exchange_request(bytes(30))


def test_the_job_is_in_the_reply_as_ebcdic(store):
    assert hostsvr._ebcdic("QUSER") in hostsvr.signon_reply(store)
    assert hostsvr._ebcdic("A/1") == bytes([0xC1, 0x61, 0xF1])


def ask(port, raw):
    with socket.create_connection(("127.0.0.1", port), timeout=3) as s:
        s.sendall(raw)
        out = b""
        while chunk := s.recv(4096):
            out += chunk
    return out


def test_over_real_sockets_the_mapper_points_at_the_signon_server_which_answers(store):
    mapper, signon = free_port(), free_port()
    env = all_ports(mapper=mapper, signon=signon)

    async def go():
        servers = await services.start("127.0.0.1", lambda: store, env)
        loop = asyncio.get_running_loop()
        try:
            call = lambda port, raw: loop.run_in_executor(None, ask, port, raw)
            return (await call(mapper, b"as-signon"), await call(signon, REQUEST), await call(signon, b"junk"))
        finally:
            for s in servers:
                s.close()

    named, answer, junk = asyncio.run(go())
    assert struct.unpack(">I", named[1:5])[0] == signon
    assert hostsvr.parse_signon_reply(answer)["release"] == "V7R4M0"
    assert junk == b""


def test_the_fact_flag_is_scored_against_the_state_and_the_fix_changes_the_answer(store):
    rows = lambda sub: dict((r[0], r[1]) for r in flags.score(store, sub, REG))
    assert rows({"hostsvr-recon": "V7R4M0/0"})["hostsvr-recon"]
    assert rows({"hostsvr-recon": "v7r4m0/0"})["hostsvr-recon"]
    assert not rows({"hostsvr-recon": "V7R4M0/3"})["hostsvr-recon"] and not rows({})["hostsvr-recon"]
    scenarios.apply(store, REG["hostsvr-recon"], "secure")
    assert rows({"hostsvr-recon": "V7R4M0/3"})["hostsvr-recon"]


def test_at_level_zero_the_case_of_a_password_does_not_matter_and_at_three_it_does(store):
    assert store.check_signon("STUDENT", "student").profile is not None
    scenarios.apply(store, REG["hostsvr-recon"], "secure")
    assert store.check_signon("STUDENT", "student").profile is None
    assert store.check_signon("STUDENT", "STUDENT").profile is not None
