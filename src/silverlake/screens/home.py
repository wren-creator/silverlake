"""Shared by the display screens: wrapping a long value beside its label."""

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
