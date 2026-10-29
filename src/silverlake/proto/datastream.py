"""The 5250 data stream: GDS record framing, commands, orders, AID keys, and
the decoder for what a terminal sends back.

Byte values follow the public tn5250 project and the RFCs (1205, 2877, 4777),
and are checked against real captures in Phase 2.
"""

from dataclasses import dataclass, field

from . import ebcdic

ESC = 0x04

# Commands (follow ESC)
CMD_CLEAR_UNIT = 0x40
CMD_WRITE_TO_DISPLAY = 0x11
CMD_READ_MDT_FIELDS = 0x52

# Orders (inside Write To Display)
ORDER_SOH = 0x01
ORDER_RA = 0x02
ORDER_SBA = 0x11
ORDER_IC = 0x13
ORDER_SF = 0x1D

# Field attribute bytes. Always 001xxxxx, and each one occupies a screen cell.
ATTR_GREEN = 0x20
ATTR_WHITE = 0x22
ATTR_GREEN_UNDERLINE = 0x24
ATTR_REVERSE_UNDERLINE = 0x25   # a parameter the prompt refused: reverse image
ATTR_WHITE_UNDERLINE = 0x26      # a required parameter on a prompt
ATTR_NONDISPLAY = 0x27
ATTR_RED = 0x28
ATTR_TURQUOISE = 0x30
ATTR_YELLOW = 0x32
ATTR_PINK = 0x38
ATTR_BLUE = 0x3A

# Field Format Word, first byte is always 01xxxxxx. Alphabetic shift, no flags.
FFW_ALPHA = (0x40, 0x00)
# Second FFW byte: bit 0x20 is monocase, the terminal upper-cases what is typed.
# A real IBM i sets it on the sign-on user field (seen in a PUB400 capture) and not
# on the password field.
FFW2_MONOCASE = 0x20

GDS_TYPE = (0x12, 0xA0)
OPCODE_PUT_GET = 0x03
OPCODE_NO_OP = 0x00

# Write To Display control characters. CC2 0x18 is what a real IBM i sends on
# a fresh screen (keyboard unlocked); verified against the PUB400 capture.
CC1_NONE = 0x00
CC2_UNLOCK = 0x18

AIDS = {
    0xF1: "ENTER", 0xF3: "HELP", 0xF4: "ROLLDOWN", 0xF5: "ROLLUP",
    0xF6: "PRINT", 0xF8: "RECORD_BACKSPACE", 0xBD: "CLEAR",
    0x6C: "PA1", 0x6E: "PA2", 0x6B: "PA3",
    **{0x30 + n: f"F{n}" for n in range(1, 13)},
    **{0xB0 + n - 12: f"F{n}" for n in range(13, 25)},
}


class ProtocolError(ValueError):
    pass


def gds_record(data: bytes, opcode: int = OPCODE_PUT_GET) -> bytes:
    """Wrap a data stream in the 10 byte GDS header. The length covers the
    header itself."""
    total = len(data) + 10
    return bytes([total >> 8, total & 0xFF, *GDS_TYPE, 0x00, 0x00, 0x04, 0x00, 0x00, opcode]) + data


def split_gds(record: bytes) -> tuple[int, bytes]:
    """Return (opcode, body) for a client record, or raise ProtocolError."""
    if len(record) < 10 or tuple(record[2:4]) != GDS_TYPE:
        raise ProtocolError("missing or invalid GDS header")
    declared = (record[0] << 8) | record[1]
    if declared != len(record):
        raise ProtocolError(f"GDS length {declared} does not match record length {len(record)}")
    return record[9], record[10:]


def address(row: int, col: int) -> bytes:
    """SBA/IC operand. Rows and columns are 0-based here, 1-based on the wire."""
    if not (0 <= row < 255 and 0 <= col < 255):
        raise ValueError(f"screen address out of range: {row},{col}")
    return bytes([row + 1, col + 1])


@dataclass
class FieldData:
    row: int  # 0-based start of the field's data
    col: int
    text: str


@dataclass
class InputRecord:
    cursor_row: int
    cursor_col: int
    aid: int
    fields: list[FieldData] = field(default_factory=list)

    @property
    def aid_name(self) -> str:
        return AIDS.get(self.aid, f"0x{self.aid:02X}")


def parse_input(body: bytes) -> InputRecord:
    """Decode a terminal's reply to a Read command: cursor row, cursor col,
    AID, then SBA-addressed field data."""
    if len(body) < 3:
        raise ProtocolError("input record too short")
    rec = InputRecord(body[0] - 1, body[1] - 1, body[2])
    cur: FieldData | None = None
    buf = bytearray()

    def close() -> None:
        if cur is not None:
            cur.text = ebcdic.decode(bytes(buf).replace(b"\x00", b"")).rstrip()
            rec.fields.append(cur)

    i = 3
    while i < len(body):
        if body[i] == ORDER_SBA:
            if i + 2 >= len(body):
                raise ProtocolError("truncated SBA")
            close()
            buf.clear()
            cur = FieldData(body[i + 1] - 1, body[i + 2] - 1, "")
            i += 3
        else:
            if cur is not None:
                buf.append(body[i])
            i += 1
    close()
    return rec
