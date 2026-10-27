"""The three "work with" lists, laid out like the real displays captured from PUB400 (Work with
Objects, Work with Objects by Owner, Work with Authorization Lists): option column, headers,
a 73 long command line at row 20 column 6, and the key lines. The wording of what the options
do is ours; their numbers and labels, and every position, are from the capture.

Each list is a WorkList. The controller owns paging and option handling."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable

from ..proto import datastream as ds
from .model import Input, Screen, Text

COMMAND_ROW, COMMAND_COL, COMMAND_LEN = 20, 6, 73


@dataclass
class WorkList:
    kind: str                          # "objects", "owner", "autls" or "jobs"
    rows: list
    requery: Callable[[], list]
    owner: str = ""                    # the profile named at the top of "owner"
    retained: dict = field(default_factory=dict)   # options typed before a confirm screen was cancelled
    page: int = 0
    per_page: int = field(init=False)
    first_row: int = field(init=False)

    def __post_init__(self) -> None:
        self.per_page, self.first_row = {"objects": (11, 7), "owner": (8, 10), "autls": (10, 8), "jobs": (9, 9), "spool": (9, 9)}[self.kind]

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
        return {"objects": _objects, "owner": _owner, "autls": _autls, "jobs": _jobs, "spool": _spool}[self.kind](self, message)


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
        rows.append(Input(first + i, col, length, f"opt{i}", monocase=True,
                          value=wl.retained.get(wl.page * wl.per_page + i, "")))


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
    if not shown:                      # seen after the last object on the list was deleted
        rows.append(Text(8, 3, "(Cannot find object to match specified name.)", ds.ATTR_BLUE))
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


def _jobs(wl: WorkList, message: str) -> Screen:
    """Work with Active Jobs, laid out like the real display (captured). `owner` holds the
    viewer's own job, which shows what it is doing right now."""
    from ..system.jobs import now_stamp
    date, clock = now_stamp()
    rows: list = [
        Text(0, 29, "Work with Active Jobs", ds.ATTR_WHITE), Text(0, 71, "SILVERLK", ds.ATTR_WHITE),
        Text(1, 57, date, ds.ATTR_WHITE), Text(1, 67, clock, ds.ATTR_WHITE),
        Text(2, 1, "CPU %:", ds.ATTR_GREEN), Text(2, 10, "  0,0", ds.ATTR_WHITE),
        Text(2, 20, "Elapsed time:", ds.ATTR_GREEN), Text(2, 36, "00:00:00", ds.ATTR_WHITE),
        Text(2, 49, "Active jobs:", ds.ATTR_GREEN), Text(2, 64, str(len(wl.rows)), ds.ATTR_WHITE),
        Text(4, 1, "Type options, press Enter.", ds.ATTR_BLUE),
        Text(5, 3, "2=Change", ds.ATTR_BLUE), Text(5, 14, "3=Hold", ds.ATTR_BLUE), Text(5, 23, "4=End", ds.ATTR_BLUE),
        Text(5, 31, "5=Work with", ds.ATTR_BLUE), Text(5, 45, "6=Release", ds.ATTR_BLUE),
        Text(5, 57, "7=Display message", ds.ATTR_BLUE),
        Text(6, 3, "8=Work with spooled files", ds.ATTR_BLUE), Text(6, 31, "13=Disconnect ...", ds.ATTR_BLUE),
        Text(7, 21, "Current", ds.ATTR_WHITE),
        Text(8, 1, "Opt", ds.ATTR_WHITE), Text(8, 6, "Subsystem/Job", ds.ATTR_WHITE), Text(8, 21, "User", ds.ATTR_WHITE),
        Text(8, 33, "Type", ds.ATTR_WHITE), Text(8, 39, "CPU %", ds.ATTR_WHITE),
        Text(8, 46, "Function", ds.ATTR_WHITE), Text(8, 62, "Status", ds.ATTR_WHITE),
    ]
    for i, j in enumerate(wl.shown()):
        r = wl.first_row + i
        mine = j.qualified == wl.owner
        rows.append(Input(r, 1, 2, f"opt{i}", monocase=True))
        rows += [Text(r, 6, j.name if j.type == "SBS" else "  " + j.name, ds.ATTR_TURQUOISE),
                 Text(r, 21, j.user, ds.ATTR_TURQUOISE), Text(r, 33, j.type, ds.ATTR_TURQUOISE),
                 Text(r, 41, f"{j.cpu:.1f}".replace(".", ","), ds.ATTR_TURQUOISE)]
        function = "CMD-WRKACTJOB" if mine else j.function
        if function:
            rows.append(Text(r, 46, function[:15], ds.ATTR_TURQUOISE))
        rows.append(Text(r, 63, "RUN" if mine else j.status, ds.ATTR_TURQUOISE))
    return _tail(rows, wl, "Parameters or command",
                 [(1, "F3=Exit"), (11, "F5=Refresh"), (28, "F7=Find"), (41, "F10=Restart statistics")],
                 [(1, "F11=Display elapsed data"), (28, "F12=Cancel"), (41, "F23=More options"),
                  (60, "F24=More keys")], message)


