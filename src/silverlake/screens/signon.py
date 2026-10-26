"""The sign-on screen and the session controller that sits behind it.

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

from ..cl import commands
from ..proto import datastream as ds
from ..system import admin, profiles
from ..system.profiles import Profile, ProfileStore
from .home import home_screen
from .model import Input, Screen, Text
from .usrprf import PAGE_SIZE, dspusrprf_screen, wrkusrprf_pages, wrkusrprf_screen

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
    runs the command line. Views (DSPUSRPRF, WRKUSRPRF) are kept as small state
    so F3 and F12 know where to go back to."""

    def __init__(self, display: str, store: ProfileStore | None = None) -> None:
        self.display = display
        self.store = store or profiles.load()
        self.profile: Profile | None = None
        self.view: tuple | None = None      # ("dsp", Profile, list view or None) or ("wrk", rows, page)

    def first(self) -> Screen:
        return signon_screen(self.display)

    def close(self) -> None:
        """The connection is gone. Count the session out."""
        self._sign_off()

    def _sign_off(self) -> None:
        if self.profile is not None:
            self.store.sign_off(self.profile)
        self.profile = None
        self.view = None

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
        self.store.sign_on(self.profile)
        return home_screen(self.store, self.profile)

    # -- after sign-on ----------------------------------------------------------

    def _home(self, aid: str, values: dict[str, str]) -> Screen:
        if self.view is not None:
            return self._in_view(aid, values)
        if aid in ("F3", "F12"):
            self._sign_off()
            return signon_screen(self.display)
        line = values.get("command", "").strip()
        if not line:
            return home_screen(self.store, self.profile)
        outcome = commands.execute(self.store, self.profile, line)
        if outcome.signoff:
            self._sign_off()
            return signon_screen(self.display)
        if outcome.view:
            kind, subject = outcome.view
            self.view = ("dsp", subject, None) if kind == "dspusrprf" else ("wrk", subject, 0)
            return self._draw_view()
        return home_screen(self.store, self.profile, outcome.message.line() if outcome.message else "")

    def _draw_view(self, message: str = "") -> Screen:
        if self.view[0] == "dsp":
            return dspusrprf_screen(self.store, self.view[1])
        return wrkusrprf_screen(self.view[1], self.view[2], message)

    def _in_view(self, aid: str, values: dict[str, str]) -> Screen:
        kind = self.view[0]
        if aid == "F3" or (kind == "wrk" and aid == "F12"):
            self.view = None
            return home_screen(self.store, self.profile)
        if kind == "dsp":
            self.view = self.view[2]       # back to the list we came from, if any
            if self.view is not None:
                return self._draw_view()
            return home_screen(self.store, self.profile)
        if aid == "F12":
            self.view = None
            return home_screen(self.store, self.profile)
        _, rows, page = self.view
        if aid in ("ROLLUP", "ROLLDOWN"):
            step = 1 if aid == "ROLLUP" else -1
            self.view = ("wrk", rows, max(0, min(page + step, wrkusrprf_pages(len(rows)) - 1)))
            return self._draw_view()
        for i in range(PAGE_SIZE):
            opt = values.get(f"opt{i}", "").strip()
            if not opt:
                continue
            index = page * PAGE_SIZE + i
            if opt != "5":
                return self._draw_view(f"Option {opt} is not valid.")
            target, err = admin.display(self.store, self.profile, rows[index].name)
            if err:
                return self._draw_view(err.line())
            self.view = ("dsp", target, self.view)
            return self._draw_view()
        return self._draw_view()
