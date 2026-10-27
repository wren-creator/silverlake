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
from ..system import admin, menus, messages, objects, profiles
from ..system.profiles import Profile, ProfileStore
from ..cl.session import Session
from .menu import command_entry_screen, menu_screen
from .model import Input, Screen, Text
from .objects import dsplibl_screen, dspobjaut_screen, dspautl_screen, pages, wrkautl_screen, wrklib_screen, wrkobj_screen
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
        self.session = Session()
        # ("dsp", Profile, list view or None), ("wrk", rows, page), or
        # ("plist", rows, page, renderer) for a list with paging and no options
        self.view: tuple | None = None

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
        return self._start(result.profile, values)

    # -- sign-on values ---------------------------------------------------------------

    def _refuse(self, profile: Profile, what: str) -> Screen:
        return signon_screen(self.display, messages.signon_value_not_allowed(what).line(), profile.name)

    def _start(self, profile: Profile, values: dict[str, str]) -> Screen:
        """Honor the program, menu and library typed at sign-on, as limited capabilities
        allows (IBM LMTCPB: *PARTIAL locks program and current library, *YES the menu too)."""
        typed = {k: values.get(k, "").strip().upper() for k in ("program", "menu", "library")}
        lmt = profile.limited_capabilities
        if typed["program"] and lmt in ("*PARTIAL", "*YES"):
            return self._refuse(profile, "Program")
        if typed["menu"] and lmt == "*YES":
            return self._refuse(profile, "Menu")
        if typed["library"] and lmt in ("*PARTIAL", "*YES"):
            return self._refuse(profile, "Current library")
        library = typed["library"] or profile.current_library
        if typed["library"] and self.store.find_library(typed["library"]) is None:
            return signon_screen(self.display, messages.library_not_found(typed["library"]).line(), profile.name)
        program = typed["program"] or profile.initial_program
        menu = typed["menu"] or profile.initial_menu
        if program not in ("*NONE", "QCMD", "QSYS/QCMD"):
            return signon_screen(self.display, messages.program_not_found(program).line(), profile.name)
        if program == "*NONE" and menu == "*SIGNOFF":
            return signon_screen(self.display)

        self.profile = profile
        self.session = Session.for_profile(library)
        self.store.sign_on(profile)
        if program != "*NONE":
            self.session.mode = "cmdentry"
            return self._base()
        obj, err = objects.use_object(self.store, profile, menu, "*MENU", self.session.search_order())
        if err:
            self.session.mode = "cmdentry"        # nowhere to land: command entry, with the reason
            return self._base(err.line())
        self.session.push_menu((obj.library, obj.name), False)
        return self._base()

    # -- the base display: a menu or command entry ------------------------------------------

    def _menu(self) -> tuple[str, menus.Menu]:
        library, name = self.session.menu_stack[-1]
        return name, menus.parse(self.store.objects[(library, name, "*MENU")].data, name)

    def _base(self, message: str = "") -> Screen:
        if self.session.mode == "cmdentry" or not self.session.menu_stack:
            return command_entry_screen(self.session.history, message)
        name, menu = self._menu()
        return menu_screen(SYSTEM_NAME, name, menu, message)

    # -- after sign-on ----------------------------------------------------------

    def _home(self, aid: str, values: dict[str, str]) -> Screen:
        if self.view is not None:
            return self._in_view(aid, values)
        sess = self.session
        if not sess.menu_stack:
            sess.mode = "cmdentry"          # no menu to look at
        if aid in ("F3", "F12"):
            if sess.mode == "cmdentry":
                if sess.menu_stack:
                    sess.mode = "menu"
                    return self._base()
                self._sign_off()
                return signon_screen(self.display)
            if aid == "F12":
                sess.cancel()
            else:
                origin = sess.exit()
                if origin:
                    sess.mode = origin
            return self._base()
        line = values.get("command", "").strip()
        if not line:
            return self._base()
        if sess.mode == "menu":
            item = self._menu()[1].find(line)
            if item is not None:
                return self._run(item.cmd)
            if self.profile.limited_capabilities == "*YES":
                return self._base(messages.command_line_not_allowed().line())
        return self._run(line)

    def _run(self, line: str) -> Screen:
        sess = self.session
        outcome = commands.execute(self.store, self.profile, line, sess)
        text = outcome.message.line() if outcome.message else ""
        if sess.mode == "cmdentry":
            sess.history.append("> " + line)
            if text:
                sess.history.append(text)
        if outcome.signoff:
            self._sign_off()
            return signon_screen(self.display)
        if outcome.view:
            self.view = self._open_view(outcome.view)
            return self._draw_view()
        if outcome.go:
            menu, rtnpnt = outcome.go
            sess.push_menu((menu.library, menu.name), bool(rtnpnt), sess.mode)
            sess.mode = "menu"
            return self._base()
        if outcome.cmdentry:
            sess.mode = "cmdentry"
            return self._base()
        return self._base(text)

    def _open_view(self, spec: tuple) -> tuple:
        kind = spec[0]
        if kind == "dspusrprf":
            return ("dsp", spec[1], None)
        if kind == "wrkusrprf":
            return ("wrk", spec[1], 0)
        if kind == "dsplibl":
            entries = spec[1].entries()
            return ("plist", entries, 0, lambda rows, page: dsplibl_screen(self.store, rows, page))
        if kind == "wrklib":
            return ("plist", spec[1], 0, wrklib_screen)
        if kind == "dspobjaut":
            obj = spec[1]
            return ("plist", spec[2], 0, lambda rows, page: dspobjaut_screen(obj, rows, page))
        if kind == "dspautl":
            autl = spec[1]
            return ("plist", spec[2], 0, lambda rows, page: dspautl_screen(autl, rows, page))
        if kind == "wrkautl":
            return ("plist", spec[1], 0, wrkautl_screen)
        if kind == "wrkobj":
            title = spec[2]
            return ("plist", spec[1], 0, lambda rows, page: wrkobj_screen(rows, title, page))
        raise AssertionError(kind)

    def _draw_view(self, message: str = "") -> Screen:
        if self.view[0] == "dsp":
            return dspusrprf_screen(self.store, self.view[1])
        if self.view[0] == "plist":
            return self.view[3](self.view[1], self.view[2])
        return wrkusrprf_screen(self.view[1], self.view[2], message)

    def _in_view(self, aid: str, values: dict[str, str]) -> Screen:
        kind = self.view[0]
        if kind == "plist":
            _, rows, page, renderer = self.view
            if aid in ("ROLLUP", "ROLLDOWN"):
                step = 1 if aid == "ROLLUP" else -1
                self.view = ("plist", rows, max(0, min(page + step, pages(len(rows)) - 1)), renderer)
                return self._draw_view()
            self.view = None                  # Enter, F3 and F12 all go back
            return self._base()
        if aid == "F3" or (kind == "wrk" and aid == "F12"):
            self.view = None
            return self._base()
        if kind == "dsp":
            self.view = self.view[2]       # back to the list we came from, if any
            if self.view is not None:
                return self._draw_view()
            return self._base()
        if aid == "F12":
            self.view = None
            return self._base()
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
