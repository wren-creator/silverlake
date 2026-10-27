"""F4 on a command: the prompt display for CRTBNDRPG, CRTPF, CRTDSPF, CRTPRTF and CRTSRCPF.

Captured from PUB400 (read only, `auth-pdm`): the title, the rows, the labels, the columns, the "Bottom"
marker, the two key lines, "Parameter FILE required." when Enter is pressed with no name, and "Already at
bottom of area." on Roll Up. Not captured: what Roll Down says (ours), how a refused command reads on the
prompt (ours), and F10, F13 and F24 (not built, they say so).

Two defaults differ from what the captured host showed. Its CRTDSPF and CRTPRTF offered SRCFILE *NONE with
a blank library, which looks like a local setting; here the field holds QDDSSRC and *LIBL, the real IBM
default, so pressing Enter works. A file with no source (RCDLEN) and a source stream file (SRCSTMF) are
laid out and refused, because compiling them is not built."""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..cl import parser
from ..proto import datastream as ds
from .model import Input, Screen, Text
from .pdm import Context, Step, _msg

# (row, label as drawn, field name, field column, field length, default). A row with no field name is a
# label only. Field names are the command's keywords, and "KW@" is the library part of a qualified name.
_COMMON = [(4, "File . . . . . . . . . . . . . . FILE", "FILE", 49, 10, ""),
           (5, "  Library  . . . . . . . . . . .", "FILE@", 51, 10, "*CURLIB"),
           (6, "Source file  . . . . . . . . . . SRCFILE", "SRCFILE", 49, 10, "QDDSSRC"),
           (7, "  Library  . . . . . . . . . . .", "SRCFILE@", 51, 10, "*LIBL"),
           (8, "Source member  . . . . . . . . . SRCMBR", "SRCMBR", 49, 10, "*FILE")]
_TEXT = "Text 'description' . . . . . . . TEXT"

SPECS: dict[str, dict] = {
    "CRTBNDRPG": {"title": ("Create Bound RPG Program (CRTBNDRPG)", 22), "rows": [
        (4, "Program  . . . . . . . . . . . . PGM", "PGM", 49, 10, "*CTLSPEC"),
        (5, "  Library  . . . . . . . . . . .", "PGM@", 51, 10, "*CURLIB"),
        (6, "Source file  . . . . . . . . . . SRCFILE", "SRCFILE", 49, 10, "QRPGLESRC"),
        (7, "  Library  . . . . . . . . . . .", "SRCFILE@", 51, 10, "*LIBL"),
        (8, "Source member  . . . . . . . . . SRCMBR", "SRCMBR", 49, 10, "*PGM"),
        (9, "Source stream file . . . . . . . SRCSTMF", "SRCSTMF", 49, 50, ""),
        (11, "Generation severity level  . . . GENLVL", "GENLVL", 49, 2, "10"),
        (12, _TEXT, "TEXT", 49, 50, "*SRCMBRTXT"),
        (14, "Default activation group . . . . DFTACTGRP", "DFTACTGRP", 49, 4, "*YES")]},
    "CRTPF": {"title": ("Create Physical File (CRTPF)", 26), "rows": _COMMON + [
        (9, "Record length, if no DDS . . . . RCDLEN", "RCDLEN", 49, 6, ""),
        (10, "Generation severity level  . . . GENLVL", "GENLVL", 49, 2, "20"),
        (11, "Flagging severity level  . . . . FLAG", "FLAG", 49, 2, "0"),
        (12, "File type  . . . . . . . . . . . FILETYPE", "FILETYPE", 49, 10, "*DATA"),
        (13, "Member, if desired . . . . . . . MBR", "MBR", 49, 10, "*FILE"),
        (14, _TEXT, "TEXT", 49, 50, "*SRCMBRTXT")]},
    "CRTDSPF": {"title": ("Create Display File (CRTDSPF)", 26), "rows": _COMMON + [
        (9, "Generation severity level  . . . GENLVL", "GENLVL", 49, 2, "20"),
        (10, "Flagging severity level  . . . . FLAG", "FLAG", 49, 2, "0"),
        (11, "Display device . . . . . . . . . DEV", "DEV", 49, 10, "*REQUESTER"),
        (12, "                          + for more values", "", 0, 0, ""),
        (13, _TEXT, "TEXT", 49, 50, "*SRCMBRTXT")]},
    "CRTPRTF": {"title": ("Create Printer File (CRTPRTF)", 26), "rows": _COMMON + [
        (9, "Generation severity level  . . . GENLVL", "GENLVL", 49, 2, "20"),
        (10, "Flagging severity level  . . . . FLAG", "FLAG", 49, 2, "0"),
        (11, "Device:                          DEV", "", 0, 0, ""),
        (12, "  Printer  . . . . . . . . . . .", "DEV", 49, 10, "*JOB"),
        (13, "Printer device type  . . . . . . DEVTYPE", "DEVTYPE", 49, 10, "*SCS"),
        (14, _TEXT, "TEXT", 49, 50, "*SRCMBRTXT")]},
    "CRTSRCPF": {"title": ("Create Source Physical File (CRTSRCPF)", 21), "rows": [
        (4, "File . . . . . . . . . . . . . . FILE", "FILE", 49, 10, ""),
        (5, "  Library  . . . . . . . . . . .", "FILE@", 51, 10, "*CURLIB"),
        (6, "Record length  . . . . . . . . . RCDLEN", "RCDLEN", 49, 6, "92"),
        (7, "Member, if desired . . . . . . . MBR", "MBR", 49, 10, "*NONE"),
        (8, _TEXT, "TEXT", 49, 50, "*BLANK")]},
}
NOT_BUILT = {("CRTPF", "RCDLEN"): "A file with no source is not built here. Name a source member.",
             ("CRTBNDRPG", "SRCSTMF"): "Source stream files are not built here. Name a source member."}