def _spool(wl: WorkList, message: str) -> Screen:
    """Work with All Spooled Files, laid out like the real display (captured)."""
    rows: list = [
        Text(0, 26, "Work with All Spooled Files", ds.ATTR_WHITE),
        Text(2, 1, "Type options, press Enter.", ds.ATTR_BLUE),
        Text(3, 3, "1=Send", ds.ATTR_BLUE), Text(3, 12, "2=Change", ds.ATTR_BLUE), Text(3, 23, "3=Hold", ds.ATTR_BLUE),
        Text(3, 32, "4=Delete", ds.ATTR_BLUE), Text(3, 43, "5=Display", ds.ATTR_BLUE),
        Text(3, 55, "6=Release", ds.ATTR_BLUE), Text(3, 67, "7=Messages", ds.ATTR_BLUE),
        Text(4, 3, "8=Attributes", ds.ATTR_BLUE), Text(4, 23, "9=Work with printing status", ds.ATTR_BLUE),
        Text(7, 30, "Device or", ds.ATTR_WHITE), Text(7, 60, "Total", ds.ATTR_WHITE), Text(7, 70, "Cur", ds.ATTR_WHITE),
        Text(8, 1, "Opt", ds.ATTR_WHITE), Text(8, 6, "File", ds.ATTR_WHITE), Text(8, 18, "User", ds.ATTR_WHITE),
        Text(8, 30, "Queue", ds.ATTR_WHITE), Text(8, 42, "User Data", ds.ATTR_WHITE), Text(8, 54, "Sts", ds.ATTR_WHITE),
        Text(8, 60, "Pages", ds.ATTR_WHITE), Text(8, 69, "Page", ds.ATTR_WHITE), Text(8, 75, "Copy", ds.ATTR_WHITE),
    ]
    for i, f in enumerate(wl.shown()):
        r = wl.first_row + i
        rows.append(Input(r, 2, 1, f"opt{i}", monocase=True))
        rows += [Text(r, 6, f.name, ds.ATTR_TURQUOISE), Text(r, 18, f.user, ds.ATTR_TURQUOISE),
                 Text(r, 30, f.outq, ds.ATTR_TURQUOISE), Text(r, 42, f.user_data[:10], ds.ATTR_TURQUOISE),
                 Text(r, 54, f.status, ds.ATTR_TURQUOISE), Text(r, 60, f"{f.pages:>5}", ds.ATTR_TURQUOISE),
                 Text(r, 78, str(f.copies), ds.ATTR_TURQUOISE)]
    return _tail(rows, wl, "Parameters for options 1, 2, 3 or command",
                 [(1, "F3=Exit"), (11, "F10=View 4"), (24, "F11=View 2"), (37, "F12=Cancel"), (50, "F22=Printers"),
                  (65, "F24=More keys")], [], message)


