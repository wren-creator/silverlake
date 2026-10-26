"""A placeholder menu shown after a successful sign-on.

It exists so a signed-on user can see what access they were given. It is not a
copy of any real IBM i menu, and it goes away when the real menus and the CL
command line arrive."""

from ..proto import datastream as ds
from ..system.profiles import Profile, ProfileStore
from .model import Input, Screen, Text

LABEL_COL = 4
VALUE_COL = 34
VALUE_WIDTH = 80 - VALUE_COL - 1   # leave the last cell for the next attribute


def wrap(value: str, width: int = VALUE_WIDTH) -> list[str]:
    """Break a space separated value into lines that fit beside its label."""
    lines, cur = [], ""
    for word in value.split(" "):
        if cur and len(cur) + 1 + len(word) > width:
            lines.append(cur)
            cur = word
        else:
            cur = f"{cur} {word}".strip()
    return lines + [cur]


def home_screen(store: ProfileStore, profile: Profile, message: str = "") -> Screen:
    info = store.describe(profile)
    rows: list[Text | Input] = [
        Text(0, 30, "Silverlake", ds.ATTR_WHITE),
        Text(1, 20, "Placeholder menu. Real menus arrive with the CL layer.", ds.ATTR_GREEN),
    ]
    facts = [
        ("User profile", info["profile"]),
        ("User class", info["class"]),
        ("Special authority from", info["special_source"]),
        ("Special authorities", info["special"]),
        ("Group profile", info["group"]),
        ("Limited capabilities", profile.limited_capabilities),
        ("QSECURITY", str(store.system.qsecurity)),
    ]
    row = 3
    for label, value in facts:
        rows.append(Text(row, LABEL_COL, f"{label} ".ljust(VALUE_COL - LABEL_COL - 3, ".") + " :", ds.ATTR_GREEN))
        for line in wrap(value):
            rows.append(Text(row, VALUE_COL, line, ds.ATTR_WHITE))
            row += 1
    rows += [
        Text(19, 2, "Selection or command", ds.ATTR_GREEN),
        Text(20, 2, "===>", ds.ATTR_GREEN),
        Input(20, 7, 70, "command", monocase=True),
        Text(22, 2, "F3=Sign off", ds.ATTR_GREEN),
    ]
    if message:
        rows.append(Text(21, 2, message[:76], ds.ATTR_WHITE))
    return Screen(rows, cursor="command")
