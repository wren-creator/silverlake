"""Screens for the library and object authority commands. Layout and wording
are ours; real screens for these have not been captured yet."""

from dataclasses import dataclass

from ..proto import datastream as ds
from ..system.authority import name_auth, parse_auth
from ..system.profiles import ProfileStore
from .model import Input, Screen, Text
from .usrprf import PAGE_SIZE, wrkusrprf_pages

FIRST_ROW = 5


def pages(count: int) -> int:
    return wrkusrprf_pages(count)


def _clamp(rows: list, page: int) -> tuple[int, list]:
    page = max(0, min(page, pages(len(rows)) - 1))
    return page, rows[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]


def _footer(rows: list[Text | Input], page: int, count: int, keys: str) -> None:
    more = "More..." if page < pages(count) - 1 else "Bottom"
    rows.append(Text(FIRST_ROW + PAGE_SIZE, 70, more, ds.ATTR_WHITE))
    rows.append(Text(23, 2, keys, ds.ATTR_GREEN))


DSPLIBL_ROWS = 12      # rows 9 to 20 on the real display
DSPOBJAUT_ROWS = 8     # rows 10 to 17


def _page_of(rows: list, page: int, per: int) -> tuple[int, int, list]:
    count = max(1, -(-len(rows) // per))
    page = max(0, min(page, count - 1))
    return page, count, rows[page * per:(page + 1) * per]


def dsplibl_screen(store: ProfileStore, entries: list[tuple[str, str]], page: int = 0) -> Screen:
    """Laid out like the real Display Library List captured from PUB400: the system name at the
    top right, an ASP Device column, rows from row 9, and F3, F12, F17 and F18 on row 22. The
    real display also has an Opt column with 5=Display objects in library. That option is not
    built, so the column and its prompt are left out rather than drawn dead. Device is blank
    (there are no ASPs), and the real Text for the current library reads differently."""
    page, count, shown = _page_of(entries, page, DSPLIBL_ROWS)
    rows: list[Text | Input] = [
        Text(0, 12, "Display Library List".rjust(38), ds.ATTR_WHITE),   # the real run starts at col 12, padded
        Text(1, 61, "System:", ds.ATTR_GREEN), Text(1, 71, "SILVERLK", ds.ATTR_GREEN),
        Text(7, 28, "ASP", ds.ATTR_WHITE),
        Text(8, 6, "Library", ds.ATTR_WHITE), Text(8, 18, "Type", ds.ATTR_WHITE),
        Text(8, 28, "Device", ds.ATTR_WHITE), Text(8, 40, "Text", ds.ATTR_WHITE),
    ]
    for i, (lib, kind) in enumerate(shown):
        obj = store.find_library(lib)
        r = 9 + i
        rows += [Text(r, 6, lib, ds.ATTR_GREEN), Text(r, 18, kind, ds.ATTR_GREEN)]
        if obj and obj.text:
            rows.append(Text(r, 40, obj.text[:40], ds.ATTR_GREEN))
    rows.append(Text(21, 67, ("More..." if page < count - 1 else "Bottom").rjust(12), ds.ATTR_WHITE))
    rows += [Text(22, 1, "F3=Exit", ds.ATTR_BLUE), Text(22, 11, "F12=Cancel", ds.ATTR_BLUE),
             Text(22, 24, "F17=Top", ds.ATTR_BLUE), Text(22, 34, "F18=Bottom", ds.ATTR_BLUE)]
    return Screen(rows)


def slscenario_screen(mode: str, lessons: list, page: int = 0) -> Screen:
    """SLSCENARIO STATE(*LIST): every lesson and the state it is in. Ours, not a capture: a plain paged list."""
    page, shown = _clamp(lessons, page)
    rows: list[Text | Input] = [
        Text(0, 24, "Silverlake Lesson States", ds.ATTR_WHITE),
        Text(2, 2, "Range mode . . . :", ds.ATTR_GREEN), Text(2, 21, mode, ds.ATTR_GREEN),
        Text(4, 2, "State", ds.ATTR_WHITE), Text(4, 14, "Grp", ds.ATTR_WHITE), Text(4, 19, "Lesson", ds.ATTR_WHITE),
        Text(4, 47, "Title", ds.ATTR_WHITE),
    ]
    for i, (state, group, sid, title) in enumerate(shown):
        r = FIRST_ROW + i
        rows += [Text(r, 2, state, ds.ATTR_GREEN), Text(r, 14, group, ds.ATTR_GREEN), Text(r, 19, sid[:27], ds.ATTR_GREEN),
                 Text(r, 47, title[:32], ds.ATTR_GREEN)]
    _footer(rows, page, len(lessons), "F3=Exit   F12=Cancel   Page Up/Down")
    return Screen(rows)


# Keys for the three views F11 cycles on Display Object Authority (captured live, `auth-dspobjaut-f11`):
# plain, object rights, data rights, plain again, in the same order and the same columns Edit Object
# Authority uses (see DETAIL_VIEWS in worklists.py), but nothing here can be typed over.
_DSPOBJAUT_KEYS = [
    [(21, 1, "F3=Exit"), (21, 11, "F11=Display detail object authorities"), (21, 51, "F12=Cancel"),
     (21, 64, "F17=Top"), (22, 1, "F18=Bottom")],
    [(21, 1, "F3=Exit"), (21, 11, "F11=Display data authorities"), (21, 42, "F12=Cancel"),
     (21, 55, "F17=Top"), (21, 65, "F18=Bottom")],
    [(21, 1, "F3=Exit"), (21, 11, "F11=Nondisplay detail"), (21, 35, "F12=Cancel"),
     (21, 48, "F17=Top"), (21, 58, "F18=Bottom")],
]


@dataclass
class DspObjAut:
    """State of one Display Object Authority display: which page of users it is showing, and
    which of the three F11 views (plain, object rights, data rights) it has reached. Laid out
    like the real display captured from PUB400 (`auth-dspobjaut-f11`): the header block, the
    authorization list line, the User, Group and Authority table from row 10, F11's detail
    columns in the same positions Edit Object Authority uses, and the keys on rows 21 and 22.
    Group is left blank, and read-only: a row's X marks come from reparsing its own Authority
    text (name_auth's own format, round tripped through parse_auth), not from typing over them."""
    obj: object
    authority_rows: list[tuple[str, str]]
    page: int = 0
    detail: int = 0

    @property
    def pages(self) -> int:
        return max(1, -(-len(self.authority_rows) // DSPOBJAUT_ROWS))

    def screen(self, message: str = "") -> Screen:
        from .worklists import DETAIL_VIEWS

        obj = self.obj
        page, count, shown = _page_of(self.authority_rows, self.page, DSPOBJAUT_ROWS)
        self.page = page
        g = ds.ATTR_GREEN
        rows: list[Text | Input] = [
            Text(0, 28, "Display Object Authority", ds.ATTR_WHITE),
            Text(2, 1, "Object . . . . . . . :", g), Text(2, 26, obj.name, g),
            Text(2, 42, "Owner  . . . . . . . :", g), Text(2, 67, obj.owner, g),
            Text(3, 3, "Library  . . . . . :", g), Text(3, 28, obj.library, g),
            Text(3, 42, "Primary group  . . . :", g), Text(3, 67, "*NONE", g),
            Text(4, 1, "Object type  . . . . :", g), Text(4, 26, obj.type, g),
            Text(4, 42, "ASP device . . . . . :", g), Text(4, 67, "*SYSBAS", g),
            Text(6, 1, "Object secured by authorization list  . . . . . . . . . . . . :", g),
            Text(6, 67, obj.autl or "*NONE", g),
            Text(8, 26, "Object", ds.ATTR_WHITE),
            Text(9, 1, "User", ds.ATTR_WHITE), Text(9, 13, "Group", ds.ATTR_WHITE), Text(9, 25, "Authority", ds.ATTR_WHITE),
        ]
        view = DETAIL_VIEWS[self.detail]
        if view:
            rows.append(Text(8, 36, view["head"], ds.ATTR_WHITE))
            rows += [Text(9, col, title, ds.ATTR_WHITE) for title, col, _, _ in view["cols"]]
        for i, (user, auth) in enumerate(shown):
            r = 10 + i
            rows += [Text(r, 1, user, g), Text(r, 25, auth[:54], g)]
            held = None if auth == "*AUTL" else parse_auth(auth)
            for title, _, xcol, right in view.get("cols", []):
                if held is not None and right in held:
                    rows.append(Text(r, xcol, "X", g))
        rows.append(Text(18, 67, ("More..." if page < count - 1 else "Bottom").rjust(12), ds.ATTR_WHITE))
        rows.append(Text(19, 1, "Press Enter to continue.", ds.ATTR_BLUE))
        rows += [Text(row, col, text, ds.ATTR_BLUE) for row, col, text in _DSPOBJAUT_KEYS[self.detail]]
        return Screen(rows)


def dspautl_screen(autl, entry_rows: list[tuple[str, str]], page: int = 0) -> Screen:
    """Laid out like the real Display Authorization List captured from PUB400: two header rows
    (Object / List over Authority / Mgt), entries from row 7 with the user at column 1, the
    object authority at 13 and the list management mark at 24. The Mgt mark is an X for
    *AUTLMGT; DSPAUTL's own capture only ever had a *PUBLIC row to confirm that against, but
    Edit Authorization List's own entries (`auth-edtautl-own`), the same table two rows further
    down the same screen, confirmed it, and *PUBLIC sorting first rather than last."""
    per_page = 11
    pages_ = max(1, -(-len(entry_rows) // per_page))
    page = max(0, min(page, pages_ - 1))
    shown = entry_rows[page * per_page:(page + 1) * per_page]
    rows: list[Text | Input] = [
        Text(0, 27, "Display Authorization List", ds.ATTR_WHITE),
        Text(2, 1, "Object . . . . . . . :", ds.ATTR_GREEN), Text(2, 26, autl.name, ds.ATTR_GREEN),
        Text(2, 42, "Owner  . . . . . . . :", ds.ATTR_GREEN), Text(2, 67, autl.owner, ds.ATTR_GREEN),
        Text(3, 3, "Library  . . . . . :", ds.ATTR_GREEN), Text(3, 28, "QSYS", ds.ATTR_GREEN),
        Text(3, 42, "Primary group  . . :", ds.ATTR_GREEN), Text(3, 67, "*NONE", ds.ATTR_GREEN),
        Text(5, 14, "Object", ds.ATTR_WHITE), Text(5, 24, "List", ds.ATTR_WHITE),
        Text(6, 1, "User", ds.ATTR_WHITE), Text(6, 13, "Authority", ds.ATTR_WHITE), Text(6, 24, "Mgt", ds.ATTR_WHITE),
    ]
    for i, (user, auth) in enumerate(shown):
        r = 7 + i
        rows += [Text(r, 1, user, ds.ATTR_GREEN),
                 Text(r, 13, auth.removesuffix(" *AUTLMGT")[:10], ds.ATTR_GREEN)]
        if auth.endswith("*AUTLMGT"):
            rows.append(Text(r, 24, "X", ds.ATTR_GREEN))
    rows.append(Text(18, 67, ("More..." if page < pages_ - 1 else "Bottom").rjust(12), ds.ATTR_WHITE))
    rows.append(Text(19, 1, "Press Enter to continue.", ds.ATTR_BLUE))
    rows.append(Text(21, 1, "F3=Exit   F12=Cancel", ds.ATTR_BLUE))
    return Screen(rows)


@dataclass
class EditAutl:
    """State of one Edit Authorization List display, captured live (`auth-edtautl-own`): the
    same header block Display Authorization List has, plus an instruction line that pushes the
    Object/List and User/Authority/Mgt headers two rows further down than DSPAUTL's own (rows
    7 and 8 here, not 5 and 6), *PUBLIC first then everyone else sorted, the same table DSPAUTL
    shows. F11=Display detail object authorities and F24=More keys are real, captured keys;
    neither was ever pressed, so neither does anything here. What a typed change does, below,
    mirrors Edit Object Authority's own untyped-in-the-capture reasoning: blank removes a user,
    ADDAUTLE/CHGAUTLE/RMVAUTLE's own rules apply to whatever is typed, one row at a time."""
    autl: object
    page: int = 0
    per_page: int = 11

    def rows(self) -> list[tuple[str, object]]:
        a = self.autl
        return [("*PUBLIC", a.public)] + sorted(a.entries.items())

    @property
    def pages(self) -> int:
        return max(1, -(-len(self.rows()) // self.per_page))

    def shown(self) -> list[tuple[str, object]]:
        self.page = max(0, min(self.page, self.pages - 1))
        return self.rows()[self.page * self.per_page:(self.page + 1) * self.per_page]

    def screen(self, message: str = "") -> Screen:
        from ..system.authority import Auth
        a = self.autl
        g = ds.ATTR_GREEN
        rows: list[Text | Input] = [
            Text(0, 28, "Edit Authorization List", ds.ATTR_WHITE),
            Text(2, 1, "Object . . . . . . . :", g), Text(2, 26, a.name, g),
            Text(2, 42, "Owner  . . . . . . . :", g), Text(2, 67, a.owner, g),
            Text(3, 3, "Library  . . . . . :", g), Text(3, 28, "QSYS", g),
            Text(3, 42, "Primary group  . . . :", g), Text(3, 67, "*NONE", g),
            Text(5, 1, "Type changes to current authorities, press Enter.", ds.ATTR_BLUE),
            Text(7, 14, "Object", ds.ATTR_WHITE), Text(7, 24, "List", ds.ATTR_WHITE),
            Text(8, 1, "User", ds.ATTR_WHITE), Text(8, 13, "Authority", ds.ATTR_WHITE), Text(8, 24, "Mgt", ds.ATTR_WHITE),
        ]
        shown = self.shown()
        for i, (user, auth) in enumerate(shown):
            r = 9 + i
            base = name_auth(auth & ~Auth.AUTLMGT) or "*EXCLUDE"
            rows += [Text(r, 1, user, g), Input(r, 13, 8, f"auth{i}", monocase=True, value=base),
                     Input(r, 25, 1, f"mgt{i}", monocase=True, value="X" if Auth.AUTLMGT in auth else "")]
        rows.append(Text(20, 67, ("More..." if self.page < self.pages - 1 else "Bottom").rjust(12), ds.ATTR_WHITE))
        rows += [Text(21, 1, "F3=Exit", ds.ATTR_BLUE), Text(21, 11, "F5=Refresh", ds.ATTR_BLUE),
                 Text(21, 24, "F6=Add new users", ds.ATTR_BLUE),
                 Text(22, 1, "F11=Display detail object authorities", ds.ATTR_BLUE),
                 Text(22, 41, "F12=Cancel", ds.ATTR_BLUE), Text(22, 54, "F24=More keys", ds.ATTR_BLUE)]
        if message:
            rows.append(Text(23, 1, message[:77], ds.ATTR_WHITE))
        return Screen(rows, cursor="auth0")


def add_autl_users_screen(autl, entries: dict[int, tuple[str, str, bool]] | None = None, message: str = "") -> Screen:
    """Add New Users, opened by F6 on Edit Authorization List, laid out like the real one
    captured (`auth-edtautl-own`): the same title column Edit Object Authority's own Add New
    Users uses, but Authorization List's own header (two lines, not four) and eleven rows of
    User, Authority and Mgt, not ten, with no Object type or ASP device to show."""
    entries = entries or {}
    g = ds.ATTR_GREEN
    rows: list[Text | Input] = [
        Text(0, 33, "Add New Users", ds.ATTR_WHITE),
        Text(2, 1, "Object . . . . . . . :", g), Text(2, 26, autl.name, g),
        Text(2, 42, "Owner  . . . . . . . :", g), Text(2, 67, autl.owner, g),
        Text(3, 3, "Library  . . . . . :", g), Text(3, 28, "QSYS", g),
        Text(3, 42, "Primary group  . . . :", g), Text(3, 67, "*NONE", g),
        Text(5, 1, "Type new users, press Enter.", ds.ATTR_BLUE),
        Text(7, 14, "Object", ds.ATTR_WHITE), Text(7, 24, "List", ds.ATTR_WHITE),
        Text(8, 1, "User", ds.ATTR_WHITE), Text(8, 13, "Authority", ds.ATTR_WHITE), Text(8, 24, "Mgt", ds.ATTR_WHITE),
    ]
    for i in range(11):
        user, auth = entries.get(i, ("", ""))
        rows += [Input(9 + i, 1, 10, f"user{i}", monocase=True, value=user),
                 Input(9 + i, 13, 8, f"auth{i}", monocase=True, value=auth),
                 Input(9 + i, 25, 1, f"mgt{i}", monocase=True, value="")]
    rows += [Text(20, 67, "More...".rjust(12), ds.ATTR_WHITE),
             Text(21, 1, "F3=Exit", ds.ATTR_BLUE), Text(21, 11, "F11=Display detail object authorities", ds.ATTR_BLUE),
             Text(21, 51, "F12=Cancel", ds.ATTR_BLUE), Text(21, 64, "F17=Top", ds.ATTR_BLUE),
             Text(22, 1, "F18=Bottom", ds.ATTR_BLUE)]
    if message:
        rows.append(Text(23, 1, message[:77], ds.ATTR_WHITE))
    return Screen(rows, cursor="user0")
