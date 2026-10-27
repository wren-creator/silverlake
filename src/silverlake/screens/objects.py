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
    rows.append(Text(FIRST_ROW + PAGE_SIZE, 70, more, ds.ATTR_BLUE))
    rows.append(Text(23, 2, keys, ds.ATTR_GREEN))


def dsplibl_screen(store: ProfileStore, entries: list[tuple[str, str]], page: int = 0) -> Screen:
    page, shown = _clamp(entries, page)
    rows: list[Text | Input] = [
        Text(0, 29, "Display Library List", ds.ATTR_WHITE),
        Text(4, 2, "Library", ds.ATTR_WHITE), Text(4, 14, "Type", ds.ATTR_WHITE), Text(4, 22, "Text", ds.ATTR_WHITE),
    ]
    for i, (lib, kind) in enumerate(shown):
        obj = store.find_library(lib)
        r = FIRST_ROW + i
        rows += [Text(r, 2, lib, ds.ATTR_TURQUOISE), Text(r, 14, kind, ds.ATTR_TURQUOISE),
                 Text(r, 22, (obj.text if obj else "*not found*")[:50], ds.ATTR_TURQUOISE)]
    _footer(rows, page, len(entries), "F3=Exit   F12=Cancel   Page Up/Down")
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
        rows += [Text(r, 2, lib.name, ds.ATTR_TURQUOISE), Text(r, 14, lib.owner, ds.ATTR_TURQUOISE),
                 Text(r, 26, lib.text[:50], ds.ATTR_TURQUOISE)]
    _footer(rows, page, len(libs), "F3=Exit   F12=Cancel   Page Up/Down")
    return Screen(rows)


def dspobjaut_screen(obj, authority_rows: list[tuple[str, str]], page: int = 0) -> Screen:
    page, shown = _clamp(authority_rows, page)
    rows: list[Text | Input] = [
        Text(0, 26, "Display Object Authority", ds.ATTR_WHITE),
        Text(1, 2, "Object . . . . . . :", ds.ATTR_GREEN), Text(1, 24, obj.name, ds.ATTR_WHITE),
        Text(1, 40, "Owner . . . . . . . :", ds.ATTR_GREEN), Text(1, 62, obj.owner, ds.ATTR_WHITE),
        Text(2, 2, "  Library . . . . . :", ds.ATTR_GREEN), Text(2, 24, obj.library, ds.ATTR_WHITE),
        Text(2, 40, "Object type . . . . :", ds.ATTR_GREEN), Text(2, 62, obj.type, ds.ATTR_WHITE),
        Text(3, 2, "Authorization list  :", ds.ATTR_GREEN), Text(3, 24, obj.autl or "*NONE", ds.ATTR_WHITE),
        Text(4, 2, "User", ds.ATTR_WHITE), Text(4, 16, "Object authority", ds.ATTR_WHITE),
    ]
    for i, (user, auth) in enumerate(shown):
        r = FIRST_ROW + i
        rows += [Text(r, 2, user, ds.ATTR_TURQUOISE), Text(r, 16, auth[:60], ds.ATTR_TURQUOISE)]
    _footer(rows, page, len(authority_rows), "F3=Exit   F12=Cancel   Page Up/Down")
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
        Text(2, 1, "Object . . . . . . . :", ds.ATTR_GREEN), Text(2, 26, autl.name, ds.ATTR_WHITE),
        Text(2, 42, "Owner  . . . . . . . :", ds.ATTR_GREEN), Text(2, 67, autl.owner, ds.ATTR_WHITE),
        Text(3, 3, "Library  . . . . . :", ds.ATTR_GREEN), Text(3, 28, "QSYS", ds.ATTR_WHITE),
        Text(3, 42, "Primary group  . . :", ds.ATTR_GREEN), Text(3, 67, "*NONE", ds.ATTR_WHITE),
        Text(5, 14, "Object", ds.ATTR_WHITE), Text(5, 24, "List", ds.ATTR_WHITE),
        Text(6, 1, "User", ds.ATTR_WHITE), Text(6, 13, "Authority", ds.ATTR_WHITE), Text(6, 24, "Mgt", ds.ATTR_WHITE),
    ]
    for i, (user, auth) in enumerate(shown):
        r = 7 + i
        rows += [Text(r, 1, user, ds.ATTR_TURQUOISE),
                 Text(r, 13, auth.removesuffix(" *AUTLMGT")[:10], ds.ATTR_TURQUOISE)]
        if auth.endswith("*AUTLMGT"):
            rows.append(Text(r, 24, "X", ds.ATTR_TURQUOISE))
    rows.append(Text(18, 67, "More..." if page < pages_ - 1 else "Bottom", ds.ATTR_BLUE))
    rows.append(Text(19, 1, "Press Enter to continue.", ds.ATTR_BLUE))
    rows.append(Text(21, 1, "F3=Exit   F12=Cancel", ds.ATTR_BLUE))
    return Screen(rows)
