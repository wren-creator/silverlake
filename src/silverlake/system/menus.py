"""Menus are *MENU objects whose `data` holds a title and numbered options, each
option running a command. Layout on the screen follows a real IBM i MAIN menu
captured from PUB400 (positions only; the wording here is ours)."""

from dataclasses import dataclass

MAX_ITEMS = 13        # rows 4 to 16 of the menu screen


class MenuError(ValueError):
    pass


@dataclass(frozen=True)
class MenuItem:
    opt: str
    text: str
    cmd: str


@dataclass(frozen=True)
class Menu:
    title: str
    items: tuple[MenuItem, ...]

    def find(self, typed: str) -> MenuItem | None:
        """Option 1 and 01 are the same option, as on a real menu."""
        typed = typed.strip()
        if not typed:
            return None
        for item in self.items:
            if item.opt == typed or (typed.isdigit() and item.opt.isdigit() and int(item.opt) == int(typed)):
                return item
        return None


def parse(data: dict, who: str = "menu") -> Menu:
    title = data.get("title")
    items = data.get("items", [])
    if not isinstance(title, str) or not title.strip() or len(title) > 40:
        raise MenuError(f"{who}: needs a title of 1 to 40 characters")
    if not isinstance(items, list) or len(items) > MAX_ITEMS:
        raise MenuError(f"{who}: at most {MAX_ITEMS} options")
    parsed, seen = [], set()
    for raw in items:
        opt, text, cmd = str(raw.get("opt", "")).strip(), str(raw.get("text", "")), str(raw.get("cmd", "")).strip()
        if not opt or len(opt) > 2 or not opt.isdigit():
            raise MenuError(f"{who}: option {opt!r} must be one or two digits")
        if str(int(opt)) in seen:
            raise MenuError(f"{who}: option {opt} appears twice")
        if not text or len(text) > 60 or not cmd:
            raise MenuError(f"{who}: option {opt} needs text (up to 60 characters) and a command")
        seen.add(str(int(opt)))
        parsed.append(MenuItem(opt, text, cmd))
    return Menu(title.strip(), tuple(parsed))
