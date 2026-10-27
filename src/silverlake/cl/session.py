"""What a signed-on job carries between commands: its library list.

The default list follows a real IBM i (DSPLIBL on PUB400): QSYS, QSYS2, QUSRSYS
and QHLPSYS in the system portion, then the current library, then QGPL and QTEMP
in the user portion. A real list is built from system values we do not model, and
a real site adds its own libraries. QTEMP is one library per job on a real
system. Here the library is shared but each object in it is tagged with the job that made it and only
that job can see it (`system.objects.in_temp`)."""

from dataclasses import dataclass, field

SYSTEM_PORTION = ("QSYS", "QSYS2", "QUSRSYS", "QHLPSYS")
DEFAULT_USER_PORTION = ("QGPL", "QTEMP")
MAX_USER_ENTRIES = 250       # IBM: "A maximum of 250 libraries"
MAX_MENUS = 10               # IBM: "Each menu stack is ten elements (menus) deep"


class SearchList(list):
    """The library names in search order, carrying whose job asked. QTEMP is one library per job on a real
    system, so an object in it is only there for the job that made it, and whoever looks it up needs to
    say which job they are."""

    job: str | None = None


@dataclass
class Session:
    user_libs: list[str] = field(default_factory=lambda: list(DEFAULT_USER_PORTION))
    current_library: str | None = None
    # The menu stack (library, name), ten deep as GO documents. return_points are
    # indexes of frames a GO was typed from with RTNPNT(*YES); F3 returns to the last one.
    menu_stack: list[tuple[str, str]] = field(default_factory=list)
    return_points: list[tuple[int, str]] = field(default_factory=list)
    mode: str = "menu"                  # what the job is looking at: "menu" or "cmdentry"
    history: list[str] = field(default_factory=list)   # command entry, newest last
    joblog: list = field(default_factory=list)   # (time, "command" or "message", text), for the job log
    job: object | None = None           # this session's row in the job table
    overrides: dict = field(default_factory=dict)   # OVRDBF: file name -> {"to": "LIB/NAME", "secure": bool}

    @classmethod
    def for_profile(cls, current_library: str) -> "Session":
        s = cls()
        if current_library and not current_library.startswith("*"):
            s.current_library = current_library
        return s

    def entries(self) -> list[tuple[str, str]]:
        """(library, type) in search order: system, current, user."""
        out = [(lib, "SYS") for lib in SYSTEM_PORTION]
        if self.current_library:
            out.append((self.current_library, "CUR"))
        return out + [(lib, "USR") for lib in self.user_libs]

    def search_order(self) -> SearchList:
        found = SearchList(lib for lib, _ in self.entries())
        found.job = self.job.qualified if self.job is not None else None
        return found

    def push_menu(self, key: tuple[str, str], return_point: bool, origin: str = "menu") -> None:
        """GO. With RTNPNT(*YES) the display GO was typed on ("menu" or "cmdentry") becomes
        the place F3 returns to."""
        if return_point:
            self.return_points.append((len(self.menu_stack) - 1, origin))
        self.menu_stack.append(key)
        if len(self.menu_stack) > MAX_MENUS:           # the eleventh pushes the oldest out
            del self.menu_stack[0]
            self.return_points = [(i - 1, o) for i, o in self.return_points if i > 0]

    def cancel(self) -> bool:
        """F12 on a menu: the previous menu. False when there is none."""
        if len(self.menu_stack) <= 1:
            return False
        self.menu_stack.pop()
        self.return_points = [(i, o) for i, o in self.return_points if i < len(self.menu_stack)]
        return True

    def exit(self) -> str | None:
        """F3 on a menu: back to where GO was typed with RTNPNT(*YES). Returns "menu" or
        "cmdentry", or None when there is no such place (seen on a real system: F3 on the
        initial menu does nothing)."""
        if not self.return_points:
            return None
        index, origin = self.return_points.pop()
        del self.menu_stack[index + 1:]
        return origin