KEYS = ("F3=Exit   F4=Prompt   F5=Refresh   F10=Additional parameters   F12=Cancel",
        "F13=How to use this display        F24=More keys")
_BARE = re.compile(r"^[A-Z0-9@#$_*./]+$")
DONE = (" placed in library ", " created in library ")


def promptable(name: str) -> bool:
    return name in SPECS


def _split_qualified(value: str) -> tuple[str, str]:
    lib, _, name = value.rpartition("/")
    return name, lib


@dataclass
class Prompt:
    ctx: Context
    command: str
    typed: dict
    values: dict

    @classmethod
    def for_command(cls, ctx: Context, line: str = "", **preset: str) -> "Prompt | None":
        """The prompt for a command line (the command may be only a name), or None when this command has no
        prompt here. `preset` fills fields the caller already knows, by field name."""
        try:
            parsed = parser.parse(line)
        except parser.ParseError:
            return None
        if parsed is None or parsed.command not in SPECS:
            return None
        from ..cl import commands                              # imported late: commands imports screens' neighbours
        spec = SPECS[parsed.command]
        order = [p.key for p in commands.COMMANDS[parsed.command]]
        given = dict(zip(order, ([v] for v in parsed.positional)))
        given.update(parsed.keywords)
        values = {name: default for _, _, name, _, _, default in spec["rows"] if name}
        for key, vals in given.items():
            if key + "@" in values and vals and "/" in vals[0]:
                name, lib = _split_qualified(vals[0])
                values[key], values[key + "@"] = name, lib
            elif key in values and vals:
                values[key] = " ".join(vals)
        values.update({k: v for k, v in preset.items() if k in values})
        return cls(ctx, parsed.command, given, values)

    # -- drawing -----------------------------------------------------------------------------------------

    def screen(self, message: str = "") -> Screen:
        spec = SPECS[self.command]
        title, col = spec["title"]
        rows: list = [Text(0, col, title, ds.ATTR_WHITE), Text(2, 1, "Type choices, press Enter.", ds.ATTR_GREEN)]
        for row, label, name, fcol, flen, _ in sorted(spec["rows"], key=lambda r: r[0]):
            rows.append(Text(row, 1, label, ds.ATTR_GREEN))
            if name:
                rows.append(Input(row, fcol, flen, name, value=self.values.get(name, "")))
        rows += [Text(20, 73, "Bottom", ds.ATTR_BLUE), Text(21, 1, KEYS[0], ds.ATTR_BLUE),
                 Text(22, 1, KEYS[1], ds.ATTR_BLUE)]
        _msg(rows, message)
        first = next(name for _, _, name, _, _, _ in sorted(spec["rows"], key=lambda r: r[0]) if name)
        return Screen(rows, cursor=first)

    # -- keys --------------------------------------------------------------------------------------------

    def handle(self, aid: str, values: dict[str, str]) -> Step:
        if aid == "F3":
            return Step(go="menu")
        if aid == "F12":
            return Step(go="back")
        if aid == "ROLLUP":
            return Step("Already at bottom of area.")                 # captured
        if aid == "ROLLDOWN":
            return Step("Already at top of area.")                    # ours
        if aid == "F5":
            self.values = {n: d for _, _, n, _, _, d in SPECS[self.command]["rows"] if n}
            return Step()
        if aid in ("F10", "F13", "F24", "F4"):
            return Step("That key is not built here.")
        for name in self.values:
            if name in values:
                self.values[name] = values[name].strip()
        key = "PGM" if self.command == "CRTBNDRPG" else "FILE"
        if not self.values.get(key):
            return Step(f"Parameter {key} required.")                 # captured
        for (cmd, kw), why in NOT_BUILT.items():
            if cmd == self.command and self.values.get(kw):
                return Step(why)
        out = self.ctx.run(self._line())
        if out.view or out.go or out.cmdentry or out.signoff:
            return Step()
        text = out.message.text if out.message else ""
        if any(d in text for d in DONE):
            return Step(text, go="back")
        return Step(text)

    def _line(self) -> str:
        """The command line these fields make. Only what is not the default goes in, so the job log reads like
        something a person would type."""
        spec = SPECS[self.command]
        defaults = {n: d for _, _, n, _, _, d in spec["rows"] if n}
        parts = []
        for _, _, name, _, _, _ in spec["rows"]:
            if not name or name.endswith("@") or (self.command, name) in NOT_BUILT:
                continue
            val = self.values.get(name, "")
            lib = self.values.get(name + "@", "")
            lib_default = defaults.get(name + "@", "")
            if name + "@" in defaults and lib and lib != lib_default:
                parts.append(f"{name}({lib}/{val})")
            elif val and (val != defaults[name] or name in ("PGM", "FILE")):
                parts.append(f"{name}({val if _BARE.match(val) else self._q(val)})")
        return " ".join([self.command, *parts])

    @staticmethod
    def _q(val: str) -> str:
        return "'" + val.replace("'", "''") + "'"
