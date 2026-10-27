"""Screens for DSPUSRPRF and WRKUSRPRF. Layout and wording are ours; a real
system's screens have not been captured for these commands yet."""

from ..proto import datastream as ds
from ..system.authority import name_auth
from ..system.profiles import Profile, ProfileStore
from .home import wrap
from .model import Input, Screen, Text

LABEL_COL = 2
VALUE_COL = 36
VALUE_WIDTH = 80 - VALUE_COL - 1

PAGE_SIZE = 15
FIRST_ROW = 5


def _fact(rows: list, row: int, label: str, value: str) -> int:
    rows.append(Text(row, LABEL_COL, f"{label} ".ljust(VALUE_COL - LABEL_COL - 3, ".") + " :", ds.ATTR_GREEN))
    for line in wrap(value or " ", VALUE_WIDTH):
        rows.append(Text(row, VALUE_COL, line, ds.ATTR_GREEN))
        row += 1
    return row


def dspusrprf_screen(store: ProfileStore, p: Profile) -> Screen:
    info = store.describe(p)
    rows: list[Text | Input] = [Text(0, 26, "Display User Profile - Basic", ds.ATTR_WHITE)]
    facts = [
        ("User profile", p.name),
        ("Status", p.status),
        ("Password", info["password"] + (", expired" if p.password_expired else "")),
        ("Password expiration interval", "*SYSVAL" if p.pwd_expitv is None else (
            "*NOMAX" if p.pwd_expitv == 0 else str(p.pwd_expitv))),
        ("User class", p.user_class.value),
        ("Special authority from", info["special_source"]),
        ("Special authorities", info["special"]),
        ("Group profile", info["group"]),
        ("Supplemental groups", " ".join(p.supplemental_groups) or "*NONE"),
        ("Owner", p.owner),
        ("Public authority (AUT)", name_auth(p.public_authority)),
        ("Limited capabilities", p.limited_capabilities),
        ("Initial program", p.initial_program),
        ("Initial menu", p.initial_menu),
        ("Current library", p.current_library),
        ("Signed on sessions", str(store.active.get(p.name, 0))),
        ("Text", p.text or "*BLANK"),
    ]
    row = 2
    for label, value in facts:
        row = _fact(rows, row, label, value)
    rows += [Text(22, 2, "Press Enter to continue.", ds.ATTR_GREEN),
             Text(23, 2, "F3=Exit   F12=Cancel", ds.ATTR_GREEN)]
    return Screen(rows)


def wrkusrprf_pages(count: int) -> int:
    return max(1, -(-count // PAGE_SIZE))


def wrkusrprf_screen(profiles: list[Profile], page: int = 0, message: str = "") -> Screen:
    page = max(0, min(page, wrkusrprf_pages(len(profiles)) - 1))
    shown = profiles[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]
    rows: list[Text | Input] = [
        Text(0, 28, "Work with User Profiles", ds.ATTR_WHITE),
        Text(2, 2, "Type options, press Enter.", ds.ATTR_BLUE),
        Text(3, 4, "5=Display", ds.ATTR_BLUE),
        Text(4, 2, "Opt", ds.ATTR_WHITE),
        Text(4, 7, "User Profile", ds.ATTR_WHITE),
        Text(4, 22, "Class", ds.ATTR_WHITE),
        Text(4, 32, "Group", ds.ATTR_WHITE),
        Text(4, 44, "Text", ds.ATTR_WHITE),
    ]
    for i, p in enumerate(shown):
        r = FIRST_ROW + i
        rows += [
            Input(r, 3, 1, f"opt{i}"),
            Text(r, 7, p.name, ds.ATTR_GREEN),
            Text(r, 22, p.user_class.value, ds.ATTR_GREEN),
            Text(r, 32, p.group_profile or "*NONE", ds.ATTR_GREEN),
            Text(r, 44, p.text[:34], ds.ATTR_GREEN),
        ]
    more = "More..." if page < wrkusrprf_pages(len(profiles)) - 1 else "Bottom"
    rows.append(Text(FIRST_ROW + PAGE_SIZE, 70, more, ds.ATTR_WHITE))
    if message:
        rows.append(Text(22, 2, message[:76], ds.ATTR_WHITE))
    rows.append(Text(23, 2, "F3=Exit   F12=Cancel   Page Up/Down", ds.ATTR_GREEN))
    return Screen(rows)
