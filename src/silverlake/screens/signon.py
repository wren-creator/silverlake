"""The sign-on screen and its Phase 1 controller.

The layout is the stock one, taken from two sources that agree: a photo of a
default sign-on display (the status bar read 6/53, which fixes the field column
exactly) and a PUB400 capture, whose right hand block is stock. The wording is
ours. Real sign-on checks arrive in Phase 3.

Layout (0-based rows and columns):
  row 0          title
  rows 1-3       System / Subsystem / Display, labels at col 47, values at col 69
  rows 5-9       User, Password, Program/procedure, Menu, Current library,
                 labels at col 14, input fields at col 52
  row 23         copyright line at col 39, or the message when there is one
Label columns are read off a photo and good to about one column. The field
column, the right hand block, and the copyright column are exact.
"""

from ..proto import datastream as ds
from ..system import profiles
from ..system.profiles import Profile, ProfileStore
from .home import home_screen
from .model import Input, Screen, Text

SYSTEM_NAME = "SILVERLK"
SUBSYSTEM = "QINTER"

TITLE_COL = 34         # estimated from the photo, centered about col 37
INFO_LABEL_COL = 47
INFO_VALUE_COL = 69
LABEL_COL = 14
LABEL_WIDTH = 35       # label and its dots run to col 48, the field starts at col 52
FIELD_COL = 52

# Colors from the PUB400 capture. A monochrome photo cannot confirm them.
INFO_LABEL_ATTR = ds.ATTR_BLUE
INFO_VALUE_ATTR = ds.ATTR_TURQUOISE


def dotted(label: str, width: int = LABEL_WIDTH) -> str:
    """A label followed by alternating dots, the last dot on the last column,
    the way IBM i prompts line up."""
    chars = list(label.ljust(width))
    for i in range(width - 1, len(label), -2):
        chars[i] = "."
    return "".join(chars)


def signon_screen(display: str, message: str = "", user: str = "") -> Screen:
    rows: list[Text | Input] = [
        Text(0, TITLE_COL, "Sign On", ds.ATTR_WHITE),
        Text(1, INFO_LABEL_COL, "System  . . . . . :", INFO_LABEL_ATTR),
        Text(1, INFO_VALUE_COL, SYSTEM_NAME, INFO_VALUE_ATTR),
        Text(2, INFO_LABEL_COL, "Subsystem . . . . :", INFO_LABEL_ATTR),
        Text(2, INFO_VALUE_COL, SUBSYSTEM, INFO_VALUE_ATTR),
        Text(3, INFO_LABEL_COL, "Display . . . . . :", INFO_LABEL_ATTR),
        Text(3, INFO_VALUE_COL, display, INFO_VALUE_ATTR),
        Text(5, LABEL_COL, dotted("User")),
        Input(5, FIELD_COL, 10, "user", monocase=True, value=user),
        Text(6, LABEL_COL, dotted("Password")),
        Input(6, FIELD_COL, 10, "password", hidden=True),
        Text(7, LABEL_COL, dotted("Program/procedure")),
        Input(7, FIELD_COL, 10, "program", monocase=True),
        Text(8, LABEL_COL, dotted("Menu")),
        Input(8, FIELD_COL, 10, "menu", monocase=True),
        Text(9, LABEL_COL, dotted("Current library")),
        Input(9, FIELD_COL, 10, "library", monocase=True),
    ]
    # A real IBM i puts the message on the bottom row, in white, and it takes
    # the place of the copyright line there (seen in a PUB400 capture).
    if message:
        rows.append(Text(23, 0, message[:80], ds.ATTR_WHITE))
    else:
        rows.append(Text(23, 39, "SILVERLAKE SIMULATION. NOT IBM.", ds.ATTR_WHITE))
    return Screen(rows, cursor="user")


class SignonController:
    """One per connection. Checks the sign-on against the profile store, then
    shows the placeholder menu. Sign off (F3) returns to the sign-on screen."""

    def __init__(self, display: str, store: ProfileStore | None = None) -> None:
        self.display = display
        self.store = store or profiles.load()
        self.profile: Profile | None = None

    def first(self) -> Screen:
        return signon_screen(self.display)

    def handle(self, aid: str, values: dict[str, str]) -> Screen:
        if self.profile is not None:
            return self._home(aid, values)
        user = values.get("user", "").strip()
        if not user:
            return signon_screen(self.display)
        result = self.store.check_signon(user, values.get("password", ""))
        if result.profile is None:
            return signon_screen(self.display, result.message.line(), user.upper())
        self.profile = result.profile
        return home_screen(self.store, self.profile)

    def _home(self, aid: str, values: dict[str, str]) -> Screen:
        if aid in ("F3", "F12"):
            self.profile = None
            return signon_screen(self.display)
        command = values.get("command", "").strip()
        message = "Commands arrive with the CL layer." if command else ""
        return home_screen(self.store, self.profile, message)
