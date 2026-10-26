"""A small 5250 client for capturing screens from a host, real or simulated."""

import asyncio
from dataclasses import dataclass, field

from ..proto import datastream as ds
from ..proto import ebcdic
from ..proto import telnet as tn
from .terminal import DecodeError, Terminal

TERMINAL_TYPE = "IBM-3179-2"
AID_BYTES = {name: code for code, name in ds.AIDS.items()}

# Query reply: cursor 0,0, AID 0x88 (inbound WSF), then one 58 byte structured
# field describing a 3179-2 display. Layout per the 5494 functions reference.
_QUERY_REPLY = bytes([0x00, 0x00, 0x88]) + (
    bytes([0x00, 0x3A, 0xD9, 0x70, 0x80, 0x06, 0x00, 0x01, 0x01, 0x00])
    + bytes(16)
    + bytes([0x01]) + ebcdic.encode("3179") + ebcdic.encode("002")
    + bytes([0x02, 0x00, 0x00]) + bytes(4) + bytes([0x00, 0x40]) + bytes(2)
    + bytes([0x23, 0x31, 0x00, 0x00]) + bytes(9)
)


class CaptureError(RuntimeError):
    pass


@dataclass
class Capture:
    """Everything one screen wait produced."""
    snapshot: dict
    records: list[bytes] = field(default_factory=list)  # raw host records since the last wait
    error_line: str = ""


class Client:
    def __init__(self, host: str, port: int, devname: str | None = None) -> None:
        self.host, self.port, self.devname = host, port, devname
        self.term = Terminal()
        self.parser = tn.Parser()
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._they: set[int] = set()
        self._we: set[int] = set()
        self._records: list[bytes] = []
        self._got_read = False

    async def connect(self, timeout: float = 10.0) -> None:
        self._reader, self._writer = await asyncio.wait_for(
            asyncio.open_connection(self.host, self.port), timeout)

    async def close(self) -> None:
        if self._writer:
            self._writer.close()
            try:
                await self._writer.wait_closed()
            except (ConnectionError, OSError):
                pass

    # -- negotiation -----------------------------------------------------------

    def _write(self, data: bytes) -> None:
        assert self._writer is not None
        self._writer.write(data)

    def _on_command(self, c: tn.Command) -> None:
        if c.verb == tn.DO:
            if c.opt in (tn.OPT_TTYPE, tn.OPT_NEWENV):
                self._write(tn.command(tn.WILL, c.opt))
            elif c.opt in (tn.OPT_BINARY, tn.OPT_EOR):
                if c.opt not in self._we:
                    self._we.add(c.opt)
                    self._write(tn.command(tn.WILL, c.opt))
            else:
                self._write(tn.command(tn.WONT, c.opt))
        elif c.verb == tn.WILL:
            if c.opt in (tn.OPT_BINARY, tn.OPT_EOR):
                if c.opt not in self._they:
                    self._they.add(c.opt)
                    self._write(tn.command(tn.DO, c.opt))
            else:
                self._write(tn.command(tn.DONT, c.opt))

    def _on_subneg(self, s: tn.Subneg) -> None:
        d = s.data
        if len(d) < 2 or d[1] != tn.TTYPE_SEND:
            return
        if d[0] == tn.OPT_TTYPE:
            self._write(tn.subneg(bytes([tn.OPT_TTYPE, tn.TTYPE_IS]) + TERMINAL_TYPE.encode()))
        elif d[0] == tn.OPT_NEWENV:
            body = bytearray([tn.OPT_NEWENV, tn.ENV_IS])

            def uservar(name: str, value: str) -> None:
                body.extend([tn.ENV_USERVAR, *name.encode(), tn.ENV_VALUE, *value.encode()])

            if self.devname:
                uservar("DEVNAME", self.devname)
            uservar("CODEPAGE", "037")
            uservar("CHARSET", "697")
            uservar("KBDTYPE", "USB")
            self._write(tn.subneg(bytes(body)))

    # -- screens ---------------------------------------------------------------

    def _on_record(self, data: bytes) -> None:
        self._records.append(data)
        try:
            _, body = ds.split_gds(data)
            events = self.term.apply(body)
        except (ds.ProtocolError, DecodeError, IndexError) as exc:
            raise CaptureError(f"could not decode host record: {exc}") from exc
        for ev in events:
            if ev.kind == "query":
                self._write(tn.record(ds.gds_record(_QUERY_REPLY)))
            elif ev.kind == "read":
                self._got_read = True
            elif ev.kind == "unsupported":
                raise CaptureError(f"host sent something this client does not decode: {ev.detail}")

    async def wait_screen(self, timeout: float = 10.0) -> Capture:
        """Read until the host issues a Read command, i.e. the screen is ready
        for input, and return what is on it."""
        assert self._reader is not None
        self._got_read = False
        self._records = []

        async def loop() -> None:
            while not self._got_read:
                chunk = await self._reader.read(4096)
                if not chunk:
                    raise CaptureError("host closed the connection before the screen was ready")
                for ev in self.parser.feed(chunk):
                    if isinstance(ev, tn.Command):
                        self._on_command(ev)
                    elif isinstance(ev, tn.Subneg):
                        self._on_subneg(ev)
                    else:
                        self._on_record(ev.data)
                await self._writer.drain()

        try:
            await asyncio.wait_for(loop(), timeout)
        except TimeoutError as exc:
            raise CaptureError(f"no screen within {timeout:.0f}s") from exc
        return Capture(self.term.snapshot(), list(self._records), self.term.error_line)

    # -- input -----------------------------------------------------------------

    def send_aid(self, key: str, fill: dict[int, str] | None = None) -> None:
        """Press a key. `fill` maps an input field's index (screen order) to
        the text typed into it."""
        code = AID_BYTES.get(key.upper())
        if code is None:
            raise CaptureError(f"unknown key {key!r}")
        fields = self.term.input_fields()
        cursor = self.term.snapshot()["cursor"] or [0, 0]
        body = bytearray([cursor[0] + 1, cursor[1] + 1, code])
        for idx, text in sorted((fill or {}).items()):
            if idx >= len(fields):
                raise CaptureError(f"no input field #{idx}, screen has {len(fields)}")
            f = fields[idx]
            text = text[: f["length"]]
            body += bytes([ds.ORDER_SBA, f["row"] + 1, f["col"] + 1]) + ebcdic.encode(text)
        self._write(tn.record(ds.gds_record(bytes(body))))
