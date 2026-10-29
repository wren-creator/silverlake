"""The screen model. Rows and columns are 0-based and name the first visible
character. The attribute cell that 5250 needs in front of each run is the
renderer's business, not the screen author's. It sits in the cell just before
the run, which for a run at column 0 is the last cell of the row above."""

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
    length: int  # may run past the end of the row, as a real 128 character password field does
    name: str
    hidden: bool = False    # password style, nothing echoed
    monocase: bool = False  # the terminal upper-cases what is typed
    value: str = ""
    required: bool = False  # drawn brighter, the way a prompt marks a parameter it will not run without
    error: bool = False     # drawn in reverse image, the way a prompt marks a parameter it just refused


@dataclass
class Screen:
    fields: list[Text | Input] = field(default_factory=list)
    cursor: str | None = None  # name of the Input that gets the cursor; first Input if None

    def inputs(self) -> list[Input]:
        return [f for f in self.fields if isinstance(f, Input)]

    def validate(self) -> None:
        names = set()
        cells = ROWS * COLS
        for f in self.fields:
            if not (0 <= f.row < ROWS and 0 <= f.col < COLS):
                raise ValueError(f"{f}: off the screen")
            start = f.row * COLS + f.col
            if start < 1:
                raise ValueError(f"{f}: the attribute cell needs a cell before the first one")
            if isinstance(f, Text):
                if f.col + len(f.text) > COLS:
                    raise ValueError(f"{f}: runs off the right edge")
                continue
            if f.length < 1:
                raise ValueError(f"{f}: length must be at least 1")
            if start + f.length > cells - 1:
                raise ValueError(f"{f}: no room for the closing attribute cell")
            if f.name in names:
                raise ValueError(f"duplicate input name {f.name!r}")
            names.add(f.name)
        if self.cursor is not None and self.cursor not in names:
            raise ValueError(f"cursor names unknown input {self.cursor!r}")
