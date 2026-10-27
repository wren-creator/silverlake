"""The QP2TERM display: a terminal over the simulated PASE shell (system/pase.py).

A real QP2TERM is a full screen terminal with a `$` prompt. This one keeps the scrollback as lines of text, takes
one command line at the bottom, and F3 or `exit` leaves. The banner on the top row says it is simulated, so nobody
mistakes what it prints for what an AIX runtime would."""

from __future__ import annotations

import textwrap

from ..proto import datastream as ds
from ..system import pase
from .model import Input, Screen, Text
from .pdm import Context, Step, _msg

FIRST, LAST = 1, 21
WIDTH = 78
KEEP = 500


class PaseTerm:
    def __init__(self, ctx: Context) -> None:
        self.ctx = ctx
        self.shell = pase.Shell(ctx.store, ctx.profile)
        self.lines: list[str] = []

    def screen(self, message: str = "") -> Screen:
        rows: list = [Text(0, 1, pase.BANNER[:78], ds.ATTR_BLUE)]
        shown = self.lines[-(LAST - FIRST + 1):]
        for i, text in enumerate(shown):
            rows.append(Text(FIRST + i, 1, text[:WIDTH] or " ", ds.ATTR_GREEN))
        rows.append(Text(22, 1, self.shell.prompt, ds.ATTR_GREEN))
        rows.append(Input(22, 1 + len(self.shell.prompt), 76 - len(self.shell.prompt), "cmd"))
        if message:
            _msg(rows, message)
        else:
            rows.append(Text(23, 1, "F3=Exit   F12=Cancel", ds.ATTR_BLUE))
        return Screen(rows, cursor="cmd")

    def handle(self, aid: str, values: dict[str, str]) -> Step:
        if aid in ("F3", "F12"):
            return Step(go="back")
        if aid != "ENTER":
            return Step()
        line = values.get("cmd", "")
        self.lines.append(self.shell.prompt + line)
        for out in self.shell.run(line):
            self.lines += textwrap.wrap(out, WIDTH, replace_whitespace=False, drop_whitespace=False) or [""]
        del self.lines[:-KEEP]
        return Step(go="back") if self.shell.done else Step()
