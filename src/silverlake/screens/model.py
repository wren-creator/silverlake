"""The screen model. Rows and columns are 0-based and name the first visible
character. The attribute cell that 5250 needs in front of each run is the
renderer's business, not the screen author's."""

from dataclasses import dataclass, field

from ..proto import datastream as ds

ROWS, COLS = 24, 80


@dataclass(frozen=True)
class Text:
    row: int
    col: int
    text: str
    attr: int = ds.ATTR_GREEN


@dataclass(frozen=True)
class Input:
    row: int
    col: int
    length: int
    name: str
    hidden: bool = False  # password style, nothing echoed
    value: str = ""


@dataclass
class Screen:
    fields: list[Text | Input] = field(default_factory=list)
    cursor: str | None = None  # name of the Input that gets the cursor; first Input if None

    def inputs(self) -> list[Input]:
        return [f for f in self.fields if isinstance(f, Input)]

    def validate(self) -> None:
        names = set()
        for f in self.fields:
            if f.col < 1:
                raise ValueError(f"{f}: col must be >= 1, the attribute cell needs the column before it")
            if f.row < 0 or f.row >= ROWS:
                raise ValueError(f"{f}: row off the screen")
            width = f.length if isinstance(f, Input) else len(f.text)
            if f.col + width > COLS - 1 and isinstance(f, Input):
                raise ValueError(f"{f}: no room for the closing attribute cell")
            if f.col + width > COLS:
                raise ValueError(f"{f}: runs off the right edge")
            if isinstance(f, Input):
                if f.name in names:
                    raise ValueError(f"duplicate input name {f.name!r}")
                names.add(f.name)
        if self.cursor is not None and self.cursor not in names:
            raise ValueError(f"cursor names unknown input {self.cursor!r}")
