"""Screens for the library and object authority commands. Layout and wording
are ours; real screens for these have not been captured yet."""

from ..proto import datastream as ds
from ..system.authority import name_auth
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


def wrklib_screen(libs: list, page: int = 0) -> Screen:
    page, shown = _clamp(libs, page)
    rows: list[Text | Input] = [
        Text(0, 28, "Work with Libraries", ds.ATTR_WHITE),
        Text(2, 2, "Libraries you have some authority to.", ds.ATTR_BLUE),
        Text(4, 2, "Library", ds.ATTR_WHITE), Text(4, 14, "Owner", ds.ATTR_WHITE), Text(4, 26, "Text", ds.ATTR_WHITE),
    ]
    for i, lib in enumerate(shown):
        r = FIRST_ROW + i
        rows += [Text(r, 2, lib.name, ds.ATTR_GREEN), Text(r, 14, lib.owner, ds.ATTR_GREEN),
                 Text(r, 26, lib.text[:50], ds.ATTR_GREEN)]
    _footer(rows, page, len(libs), "F3=Exit   F12=Cancel   Page Up/Down")
    return Screen(rows)


def dspobjaut_screen(obj, authority_rows: list[tuple[str, str]], page: int = 0) -> Screen:
    """Laid out like the real Display Object Authority captured from PUB400: the header block,
    the authorization list line, a User, Group and Authority table from row 10, and the keys
    on rows 21 and 22. The real display also offers F11 for the detail authorities, which is
    not built, so the key is not drawn. Group is left blank, and the capture only held
    *PUBLIC rows, so the wording of user defined authorities is ours."""
    page, count, shown = _page_of(authority_rows, page, DSPOBJAUT_ROWS)
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
    for i, (user, auth) in enumerate(shown):
        r = 10 + i
        rows += [Text(r, 1, user, g), Text(r, 25, auth[:54], g)]
    rows.append(Text(18, 67, ("More..." if page < count - 1 else "Bottom").rjust(12), ds.ATTR_WHITE))
    rows += [Text(19, 1, "Press Enter to continue.", ds.ATTR_BLUE),
             Text(21, 1, "F3=Exit", ds.ATTR_BLUE), Text(21, 11, "F12=Cancel", ds.ATTR_BLUE),
             Text(21, 24, "F17=Top", ds.ATTR_BLUE), Text(22, 1, "F18=Bottom", ds.ATTR_BLUE)]
    return Screen(rows)


def dspautl_screen(autl, entry_rows: list[tuple[str, str]], page: int = 0) -> Screen:
    """Laid out like the real Display Authorization List captured from PUB400: two header rows
    (Object / List over Authority / Mgt), entries from row 7 with the user at column 1, the
    object authority at 13 and the list management mark at 24. The Mgt mark is an X for
    *AUTLMGT, which is assumed (the capture only had a *PUBLIC row)."""
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
    rows.append(Text(18, 67, "More..." if page < pages_ - 1 else "Bottom", ds.ATTR_WHITE))
    rows.append(Text(19, 1, "Press Enter to continue.", ds.ATTR_BLUE))
    rows.append(Text(21, 1, "F3=Exit   F12=Cancel", ds.ATTR_BLUE))
    return Screen(rows)
