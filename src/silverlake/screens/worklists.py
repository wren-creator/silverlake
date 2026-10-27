"""The three "work with" lists, laid out like the real displays captured from PUB400 (Work with
Objects, Work with Objects by Owner, Work with Authorization Lists): option column, headers,
a 73 long command line at row 20 column 6, and the key lines. The wording of what the options
do is ours; their numbers and labels, and every position, are from the capture.

Each list is a WorkList. The controller owns paging and option handling."""

from dataclasses import dataclass, field
from typing import Callable

from ..proto import datastream as ds
from .model import Input, Screen, Text

COMMAND_ROW, COMMAND_COL, COMMAND_LEN = 20, 6, 73


@dataclass
class WorkList:
    kind: str                          # "objects", "owner" or "autls"
    rows: list
    requery: Callable[[], list]
    owner: str = ""                    # the profile named at the top of "owner"
    page: int = 0
    per_page: int = field(init=False)
    first_row: int = field(init=False)

    def __post_init__(self) -> None:
        self.per_page, self.first_row = {"objects": (11, 7), "owner": (8, 10), "autls": (10, 8)}[self.kind]

    @property
    def pages(self) -> int:
        return max(1, -(-len(self.rows) // self.per_page))

    def shown(self) -> list:
        self.page = max(0, min(self.page, self.pages - 1))
        return self.rows[self.page * self.per_page:(self.page + 1) * self.per_page]

    def refresh(self) -> None:
        self.rows = self.requery()
        self.page = max(0, min(self.page, self.pages - 1))

    def screen(self, message: str = "") -> Screen:
        return {"objects": _objects, "owner": _owner, "autls": _autls}[self.kind](self, message)


def _tail(rows: list, wl: WorkList, prompt: str, keys1: list[tuple[int, str]], keys2: list[tuple[int, str]],
          message: str) -> Screen:
    rows.append(Text(18, 67, "More..." if wl.page < wl.pages - 1 else "Bottom", ds.ATTR_BLUE))
    rows += [Text(19, 1, prompt, ds.ATTR_GREEN), Text(20, 1, "===>", ds.ATTR_GREEN),
             Input(COMMAND_ROW, COMMAND_COL, COMMAND_LEN, "command")]
    rows += [Text(21, c, t, ds.ATTR_BLUE) for c, t in keys1]
    rows += [Text(22, c, t, ds.ATTR_BLUE) for c, t in keys2]
    if message:
        rows.append(Text(23, 1, message[:77], ds.ATTR_WHITE))
        if len(message) > 77:
            rows.append(Text(23, 78, "+", ds.ATTR_WHITE))
    first = "optnew" if wl.kind == "autls" else ("opt0" if wl.shown() else "command")
    return Screen(rows, cursor=first)


def _opts(rows: list, wl: WorkList, count: int, first: int) -> None:
    """Real option fields are monocase. On Work with Objects by Owner they are one character
    at column 2, on the other two lists two characters at column 1 (all seen in the capture)."""
    col, length = (2, 1) if wl.kind == "owner" else (1, 2)
    for i in range(count):
        rows.append(Input(first + i, col, length, f"opt{i}", monocase=True))


def _objects(wl: WorkList, message: str) -> Screen:
    rows: list = [
        Text(0, 31, "Work with Objects", ds.ATTR_WHITE),
        Text(2, 1, "Type options, press Enter.", ds.ATTR_BLUE),
        Text(3, 3, "2=Edit authority", ds.ATTR_BLUE), Text(3, 27, "3=Copy", ds.ATTR_BLUE),
        Text(3, 36, "4=Delete", ds.ATTR_BLUE), Text(3, 47, "5=Display authority", ds.ATTR_BLUE),
        Text(3, 69, "7=Rename", ds.ATTR_BLUE),
        Text(4, 3, "8=Display description", ds.ATTR_BLUE), Text(4, 27, "13=Change description", ds.ATTR_BLUE),
        Text(6, 1, "Opt", ds.ATTR_WHITE), Text(6, 6, "Object", ds.ATTR_WHITE), Text(6, 18, "Type", ds.ATTR_WHITE),
        Text(6, 28, "Library", ds.ATTR_WHITE), Text(6, 40, "Attribute", ds.ATTR_WHITE),
        Text(6, 52, "Text", ds.ATTR_WHITE),
    ]
    shown = wl.shown()
    _opts(rows, wl, len(shown), 7)
    for i, o in enumerate(shown):
        r = 7 + i
        rows += [Text(r, 6, o.name, ds.ATTR_TURQUOISE), Text(r, 18, o.type, ds.ATTR_TURQUOISE),
                 Text(r, 28, o.library, ds.ATTR_TURQUOISE)]
        if o.type == "*LIB":
            rows.append(Text(r, 40, "PROD", ds.ATTR_TURQUOISE))      # seen on every library in the capture
        if o.text:
            rows.append(Text(r, 52, o.text[:27], ds.ATTR_TURQUOISE))
    return _tail(rows, wl, "Parameters for options 5, 7 and 13 or command",
                 [(1, "F3=Exit"), (11, "F4=Prompt"), (23, "F5=Refresh"), (36, "F9=Retrieve"),
                  (50, "F11=Display names and types")],
                 [(1, "F12=Cancel"), (14, "F16=Repeat position to"), (39, "F17=Position to")], message)


def _owner(wl: WorkList, message: str) -> Screen:
    rows: list = [
        Text(0, 27, "Work with Objects by Owner", ds.ATTR_WHITE),
        Text(2, 1, "User profile . . . . . . . :", ds.ATTR_GREEN), Text(2, 32, wl.owner, ds.ATTR_WHITE),
        Text(4, 1, "Type options, press Enter.", ds.ATTR_BLUE),
        Text(5, 3, "2=Edit authority", ds.ATTR_BLUE), Text(5, 27, "4=Delete", ds.ATTR_BLUE),
        Text(5, 38, "5=Display authority", ds.ATTR_BLUE), Text(5, 60, "7=Rename", ds.ATTR_BLUE),
        Text(6, 3, "8=Display description", ds.ATTR_BLUE), Text(6, 27, "9=Change owner", ds.ATTR_BLUE),
        Text(8, 64, "ASP", ds.ATTR_WHITE),
        Text(9, 1, "Opt", ds.ATTR_WHITE), Text(9, 6, "Object", ds.ATTR_WHITE), Text(9, 28, "Library", ds.ATTR_WHITE),
        Text(9, 42, "Type", ds.ATTR_WHITE), Text(9, 52, "Attribute", ds.ATTR_WHITE),
        Text(9, 64, "Device", ds.ATTR_WHITE),
    ]
    shown = wl.shown()
    _opts(rows, wl, len(shown), 10)
    for i, o in enumerate(shown):
        r = 10 + i
        rows += [Text(r, 6, o.name, ds.ATTR_TURQUOISE), Text(r, 28, o.library, ds.ATTR_TURQUOISE),
                 Text(r, 42, o.type, ds.ATTR_TURQUOISE)]
        if o.type == "*LIB":
            rows.append(Text(r, 52, "PROD", ds.ATTR_TURQUOISE))
        rows.append(Text(r, 64, "*SYSBAS", ds.ATTR_TURQUOISE))
    return _tail(rows, wl, "Parameters or command",
                 [(1, "F3=Exit"), (14, "F4=Prompt"), (26, "F5=Refresh"), (39, "F9=Retrieve"),
                  (53, "F11=Display descriptions")],
                 [(1, "F12=Cancel"), (14, "F17=Top"), (26, "F18=Bottom"), (39, "F22=Display entire name")], message)


def _autls(wl: WorkList, message: str) -> Screen:
    rows: list = [
        Text(0, 25, "Work with Authorization Lists", ds.ATTR_WHITE),
        Text(2, 1, "Type options, press Enter.", ds.ATTR_BLUE),
        Text(3, 3, "1=Create", ds.ATTR_BLUE), Text(3, 14, "2=Edit", ds.ATTR_BLUE), Text(3, 23, "4=Delete", ds.ATTR_BLUE),
        Text(3, 41, "5=Display", ds.ATTR_BLUE), Text(3, 53, "8=Display objects in list", ds.ATTR_BLUE),
        Text(4, 3, "9=Display documents/folders in list", ds.ATTR_BLUE), Text(4, 41, "13=Change description", ds.ATTR_BLUE),
        Text(6, 1, "Opt", ds.ATTR_WHITE), Text(6, 6, "List", ds.ATTR_WHITE), Text(6, 18, "Text", ds.ATTR_WHITE),
        Input(7, 1, 2, "optnew", monocase=True), Input(7, 6, 10, "newname", monocase=True),     # the create row
    ]
    shown = wl.shown()
    _opts(rows, wl, len(shown), 8)
    for i, a in enumerate(shown):
        r = 8 + i
        rows.append(Text(r, 6, a.name, ds.ATTR_TURQUOISE))
        if a.text:
            rows.append(Text(r, 18, a.text[:50], ds.ATTR_TURQUOISE))
    return _tail(rows, wl, "Parameters for options 1, 5, 8, 9 and 13 or command",
                 [(1, "F3=Exit"), (14, "F4=Prompt"), (26, "F5=Refresh"), (39, "F9=Retrieve"),
                  (53, "F11=Display names only")],
                 [(1, "F12=Cancel"), (14, "F16=Repeat position to"), (39, "F17=Position to")], message)


def objects_in_list_screen(autl: str, objs: list, page: int = 0) -> Screen:
    """Option 8 on a list. The real display was not captured, so this layout is ours."""
    per = 10
    pages = max(1, -(-len(objs) // per))
    page = max(0, min(page, pages - 1))
    rows: list = [
        Text(0, 22, "Display Authorization List Objects", ds.ATTR_WHITE),
        Text(1, 1, "Authorization list . . . :", ds.ATTR_GREEN), Text(1, 28, autl, ds.ATTR_WHITE),
        Text(3, 1, "Object", ds.ATTR_WHITE), Text(3, 13, "Library", ds.ATTR_WHITE),
        Text(3, 25, "Type", ds.ATTR_WHITE), Text(3, 35, "Owner", ds.ATTR_WHITE),
    ]
    for i, o in enumerate(objs[page * per:(page + 1) * per]):
        r = 4 + i
        rows += [Text(r, 1, o.name, ds.ATTR_TURQUOISE), Text(r, 13, o.library, ds.ATTR_TURQUOISE),
                 Text(r, 25, o.type, ds.ATTR_TURQUOISE), Text(r, 35, o.owner, ds.ATTR_TURQUOISE)]
    rows.append(Text(18, 67, "More..." if page < pages - 1 else "Bottom", ds.ATTR_BLUE))
    rows.append(Text(21, 1, "F3=Exit   F12=Cancel", ds.ATTR_BLUE))
    return Screen(rows)
