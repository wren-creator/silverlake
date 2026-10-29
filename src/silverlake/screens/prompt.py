"""F4 on a command: the prompt display, drawn from the layouts captured on PUB400 (read only, `auth-pdm` and
`auth-prompts-*` and `auth-f10-*`, held in `promptspecs.py`).

What the captures showed, and this follows: the title, the rows, the labels, the columns and the lengths; a
"Bottom" or "More..." marker and the key lines; required parameters drawn brighter, with "Parameter X required."
on Enter and on Roll Up while one is empty; F10=Additional parameters (no check first, the whole prompt again
with the rest below an "Additional Parameters" line and its own key lines, F12 leaving the prompt from there); Roll Up paging a prompt that is more than one page, and "Already at
bottom of area." on the last. CHGPWD has nothing to prompt for and says so. CRTLIB is the one prompt not captured (the host refused it first), so its layout is ours (LOCAL). Not captured, so ours: what Roll Down
says at the top, how a refused command reads on the prompt, and F13 and F24, which say they are not built, as does F10
on a prompt with no additional parameters or when pressed a second time. CHGSPLFA's F10 view stops at its first page:
the host will not page it without a spooled file that exists.

Where this differs from the captured host on purpose: its CRTDSPF and CRTPRTF offered SRCFILE *NONE with a blank
library, which looks like a local setting. Here the field holds QDDSSRC and *LIBL, the real IBM default, so
pressing Enter works (OVERRIDES). A file with no source (RCDLEN) and a source stream file (SRCSTMF) are laid out and
refused, because compiling them is not built (NOT_BUILT)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..cl import parser
from ..proto import datastream as ds
from .model import Input, Screen, Text
from .pdm import Context, Step, _msg
from .promptspecs import SPECS as CAPTURED

OVERRIDES = {("CRTDSPF", "SRCFILE"): "QDDSSRC", ("CRTDSPF", "SRCFILE@"): "*LIBL",
             ("CRTPRTF", "SRCFILE"): "QDDSSRC", ("CRTPRTF", "SRCFILE@"): "*LIBL"}
NOT_BUILT = {("CRTPF", "RCDLEN"): "A file with no source is not built here. Name a source member.",
             ("CRTBNDRPG", "SRCSTMF"): "Source stream files are not built here. Name a source member."}
_BARE = re.compile(r"^[A-Z0-9@#$_*./]+$")
DONE = (" placed in library ", " created in library ")
# A command that ran and finished says so in a sentence with no message ID (the wording is ours). One that
# did not has an ID, or reads "... not found." or "Cannot ...". This is a guess at the difference.
_FINISHED = re.compile(r"\b(created|deleted|changed|added|removed|granted|revoked|renamed|placed|held|released|"
                       r"cleared|sent|ended|copied|replaced|overridden|updated|moved)\b", re.I)


def _with_overrides(command: str, rows: list) -> list:
    return [(r, label, name, col, length, OVERRIDES.get((command, name), default))
            for r, label, name, col, length, default in rows]


# Not captured, so ours: the host refused CRTLIB to the captured profile before any prompt opened. The rows follow
# the CRTMSGQ capture (same columns, same key lines) and IBM's parameter order; AUT and the rest sit behind F10.
LOCAL = {"CRTLIB": {
    "title": ("Create Library (CRTLIB)", 28), "bottom": "Bottom", "required": ("LIB",),
    "keys": CAPTURED["CRTMSGQ"]["keys"],
    "rows": [(4, "Library  . . . . . . . . . . . LIB", "LIB", 49, 10, ""),
             (5, "Library type  . . . . . . . . . TYPE", "TYPE", 49, 7, "*PROD"),
             (6, "Text 'description' . . . . . . . TEXT", "TEXT", 49, 50, "*BLANK")]}}


def _build() -> dict[str, dict]:
    specs = {}
    for command, spec in {**CAPTURED, **LOCAL}.items():
        pages = [(_with_overrides(command, spec["rows"]), spec["bottom"])]
        pages += [(_with_overrides(command, rows), bottom) for rows, bottom in spec.get("pages", [])]
        specs[command] = {"title": spec["title"], "pages": pages, "keys": spec["keys"],
                          "required": spec["required"], "note": spec.get("note", "")}
        if "more" in spec:                  # F10=Additional parameters: the whole prompt again, and what follows
            specs[command]["more"] = {"keys": spec["more"]["keys"],
                                      "pages": [(_with_overrides(command, rows), bottom)
                                                for rows, bottom in spec["more"]["pages"]]}
        # the first page's rows, for the callers that only want to know what the prompt holds
        specs[command]["rows"] = pages[0][0]
    return specs


SPECS: dict[str, dict] = _build()


def promptable(name: str) -> bool:
    return name in SPECS


def _split_qualified(value: str) -> tuple[str, str]:
    lib, _, name = value.rpartition("/")
    return name, lib


def _all_rows(spec: dict) -> list:
    pages = spec["pages"] + spec.get("more", {}).get("pages", [])
    return [row for rows, _ in pages for row in rows]


def _resolve(default: str, ctx: Context) -> str:
    """The table holds a token where the host showed a value of the profile it was captured with (current library,
    text, profile name), because a change command shows current values. Here they are the signed-on profile's."""
    if default == "{USER}":
        return ctx.profile.name
    if default == "{CURLIB}":
        return ctx.profile.current_library
    if default == "{TEXT}":
        return "'" + ctx.profile.text.replace("'", "''") + "'" if ctx.profile.text else "*BLANK"
    return default


