"""The sign-on screen and its Phase 1 controller. The labels and layout follow
the shape of a real IBM i sign-on so structure can be diffed against a capture;
the wording around them is ours. Real sign-on checks arrive in Phase 3."""

import time

from ..proto import datastream as ds
from .model import Input, Screen, Text

SYSTEM_NAME = "SILVERLK"
SUBSYSTEM = "QINTER"

_LABEL_COL = 2
_FIELD_COL = 53


def signon_screen(display: str, message: str = "", user: str = "") -> Screen:
    when = time.strftime("%m/%d/%y  %H:%M:%S")
    rows: list[Text | Input] = [
        Text(1, 30, "Sign On", ds.ATTR_WHITE),
        Text(3, _LABEL_COL, f"System  . . . . . :   {SYSTEM_NAME}", ds.ATTR_WHITE),
        Text(4, _LABEL_COL, f"Subsystem . . . . :   {SUBSYSTEM}", ds.ATTR_WHITE),
        Text(5, _LABEL_COL, f"Display . . . . . :   {display}", ds.ATTR_WHITE),
        Text(7, _LABEL_COL, "User  . . . . . . . . . . . . . . . . . . . . . . ."),
        Input(7, _FIELD_COL, 10, "user", value=user),
        Text(8, _LABEL_COL, "Password  . . . . . . . . . . . . . . . . . . . . ."),
        Input(8, _FIELD_COL, 10, "password", hidden=True),
        Text(9, _LABEL_COL, "Program/procedure  . . . . . . . . . . . . . . . . ."),
        Input(9, _FIELD_COL, 10, "program"),
        Text(10, _LABEL_COL, "Menu  . . . . . . . . . . . . . . . . . . . . . . ."),
        Input(10, _FIELD_COL, 10, "menu"),
        Text(11, _LABEL_COL, "Current library  . . . . . . . . . . . . . . . . ."),
        Input(11, _FIELD_COL, 10, "library"),
        Text(22, _LABEL_COL, when),
        Text(23, _LABEL_COL, "Silverlake simulated system. Not IBM."),
    ]
    if message:
        rows.append(Text(20, _LABEL_COL, message[:76], ds.ATTR_RED))
    return Screen(rows, cursor="user")


class SignonController:
    """One per connection. Phase 1 only proves the round trip: it draws the
    sign-on screen, reads back what was typed, and says it is not wired yet."""

    def __init__(self, display: str) -> None:
        self.display = display
        self.last_values: dict[str, str] = {}

    def first(self) -> Screen:
        return signon_screen(self.display)

    def handle(self, aid: str, values: dict[str, str]) -> Screen:
        self.last_values = values
        user = values.get("user", "").upper()
        return signon_screen(self.display, "Sign-on is not wired up yet (Phase 3).", user)