def dspsplf_screen(f, top: int = 0, message: str = "") -> Screen:
    """Display Spooled File, laid out like the real one (captured): a header, a ruler, and sixteen
    lines of the file from row 5. Roll keys move by a screenful. Find and column shifting are not built."""
    shown = f.lines[top:top + 16]
    ruler = "*...+....1....+....2....+....3....+....4....+....5....+....6....+....7....+...."
    rows: list = [
        Text(0, 30, "Display Spooled File", ds.ATTR_WHITE),
        Text(1, 1, "File  . . . . . :", ds.ATTR_GREEN), Text(1, 21, f.name, ds.ATTR_WHITE),
        Text(1, 54, "Page/Line", ds.ATTR_GREEN), Text(1, 66, f"{top // 55 + 1}/{top % 55 + 1}", ds.ATTR_WHITE),
        Text(2, 1, "Control . . . . .", ds.ATTR_GREEN), Input(2, 21, 8, "control"),
        Text(2, 54, "Columns", ds.ATTR_GREEN), Text(2, 66, "1 - 78", ds.ATTR_WHITE),
        Text(3, 1, "Find  . . . . . .", ds.ATTR_GREEN), Input(3, 21, 30, "find"),
        Text(4, 1, ruler, ds.ATTR_BLUE),
    ]
    rows += [Text(5 + i, 0, line[:78], ds.ATTR_WHITE) for i, line in enumerate(shown)]
    more = top + 16 < len(f.lines)
    rows.append(Text(21, 72 if more else 73, "More..." if more else "Bottom", ds.ATTR_BLUE))
    rows.append(Text(22, 1, "F3=Exit   F12=Cancel   F19=Left   F20=Right   F24=More keys", ds.ATTR_BLUE))
    if message:
        rows.append(Text(23, 1, message[:77], ds.ATTR_WHITE))
    return Screen(rows, cursor="control")


def spoolattr_screen(f, system_name: str) -> Screen:
    """Work with Spooled File Attributes, first page, laid out like the real one (captured). The
    second page and F13 (change) are not built."""
    when = f.stamp()
    g = lambda r, c, t: Text(r, c, t, ds.ATTR_GREEN)
    v = lambda r, c, t: Text(r, c, str(t), ds.ATTR_WHITE)
    return Screen([
        Text(0, 23, "Work with Spooled File Attributes", ds.ATTR_WHITE),
        g(2, 1, "Job  . . . . . . . . :"), v(2, 26, f.job_name), g(2, 42, "File . . . . . . . . :"), v(2, 67, f.name),
        g(3, 3, "User . . . . . . . :"), v(3, 28, f.user), g(3, 44, "Number . . . . . . :"), v(3, 69, f"{f.file_no:06d}"),
        g(4, 3, "Number . . . . . . :"), v(4, 28, f.job_number), g(4, 42, "Creation date  . . . :"),
        v(4, 67, when.strftime("%y-%m-%d")),
        g(5, 1, "Job system name  . . :"), v(5, 26, system_name), g(5, 42, "Creation time  . . . :"),
        v(5, 67, when.strftime("%H:%M:%S")),
        g(7, 1, "Status . . . . . . . . . . . . . . . . :"), v(7, 44, "HELD" if f.status == "HLD" else "READY"),
        g(8, 1, "Output queue . . . . . . . . . . . . . :"), v(8, 44, f.outq),
        g(9, 3, "Library  . . . . . . . . . . . . . . :"), v(9, 46, f.outq_lib),
        g(10, 1, "ASP file resides on  . . . . . . . . . :"), v(10, 44, "1"),
        g(11, 1, "Form type  . . . . . . . . . . . . . . :"), v(11, 44, f.form_type),
        g(12, 1, "Output priority  . . . . . . . . . . . :"), v(12, 44, f.priority),
        g(13, 1, "Copies left to produce . . . . . . . . :"), v(13, 44, f.copies),
        g(14, 1, "Total copies . . . . . . . . . . . . . :"), v(14, 44, f.copies),
        g(15, 1, "Maximum records  . . . . . . . . . . . :"), v(15, 44, "*NOMAX"),
        g(16, 1, "Number of separators . . . . . . . . . :"), v(16, 44, "0"),
        g(17, 1, "File becomes available . . . . . . . . :"), v(17, 44, "*FILEEND"),
        g(18, 1, "Hold file before written . . . . . . . :"), v(18, 44, "*NO"),
        Text(19, 72, "More...", ds.ATTR_BLUE),
        Text(20, 1, "Press Enter to continue.", ds.ATTR_BLUE),
        Text(22, 1, "F3=Exit", ds.ATTR_BLUE), Text(22, 11, "F5=Refresh", ds.ATTR_BLUE),
        Text(22, 24, "F12=Cancel", ds.ATTR_BLUE), Text(22, 37, "F13=Change", ds.ATTR_BLUE),
    ])


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


