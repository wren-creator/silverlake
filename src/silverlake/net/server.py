"""The 5250 listener. One Connection per client: negotiate (RFC 4777), send a
screen, read the reply, repeat."""

import asyncio
import logging
from collections.abc import Callable

from ..proto import datastream as ds
from ..proto import telnet as tn
from ..screens.model import Screen
from ..screens.render import render
from ..screens.signon import SignonController

log = logging.getLogger("silverlake.net")

NEGOTIATION_TIMEOUT = 10.0
NEWENV_GRACE = 2.0  # how long to wait for NEW-ENVIRON before starting without it
MAX_CONNECTIONS = 20

# We ask the client for all of these, and offer these two ourselves.
ASK_DO = (tn.OPT_TTYPE, tn.OPT_NEWENV, tn.OPT_BINARY, tn.OPT_EOR)
OFFER_WILL = (tn.OPT_BINARY, tn.OPT_EOR)


class Controller:
    """What a connection needs from the system layer."""

    def first(self) -> Screen: ...
    def handle(self, aid: str, values: dict[str, str]) -> Screen: ...
    def close(self) -> None: ...


ControllerFactory = Callable[[str], Controller]


class Connection:
    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter,
                 make_controller: ControllerFactory, serial: int) -> None:
        self.reader, self.writer = reader, writer
        self.make_controller = make_controller
        self.serial = serial
        self.peer = writer.get_extra_info("peername")
        self.parser = tn.Parser()
        self.they_will: set[int] = set()   # options the client agreed to do
        self.we_will: set[int] = set()     # options the client asked us to do
        self.refused: set[int] = set()
        self.terminal_type = ""
        self.environ: dict[str, str] = {}
        self.got_environ = False
        self.controller: Controller | None = None
        self.screen: Screen | None = None
        self.started = False
        self.display = f"QPADEV{serial:04d}"

    # -- output ------------------------------------------------------------

    def _send(self, data: bytes) -> None:
        self.writer.write(data)

    def _send_screen(self, screen: Screen) -> None:
        self.screen = screen
        self._send(tn.record(ds.gds_record(render(screen))))

    # -- negotiation ---------------------------------------------------------

    def _open(self) -> None:
        for opt in ASK_DO:
            self._send(tn.command(tn.DO, opt))
        for opt in OFFER_WILL:
            self._send(tn.command(tn.WILL, opt))

    def _on_command(self, c: tn.Command) -> None:
        if c.verb == tn.WILL:
            if c.opt in ASK_DO:
                self.they_will.add(c.opt)
                if c.opt == tn.OPT_TTYPE:
                    self._send(tn.subneg(bytes([tn.OPT_TTYPE, tn.TTYPE_SEND])))
                elif c.opt == tn.OPT_NEWENV:
                    self._send(tn.subneg(bytes([tn.OPT_NEWENV, tn.ENV_SEND])))
            else:
                self._send(tn.command(tn.DONT, c.opt))
        elif c.verb == tn.WONT:
            self.refused.add(c.opt)
        elif c.verb == tn.DO:
            if c.opt in OFFER_WILL:
                self.we_will.add(c.opt)
            else:
                self._send(tn.command(tn.WONT, c.opt))

    def _on_subneg(self, s: tn.Subneg) -> None:
        d = s.data
        if len(d) >= 2 and d[0] == tn.OPT_TTYPE and d[1] == tn.TTYPE_IS:
            self.terminal_type = d[2:].decode("ascii", "replace")
        elif len(d) >= 2 and d[0] == tn.OPT_NEWENV and d[1] in (tn.ENV_IS, tn.ENV_INFO):
            self.environ.update(tn.parse_environ(d[2:]))
            self.got_environ = True

    def _ready(self, newenv_waived: bool) -> bool:
        if not self.terminal_type:
            return False
        if not {tn.OPT_BINARY, tn.OPT_EOR} <= self.they_will:
            return False
        if not {tn.OPT_BINARY, tn.OPT_EOR} <= self.we_will:
            return False
        return self.got_environ or tn.OPT_NEWENV in self.refused or newenv_waived

    def _maybe_start(self, newenv_waived: bool = False) -> None:
        if self.started or not self._ready(newenv_waived):
            return
        self.started = True
        devname = self.environ.get("DEVNAME", "").strip().upper()
        if devname:
            self.display = devname[:10]
        log.info("[%d] %s up: type=%s display=%s env=%s", self.serial, self.peer,
                 self.terminal_type, self.display, sorted(self.environ))
        self.controller = self.make_controller(self.display)
        self._send_screen(self.controller.first())

    # -- input ---------------------------------------------------------------

    def _on_record(self, data: bytes) -> None:
        if not self.started or self.controller is None or self.screen is None:
            log.debug("[%d] record before start, ignored", self.serial)
            return
        try:
            opcode, body = ds.split_gds(data)
        except ds.ProtocolError as exc:
            log.warning("[%d] bad record: %s", self.serial, exc)
            return
        if opcode != ds.OPCODE_PUT_GET:
            log.debug("[%d] opcode 0x%02X ignored", self.serial, opcode)
            return
        try:
            inp = ds.parse_input(body)
        except ds.ProtocolError as exc:
            log.warning("[%d] bad input record: %s", self.serial, exc)
            return
        by_pos = {(i.row, i.col): i.name for i in self.screen.inputs()}
        values = {by_pos[(f.row, f.col)]: f.text for f in inp.fields if (f.row, f.col) in by_pos}
        log.info("[%d] AID=%s fields=%s", self.serial, inp.aid_name, sorted(values))
        self._send_screen(self.controller.handle(inp.aid_name, values))

    # -- main loop -----------------------------------------------------------

    async def run(self) -> None:
        log.info("[%d] connect from %s", self.serial, self.peer)
        self._open()
        loop = asyncio.get_running_loop()
        deadline = loop.time() + NEGOTIATION_TIMEOUT
        grace_at: float | None = None  # when to stop waiting for NEW-ENVIRON
        grace_used = False
        try:
            while True:
                timeout = None
                if not self.started:
                    wake = deadline if grace_at is None else min(deadline, grace_at)
                    timeout = max(wake - loop.time(), 0)
                try:
                    chunk = await asyncio.wait_for(self.reader.read(4096), timeout)
                except TimeoutError:
                    now = loop.time()
                    if grace_at is not None and now >= grace_at:
                        grace_at, grace_used = None, True
                        self._maybe_start(newenv_waived=True)
                    if not self.started and now >= deadline:
                        log.warning("[%d] negotiation timed out", self.serial)
                        return
                    continue
                if not chunk:
                    return
                for ev in self.parser.feed(chunk):
                    if isinstance(ev, tn.Command):
                        self._on_command(ev)
                    elif isinstance(ev, tn.Subneg):
                        self._on_subneg(ev)
                    else:
                        self._on_record(ev.data)
                self._maybe_start()
                if not self.started and self.terminal_type and grace_at is None and not grace_used:
                    grace_at = loop.time() + NEWENV_GRACE
                await self.writer.drain()
        except (ConnectionError, asyncio.IncompleteReadError):
            pass
        except Exception:
            # A bug in a screen or a controller costs this one session, loudly,
            # and nothing else.
            log.exception("[%d] session failed", self.serial)
        finally:
            log.info("[%d] disconnect", self.serial)
            if self.controller is not None:
                try:
                    self.controller.close()
                except Exception:
                    log.exception("[%d] controller close failed", self.serial)
            self.writer.close()


async def serve(host: str, port: int, make_controller: ControllerFactory = SignonController,
                ssl_context=None) -> asyncio.Server:
    counter = 0
    active = 0

    async def on_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        nonlocal counter, active
        if active >= MAX_CONNECTIONS:
            writer.close()
            return
        counter += 1
        active += 1
        try:
            await Connection(reader, writer, make_controller, counter).run()
        finally:
            active -= 1

    return await asyncio.start_server(on_client, host, port, ssl=ssl_context)
