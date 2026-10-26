"""What a signed-on job carries between commands: its library list.

The default list is a simplification. A real one has a system portion, product
libraries, a current library and a user portion, built from system values we do
not model. Here: QSYS and QUSRSYS in the system portion, QGPL in the user
portion, plus the profile's current library when it names one."""

from dataclasses import dataclass, field

SYSTEM_PORTION = ("QSYS", "QUSRSYS")
DEFAULT_USER_PORTION = ("QGPL",)
MAX_USER_ENTRIES = 250       # IBM: "A maximum of 250 libraries"


@dataclass
class Session:
    user_libs: list[str] = field(default_factory=lambda: list(DEFAULT_USER_PORTION))
    current_library: str | None = None

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

    def search_order(self) -> list[str]:
        return [lib for lib, _ in self.entries()]