def confirm_delete_screen(picks: list) -> Screen:
    """Laid out like the real Confirm Delete of Objects (captured). One row per object picked."""
    rows: list = [
        Text(0, 27, "Confirm Delete of Objects", ds.ATTR_WHITE),
        Text(2, 1, "Press Enter to confirm your choices for 4=Delete.", ds.ATTR_BLUE),
        Text(3, 1, "Press F12 to return to change your choices.", ds.ATTR_BLUE),
        Text(5, 1, "Opt", ds.ATTR_WHITE), Text(5, 6, "Object", ds.ATTR_WHITE), Text(5, 18, "Type", ds.ATTR_WHITE),
        Text(5, 28, "Library", ds.ATTR_WHITE), Text(5, 40, "Attribute", ds.ATTR_WHITE), Text(5, 52, "Text", ds.ATTR_WHITE),
    ]
    for i, o in enumerate(picks[:14]):
        r = 6 + i
        rows += [Text(r, 1, "4", ds.ATTR_TURQUOISE), Text(r, 6, o.name, ds.ATTR_TURQUOISE),
                 Text(r, 18, o.type, ds.ATTR_TURQUOISE), Text(r, 28, o.library, ds.ATTR_TURQUOISE)]
        if o.text:
            rows.append(Text(r, 52, o.text[:27], ds.ATTR_TURQUOISE))
    rows += [Text(20, 73 if len(picks) <= 14 else 72, "Bottom" if len(picks) <= 14 else "More...", ds.ATTR_BLUE),
             Text(21, 1, "F11=Display names and types", ds.ATTR_BLUE), Text(21, 31, "F12=Cancel", ds.ATTR_BLUE)]
    return Screen(rows)


