"""PDM and the source editor: STRPDM, WRKMBRPDM and STRSEU.

Each is a widget the controller keeps as a view: `screen(message)` draws it and `handle(aid, values)`
answers a key with a Step (stay, go back, leave to the menu, or open another widget). They work on the
members of a source file (system/source.py) and reach the rest of the system through a Context.

What is from a real PUB400 capture (`auth-pdm`, read only): the PDM start menu, and the refusals. The
Work with Members and SEU displays are laid out from the way they are known to look, not captured, so
their wording and positions are ours. SEU is a small one: line commands I, D, C, M, R (with counts, and
doubled for a block, A and B to place a copy or move), a command line (TOP, BOTTOM, FIND, CHANGE, SAVE,
FILE, CANCEL), Roll, and an exit display. Not built: prefix areas for formatting, syntax prompts, and
column shifting."""

from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from ..proto import datastream as ds
from ..system import source
from ..system.authority import Auth, SecuredObject
from .model import Input, Screen, Text

SYSTEM_NAME = "SILVERLK"
CMD_ROW, CMD_COL, CMD_LEN = 20, 6, 73
TYPE_COMMANDS = {"RPGLE": "CRTBNDRPG", "PF": "CRTPF", "DSPF": "CRTDSPF", "PRTF": "CRTPRTF"}


@dataclass
class Context:
    """What the widgets need from the controller."""
    store: object
    profile: object
    session: object
    run: Callable[[str], object]        # run a command line the way the command line does (and log it)


@dataclass
class Step:
    message: str = ""
    go: str = "stay"                    # stay, back (one level), menu (all the way out), open
    widget: object = None


def _title(text: str, col: int) -> Text:
    return Text(0, col, text, ds.ATTR_WHITE)


def _msg(rows: list, message: str) -> None:
    if message:
        rows.append(Text(23, 1, message[:77], ds.ATTR_WHITE))
        if len(message) > 77:
            rows.append(Text(23, 78, "+", ds.ATTR_WHITE))


# -- STRPDM ------------------------------------------------------------------------------------------------

class PdmMenu:
    """The PDM start menu (captured). 1 to 3 would ask which libraries, objects and members, which is not built:
    they say how to get there with a command."""

    def __init__(self, ctx: Context) -> None:
        self.ctx = ctx

    def screen(self, message: str = "") -> Screen:
        rows: list = [
            Text(0, 25, "Programming Development Manager (PDM)", ds.ATTR_WHITE),
            Text(2, 1, "Select one of the following:", ds.ATTR_GREEN),
            Text(4, 6, "1. Work with libraries", ds.ATTR_GREEN),
            Text(5, 6, "2. Work with objects", ds.ATTR_GREEN),
            Text(6, 6, "3. Work with members", ds.ATTR_GREEN),
            Text(8, 6, "9. Work with user-defined options", ds.ATTR_GREEN),
            Text(18, 1, "Selection or command", ds.ATTR_GREEN), Text(19, 1, "===>", ds.ATTR_GREEN),
            Input(19, 6, 73, "command"),
            Text(21, 1, "F3=Exit       F4=Prompt       F9=Retrieve        F10=Command entry", ds.ATTR_BLUE),
            Text(22, 1, "F12=Cancel    F18=Change defaults", ds.ATTR_BLUE),
            Text(23, 43, "(C) COPYRIGHT IBM CORP. 1981, 2007.", ds.ATTR_BLUE) if not message else Text(23, 1, message[:77], ds.ATTR_WHITE),
        ]
        return Screen(rows, cursor="command")

    def handle(self, aid: str, values: dict[str, str]) -> Step:
        ctx = self.ctx
        if aid == "F3":
            return Step(go="menu")
        if aid == "F12":
            return Step(go="back")
        line = values.get("command", "").strip()
        hint = {"1": "Use WRKLIB to work with libraries.",
                "2": "Use WRKOBJPDM LIB(library) to work with the objects of a library.",
                "3": "Use WRKMBRPDM FILE(library/file) to work with the members of a source file.",
                "9": "User-defined options are not built."}
        if line in hint:
            return Step(hint[line])
        if line:
            out = ctx.run(line)
            if out.view:
                return Step("That command needs a full display. Leave PDM and run it from the command line.")
            return Step(out.message.text if out.message else "")
        return Step()


# -- WRKMBRPDM ---------------------------------------------------------------------------------------------

