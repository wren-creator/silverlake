"""DSPPFM: Display Physical File Member. The records of a file as raw characters, with a Control field to
jump to a record, F19 and F20 to shift left and right, F10/F11 to switch to a hex view and back, and a
Find field to jump to the next record whose text contains a string.

The layout is ours, not captured. A real DSPPFM also has F21 (split) and a member other than the first.
Not built."""

from __future__ import annotations

from ..proto import datastream as ds
from ..system import dbfiles
from .model import Input, Screen, Text
from .pdm import Context, Step, _msg, _title

FIRST, LAST = 7, 19
WIDTH = 71
HEX_WIDTH = 24                    # bytes per line in the hex view: 24*"XX " - 1 trailing space = 71 columns


class PfmView:
    def __init__(self, ctx: Context, obj) -> None:
        self.ctx, self.obj = ctx, obj
        self.pf = dbfiles.layout(obj)
        self.top = 1                      # record number at the top
        self.col = 1                      # first column (or, in hex, first byte) shown
        self.hex = False

    def _rows(self) -> list[str]:
        return [dbfiles.record_text(self.pf, r) for r in self.obj.data.get("records", [])]

    def _span(self) -> int:
        return HEX_WIDTH if self.hex else WIDTH

    def _rows_per_record(self) -> int:
        return 2 if self.hex else 1

    def screen(self, message: str = "") -> Screen:
        records = self._rows()
        rows: list = [
            _title("Display Physical File Member", 26),
            Text(1, 1, f"File  . . . . . . :   {self.obj.name:<10}   Library . . . . :   {self.obj.library}", ds.ATTR_GREEN),
            Text(2, 1, f"Member  . . . . . :   {self.obj.name:<10}   Record . . . . . :   {self.top}", ds.ATTR_GREEN),
            Text(3, 1, "Control  . . . . .", ds.ATTR_GREEN), Input(3, 20, 8, "control"),
            Text(3, 40, f"Column  . . . . . :   {self.col}", ds.ATTR_GREEN),
            Text(4, 1, "Find . . . . . . .", ds.ATTR_GREEN), Input(4, 20, 40, "find"),
        ]
        height = (LAST - FIRST + 1) // self._rows_per_record()
        if self.hex:
            chunk = records[self.top - 1:self.top - 1 + height]
            for i, text in enumerate(chunk):
                r = FIRST + i * 2
                field = text[self.col - 1:self.col - 1 + HEX_WIDTH].ljust(HEX_WIDTH)
                rows.append(Text(r, 0, " ".join(f"{ord(c):02X}" for c in field), ds.ATTR_GREEN))
                rows.append(Text(r + 1, 0, field, ds.ATTR_GREEN))
            last_row = FIRST + len(chunk) * 2
        else:
            rows.append(Text(6, 1, "".join(str((i // 10) % 10) if i % 10 == 0 else "." for i in
                                           range(self.col, self.col + WIDTH)), ds.ATTR_BLUE))
            chunk = records[self.top - 1:self.top - 1 + height]
            for i, text in enumerate(chunk):
                rows.append(Text(FIRST + i, 0, text[self.col - 1:self.col - 1 + WIDTH] or " ", ds.ATTR_GREEN))
            last_row = FIRST + len(chunk)
        if not chunk:
            rows.append(Text(FIRST, 0, "No records in the file." if not records else "", ds.ATTR_BLUE))
        elif self.top - 1 + height >= len(records):
            rows.append(Text(last_row, 0, "*" * 18 + " End of Data " + "*" * 18, ds.ATTR_BLUE))
        toggle = "F11=Display character" if self.hex else "F10=Display hex"
        rows.append(Text(21, 1, f"F3=Exit   {toggle}   F12=Cancel   F19=Left   F20=Right", ds.ATTR_BLUE))
        _msg(rows, message)
        return Screen(rows, cursor="control")

    def handle(self, aid: str, values: dict[str, str]) -> Step:
        if aid in ("F3", "F12"):
            return Step(go="back")
        height = (LAST - FIRST + 1) // self._rows_per_record()
        records = self._rows()
        total = len(records)
        if aid == "ROLLUP":
            self.top = min(max(1, total), self.top + height)
        elif aid == "ROLLDOWN":
            self.top = max(1, self.top - height)
        elif aid == "F10":
            self.hex, self.col = True, 1
        elif aid == "F11":
            self.hex, self.col = False, 1
        elif aid == "F20":
            self.col += self._span()
        elif aid == "F19":
            self.col = max(1, self.col - self._span())
        ctl = values.get("control", "").strip().upper()
        if ctl:
            if ctl in ("T", "TOP"):
                self.top = 1
            elif ctl in ("B", "BOT", "BOTTOM"):
                self.top = max(1, total - height + 1)
            elif ctl.isdigit() and int(ctl) >= 1:
                self.top = min(max(1, total), int(ctl))
            else:
                return Step("Control must be a record number, T or B.")
        find = values.get("find", "").strip()
        if find:
            hit = next((i for i in range(self.top, total + 1) if find.upper() in records[i - 1].upper()), None)
            if hit is None:
                return Step(f"String '{find}' not found.")
            self.top = hit
        return Step()