@dataclass
class EditAuth:
    """State of one Edit Object Authority display."""
    obj: object
    page: int = 0
    per_page: int = 8

    def rows(self) -> list[tuple[str, str]]:
        from ..system.authority import SPECIAL_VALUES, Auth, name_auth

        def show(a):
            if a is None:
                return "*AUTL"
            text = name_auth(a)
            return text if a in SPECIAL_VALUES.values() else "USER DEF"
        o = self.obj
        out = [("*PUBLIC", show(o.public)), (o.owner, show(o.owner_auth))]
        return out + [(u, show(a)) for u, a in sorted(o.private.items())]

    @property
    def pages(self) -> int:
        return max(1, -(-len(self.rows()) // self.per_page))

    def shown(self) -> list[tuple[str, str]]:
        self.page = max(0, min(self.page, self.pages - 1))
        return self.rows()[self.page * self.per_page:(self.page + 1) * self.per_page]

    def screen(self, message: str = "") -> Screen:
        o = self.obj
        rows: list = [
            Text(0, 29, "Edit Object Authority", ds.ATTR_WHITE),
            Text(2, 1, "Object . . . . . . . :", ds.ATTR_GREEN), Text(2, 26, o.name, ds.ATTR_WHITE),
            Text(2, 42, "Owner  . . . . . . . :", ds.ATTR_GREEN), Text(2, 67, o.owner, ds.ATTR_WHITE),
            Text(3, 3, "Library  . . . . . :", ds.ATTR_GREEN), Text(3, 28, o.library, ds.ATTR_WHITE),
            Text(3, 42, "Primary group  . . . :", ds.ATTR_GREEN), Text(3, 67, "*NONE", ds.ATTR_WHITE),
            Text(4, 1, "Object type  . . . . :", ds.ATTR_GREEN), Text(4, 26, o.type, ds.ATTR_WHITE),
            Text(4, 42, "ASP device . . . . . :", ds.ATTR_GREEN), Text(4, 67, "*SYSBAS", ds.ATTR_WHITE),
            Text(6, 1, "Type changes to current authorities, press Enter.", ds.ATTR_BLUE),
            Text(8, 3, "Object secured by authorization list  . . . . . . . . . . . .", ds.ATTR_GREEN),
            Input(8, 67, 10, "autl", monocase=True, value=o.autl or "*NONE"),
            Text(10, 26, "Object", ds.ATTR_WHITE),
            Text(11, 1, "User", ds.ATTR_WHITE), Text(11, 13, "Group", ds.ATTR_WHITE),
            Text(11, 25, "Authority", ds.ATTR_WHITE),
        ]
        for i, (user, auth) in enumerate(self.shown()):
            r = 12 + i
            rows += [Text(r, 1, user, ds.ATTR_TURQUOISE),
                     Input(r, 25, 8, f"auth{i}", monocase=True, value=auth)]
        rows.append(Text(20, 72 if self.page < self.pages - 1 else 73, "More..." if self.page < self.pages - 1 else "Bottom", ds.ATTR_BLUE))
        rows += [Text(21, 1, "F3=Exit", ds.ATTR_BLUE), Text(21, 11, "F5=Refresh", ds.ATTR_BLUE),
                 Text(21, 24, "F6=Add new users", ds.ATTR_BLUE), Text(21, 43, "F10=Grant with reference object", ds.ATTR_BLUE),
                 Text(22, 1, "F11=Display detail object authorities", ds.ATTR_BLUE), Text(22, 43, "F12=Cancel", ds.ATTR_BLUE),
                 Text(22, 56, "F17=Top", ds.ATTR_BLUE), Text(22, 66, "F18=Bottom", ds.ATTR_BLUE)]
        rows.append(Text(23, 1, message[:77] if message else "SILVERLAKE SIMULATION. NOT IBM.", ds.ATTR_WHITE))
        return Screen(rows, cursor="autl")


def dspobjd_basic_screen(obj, message: str = "") -> Screen:
    """Display Object Description - Basic, laid out like the real one (captured from QGPL): a list
    of the one object with options 5 and 8. Attribute and Size are blank, because Silverlake
    objects have neither."""
    return Screen([
        Text(0, 23, "Display Object Description - Basic", ds.ATTR_WHITE),
        Text(1, 65, "Library 1 of 1", ds.ATTR_BLUE),
        Text(2, 1, "Library . . . . . . . :", ds.ATTR_GREEN), Text(2, 27, obj.library, ds.ATTR_WHITE),
        Text(2, 42, "Library ASP device  . :", ds.ATTR_GREEN), Text(2, 68, "*SYSBAS", ds.ATTR_WHITE),
        Text(3, 42, "Library ASP group . . :", ds.ATTR_GREEN), Text(3, 68, "*SYSBAS", ds.ATTR_WHITE),
        Text(5, 1, "Type options, press Enter.", ds.ATTR_BLUE),
        Text(6, 3, "5=Display full attributes", ds.ATTR_BLUE), Text(6, 31, "8=Display service attributes", ds.ATTR_BLUE),
        Text(8, 1, "Opt", ds.ATTR_WHITE), Text(8, 6, "Object", ds.ATTR_WHITE), Text(8, 18, "Type", ds.ATTR_WHITE),
        Text(8, 28, "Attribute", ds.ATTR_WHITE), Text(8, 52, "Size", ds.ATTR_WHITE), Text(8, 58, "Text", ds.ATTR_WHITE),
        Input(9, 2, 1, "opt0", monocase=True),
        Text(9, 6, obj.name, ds.ATTR_TURQUOISE), Text(9, 18, obj.type, ds.ATTR_TURQUOISE),
        Text(9, 58, obj.text[:21], ds.ATTR_TURQUOISE),
        Text(21, 73, "Bottom", ds.ATTR_BLUE),
        Text(22, 1, "F3=Exit", ds.ATTR_BLUE), Text(22, 11, "F12=Cancel", ds.ATTR_BLUE),
        Text(22, 24, "F17=Top", ds.ATTR_BLUE), Text(22, 34, "F18=Bottom", ds.ATTR_BLUE),
        Text(23, 1, message[:77] if message else "SILVERLAKE SIMULATION. NOT IBM.", ds.ATTR_WHITE),
    ], cursor="opt0")


def add_users_screen(obj, entries: dict[str, tuple[str, str]] | None = None, message: str = "") -> Screen:
    """Add New Users, opened by F6 on Edit Object Authority. Ten rows of user and authority, laid
    out like the real display (captured, nothing typed on it)."""
    entries = entries or {}
    rows: list = [
        Text(0, 33, "Add New Users", ds.ATTR_WHITE),
        Text(2, 1, "Object . . . . . . . :", ds.ATTR_GREEN), Text(2, 26, obj.name, ds.ATTR_WHITE),
        Text(2, 42, "Owner  . . . . . . . :", ds.ATTR_GREEN), Text(2, 67, obj.owner, ds.ATTR_WHITE),
        Text(3, 3, "Library  . . . . . :", ds.ATTR_GREEN), Text(3, 28, obj.library, ds.ATTR_WHITE),
        Text(3, 42, "Primary group  . . . :", ds.ATTR_GREEN), Text(3, 67, "*NONE", ds.ATTR_WHITE),
        Text(4, 1, "Object type  . . . . :", ds.ATTR_GREEN), Text(4, 26, obj.type, ds.ATTR_WHITE),
        Text(4, 42, "ASP device . . . . . :", ds.ATTR_GREEN), Text(4, 67, "*SYSBAS", ds.ATTR_WHITE),
        Text(6, 1, "Type new users, press Enter.", ds.ATTR_BLUE),
        Text(8, 14, "Object", ds.ATTR_WHITE),
        Text(9, 1, "User", ds.ATTR_WHITE), Text(9, 13, "Authority", ds.ATTR_WHITE),
    ]
    for i in range(10):
        user, auth = entries.get(i, ("", ""))
        rows += [Input(10 + i, 1, 10, f"user{i}", monocase=True, value=user),
                 Input(10 + i, 13, 8, f"auth{i}", monocase=True, value=auth)]
    rows += [Text(20, 72, "More...", ds.ATTR_BLUE),
             Text(21, 1, "F3=Exit", ds.ATTR_BLUE), Text(21, 11, "F11=Display detail object authorities", ds.ATTR_BLUE),
             Text(21, 51, "F12=Cancel", ds.ATTR_BLUE), Text(21, 64, "F17=Top", ds.ATTR_BLUE),
             Text(22, 1, "F18=Bottom", ds.ATTR_BLUE),
             Text(23, 1, message[:77] if message else "SILVERLAKE SIMULATION. NOT IBM.", ds.ATTR_WHITE)]
    return Screen(rows, cursor="user0")


def dspobjd_screen(obj, detail: str, system_name: str, page: int = 0) -> Screen:
    """Display Object Description, laid out like the real *FULL display (captured). The creation
    date and time are kept for libraries made here (CRTLIB), and blank for the seed. The real display has a second page (More...)
    that was not captured, and the *BASIC display was not captured at all."""
    title = "Display Object Description - Full"
    if page == 1:
        return _dspobjd_page_two(obj, title)
    rows: list = [
        Text(0, 23, title, ds.ATTR_WHITE),
        Text(1, 66, "Library 1 of 1", ds.ATTR_BLUE),
        Text(2, 1, "Object . . . . . . . :", ds.ATTR_GREEN), Text(2, 26, obj.name, ds.ATTR_WHITE),
        Text(2, 42, "Attribute  . . . . . :", ds.ATTR_GREEN),
        Text(3, 3, "Library  . . . . . :", ds.ATTR_GREEN), Text(3, 28, obj.library, ds.ATTR_WHITE),
        Text(3, 42, "Owner  . . . . . . . :", ds.ATTR_GREEN), Text(3, 67, obj.owner, ds.ATTR_WHITE),
        Text(4, 1, "Library ASP device . :", ds.ATTR_GREEN), Text(4, 26, "*SYSBAS", ds.ATTR_WHITE),
        Text(4, 42, "Library ASP group  . :", ds.ATTR_GREEN), Text(4, 67, "*SYSBAS", ds.ATTR_WHITE),
        Text(5, 1, "Type . . . . . . . . :", ds.ATTR_GREEN), Text(5, 26, obj.type, ds.ATTR_WHITE),
        Text(5, 42, "Primary group  . . . :", ds.ATTR_GREEN), Text(5, 67, "*NONE", ds.ATTR_WHITE),
        Text(7, 1, "User-defined information:", ds.ATTR_GREEN),
        Text(8, 3, "Attribute  . . . . . . . . . . . . . :", ds.ATTR_GREEN),
        Text(9, 3, "Text . . . . . . . . . . . . . . . . :", ds.ATTR_GREEN),
        Text(11, 1, "Creation information:", ds.ATTR_GREEN),
        Text(12, 3, "Creation date/time . . . . . . . . . :", ds.ATTR_GREEN),
        Text(13, 3, "Created by user  . . . . . . . . . . :", ds.ATTR_GREEN), Text(13, 44, obj.owner, ds.ATTR_WHITE),
        Text(14, 3, "System created on  . . . . . . . . . :", ds.ATTR_GREEN), Text(14, 44, system_name, ds.ATTR_WHITE),
        Text(15, 3, "Object domain  . . . . . . . . . . . :", ds.ATTR_GREEN), Text(15, 44, "*SYSTEM", ds.ATTR_WHITE),
        Text(19, 72, "More...", ds.ATTR_BLUE),
        Text(20, 1, "Press Enter to continue.", ds.ATTR_BLUE),
        Text(22, 1, "F3=Exit", ds.ATTR_BLUE), Text(22, 11, "F12=Cancel", ds.ATTR_BLUE),
    ]
    if obj.text:
        rows.append(Text(9, 44, obj.text[:36], ds.ATTR_WHITE))
    made = (obj.data or {}).get("created")
    if made:
        rows.append(Text(12, 44, datetime.fromisoformat(made).strftime("%y-%m-%d  %H:%M:%S"), ds.ATTR_WHITE))
    return Screen(rows)


def _dspobjd_page_two(obj, title: str) -> Screen:
    """The second page of the full description (captured from QGPL): change and usage information,
    then auditing and integrity. We keep no usage data, so the values are the quiet ones, and
    the object auditing value is our guess (the captured system object said *NOTAVL)."""
    made = (obj.data or {}).get("created")
    changed = datetime.fromisoformat(made).strftime("%y-%m-%d  %H:%M:%S") if made else ""
    label = lambda r, c, t: Text(r, c, t, ds.ATTR_GREEN)
    value = lambda r, t: Text(r, 44, t, ds.ATTR_WHITE)
    return Screen([
        Text(0, 23, title, ds.ATTR_WHITE), Text(1, 66, "Library 1 of 1", ds.ATTR_BLUE),
        label(2, 1, "Object . . . . . . . :"), Text(2, 26, obj.name, ds.ATTR_WHITE),
        label(2, 42, "Attribute  . . . . . :"),
        label(3, 3, "Library  . . . . . :"), Text(3, 28, obj.library, ds.ATTR_WHITE),
        label(3, 42, "Owner  . . . . . . . :"), Text(3, 67, obj.owner, ds.ATTR_WHITE),
        label(4, 1, "Library ASP device . :"), Text(4, 26, "*SYSBAS", ds.ATTR_WHITE),
        label(4, 42, "Library ASP group  . :"), Text(4, 67, "*SYSBAS", ds.ATTR_WHITE),
        label(5, 1, "Type . . . . . . . . :"), Text(5, 26, obj.type, ds.ATTR_WHITE),
        label(5, 42, "Primary group  . . . :"), Text(5, 67, "*NONE", ds.ATTR_WHITE),
        label(7, 1, "Change/Usage information:"),
        label(8, 3, "Change date/time . . . . . . . . . . :"), value(8, changed),
        label(9, 3, "Usage data collected . . . . . . . . :"), value(9, "NO"),
        label(10, 3, "Last used date . . . . . . . . . . . :"),
        label(11, 3, "Days used count  . . . . . . . . . . :"), value(11, "0"),
        label(12, 5, "Reset date . . . . . . . . . . . . :"),
        label(13, 3, "Allow change by program  . . . . . . :"), value(13, "NO"),
        label(14, 1, "Auditing/Integrity information:"),
        label(15, 3, "Object auditing value  . . . . . . . :"), value(15, "*NONE"),
        label(16, 3, "Digitally signed . . . . . . . . . . :"), value(16, "NO"),
        label(17, 3, "Authority collection value . . . . . :"), value(17, "*NONE"),
        Text(20, 1, "Press Enter to continue.", ds.ATTR_BLUE),
        Text(22, 1, "F3=Exit", ds.ATTR_BLUE), Text(22, 11, "F12=Cancel", ds.ATTR_BLUE),
        Text(19, 72, "More...", ds.ATTR_BLUE),      # the real one has a third page, not modeled
    ])
