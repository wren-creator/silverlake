"""Turn a Screen into the bytes a 5250 terminal wants: clear the unit, write
the display, then ask for the modified fields."""

from ..proto import datastream as ds
from ..proto import ebcdic
from .model import COLS, Input, Screen, Text


def _cell(row: int, col: int, back: int = 0) -> bytes:
    """Wire address of the cell `back` cells before (row, col), wrapping rows."""
    r, c = divmod(row * COLS + col - back, COLS)
    return ds.address(r, c)


def _text(f: Text) -> bytes:
    # SBA to the attribute cell, then the attribute byte, then the text.
    return bytes([ds.ORDER_SBA]) + _cell(f.row, f.col, 1) + bytes([f.attr]) + ebcdic.encode(f.text)


def _input(f: Input) -> bytes:
    if f.hidden:
        attr = ds.ATTR_NONDISPLAY
    elif f.error:
        attr = ds.ATTR_REVERSE_UNDERLINE
    else:
        attr = ds.ATTR_WHITE_UNDERLINE if f.required else ds.ATTR_GREEN_UNDERLINE
    ffw1, ffw2 = ds.FFW_ALPHA
    if f.monocase:
        ffw2 |= ds.FFW2_MONOCASE
    sf = bytes([ds.ORDER_SF, ffw1, ffw2, attr, f.length >> 8, f.length & 0xFF])
    content = ebcdic.encode(f.value.ljust(f.length)[: f.length]) if f.value else b""
    # Real systems close every field with a plain attribute cell right after
    # it, so the next run is not swallowed by the field.
    end = bytes([ds.ORDER_SBA]) + _cell(f.row, f.col + f.length) + bytes([ds.ATTR_GREEN])
    return bytes([ds.ORDER_SBA]) + _cell(f.row, f.col, 1) + sf + content + end


def render(screen: Screen) -> bytes:
    """Return the data stream for one screen, without GDS framing."""
    screen.validate()
    wtd = bytearray([ds.ESC, ds.CMD_WRITE_TO_DISPLAY, ds.CC1_NONE, ds.CC2_UNLOCK])
    for f in screen.fields:
        wtd += _text(f) if isinstance(f, Text) else _input(f)

    inputs = screen.inputs()
    if inputs:
        target = next((i for i in inputs if i.name == screen.cursor), inputs[0])
        wtd += bytes([ds.ORDER_IC]) + _cell(target.row, target.col)

    return (
        bytes([ds.ESC, ds.CMD_CLEAR_UNIT])
        + bytes(wtd)
        + bytes([ds.ESC, ds.CMD_READ_MDT_FIELDS, 0x00, 0x00])
    )
