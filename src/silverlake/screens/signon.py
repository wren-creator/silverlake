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

from dataclasses import dataclass
from datetime import datetime

from ..cl import commands
from ..proto import datastream as ds
from ..system import admin, autls, menus, messages, msgq, objects, profiles, spool
from ..system.authority import ALL, CHANGE, EXCLUDE
from ..system.profiles import Profile, ProfileStore
from ..cl.session import Session
from .menu import command_entry_screen, menu_screen
from .model import Input, Screen, Text
from .objects import dsplibl_screen, dspobjaut_screen, dspautl_screen, pages, wrklib_screen
from .worklists import (EditAuth, WorkList, add_users_screen, confirm_delete_screen, dspobjd_basic_screen,
                        dspmsg_screen, message_lines as dspmsg_lines, dspobjd_screen, dspsplf_screen, objects_in_list_screen, spoolattr_screen)
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


@dataclass
class _AutlRow:
    """An authorization list, shaped like an object row so the confirm screen can show it."""
    autl: object
    type: str = "*AUTL"
    library: str = "QSYS"

    @property
    def name(self) -> str:
        return self.autl.name

    @property
    def text(self) -> str:
        return self.autl.text


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
        # views a work list opened (option 5 and the like), so Enter and F3 come back to the list
        self.parents: list[tuple] = []

    def first(self) -> Screen:
        return signon_screen(self.display)

    def close(self) -> None:
        """The connection is gone. Count the session out."""
        self._sign_off()

    def _sign_off(self) -> None:
        if self.profile is not None:
            self.store.sign_off(self.profile)
            spool.write_joblog(self.store, self.session.job, self.session.joblog)
            self.store.jobs.end(self.session.job)
        self.profile = None
        self.view = None
        self.parents.clear()

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
        self.session.job = self.store.jobs.start_interactive(
            profile.name, self.display, max((int(f.job_number) for f in self.store.spool), default=0))
        if program != "*NONE":
            self.session.mode = "cmdentry"
            return self._base()
        obj, err = objects.use_object(self.store, profile, menu, "*MENU", self.session.search_order())
        if err:
            self.session.mode = "cmdentry"        # nowhere to land: command entry, with the reason
            return self._base(err.text)
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

    def _log(self, line: str, outcome: "commands.Outcome") -> None:
        """What the job log will say: the command, and the message it raised."""
        now = datetime.now()
        self.session.joblog.append((now, "command", line))
        if outcome.message and outcome.message.text:
            self.session.joblog.append((now, "message", outcome.message.text))

    def _run(self, line: str) -> Screen:
        outcome = commands.execute(self.store, self.profile, line, self.session)
        self._log(line, outcome)
        return self._apply(outcome, line)

    def _apply(self, outcome: commands.Outcome, line: str) -> Screen:
        sess = self.session
        text = outcome.message.text if outcome.message else ""
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
            return ("work", WorkList("autls", spec[1], spec[2]))
        if kind == "wrkobj":
            return ("work", WorkList(spec[2], spec[1], spec[4], owner=spec[3] or ""))
        if kind == "wrksplf":
            return ("work", WorkList("spool", spec[1], spec[2]))
        if kind == "dspsplf":
            return ("spoolview", spec[1], 0)
        if kind == "dspmsg":
            return ("msgview", spec[1], 0)
        if kind == "wrkactjob":
            sbs = spec[1]
            own = self.session.job.qualified if self.session.job else ""
            return ("work", WorkList("jobs", self.store.jobs.active(sbs), lambda: self.store.jobs.active(sbs), owner=own))
        if kind == "edtobjaut":
            return ("edit", EditAuth(spec[1]))
        if kind == "dspobjd":
            return ("dobjd", spec[1], spec[2], 0)
        if kind == "autlobjs":
            name = spec[1]
            return ("plist", spec[2], 0, lambda rows, page: objects_in_list_screen(name, rows, page))
        raise AssertionError(kind)

    def _draw_view(self, message: str = "") -> Screen:
        if self.view[0] == "dsp":
            return dspusrprf_screen(self.store, self.view[1])
        if self.view[0] == "plist":
            return self.view[3](self.view[1], self.view[2])
        if self.view[0] == "work":
            return self.view[1].screen(message)
        if self.view[0] == "edit":
            return self.view[1].screen(message)
        if self.view[0] == "confirm":
            return confirm_delete_screen(self.view[2])
        if self.view[0] == "dobjd":
            _, obj, detail, page = self.view
            if detail == "*BASIC":
                return dspobjd_basic_screen(obj, message)
            return dspobjd_screen(obj, detail, SYSTEM_NAME, page)
        if self.view[0] == "spoolview":
            return dspsplf_screen(self.view[1], self.view[2], message)
        if self.view[0] == "msgview":
            return dspmsg_screen(self.view[1], SYSTEM_NAME, self.view[2], message)
        if self.view[0] == "spoolattr":
            return spoolattr_screen(self.view[1], SYSTEM_NAME)
        if self.view[0] == "add":
            return add_users_screen(self.view[1].obj, self.view[2], message)
        return wrkusrprf_screen(self.view[1], self.view[2], message)

    def _in_view(self, aid: str, values: dict[str, str]) -> Screen:
        kind = self.view[0]
        if kind == "plist":
            _, rows, page, renderer = self.view
            if aid in ("ROLLUP", "ROLLDOWN"):
                step = 1 if aid == "ROLLUP" else -1
                self.view = ("plist", rows, max(0, min(page + step, pages(len(rows)) - 1)), renderer)
                return self._draw_view()
            return self._close_view()            # Enter, F3 and F12 all go back
        if kind == "work":
            return self._in_work(aid, values)
        if kind == "edit":
            return self._in_edit(aid, values)
        if kind == "confirm":
            return self._in_confirm(aid)
        if kind == "dobjd":
            return self._in_dobjd(aid, values)
        if kind == "add":
            return self._in_add(aid, values)
        if kind == "spoolview":
            return self._in_spoolview(aid)
        if kind == "msgview":
            return self._in_msgview(aid)
        if kind == "spoolattr":
            if aid == "F3":
                self.view = None
                self.parents.clear()
                return self._base()
            return self._close_view()
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
                return self._draw_view(err.text)
            self.view = ("dsp", target, self.view)
            return self._draw_view()
        return self._draw_view()

    def _close_view(self) -> Screen:
        """Back to the work list that opened this view, or to the menu."""
        self.view = self.parents.pop() if self.parents else None
        return self._draw_view() if self.view is not None else self._base()

    # -- the work lists (WRKOBJ, WRKOBJOWN, WRKAUTL) --------------------------------------------

    def _in_work(self, aid: str, values: dict[str, str]) -> Screen:
        wl: WorkList = self.view[1]
        if aid in ("F3", "F12"):
            self.view = None
            self.parents.clear()
            return self._base()
        if aid in ("ROLLUP", "ROLLDOWN"):
            wl.page += 1 if aid == "ROLLUP" else -1
            wl.shown()
            return self._draw_view()
        if aid in ("F17", "F18") and wl.kind == "owner":          # Top and Bottom, as that display labels them
            wl.page = 0 if aid == "F17" else wl.pages - 1
            return self._draw_view()
        if aid == "F5":
            wl.refresh()
            return self._draw_view()
        param = values.get("command", "").strip()
        picks = [(i, values.get(f"opt{i}", "").strip()) for i in range(wl.per_page)]
        picks = [(wl.page * wl.per_page + i, opt) for i, opt in picks if opt and wl.page * wl.per_page + i < len(wl.rows)]
        new_opt, new_name = values.get("optnew", "").strip(), values.get("newname", "").strip()
        if wl.kind == "autls" and (new_opt or new_name):
            if new_opt != "1" or not new_name:
                return self._draw_view("Option 1 needs a name for the new list." if new_opt == "1" or new_name
                                       else f"Option {new_opt} is not valid.")
            return self._work_exec(wl, f"CRTAUTL AUTL({new_name})")
        deletes = [wl.rows[i] if wl.kind != "autls" else _AutlRow(wl.rows[i]) for i, opt in picks if opt == "4"]
        if deletes and wl.kind in ("objects", "owner", "autls"):
            wl.retained = {i: opt for i, opt in picks}
            self.parents.append(self.view)
            self.view = ("confirm", wl, deletes)
            return self._draw_view()
        if picks:
            index, opt = picks[0]
            line, problem = self._work_option(wl, wl.rows[index], opt, param)
            if problem:
                return self._draw_view(problem)
            return self._work_exec(wl, line)
        if param:
            return self._work_exec(wl, param)
        return self._draw_view()

    def _work_option(self, wl: WorkList, row, opt: str, param: str) -> tuple[str | None, str]:
        """The command a work list option runs. The options the command line parameters feed
        are the ones the real display names ("Parameters for options 5, 7 and 13")."""
        if wl.kind == "spool":
            if opt in ("5", "8"):
                from ..system import spool
                f = row
                if not spool.can_display(self.store, self.profile, f):
                    return None, "Not authorized to spooled file."
                return f"@SPOOL{opt} {self.store.spool.index(f)}", ""
            if opt in ("3", "6"):
                verb = "HLDSPLF" if opt == "3" else "RLSSPLF"
                return f"{verb} FILE({row.name}) JOB({row.job}) SPLNBR({row.file_no})", ""
            if opt in ("1", "2", "4", "7", "9"):
                return None, f"Option {opt} is not available in Silverlake yet."
            return None, f"Option {opt} is not valid."
        if wl.kind == "jobs":
            if opt == "8" and row.type != "SBS":
                return f"WRKSPLF SELECT(*ALL) JOB({row.qualified})", ""
            if opt in ("2", "3", "4", "5", "6", "7", "8", "13"):
                return None, f"Option {opt} is not available in Silverlake yet."
            return None, f"Option {opt} is not valid."
        if wl.kind == "autls":
            if opt == "5":
                return f"DSPAUTL AUTL({row.name})", ""
            if opt == "8":
                return f"@AUTLOBJS {row.name}", ""
            if opt == "13":
                return f"@AUTLTEXT {row.name} {param}", ""
            if opt == "9":
                return None, "No documents or folders are secured by the list."
        else:
            ref = f"OBJ({row.library}/{row.name}) OBJTYPE({row.type})"
            if opt == "5":
                return f"DSPOBJAUT {ref}", ""
            if opt == "2":
                return f"EDTOBJAUT {ref}", ""
            if opt == "8":
                return f"DSPOBJD {ref} DETAIL(*FULL)", ""
            if opt == "7":
                return (f"RNMOBJ {ref} NEWOBJ({param.split()[0]})", "") if param else \
                    (None, "Type the new name on the command line for option 7.")
            if opt == "13" and wl.kind == "objects":
                return f"CHGOBJD {ref} TEXT('{param.replace(chr(39), chr(39) * 2)}')", ""
            if opt == "9" and wl.kind == "owner":
                return (f"CHGOBJOWN {ref} NEWOWN({param.split()[0]})", "") if param else \
                    (None, "Type the new owner on the command line for option 9.")
        if opt in ("1", "2", "3", "4", "8", "9", "13"):
            return None, f"Option {opt} is not available in Silverlake yet."
        return None, f"Option {opt} is not valid."

    def _work_exec(self, wl: WorkList, line: str) -> Screen:
        if line.startswith("@SPOOL"):                           # options 5 and 8 on Work with Spooled Files
            f = self.store.spool[int(line.split()[1])]
            self.parents.append(self.view)
            self.view = ("spoolview", f, 0) if line.startswith("@SPOOL5") else ("spoolattr", f)
            return self._draw_view()
        if line.startswith("@AUTLTEXT "):                       # option 13: change the list's text
            _, name, text = (line.split(None, 2) + [""])[:3]
            wl.retained = {}
            done = autls.change_text(self.store, self.profile, name, text)
            wl.refresh()
            return self._draw_view(done.message.text)
        if line.startswith("@AUTLOBJS "):                       # option 8: objects the list secures
            name = line.split()[1]
            cmd = self.store.objects.get(("QSYS", "DSPAUTL", "*CMD"))
            if cmd is None or commands.USE & ~self.store.authority_to_object(self.profile, cmd):
                return self._draw_view(messages.not_authorized_to_command("DSPAUTL").text)
            from ..system import objlist
            self.parents.append(self.view)
            self.view = self._open_view(("autlobjs", name, objlist.objects_secured_by(self.store, self.profile, name)))
            return self._draw_view()
        outcome = commands.execute(self.store, self.profile, line, self.session)
        self._log(line, outcome)
        if outcome.view:
            self.parents.append(self.view)
            self.view = self._open_view(outcome.view)
            return self._draw_view()
        if outcome.signoff or outcome.go or outcome.cmdentry:
            self.view = None
            self.parents.clear()
            return self._apply(outcome, line)
        wl.refresh()
        return self._draw_view(outcome.message.text if outcome.message else "")

    # -- Confirm Delete of Objects and Edit Object Authority ------------------------------------------

    DELETE_LINE = {"*LIB": "DLTLIB LIB({name})", "*FILE": "DLTF FILE({lib}/{name})",
                   "*CMD": "DLTCMD CMD({lib}/{name})", "*MENU": "DLTMNU MENU({lib}/{name})",
                   "*PGM": "DLTPGM PGM({lib}/{name})", "*AUTL": "DLTAUTL AUTL({name})"}

    def _in_confirm(self, aid: str) -> Screen:
        """F12 returns to the list with the options still typed. Enter deletes."""
        wl: WorkList = self.view[1]
        picks = self.view[2]
        self.view = self.parents.pop()
        if aid != "ENTER":
            return self._draw_view()
        wl.retained = {}
        done, last = 0, ""
        for obj in picks:
            line = self.DELETE_LINE[obj.type].format(name=obj.name, lib=obj.library)
            outcome = commands.execute(self.store, self.profile, line, self.session)
            text = outcome.message.text if outcome.message else ""
            if text.endswith("deleted."):
                done += 1
            last = text
        wl.refresh()
        message = last if len(picks) == 1 else (f"{done} objects deleted." + (f" {last}" if done < len(picks) else ""))
        return self._draw_view(message)

    def _in_msgview(self, aid: str) -> Screen:
        _, q, top = self.view
        if aid == "F3":
            self.view = None
            self.parents.clear()
            return self._base()
        if aid in ("ROLLUP", "ROLLDOWN"):
            last = max(0, len(dspmsg_lines(q)) - 1) // 13 * 13
            self.view = ("msgview", q, max(0, min(top + (13 if aid == "ROLLUP" else -13), last)))
            return self._draw_view()
        if aid in ("F13", "F16"):
            if not msgq.can_change(self.store, self.profile, q):
                return self._draw_view(msgq.not_authorized(q).text)
            msgq.messages_of(q).clear()
            self.store.on_change()
            self.view = ("msgview", q, 0)
            return self._draw_view("All messages removed." if aid == "F13" else "Messages removed.")
        if aid in ("F11", "F24"):
            return self._draw_view(f"{aid} is not available in Silverlake yet.")
        return self._close_view()

    def _in_spoolview(self, aid: str) -> Screen:
        _, f, top = self.view
        if aid == "F3":
            self.view = None
            self.parents.clear()
            return self._base()
        if aid in ("ROLLUP", "ROLLDOWN"):
            top = max(0, min(top + (16 if aid == "ROLLUP" else -16), max(0, len(f.lines) - 1) // 16 * 16))
            self.view = ("spoolview", f, top)
            return self._draw_view()
        if aid in ("F19", "F20", "F24"):
            return self._draw_view(f"{aid} is not available in Silverlake yet.")
        return self._close_view()

    def _in_dobjd(self, aid: str, values: dict[str, str]) -> Screen:
        """Display Object Description. The Basic list takes 5 (the full display) and 8 (service
        attributes, not modeled). On the Full display Roll Up and Roll Down switch pages (Enter was not
        captured, so it goes back, like F12), and F3 leaves everything."""
        _, obj, detail, page = self.view
        if aid == "F3":
            self.view = None
            self.parents.clear()
            return self._base()
        if detail == "*BASIC":
            opt = values.get("opt0", "").strip()
            if aid == "ENTER" and opt:
                if opt == "5":
                    self.parents.append(self.view)
                    self.view = ("dobjd", obj, "*FULL", 0)
                    return self._draw_view()
                return self._draw_view("Option 8 is not available in Silverlake yet." if opt == "8"
                                       else f"Option {opt} is not valid.")
            return self._close_view()
        if aid in ("ROLLUP", "ROLLDOWN"):
            self.view = ("dobjd", obj, detail, 1 if aid == "ROLLUP" else 0)
            return self._draw_view()
        return self._close_view()

    def _in_add(self, aid: str, values: dict[str, str]) -> Screen:
        """Add New Users. Enter grants each typed row through GRTOBJAUT's own rules and returns to
        the edit display. The first refusal keeps you here with what you typed."""
        ea = self.view[1]
        if aid == "F3":
            self.view = None
            self.parents.clear()
            return self._base()
        if aid == "F12":
            return self._close_view()
        if aid != "ENTER":
            return self._draw_view(f"{aid} is not available in Silverlake yet.")
        typed = {i: (values.get(f"user{i}", "").strip().upper(), values.get(f"auth{i}", "").strip().upper())
                 for i in range(10)}
        typed = {i: v for i, v in typed.items() if v[0] or v[1]}
        self.view = ("add", ea, typed)
        obj, ref = ea.obj, f"{ea.obj.library}/{ea.obj.name}"
        for user, text in typed.values():
            if not user or not text:
                return self._draw_view("Type both a user and an authority on each row.")
            try:
                aut = commands.resolve_aut([text])
            except ValueError:
                return self._draw_view(f"Authority {text} is not valid.")
            if isinstance(aut, messages.Message):
                return self._draw_view(aut.text)
            done = objects.grant(self.store, self.profile, ref, obj.type, self.session, [user], aut, "*NONE", True)
            if not done.ok:
                return self._draw_view(done.message.text)
        self.view = self.parents.pop()
        return self._draw_view("Authorities changed." if typed else "")

    def _in_edit(self, aid: str, values: dict[str, str]) -> Screen:
        ea: EditAuth = self.view[1]
        if aid == "F3":
            self.view = None
            self.parents.clear()
            return self._base()
        if aid == "F12":
            return self._close_view()
        if aid in ("ROLLUP", "ROLLDOWN"):
            ea.page += 1 if aid == "ROLLUP" else -1
            return self._draw_view()
        if aid in ("F17", "F18"):
            ea.page = 0 if aid == "F17" else ea.pages - 1
            return self._draw_view()
        if aid == "F6":
            self.parents.append(self.view)
            self.view = ("add", ea, {})
            return self._draw_view()
        if aid in ("F10", "F11"):
            return self._draw_view(f"{aid} is not available in Silverlake yet.")
        if aid == "F5":
            return self._draw_view()
        return self._draw_view(self._apply_edits(ea, values))

    def _apply_edits(self, ea: EditAuth, values: dict[str, str]) -> str:
        """Apply what was typed over the authorities, one change at a time through the same
        rules GRTOBJAUT and RVKOBJAUT use. Blank removes a user, which is our reading: the
        command page says nothing about it. The first refusal stops the rest."""
        obj, store, who = ea.obj, self.store, self.profile
        ref = f"{obj.library}/{obj.name}"
        changed = False
        for i, (user, current) in enumerate(ea.shown()):
            if f"auth{i}" not in values:
                continue
            typed = values[f"auth{i}"].strip().upper()
            if typed == current:
                continue
            if not typed:
                if user in ("*PUBLIC", obj.owner):
                    continue
                done = objects.revoke(store, who, ref, obj.type, self.session, [user], ALL, "*NONE")
            else:
                try:
                    aut = commands.resolve_aut([typed])
                except ValueError:
                    return f"Authority {typed} is not valid."
                if isinstance(aut, messages.Message):
                    return aut.text
                done = objects.grant(store, who, ref, obj.type, self.session, [user], aut, "*NONE", True)
            if not done.ok:
                return done.message.text
            changed = True
        typed = values.get("autl", "").strip().upper()
        if typed and typed != (obj.autl or "*NONE"):
            if typed == "*NONE":
                done = objects.revoke(store, who, ref, obj.type, self.session, [], EXCLUDE, obj.autl or "*NONE")
            else:
                done = objects.grant(store, who, ref, obj.type, self.session, [], CHANGE, typed, False)
            if not done.ok:
                return done.message.text
            changed = True
        return "Authorities changed." if changed else ""
