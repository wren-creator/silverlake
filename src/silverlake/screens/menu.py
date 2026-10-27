"""The menu and command entry screens. Positions follow a real IBM i main menu
captured from PUB400 (title row, System: block, options from row 4, "Selection or
command" on row 18, a 153 long command line at row 19, column 6, keys on row 21,
message on row 23). The wording is ours."""

from ..proto import datastream as ds
from ..system.menus import Menu
from .model import Input, Screen, Text

COMMAND_ROW, COMMAND_COL, COMMAND_LEN = 19, 6, 153
LAST_OPTION_ROW = 16          # a sign-off style option (80 and up) sits here, as on a real menu
HISTORY_LINES = 16
SYSTEM_LABEL_COL, SYSTEM_VALUE_COL = 61, 71


def _message(rows: list, message: str, row: int = 23) -> None:
    """A message takes the bottom row. A long one is cut with a plus sign at column 78,
    which is how a real message line shows there is more."""
    if len(message) > 77:
        rows.append(Text(row, 1, message[:77], ds.ATTR_WHITE))
        rows.append(Text(row, 78, "+", ds.ATTR_WHITE))
    else:
        rows.append(Text(row, 1, message, ds.ATTR_WHITE))


def menu_screen(system_name: str, name: str, menu: Menu, message: str = "") -> Screen:
    rows: list[Text | Input] = [
        Text(0, 1, name, ds.ATTR_BLUE),
        Text(0, max(0, (80 - len(menu.title)) // 2), menu.title, ds.ATTR_WHITE),
        Text(1, SYSTEM_LABEL_COL, "System:", ds.ATTR_GREEN),
        Text(1, SYSTEM_VALUE_COL, system_name, ds.ATTR_GREEN),
        Text(2, 1, "Select one of the following:", ds.ATTR_BLUE),
    ]
    row = 4
    for item in menu.items:
        if int(item.opt) >= 80 and row < LAST_OPTION_ROW:
            row = LAST_OPTION_ROW
        rows.append(Text(row, 6 if len(item.opt) == 1 else 5, f"{item.opt}. {item.text}", ds.ATTR_GREEN))
        row += 1
    rows += [
        Text(18, 1, "Selection or command", ds.ATTR_GREEN),
        Text(19, 1, "===>", ds.ATTR_GREEN),
        Input(COMMAND_ROW, COMMAND_COL, COMMAND_LEN, "command"),
        Text(21, 1, "F3=Exit   F12=Cancel", ds.ATTR_BLUE),
    ]
    if message:
        _message(rows, message)
    else:
        rows.append(Text(23, 1, "SILVERLAKE SIMULATION. NOT IBM.", ds.ATTR_WHITE))
    return Screen(rows, cursor="command")


def command_entry_screen(history: list[str], message: str = "") -> Screen:
    rows: list[Text | Input] = [
        Text(0, 33, "Command Entry", ds.ATTR_WHITE),
        Text(1, 1, "Previous commands and messages:", ds.ATTR_BLUE),
    ]
    for i, line in enumerate(history[-HISTORY_LINES:]):
        is_cmd = line.startswith("> ")
        rows.append(Text(2 + i, 1, line[:77], ds.ATTR_GREEN if is_cmd else ds.ATTR_WHITE))
    rows += [
        Text(19, 1, "Type command, press Enter.", ds.ATTR_BLUE),
        Text(20, 1, "===>", ds.ATTR_GREEN),
        Input(20, 6, COMMAND_LEN, "command"),
        Text(22, 1, "F3=Exit   F12=Cancel", ds.ATTR_BLUE),
    ]
    if message:
        _message(rows, message)
    return Screen(rows, cursor="command")