class MemberList:
    """Work with Members Using PDM: the members of one source file with the options PDM offers. The options
    that take a value (3 copy, 7 rename, 13 change text) read it from the command line, as PDM's own
    "Parameters for options 5, 7 and 13" does."""

    PER_PAGE = 9

    def __init__(self, ctx: Context, file: SecuredObject, pattern: str = "*ALL") -> None:
        self.ctx, self.file, self.pattern = ctx, file, pattern.upper()
        self.page = 0
        self.mode = "list"                  # list, confirm (delete) or new (create a member)
        self.pending: list[str] = []
        self.draft = {"member": "", "type": "", "text": ""}

    def names(self) -> list[str]:
        members = self.file.data.get("members", {})
        pat = self.pattern
        return sorted(n for n in members if pat in ("*ALL", "") or fnmatch.fnmatchcase(n, pat))

    def screen(self, message: str = "") -> Screen:
        if self.mode == "confirm":
            return self._confirm(message)
        if self.mode == "new":
            return self._new(message)
        names = self.names()
        pages = max(1, -(-len(names) // self.PER_PAGE))
        self.page = max(0, min(self.page, pages - 1))
        shown = names[self.page * self.PER_PAGE:(self.page + 1) * self.PER_PAGE]
        members = self.file.data.get("members", {})
        rows: list = [
            _title("Work with Members Using PDM", 27), Text(0, 72, SYSTEM_NAME, ds.ATTR_GREEN),
            Text(1, 1, "File  . . . . . .   " + self.file.name, ds.ATTR_GREEN),
            Text(2, 1, "  Library  . . . .     " + self.file.library, ds.ATTR_GREEN),
            Text(2, 40, "Position to  . . . . .", ds.ATTR_GREEN), Input(2, 63, 10, "pos", monocase=True),
            Text(4, 1, "Type options, press Enter.", ds.ATTR_BLUE),
            Text(5, 3, "2=Edit  3=Copy  4=Delete  5=Display  7=Rename  13=Chg text  14=Compile", ds.ATTR_BLUE),
            Text(7, 1, "Opt  Member       Type        Text", ds.ATTR_WHITE),
        ]
        for i, name in enumerate(shown):
            m = members[name]
            r = 8 + i
            rows += [Input(r, 1, 2, f"opt{i}", monocase=True), Text(r, 6, name, ds.ATTR_GREEN),
                     Text(r, 19, m.get("type", "")[:10], ds.ATTR_GREEN), Text(r, 31, m.get("text", "")[:48], ds.ATTR_GREEN)]
        rows.append(Text(18, 67, "More..." if self.page < pages - 1 else "Bottom", ds.ATTR_WHITE))
        rows += [Text(19, 1, "Parameters or command", ds.ATTR_GREEN), Text(20, 1, "===>", ds.ATTR_GREEN),
                 Input(CMD_ROW, CMD_COL, CMD_LEN, "command"),
                 Text(21, 1, "F3=Exit   F5=Refresh   F6=Create   F12=Cancel", ds.ATTR_BLUE)]
        _msg(rows, message)
        return Screen(rows, cursor="opt0" if shown else "command")

    def _confirm(self, message: str) -> Screen:
        rows: list = [_title("Confirm Delete of Members", 27),
                      Text(2, 1, "Press Enter to confirm your choices for 4=Delete.", ds.ATTR_BLUE),
                      Text(3, 1, "Press F12 to return to change your choices.", ds.ATTR_BLUE),
                      Text(5, 1, "Opt  Member       Type", ds.ATTR_WHITE)]
        members = self.file.data.get("members", {})
        for i, name in enumerate(self.pending[:14]):
            rows += [Text(6 + i, 3, "4", ds.ATTR_GREEN), Text(6 + i, 6, name, ds.ATTR_GREEN),
                     Text(6 + i, 19, members.get(name, {}).get("type", ""), ds.ATTR_GREEN)]
        rows.append(Text(21, 1, "F11=Display names and text   F12=Cancel", ds.ATTR_BLUE))
        _msg(rows, message)
        return Screen(rows)

    def _new(self, message: str) -> Screen:
        d = self.draft
        rows: list = [_title("Create Member", 33),
                      Text(2, 1, "Type choices, press Enter.", ds.ATTR_BLUE),
                      Text(4, 1, "Member . . . . . . . . . . . . . .", ds.ATTR_GREEN), Input(4, 37, 10, "member", monocase=True, value=d["member"]),
                      Text(5, 1, "Source type  . . . . . . . . . . .", ds.ATTR_GREEN), Input(5, 37, 10, "type", monocase=True, value=d["type"]),
                      Text(6, 1, "Text 'description'  . . . . . . . .", ds.ATTR_GREEN), Input(6, 37, 40, "text", value=d["text"]),
                      Text(21, 1, "F3=Exit   F12=Cancel", ds.ATTR_BLUE)]
        _msg(rows, message)
        return Screen(rows, cursor="member")

    # -- keys ---------------------------------------------------------------------------------------------

    def handle(self, aid: str, values: dict[str, str]) -> Step:
        if self.mode == "confirm":
            return self._in_confirm(aid)
        if self.mode == "new":
            return self._in_new(aid, values)
        if aid == "F3":
            return Step(go="menu")
        if aid == "F12":
            return Step(go="back")
        if aid in ("ROLLUP", "ROLLDOWN"):
            self.page += 1 if aid == "ROLLUP" else -1
            return Step()
        if aid == "F5":
            return Step()
        if aid == "F6":
            self.mode = "new"
            self.draft = {"member": "", "type": "", "text": ""}
            return Step()
        pos = values.get("pos", "").strip().upper()
        if pos:
            names = self.names()
            self.page = next((i // self.PER_PAGE for i, n in enumerate(names) if n >= pos), self.page)
        names = self.names()
        param = values.get("command", "").strip()
        picks = []
        for i in range(self.PER_PAGE):
            opt = values.get(f"opt{i}", "").strip()
            idx = self.page * self.PER_PAGE + i
            if opt and idx < len(names):
                picks.append((names[idx], opt))
        deletes = [n for n, o in picks if o == "4"]
        if deletes:
            if not source.can_write(self.ctx.store, self.ctx.profile, self.file):
                return Step(f"You do not have authority to file {self.file.name} in {self.file.library}.")
            self.mode, self.pending = "confirm", deletes
            return Step()
        for name, opt in picks:
            step = self._option(name, opt, param)
            if step.message or step.go != "stay":
                return step
        if not picks and param:
            out = self.ctx.run(param)
            if out.view:
                return Step("That command needs a full display. Leave PDM and run it from the command line.")
            return Step(out.message.text if out.message else "")
        return Step()

    def _option(self, name: str, opt: str, param: str) -> Step:
        ctx, f = self.ctx, self.file
        if opt in ("2", "5"):
            editor, err = Editor.open(ctx, f, name, browse=(opt == "5"))
            return Step(err) if err else Step(go="open", widget=editor)
        if opt == "13":
            if not source.can_write(ctx.store, ctx.profile, f):
                return Step(f"You do not have authority to file {f.name} in {f.library}.")
            source.put_member(ctx.store, f, name, f.data["members"][name]["lines"], text=param[:50])
            return Step(f"Text of member {name} changed.")
        if opt in ("3", "7"):
            new = param.upper()
            if not new or not source.NAME.match(new):
                return Step("Type the new member name on the command line.")
            if not source.can_write(ctx.store, ctx.profile, f):
                return Step(f"You do not have authority to file {f.name} in {f.library}.")
            if source.member(f, new):
                return Step(f"Member {new} already exists in file {f.name}.")
            m = f.data["members"][name]
            source.put_member(ctx.store, f, new, list(m["lines"]), m.get("type", ""), m.get("text", ""))
            if opt == "7":
                source.delete_member(ctx.store, f, name)
            return Step(f"Member {name} {'copied' if opt == '3' else 'renamed'} to {new}.")
        if opt == "14":
            typ = f.data["members"][name].get("type", "").upper()
            cmd = TYPE_COMMANDS.get(typ)
            if cmd is None:
                return Step(f"Member type {typ or '(blank)'} cannot be compiled.")
            if cmd == "CRTBNDRPG":
                line = f"CRTBNDRPG PGM({f.library}/{name}) SRCFILE({f.library}/{f.name}) SRCMBR({name})"
            else:
                line = f"{cmd} FILE({f.library}/{name}) SRCFILE({f.library}/{f.name}) SRCMBR({name})"
            out = ctx.run(line)
            return Step(out.message.text if out.message else "")
        return Step(f"Option {opt} is not valid." if opt not in ("6", "8", "9", "15", "16", "17") else
                    f"Option {opt} is not built yet.")

    def _in_confirm(self, aid: str) -> Step:
        if aid == "F12":
            self.mode = "list"
            return Step()
        if aid == "ENTER":
            for name in self.pending:
                source.delete_member(self.ctx.store, self.file, name)
            n = len(self.pending)
            self.mode, self.pending = "list", []
            return Step(f"{n} member{'s' if n != 1 else ''} deleted.")
        return Step()

    def _in_new(self, aid: str, values: dict[str, str]) -> Step:
        if aid in ("F12", "F3"):
            self.mode = "list"
            return Step()
        for k in ("member", "type", "text"):
            self.draft[k] = values.get(k, self.draft[k]).strip()
        name = self.draft["member"].upper()
        if not source.NAME.match(name):
            return Step("Type a member name.")
        if source.member(self.file, name):
            return Step(f"Member {name} already exists in file {self.file.name}.")
        if not source.can_write(self.ctx.store, self.ctx.profile, self.file):
            return Step(f"You do not have authority to file {self.file.name} in {self.file.library}.")
        editor, err = Editor.open(self.ctx, self.file, name, new=True, type_=self.draft["type"].upper(),
                                  text=self.draft["text"])
        self.mode = "list"
        return Step(err) if err else Step(go="open", widget=editor)


# -- STRSEU ------------------------------------------------------------------------------------------------

ROWS_FIRST, ROWS_LAST = 3, 20          # the lines of source are drawn on rows 3 to 20
DATA_COL, DATA_LEN, PFX_LEN = 8, 71, 7
_PREFIX = re.compile(r"^([A-Za-z]{1,2})(\d*)$")


def _ruler() -> str:
    out = []
    for c in range(1, DATA_LEN + 1):
        out.append(str(c // 10 % 10) if c % 10 == 0 else ("+" if c % 10 == 5 else "."))
    return "".join(out)


class Editor:
    """Source Entry Utility, small. A line is [text, id]; the ids stay put while lines move so a block
    command typed on one screen can be finished on a later one."""

    def __init__(self, ctx: Context, file: SecuredObject, name: str, lines: list[str], browse: bool, new: bool,
                 type_: str, text: str) -> None:
        self.ctx, self.file, self.name, self.browse, self.new = ctx, file, name, browse, new
        self.type, self.text = type_, text
        self._next = 0
        self.lines = [self._line(t) for t in lines]
        self.top = 0                             # index into the display items
        self.dirty = False
        self.inserts: dict[int, int] = {}        # line id -> blank lines being entered after it
        self.block: tuple[str, int] | None = None   # (command, line id) of an unfinished DD, CC, MM or RR
        self.carry: tuple[str, list[int]] | None = None   # ("C" or "M", line ids) waiting for A or B
        self.mode = "edit"                       # edit or exit
        self.exit_draft = {"save": "Y", "member": name, "text": text, "back": "N"}
        self.shown: list[tuple] = []             # what the last draw put on each row, to read the answers back
        self.find_text = ""

    def _line(self, text: str) -> list:
        self._next += 1
        return [text, self._next]

    @classmethod
    def open(cls, ctx: Context, file: SecuredObject, name: str, browse: bool = False, new: bool = False,
             type_: str = "", text: str = ""):
        name = name.upper()
        m = source.member(file, name)
        if m is None and not new:
            return None, f"Member {name} not found in file {file.name}."
        if not browse and not source.can_write(ctx.store, ctx.profile, file):
            return None, f"You do not have authority to edit member {name}. Use option 5 to display it."
        if browse and (Auth.READ & ~ctx.store.authority_to_object(ctx.profile, file)):
            return None, f"You do not have authority to file {file.name} in {file.library}."
        key = (file.library, file.name, name)
        who = ctx.session.job.qualified if ctx.session.job else ctx.profile.name
        if not browse:
            holder = ctx.store.member_locks.get(key)
            if holder and holder != who:
                return None, f"Member {name} of file {file.name} in library {file.library} is in use."
            ctx.store.member_locks[key] = who
        ed = cls(ctx, file, name, list((m or {}).get("lines", [])), browse, new and m is None,
                 (m or {}).get("type", type_), (m or {}).get("text", text))
        ed.lock_key = None if browse else key
        return ed, ""

    lock_key = None

    def release(self) -> None:
        if self.lock_key is not None:
            self.ctx.store.member_locks.pop(self.lock_key, None)
            self.lock_key = None

    # -- drawing ------------------------------------------------------------------------------------------

    def _items(self) -> list[tuple]:
        items: list[tuple] = [("beg",)]
        for idx, (text, lid) in enumerate(self.lines):
            items.append(("line", idx))
            items += [("ins", lid, k) for k in range(self.inserts.get(lid, 0))]
        items.append(("end",))
        return items

    def screen(self, message: str = "") -> Screen:
        if self.mode == "exit":
            return self._exit_screen(message)
        items = self._items()
        height = ROWS_LAST - ROWS_FIRST + 1
        self.top = max(0, min(self.top, max(0, len(items) - 1)))
        window = items[self.top:self.top + height]
        rows: list = [
            Text(0, 1, "Columns . . . :    1  71", ds.ATTR_GREEN), _title("Browse" if self.browse else "Edit", 36),
            Text(0, 79 - len(f"{self.file.library}/{self.file.name}"), f"{self.file.library}/{self.file.name}", ds.ATTR_GREEN),
            Text(1, 1, "SEU==>", ds.ATTR_GREEN), Input(1, 8, 62, "seu"),
            Text(1, 79 - len(self.name), self.name, ds.ATTR_GREEN),
            Text(2, 1, "FMT **", ds.ATTR_BLUE), Text(2, DATA_COL, _ruler(), ds.ATTR_BLUE),
        ]
        self.shown = []
        for i, item in enumerate(window):
            r = ROWS_FIRST + i
            self.shown.append(item)
            if item[0] == "beg":
                rows.append(Text(r, DATA_COL, "*" * 16 + " Beginning of data " + "*" * 36, ds.ATTR_BLUE))
            elif item[0] == "end":
                rows.append(Text(r, DATA_COL, "*" * 19 + " End of data " + "*" * 39, ds.ATTR_BLUE))
            elif item[0] == "line":
                idx = item[1]
                text = self.lines[idx][0]
                rows.append(Input(r, 0, PFX_LEN, f"p{i}", monocase=True, value=f"{idx + 1:04d}.00"))
                rows.append(Input(r, DATA_COL, DATA_LEN, f"d{i}", value=text[:DATA_LEN]) if not self.browse
                            else Text(r, DATA_COL, text[:DATA_LEN], ds.ATTR_GREEN))
            else:
                rows.append(Input(r, 0, PFX_LEN, f"p{i}", monocase=True, value=""))
                rows.append(Input(r, DATA_COL, DATA_LEN, f"d{i}", value=""))
        keys = "F3=Exit   F5=Refresh   F12=Cancel   F23=Select prompt" if not self.browse else "F3=Exit   F12=Cancel"
        rows.append(Text(21, 1, keys, ds.ATTR_BLUE))
        if self.block or self.carry:
            pending = (f"Block {self.block[0]} started." if self.block else
                       f"{'Copy' if self.carry[0] == 'C' else 'Move'} waiting for A or B.")
            message = message or pending
        _msg(rows, message)
        return Screen(rows, cursor="seu")

    def _exit_screen(self, message: str) -> Screen:
        d = self.exit_draft
        rows: list = [
            _title("Exit", 38), Text(2, 1, "Type choices, press Enter.", ds.ATTR_BLUE),
            Text(4, 3, "Change/create member . . . . . . . .", ds.ATTR_GREEN), Input(4, 41, 1, "save", monocase=True, value=d["save"]),
            Text(4, 46, "Y=Yes, N=No", ds.ATTR_BLUE),
            Text(5, 3, "Member . . . . . . . . . . . . . . .", ds.ATTR_GREEN), Input(5, 41, 10, "member", monocase=True, value=d["member"]),
            Text(6, 3, "File . . . . . . . . . . . . . . . .", ds.ATTR_GREEN), Text(6, 41, self.file.name, ds.ATTR_GREEN),
            Text(7, 5, "Library  . . . . . . . . . . . . .", ds.ATTR_GREEN), Text(7, 41, self.file.library, ds.ATTR_GREEN),
            Text(8, 3, "Text . . . . . . . . . . . . . . . .", ds.ATTR_GREEN), Input(8, 41, 40, "text", value=d["text"]),
            Text(10, 3, "Return to editing  . . . . . . . . .", ds.ATTR_GREEN), Input(10, 41, 1, "back", monocase=True, value=d["back"]),
            Text(21, 1, "F3=Exit   F12=Cancel", ds.ATTR_BLUE),
        ]
        _msg(rows, message)
        return Screen(rows, cursor="save")

    # -- keys ---------------------------------------------------------------------------------------------

    def handle(self, aid: str, values: dict[str, str]) -> Step:
        if self.mode == "exit":
            return self._in_exit(aid, values)
        if aid == "F3" or aid == "F12":
            if self.browse or not self.dirty:
                self.release()
                return Step(go="back")
            self.mode = "exit"
            return Step()
        if aid in ("ROLLUP", "ROLLDOWN"):
            self.top += (ROWS_LAST - ROWS_FIRST) if aid == "ROLLUP" else -(ROWS_LAST - ROWS_FIRST)
            self.top = max(0, self.top)
            return Step()
        if aid == "F5":
            return Step()
        message = ""
        if not self.browse:
            message = self._apply(values)
        cmd = values.get("seu", "").strip()
        if cmd:
            step = self._command(cmd)
            if step.message or step.go != "stay":
                return step if not message else Step(message, step.go, step.widget)
        return Step(message)

    def _apply(self, values: dict[str, str]) -> str:
        """The typed data first (changed lines, new lines in the blanks that I opened), then the line commands
        in the order they sit on the screen."""
        cmds: list[tuple[int, str, int]] = []
        new_for: dict[int, list[str]] = {}
        for i, item in enumerate(self.shown):
            if item[0] == "line":
                idx = item[1]
                lid = self.lines[idx][1]
                old = self.lines[idx][0]
                if f"d{i}" in values:
                    typed = values[f"d{i}"].ljust(DATA_LEN)[:DATA_LEN]
                    updated = (typed + old[DATA_LEN:]).rstrip()
                    if updated != old:
                        self.lines[idx][0] = updated
                        self.dirty = True
                parsed = self._prefix(values[f"p{i}"], f"{idx + 1:04d}.00") if f"p{i}" in values else None
                if parsed:
                    cmds.append((lid, *parsed))
            elif item[0] == "ins":
                text = values.get(f"d{i}", "").rstrip()
                if text:
                    new_for.setdefault(item[1], []).append(text)
        for lid in list(self.inserts):
            self.inserts.pop(lid)
        for lid, texts in new_for.items():
            at = self._index(lid) + 1
            for text in texts:
                self.lines.insert(at, self._line(text))
                at += 1
            self.dirty = True
        error = ""
        cmds.sort(key=lambda c: c[1] in ("A", "B"))        # a copy or move target is used after its source is picked
        for lid, cmd, count in cmds:
            error = self._line_command(lid, cmd, count) or error
        return error

    @staticmethod
    def _prefix(value: str, original: str) -> tuple[str, int] | None:
        """What was typed over the sequence number. The field comes back whole, with the typed characters laid over the
        number, so only the characters up to the last one that differs from it were typed."""
        value = value.ljust(len(original))
        diff = [i for i, (a, b) in enumerate(zip(value, original)) if a != b]
        if not diff:
            return None
        typed = value[:diff[-1] + 1].strip()
        if not typed:
            return None
        m = _PREFIX.match(typed)
        if not m:
            return ("?", 0)
        return m.group(1).upper(), int(m.group(2)) if m.group(2) else 0

    def _index(self, lid: int) -> int:
        return next(i for i, (_, x) in enumerate(self.lines) if x == lid)

    def _line_command(self, lid: int, cmd: str, count: int) -> str:
        n = max(1, count)
        i = self._index(lid)
        if cmd == "I":
            self.inserts[lid] = n
            return ""
        if cmd == "D":
            del self.lines[i:i + n]
            self.dirty = True
            return ""
        if cmd == "R":
            for _ in range(n):
                self.lines.insert(i + 1, self._line(self.lines[i][0]))
            self.dirty = True
            return ""
        if cmd in ("C", "M"):
            self.carry = (cmd, [x for _, x in self.lines[i:i + n]])
            return ""
        if cmd in ("DD", "CC", "MM", "RR"):
            if self.block and self.block[0] == cmd:
                start = self._index(self.block[1])
                a, b = sorted((start, i))
                self.block = None
                return self._block(cmd, a, b)
            self.block = (cmd, lid)
            return ""
        if cmd in ("A", "B"):
            if not self.carry:
                return "A and B need a copy or move waiting."
            kind, ids = self.carry
            self.carry = None
            texts = [self.lines[self._index(x)][0] for x in ids]
            at = self._index(lid) + (1 if cmd == "A" else 0)
            if kind == "M":
                at -= sum(1 for x in ids if self._index(x) < at)
                self.lines[:] = [ln for ln in self.lines if ln[1] not in ids]
            for text in texts:
                self.lines.insert(at, self._line(text))
                at += 1
            self.dirty = True
            return ""
        return f"Line command {cmd} is not valid."

    def _block(self, cmd: str, a: int, b: int) -> str:
        if cmd == "DD":
            del self.lines[a:b + 1]
            self.dirty = True
        elif cmd == "RR":
            copy = [self._line(t) for t, _ in self.lines[a:b + 1]]
            self.lines[b + 1:b + 1] = copy
            self.dirty = True
        else:
            self.carry = ("C" if cmd == "CC" else "M", [x for _, x in self.lines[a:b + 1]])
        return ""

    def _command(self, text: str) -> Step:
        word, _, rest = text.partition(" ")
        word = word.upper()
        items = self._items()
        if word in ("T", "TOP"):
            self.top = 0
        elif word in ("B", "BOT", "BOTTOM"):
            self.top = max(0, len(items) - (ROWS_LAST - ROWS_FIRST + 1))
        elif word in ("F", "FIND"):
            return self._find(rest.strip().strip("'\""))
        elif word in ("C", "CHANGE") and not self.browse:
            return self._change(rest)
        elif word == "SAVE" and not self.browse:
            self._save(self.name, self.text)
            return Step(f"Member {self.name} saved.")
        elif word == "FILE" and not self.browse:
            self._save(self.name, self.text)
            self.release()
            return Step(f"Member {self.name} saved.", go="back")
        elif word == "CANCEL":
            self.release()
            return Step(go="back")
        else:
            return Step(f"Command {word} is not valid.")
        return Step()

    def _find(self, needle: str) -> Step:
        needle = needle or self.find_text
        if not needle:
            return Step("Type what to find.")
        self.find_text = needle
        start = 0
        for item in self._items()[self.top:self.top + 1]:
            start = item[1] + 1 if item[0] == "line" else 0
        order = list(range(start, len(self.lines))) + list(range(0, start))
        for idx in order:
            if needle.upper() in self.lines[idx][0].upper():
                pos = next(k for k, it in enumerate(self._items()) if it == ("line", idx))
                self.top = max(0, pos - 1)
                return Step(f"'{needle}' found on line {idx + 1}.")
        return Step(f"'{needle}' was not found.")

    def _change(self, rest: str) -> Step:
        m = re.match(r"""\s*(['"])(.*?)\1\s+(['"])(.*?)\3\s*(ALL)?\s*$""", rest, re.I)
        if not m:
            return Step("Use CHANGE 'old' 'new' or CHANGE 'old' 'new' ALL.")
        old, new, everywhere = m.group(2), m.group(4), bool(m.group(5))
        count = 0
        for ln in self.lines:
            if old.lower() in ln[0].lower():
                pat = re.compile(re.escape(old), re.I)
                ln[0] = pat.sub(lambda _: new, ln[0], count=0 if everywhere else 1)
                count += 1
                self.dirty = True
                if not everywhere:
                    break
        return Step(f"{count} line{'s' if count != 1 else ''} changed." if count else f"'{old}' was not found.")

    def _save(self, name: str, text: str) -> None:
        store = self.ctx.store
        m = source.put_member(store, self.file, name, [t for t, _ in self.lines], self.type, text)
        self.new = False
        self.dirty = False
        self.name, self.text = name.upper(), text
        if m.get("type", "") == "" and self.type:
            m["type"] = self.type

    def _in_exit(self, aid: str, values: dict[str, str]) -> Step:
        d = self.exit_draft
        if aid in ("F12",):
            self.mode = "edit"
            return Step()
        for k in ("save", "member", "text", "back"):
            d[k] = values.get(k, d[k]).strip()
        if d["back"].upper() == "Y":
            self.mode = "edit"
            return Step()
        if d["save"].upper() == "Y":
            name = d["member"].upper()
            if not source.NAME.match(name):
                return Step("Type a member name.")
            self._save(name, d["text"])
            self.release()
            return Step(f"Member {name} saved.", go="back")
        self.release()
        return Step(go="back")
