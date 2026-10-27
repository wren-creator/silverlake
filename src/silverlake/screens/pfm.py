"""DSPPFM: Display Physical File Member. The records of a file as raw characters, with a Control field to
jump to a record and F19 and F20 to shift left and right.

The layout is ours, not captured. A real DSPPFM also has F21 (split), F10 and F11 (display in hex and
in character), and a Find. Not built."""

from __future__ import annotations

from ..proto import datastream as ds
from ..system import dbfiles
from .model import Input, Screen, Text
from .pdm import Context, Step, _msg, _title

FIRST, LAST = 6, 19
WIDTH = 71


class PfmView:
    def __init__(self, ctx: Context, obj) -> None:
        self.ctx, self.obj = ctx, obj
        self.pf = dbfiles.layout(obj)
        self.top = 1                      # record number at the top
        self.col = 1                      # first column shown

    def _rows(self) -> list[str]:
        return [dbfiles.record_text(self.pf, r) for r in self.obj.data.get("records", [])]

    def screen(self, message: str = "") -> Screen:
        records = self._rows()
        height = LAST - FIRST + 1
        rows: list = [
            _title("Display Physical File Member", 26),
            Text(1, 1, f"File  . . . . . . :   {self.obj.name:<10}   Library . . . . :   {self.obj.library}", ds.ATTR_GREEN),
            Text(2, 1, f"Member  . . . . . :   {self.obj.name:<10}   Record . . . . . :   {self.top}", ds.ATTR_GREEN),
            Text(3, 1, "Control  . . . . .", ds.ATTR_GREEN), Input(3, 20, 8, "control"),
            Text(3, 40, f"Column  . . . . . :   {self.col}", ds.ATTR_GREEN),
            Text(4, 1, "".join(str((i // 10) % 10) if i % 10 == 0 else "." for i in range(self.col, self.col + WIDTH)),
                 ds.ATTR_BLUE),
        ]
        chunk = records[self.top - 1:self.top - 1 + height]
        for i, text in enumerate(chunk):
            rows.append(Text(FIRST + i, 0, text[self.col - 1:self.col - 1 + WIDTH] or " ", ds.ATTR_GREEN))
        if not chunk:
            rows.append(Text(FIRST, 0, "No records in the file." if not records else "", ds.ATTR_BLUE))
        elif self.top - 1 + height >= len(records):
            rows.append(Text(FIRST + len(chunk), 0, "*" * 18 + " End of Data " + "*" * 18, ds.ATTR_BLUE))
        rows.append(Text(21, 1, "F3=Exit   F12=Cancel   F19=Left   F20=Right", ds.ATTR_BLUE))
        _msg(rows, message)
        return Screen(rows, cursor="control")

    def handle(self, aid: str, values: dict[str, str]) -> Step:
        if aid in ("F3", "F12"):
            return Step(go="back")
        height = LAST - FIRST + 1
        total = len(self.obj.data.get("records", []))
        if aid == "ROLLUP":
            self.top = min(max(1, total), self.top + height)
        elif aid == "ROLLDOWN":
            self.top = max(1, self.top - height)
        elif aid == "F20":
            self.col += WIDTH
        elif aid == "F19":
            self.col = max(1, self.col - WIDTH)
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
        return Step()
