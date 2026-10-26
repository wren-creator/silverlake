"""A terminal's view of the host data stream: apply Write To Display records to
a cell buffer, then reduce the result to a structural snapshot.

This is the decoder half. Silverlake's renderer is the encoder half, so a
Silverlake screen can be run through here and compared with a capture from a
real system."""

import re
from dataclasses import dataclass, field

from ..proto import datastream as ds
from ..proto import ebcdic

# Commands beyond the ones Silverlake sends
CMD_CLEAR_UNIT_ALT = 0x20
CMD_WRITE_ERROR_CODE = 0x21
CMD_CLEAR_FORMAT_TABLE = 0x50
CMD_READ_INPUT_FIELDS = 0x42
CMD_READ_IMMEDIATE = 0x72
CMD_READ_MDT_ALT = 0x82
CMD_SAVE_SCREEN = 0x02
CMD_RESTORE_SCREEN = 0x12
CMD_WSF = 0xF3

READ_COMMANDS = {ds.CMD_READ_MDT_FIELDS, CMD_READ_INPUT_FIELDS, CMD_READ_IMMEDIATE, CMD_READ_MDT_ALT}

ORDER_TD = 0x10
ORDER_EA = 0x03
ORDER_WEA = 0x12
ORDER_MC = 0x14
ORDER_WDSF = 0x15

FFW_BYPASS = 0x2000
FFW_MDT = 0x0800
FFW_SHIFT_MASK = 0x0700
FFW_MONOCASE = 0x0020

MESSAGE_ID = re.compile(r"\b(?:CPF|CPD|CPA|CPC|CPE|CPI|MCH|SQL|GUI|RPG)[0-9A-F]{4}\b")


def is_attr(b: int) -> bool:
    return (b & 0xE0) == 0x20


class DecodeError(ValueError):
    pass


@dataclass
class Cell:
    char: int = 0x00
    attr: int | None = None       # set on the attribute cell that starts a field or run
    ffw: int | None = None        # set when the attribute came from a Start Of Field with an FFW
    length: int | None = None     # input field length, on the attribute cell


@dataclass
class Event:
    kind: str                     # "read", "query", "unsupported"
    detail: str = ""


