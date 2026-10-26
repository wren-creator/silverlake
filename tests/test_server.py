"""End to end over a real socket, with a bare-bones 5250 client written in the
test. This checks negotiation and the sign-on round trip; the independent
client check lives in test_interop_web3270.py."""

import asyncio

from silverlake.net import server as srv
from silverlake.proto import datastream as ds
from silverlake.proto import ebcdic
from silverlake.proto import telnet as tn
from silverlake.screens.signon import SignonController


class Client:
    def __init__(self, reader, writer, terminal="IBM-3179-2", environ=True, devname=None):
        self.r, self.w = reader, writer
        self.parser = tn.Parser()
        self.terminal, self.environ, self.devname = terminal, environ, devname
        self.records: list[bytes] = []

    async def pump(self, until, timeout=3.0):
        async def loop():
            while not until():
                chunk = await self.r.read(4096)
                if not chunk:
                    return
                for ev in self.parser.feed(chunk):
                    self._react(ev)
        await asyncio.wait_for(loop(), timeout)

    def _react(self, ev):
        if isinstance(ev, tn.Command):
            if ev.verb == tn.DO:
                if ev.opt == tn.OPT_NEWENV and not self.environ:
                    self.w.write(tn.command(tn.WONT, ev.opt))
                else:
                    self.w.write(tn.command(tn.WILL, ev.opt))
            elif ev.verb == tn.WILL:
                self.w.write(tn.command(tn.DO, ev.opt))
        elif isinstance(ev, tn.Subneg):
            d = ev.data
            if d[0] == tn.OPT_TTYPE and d[1] == tn.TTYPE_SEND:
                self.w.write(tn.subneg(bytes([tn.OPT_TTYPE, tn.TTYPE_IS]) + self.terminal.encode()))
            elif d[0] == tn.OPT_NEWENV and d[1] == tn.ENV_SEND:
                body = bytes([tn.OPT_NEWENV, tn.ENV_IS])
                if self.devname:
                    body += bytes([tn.ENV_USERVAR]) + b"DEVNAME" + bytes([tn.ENV_VALUE]) + self.devname.encode()
                self.w.write(tn.subneg(body))
        else:
            self.records.append(ev.data)

    def send_input(self, aid, fields):
        body = bytes([1, 1, aid])
        for row, col, text in fields:
            body += bytes([ds.ORDER_SBA, row + 1, col + 1]) + ebcdic.encode(text)
        self.w.write(tn.record(ds.gds_record(body)))


def run(coro):
    return asyncio.run(coro)


async def with_server(fn, **kw):
    server = await srv.serve("127.0.0.1", 0, SignonController)
    port = server.sockets[0].getsockname()[1]
    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        client = Client(reader, writer, **kw)
        try:
            await fn(client)
        finally:
            writer.close()
    finally:
        server.close()
        await server.wait_closed()


def signon_text(record):
    return ebcdic.decode(record)


def test_negotiates_and_sends_signon_screen():
    async def fn(c):
        await c.pump(lambda: c.records)
        opcode, body = ds.split_gds(c.records[0])
        assert opcode == ds.OPCODE_PUT_GET
        assert body[:2] == bytes([ds.ESC, ds.CMD_CLEAR_UNIT])
        assert body.endswith(bytes([ds.ESC, ds.CMD_READ_MDT_FIELDS, 0, 0]))
        assert "Sign On" in signon_text(body)
        assert "QPADEV0001" in signon_text(body)
    run(with_server(fn))


def test_device_name_from_new_environ_is_used():
    async def fn(c):
        await c.pump(lambda: c.records)
        assert "MYTERM01" in signon_text(c.records[0])
    run(with_server(fn, devname="myterm01"))


def test_client_that_refuses_new_environ_still_gets_a_screen():
    async def fn(c):
        await c.pump(lambda: c.records)
        assert "Sign On" in signon_text(c.records[0])
    run(with_server(fn, environ=False))


def test_enter_round_trip_echoes_user_and_reports_not_wired():
    async def fn(c):
        await c.pump(lambda: c.records)
        c.send_input(0xF1, [(7, 53, "wren01"), (8, 53, "secret")])
        await c.pump(lambda: len(c.records) >= 2)
        text = signon_text(ds.split_gds(c.records[1])[1])
        assert "WREN01" in text
        assert "not wired up" in text
        assert "secret" not in text.lower()  # the password is never drawn back
    run(with_server(fn))


def test_garbage_record_does_not_kill_the_connection():
    async def fn(c):
        await c.pump(lambda: c.records)
        c.w.write(tn.record(b"not a gds record at all"))
        c.send_input(0xF1, [(7, 53, "bob")])
        await c.pump(lambda: len(c.records) >= 2)
        assert "BOB" in signon_text(ds.split_gds(c.records[1])[1])
    run(with_server(fn))


def test_loopback_only_listener_address():
    from silverlake.config import listen_address
    assert listen_address()[0] == "127.0.0.1"