def _defaults(spec: dict, ctx: Context) -> dict[str, str]:
    return {name: _resolve(default, ctx) for _, _, name, _, _, default in _all_rows(spec) if name}


def _group(values: dict, key: str) -> list[str]:
    """The fields that make up one keyword: KW, then KW@ (the library, or a second value), KW@3 and on, and KW+ (the
    "+ for more values" line), and KW+@ (a bare field under it)."""
    return [n for n in values if n == key or n.startswith(key + "@") or n.startswith(key + "+")]


@dataclass
class Prompt:
    ctx: Context
    command: str
    typed: dict
    values: dict
    page: int = field(default=0)
    extra: bool = False                             # F10 pressed: the additional parameters view
    flagged: set = field(default_factory=set)      # fields drawn in reverse image after a refusal
    cursor: str = ""                                # where the cursor goes after one

    @classmethod
    def refused(cls, ctx: Context, line: str) -> str:
        """Captured: F4 on a command the profile may not use is refused where it was typed, before any prompt
        opens ("Not authorized to command X in library *LIBL."). Empty when the command may be used."""
        try:
            parsed = parser.parse(line)
        except parser.ParseError:
            return ""
        if parsed is None:
            return ""
        from ..cl import commands
        if parsed.command not in commands.COMMANDS:
            return ""
        message = commands.command_refusal(ctx.store, ctx.profile, parsed.command)
        return message.text if message else ""

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
        values = _defaults(spec, ctx)
        for key, vals in given.items():
            names = _group(values, key)
            if not names or not vals:
                continue
            if len(names) == 2 and names[1] == key + "@" and len(vals) == 1 and "/" in vals[0]:
                name, lib = _split_qualified(vals[0])
                values[key], values[key + "@"] = name, lib
            elif len(vals) > 1 and len(names) > 1:
                for n, v in zip(names, vals):
                    values[n] = v
            else:
                values[names[0]] = " ".join(vals)
        values.update({k: v for k, v in preset.items() if k in values})
        return cls(ctx, parsed.command, given, values)

    def _view(self) -> tuple[list, tuple]:
        """The pages and key lines on show: the plain prompt, or what F10 asks for."""
        spec = SPECS[self.command]
        return (spec["more"]["pages"], spec["more"]["keys"]) if self.extra else (spec["pages"], spec["keys"])

    # -- drawing -----------------------------------------------------------------------------------------

    def screen(self, message: str = "") -> Screen:
        spec = SPECS[self.command]
        title, col = spec["title"]
        rows: list = [Text(0, col, title, ds.ATTR_WHITE)]
        if spec["note"]:                                           # CHGPWD: nothing to prompt for
            rows += [Text(21, 1, spec["keys"][0], ds.ATTR_BLUE)]
            _msg(rows, message or spec["note"])
            return Screen(rows)
        pages, keys = self._view()
        page_rows, marker = pages[self.page]
        rows.append(Text(2, 1, "Type choices, press Enter.", ds.ATTR_BLUE))
        for row, label, name, fcol, flen, _ in sorted(page_rows, key=lambda r: r[0]):
            if label:
                rows.append(Text(row, 1, label, ds.ATTR_GREEN))
            if name:
                rows.append(Input(row, fcol, flen, name, value=self.values.get(name, ""),
                                  required=name in spec["required"], error=name in self.flagged))
        rows.append(Text(20, 79 - len(marker), marker, ds.ATTR_WHITE))
        rows += [Text(21 + i, 1, line, ds.ATTR_BLUE) for i, line in enumerate(keys)]
        _msg(rows, message)
        first = next(name for _, _, name, _, _, _ in sorted(page_rows, key=lambda r: r[0]) if name)
        return Screen(rows, cursor=self.cursor or first)

    # -- keys --------------------------------------------------------------------------------------------

    def _missing(self) -> list[str]:
        """The parameters the host will not run without that are still empty, in the order of the prompt."""
        return [n for n in SPECS[self.command]["required"] if not self.values.get(n)]

    def _refuse(self, missing: list[str]) -> Step:
        """Captured on every required parameter left empty: "Parameter X required." for the first, every field of
        every empty one redrawn in reverse image, and the cursor on the first. A filled one is left alone (ours:
        the captures only ever had empty prompts). The page that holds the first one comes back up (ours)."""
        first = missing[0]
        self.flagged = {n for key in missing for n in _group(self.values, key)}
        self.cursor = first
        self.page = next(i for i, (rows, _) in enumerate(self._view()[0])
                         if any(r[2] == first for r in rows))
        return Step(f"Parameter {first} required.")

    def handle(self, aid: str, values: dict[str, str]) -> Step:
        spec = SPECS[self.command]
        self.flagged, self.cursor = set(), ""
        if aid == "F3":
            return Step(go="menu")
        if aid == "F12":
            return Step(go="back")
        if aid == "F5":
            self.values = _defaults(spec, self.ctx)
            return Step()
        for name in self.values:                                  # what was typed stays when the view changes
            if name in values:
                self.values[name] = values[name].strip()
        if aid == "F10" and "more" in spec and not self.extra:    # captured: no check, straight to the view
            self.extra, self.page = True, 0
            return Step()
        if aid in ("F10", "F13", "F24", "F4"):
            return Step("That key is not built here.")
        if aid == "ROLLUP":
            if (missing := self._missing()):                      # captured: the host checks these first
                return self._refuse(missing)
            if self.page + 1 < len(self._view()[0]):
                self.page += 1
                return Step()
            return Step("Already at bottom of area.")             # captured
        if aid == "ROLLDOWN":
            if self.page:
                self.page -= 1
                return Step()
            return Step("Already at top of area.")                # ours
        if (missing := self._missing()):
            return self._refuse(missing)                          # captured
        for (cmd, kw), why in NOT_BUILT.items():
            if cmd == self.command and self.values.get(kw):
                return Step(why)
        out = self.ctx.run(self._line())
        if out.view or out.go or out.cmdentry or out.signoff:
            return Step()
        text = out.message.text if out.message else ""
        if any(d in text for d in DONE) or (out.message and not out.message.id and _FINISHED.search(text)
                                            and " not " not in text):
            return Step(text, go="back")
        return Step(text)

    def _line(self) -> str:
        """The command line these fields make. Only what is not the default goes in, so the job log reads like
        something a person would type. A required parameter always goes in."""
        spec = SPECS[self.command]
        defaults = _defaults(spec, self.ctx)
        required = set(spec["required"])
        parts = []
        for name in defaults:
            if "@" in name or name.endswith("+") or (self.command, name) in NOT_BUILT:
                continue
            group = _group(defaults, name)
            vals = [self.values.get(n, "") for n in group]
            if len(group) == 2 and group[1] == name + "@":       # a qualified name: library, then name
                lib, lib_default = vals[1], defaults[group[1]]
                if lib and lib != lib_default:
                    parts.append(f"{name}({lib}/{vals[0]})")
                    continue
            elif len(group) > 1:                                  # a list of values
                if vals != [defaults[n] for n in group]:
                    parts.append(f"{name}({' '.join(self._fmt(v) for v in vals if v)})")
                continue
            val = vals[0]
            if val and (val != defaults[name] or name in required):
                parts.append(f"{name}({self._fmt(val)})")
        return " ".join([self.command, *parts])

    @classmethod
    def _fmt(cls, val: str) -> str:
        return val if _BARE.match(val) else cls._q(val)

    @staticmethod
    def _q(val: str) -> str:
        return "'" + val.replace("'", "''") + "'"