@dataclass
class Terminal:
    rows: int = 24
    cols: int = 80
    cells: list[Cell] = field(default_factory=list)
    cursor: int | None = None     # set by IC; None means "home to first input"
    read_command: int | None = None
    error_line: str = ""

    def __post_init__(self) -> None:
        if not self.cells:
            self.clear()

    def clear(self, rows: int | None = None, cols: int | None = None) -> None:
        if rows:
            self.rows, self.cols = rows, cols or self.cols
        self.cells = [Cell() for _ in range(self.rows * self.cols)]
        self.cursor = None

    # -- decoding ------------------------------------------------------------

    def apply(self, body: bytes) -> list[Event]:
        """Apply one record body (GDS header already removed)."""
        events: list[Event] = []
        i = 0
        while i < len(body):
            if body[i] != ds.ESC:
                raise DecodeError(f"expected ESC at {i}, found 0x{body[i]:02X}")
            if i + 1 >= len(body):
                raise DecodeError("ESC at end of record")
            cmd = body[i + 1]
            i += 2
            if cmd == ds.CMD_CLEAR_UNIT:
                self.clear(24, 80)
            elif cmd == CMD_CLEAR_UNIT_ALT:
                self.clear(27, 132)
                i += 1  # one filler byte
            elif cmd == CMD_CLEAR_FORMAT_TABLE:
                pass
            elif cmd == ds.CMD_WRITE_TO_DISPLAY:
                i = self._write_to_display(body, i)
            elif cmd == CMD_WRITE_ERROR_CODE:
                i = self._write_error_code(body, i)
            elif cmd in READ_COMMANDS:
                self.read_command = cmd
                i += 2  # CC1, CC2
                events.append(Event("read", f"0x{cmd:02X}"))
            elif cmd == CMD_WSF:
                i = self._write_structured_field(body, i, events)
            else:
                events.append(Event("unsupported", f"command 0x{cmd:02X}"))
                break  # cannot know where the next command starts
        return events

    def _addr(self, row1: int, col1: int) -> int:
        row, col = row1 - 1, col1 - 1
        if not (0 <= row < self.rows and 0 <= col < self.cols):
            raise DecodeError(f"address {row1},{col1} off a {self.rows}x{self.cols} screen")
        return row * self.cols + col

    def _write_to_display(self, b: bytes, i: int) -> int:
        i += 2  # CC1, CC2
        pos = 0
        total = len(self.cells)

        def put(cell: Cell) -> None:
            nonlocal pos
            if pos < total:
                self.cells[pos] = cell
                pos += 1

        while i < len(b):
            x = b[i]
            if x == ds.ESC:
                break
            if x == ds.ORDER_SOH:
                i += 1 + b[i + 1]
            elif x == ds.ORDER_SBA:
                pos = self._addr(b[i + 1], b[i + 2])
                i += 3
            elif x == ds.ORDER_IC:
                self.cursor = self._addr(b[i + 1], b[i + 2])
                i += 3
            elif x == ds.ORDER_RA:
                end = self._addr(b[i + 1], b[i + 2])
                ch = b[i + 3]
                i += 4
                while pos <= end:
                    put(Cell(char=ch))
            elif x == ORDER_EA:
                end = self._addr(b[i + 1], b[i + 2])
                attr_count = b[i + 3]  # length byte, then that many attribute types
                i += 3 + attr_count
                while pos <= end:
                    put(Cell())
            elif x == ORDER_TD:
                n = (b[i + 1] << 8) | b[i + 2]
                for ch in b[i + 3:i + 1 + n]:
                    put(Cell(char=ch))
                i += 1 + n
            elif x == ORDER_MC:
                self.cursor = self._addr(b[i + 1], b[i + 2])
                i += 3
            elif x == ORDER_WEA:
                i += 3
            elif x == ORDER_WDSF:
                n = (b[i + 1] << 8) | b[i + 2]
                i += 1 + n
            elif x == ds.ORDER_SF:
                i = self._start_of_field(b, i + 1, put)
            elif is_attr(x):
                # A real host can write a field's attribute cell again as a bare
                # attribute after its Start Of Field. That refreshes the
                # attribute and must not erase the field definition.
                here = self.cells[pos] if pos < total else None
                if here is not None and here.ffw is not None:
                    here.attr = x
                    pos += 1
                else:
                    put(Cell(attr=x))
                i += 1
            elif x < 0x40:
                put(Cell())  # an unhandled control byte occupies a cell as nothing
                i += 1
            else:
                put(Cell(char=x))
                i += 1
        return i

    def _start_of_field(self, b: bytes, i: int, put) -> int:
        ffw = None
        if not is_attr(b[i]):
            ffw = (b[i] << 8) | b[i + 1]
            i += 2
            while i < len(b) and not is_attr(b[i]):
                i += 2  # field control words
        attr = b[i]
        i += 1
        length = None
        if ffw is not None:
            length = (b[i] << 8) | b[i + 1]
            i += 2
        put(Cell(attr=attr, ffw=ffw, length=length))
        return i

    def _write_error_code(self, b: bytes, i: int) -> int:
        start = i
        while i < len(b) and b[i] != ds.ESC:
            i += 1
        self.error_line = ebcdic.decode(bytes(c for c in b[start:i] if c >= 0x40)).strip()
        return i

    def _write_structured_field(self, b: bytes, i: int, events: list[Event]) -> int:
        while i + 4 <= len(b) and b[i] != ds.ESC:
            n = (b[i] << 8) | b[i + 1]
            cls, typ = b[i + 2], b[i + 3]
            if (cls, typ) == (0xD9, 0x70):
                events.append(Event("query"))
            else:
                events.append(Event("unsupported", f"structured field 0x{cls:02X}/0x{typ:02X}"))
            if n < 4:
                break
            i += n
        return i

    # -- reduction -------------------------------------------------------------

    def input_fields(self) -> list[dict]:
        """Input fields in screen order. `row`/`col` are the first data cell."""
        out = []
        for addr, c in enumerate(self.cells):
            if c.attr is None or c.ffw is None or c.ffw & FFW_BYPASS:
                continue
            data = addr + 1
            out.append({
                "row": data // self.cols, "col": data % self.cols,
                "length": c.length, "attr": f"0x{c.attr:02X}",
                "hidden": c.attr == ds.ATTR_NONDISPLAY,
                "ffw": f"0x{c.ffw:04X}",
                "monocase": bool(c.ffw & FFW_MONOCASE),
                "shift": (c.ffw & FFW_SHIFT_MASK) >> 8,
            })
        return out

    def runs(self) -> list[dict]:
        """Text runs: what follows each attribute cell, split at row ends."""
        out = []
        attr = None
        for r in range(self.rows):
            run_start = None
            text: list[str] = []

            def flush(r=r) -> None:
                nonlocal run_start, text
                s = "".join(text).rstrip()
                if run_start is not None and s.strip():
                    out.append({"row": r, "col": run_start, "attr": f"0x{attr:02X}" if attr is not None else None,
                                "length": len(s), "text": s})
                run_start, text = None, []

            for c in range(self.cols):
                cell = self.cells[r * self.cols + c]
                if cell.attr is not None:
                    flush()
                    attr = cell.attr
                    continue
                if cell.char and run_start is None:
                    run_start = c
                if run_start is not None:
                    text.append(ebcdic.decode(bytes([cell.char])) if cell.char else " ")
            flush()
        return out

    def snapshot(self) -> dict:
        fields = self.input_fields()
        cursor = self.cursor
        if cursor is None and fields:
            cursor = fields[0]["row"] * self.cols + fields[0]["col"]
        text = " ".join(r["text"] for r in self.runs())
        return {
            "geometry": [self.rows, self.cols],
            "cursor": None if cursor is None else [cursor // self.cols, cursor % self.cols],
            "fields": fields,
            "runs": self.runs(),
            "message_ids": sorted(set(MESSAGE_ID.findall(text))),
        }
