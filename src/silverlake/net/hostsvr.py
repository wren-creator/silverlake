"""IBM i host servers, the two a scanner finds first: the server mapper (449 on a real system, 4449 here, since
449 is privileged) and the sign-on server (8476). Nothing else is built: there is no database, file, data
queue or remote command server, and the mapper only points at them.

The sign-on server answers one request before anyone has signed on, the exchange of attributes that every
client opens with. The reply carries the OS release, a datastream level, a seed, the password level
(QPWDLVL) and the answering job. The reply shapes follow what a live IBM i 7.5 sent, as captured for the
web3270 mock, so a client that parses real bytes parses these. The values come from the saved state, so
changing QPWDLVL changes what the wire says.

Reading that reply costs nothing and needs no password, which is the lesson: the server tells every caller how
the passwords are checked.

`mapper_reply` and `signon_reply` are pure so the tests need no sockets."""

from __future__ import annotations

import asyncio
import logging
import struct
from collections.abc import Callable

from ..system.profiles import ProfileStore

log = logging.getLogger("silverlake.hostsvr")

OS_LEVEL = "V7R4M0"
ANSWERING_JOB = "135258/QUSER/QZSOSIGN"
EXCHANGE_REQUEST = 0x7003
SIGNON_SERVER_ID = 0xE009
MAPPER_FOUND, MAPPER_UNKNOWN = 0x2B, 0x2D
IDLE = 3.0

# The ports the mapper names. Only the sign-on one has a listener here.
DEFAULT_PORTS = {
    "as-central": 8470, "as-database": 8471, "as-dtaq": 8472, "as-file": 8473,
    "as-netprt": 8474, "as-rmtcmd": 8475, "as-signon": 8476,
}


def mapper_reply(name: str, table: dict[str, int]) -> bytes:
    port = table.get(name.strip())
    if port is None:
        return bytes([MAPPER_UNKNOWN])
    return bytes([MAPPER_FOUND]) + struct.pack(">I", port)


def _ebcdic(text: str) -> bytes:
    """The few CP037 characters a job name needs."""
    out = bytearray()
    for ch in text:
        c = ord(ch)
        if ch == "/":
            out.append(0x61)
        elif "0" <= ch <= "9":
            out.append(0xF0 + c - 0x30)
        elif "A" <= ch <= "I":
            out.append(0xC1 + c - 0x41)
        elif "J" <= ch <= "R":
            out.append(0xD1 + c - 0x4A)
        elif "S" <= ch <= "Z":
            out.append(0xE2 + c - 0x53)
        else:
            out.append(0x6F)
    return bytes(out)


def _field(code_point: int, data: bytes) -> bytes:
    return struct.pack(">IH", 6 + len(data), code_point) + data


def is_exchange_request(data: bytes) -> bool:
    return (len(data) >= 20 and struct.unpack(">H", data[6:8])[0] == SIGNON_SERVER_ID
            and struct.unpack(">H", data[18:20])[0] == EXCHANGE_REQUEST)


def signon_reply(store: ProfileStore) -> bytes:
    v, r, m = (int(x) for x in OS_LEVEL[1:].replace("R", " ").replace("M", " ").split())
    body = b"".join([
        _field(0x1101, struct.pack(">I", (v << 16) | (r << 8) | m)),
        _field(0x1102, struct.pack(">H", 15)),
        _field(0x1103, bytes([1, 2, 3, 4, 5, 6, 7, 8])),
        _field(0x1119, bytes([store.system.qpwdlvl])),
        _field(0x111F, bytes(4) + _ebcdic(ANSWERING_JOB)),
    ])
    head = bytearray(24)
    struct.pack_into(">I", head, 0, 24 + len(body))
    struct.pack_into(">H", head, 6, SIGNON_SERVER_ID)
    struct.pack_into(">H", head, 16, 4)             # template length: the return code
    struct.pack_into(">H", head, 18, 0xF003)        # the reply id a real 7.5 sent
    return bytes(head) + body


def parse_signon_reply(data: bytes) -> dict[str, int | str]:
    """What a client reads from the reply: release, datastream level, password level, answering job."""
    out: dict[str, int | str] = {}
    pos = 24
    while pos + 6 <= len(data):
        length, cp = struct.unpack(">IH", data[pos:pos + 6])
        body = data[pos + 6:pos + length]
        if cp == 0x1101:
            n = struct.unpack(">I", body)[0]
            out["release"] = f"V{n >> 16}R{(n >> 8) & 255}M{n & 255}"
        elif cp == 0x1102:
            out["datastream_level"] = struct.unpack(">H", body)[0]
        elif cp == 0x1119:
            out["password_level"] = body[0]
        pos += max(length, 6)
    return out


async def serve(host: str, mapper_port: int, signon_port: int,
                store_of: Callable[[], ProfileStore], tls_port: int | None = None,
                ssl_context=None) -> list[asyncio.Server]:
    table = dict(DEFAULT_PORTS, **{"as-signon": signon_port})
    if ssl_context is not None and tls_port is not None:
        table["as-signon-s"] = tls_port
        table["as-database-s"] = 9471               # named, nothing listens, as with the plain ones

    async def mapper(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            data = await asyncio.wait_for(reader.read(64), IDLE)
            if data:
                writer.write(mapper_reply(data.decode("ascii", "replace"), table))
                await writer.drain()
        except (asyncio.TimeoutError, ConnectionError):
            pass
        finally:
            writer.close()

    async def signon(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            data = await asyncio.wait_for(reader.read(512), IDLE)
            if is_exchange_request(data):
                writer.write(signon_reply(store_of()))
                await writer.drain()
        except (asyncio.TimeoutError, ConnectionError):
            pass
        finally:
            writer.close()

    servers = [await asyncio.start_server(mapper, host, mapper_port)]
    try:
        servers.append(await asyncio.start_server(signon, host, signon_port))
        if ssl_context is not None and tls_port is not None:
            servers.append(await asyncio.start_server(signon, host, tls_port, ssl=ssl_context))
    except OSError:
        for s in servers:
            s.close()
        raise
    return servers
