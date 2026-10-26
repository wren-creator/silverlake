"""Telnet framing for TN5250 (RFC 854, 1091, 1572, 4777).

The parser is a byte-at-a-time state machine, so a command, subnegotiation or
record split across TCP reads comes out the same as one that arrived whole.
"""

from dataclasses import dataclass

IAC, DONT, DO, WONT, WILL, SB, SE = 0xFF, 0xFE, 0xFD, 0xFC, 0xFB, 0xFA, 0xF0
EOR, NOP = 0xEF, 0xF1

OPT_BINARY = 0x00
OPT_TTYPE = 0x18
OPT_EOR = 0x19
OPT_NEWENV = 0x27

# TERMINAL-TYPE (RFC 1091)
TTYPE_IS, TTYPE_SEND = 0, 1

# NEW-ENVIRON (RFC 1572)
ENV_IS, ENV_SEND, ENV_INFO = 0, 1, 2
ENV_VAR, ENV_VALUE, ENV_ESC, ENV_USERVAR = 0, 1, 2, 3


@dataclass(frozen=True)
class Command:
    verb: int  # DO, DONT, WILL, WONT
    opt: int


@dataclass(frozen=True)
class Subneg:
    data: bytes  # option byte first, IAC IAC already collapsed


@dataclass(frozen=True)
class Record:
    data: bytes  # one 5250 record, IAC IAC already collapsed


def escape(data: bytes) -> bytes:
    return data.replace(b"\xff", b"\xff\xff")


def command(verb: int, opt: int) -> bytes:
    return bytes([IAC, verb, opt])


def subneg(data: bytes) -> bytes:
    return bytes([IAC, SB]) + escape(data) + bytes([IAC, SE])


def record(data: bytes) -> bytes:
    return escape(data) + bytes([IAC, EOR])


_DATA, _IAC, _VERB, _SB, _SB_IAC = range(5)


class Parser:
    def __init__(self) -> None:
        self._state = _DATA
        self._verb = 0
        self._rec = bytearray()
        self._sb = bytearray()

    def feed(self, chunk: bytes) -> list:
        out: list = []
        for b in chunk:
            st = self._state
            if st == _DATA:
                if b == IAC:
                    self._state = _IAC
                else:
                    self._rec.append(b)
            elif st == _IAC:
                if b == IAC:
                    self._rec.append(IAC)
                    self._state = _DATA
                elif b == EOR:
                    if self._rec:
                        out.append(Record(bytes(self._rec)))
                    self._rec.clear()
                    self._state = _DATA
                elif b in (DO, DONT, WILL, WONT):
                    self._verb = b
                    self._state = _VERB
                elif b == SB:
                    self._sb.clear()
                    self._state = _SB
                else:  # NOP and anything we do not act on
                    self._state = _DATA
            elif st == _VERB:
                out.append(Command(self._verb, b))
                self._state = _DATA
            elif st == _SB:
                if b == IAC:
                    self._state = _SB_IAC
                else:
                    self._sb.append(b)
            else:  # _SB_IAC
                if b == SE:
                    out.append(Subneg(bytes(self._sb)))
                    self._state = _DATA
                elif b == IAC:
                    self._sb.append(IAC)
                    self._state = _SB
                else:  # malformed, drop the subnegotiation
                    self._state = _DATA
        return out


def parse_environ(payload: bytes) -> dict[str, str]:
    """Decode the variable list of a NEW-ENVIRON IS or INFO (after the
    option and IS bytes). VAR and USERVAR are treated alike, since IBM sends
    DEVNAME and friends as USERVARs and USER as a VAR."""
    result: dict[str, str] = {}
    name = bytearray()
    value = bytearray()
    cur: bytearray | None = None  # the buffer being filled
    have_name = False

    def flush() -> None:
        nonlocal name, value, have_name
        if have_name:
            result[name.decode("ascii", "replace")] = value.decode("ascii", "replace")
        name, value, have_name = bytearray(), bytearray(), False

    i = 0
    while i < len(payload):
        b = payload[i]
        if b in (ENV_VAR, ENV_USERVAR):
            flush()
            have_name = True
            cur = name
        elif b == ENV_VALUE:
            cur = value
        elif b == ENV_ESC:
            i += 1
            if cur is not None and i < len(payload):
                cur.append(payload[i])
        elif cur is not None:
            cur.append(b)
        i += 1
    flush()
    return result
