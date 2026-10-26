import pytest

from silverlake.proto import datastream as ds
from silverlake.proto import ebcdic
from silverlake.screens.model import Input, Screen, Text
from silverlake.screens.render import render
from silverlake.screens.signon import signon_screen


def test_gds_round_trip():
    rec = ds.gds_record(b"abc")
    assert rec[:10] == bytes([0, 13, 0x12, 0xA0, 0, 0, 4, 0, 0, 3])
    assert ds.split_gds(rec) == (3, b"abc")


@pytest.mark.parametrize("bad", [b"", b"\x00\x05\x12\xa0\x00", bytes([0, 12, 0x13, 0xA0, 0, 0, 4, 0, 0, 3, 0, 0])])
def test_split_gds_rejects(bad):
    with pytest.raises(ds.ProtocolError):
        ds.split_gds(bad)


def test_split_gds_rejects_wrong_length():
    rec = bytearray(ds.gds_record(b"abc"))
    rec[1] = 99
    with pytest.raises(ds.ProtocolError):
        ds.split_gds(bytes(rec))


def test_parse_input_fields_and_aid():
    body = (
        bytes([5, 25, 0xF1])
        + bytes([ds.ORDER_SBA, 8, 54]) + ebcdic.encode("wren01") + b"\x00\x00"
        + bytes([ds.ORDER_SBA, 9, 54]) + ebcdic.encode("secret")
    )
    rec = ds.parse_input(body)
    assert (rec.cursor_row, rec.cursor_col, rec.aid_name) == (4, 24, "ENTER")
    assert [(f.row, f.col, f.text) for f in rec.fields] == [(7, 53, "wren01"), (8, 53, "secret")]


def test_parse_input_no_fields_and_function_keys():
    assert ds.parse_input(bytes([1, 1, 0x33])).aid_name == "F3"
    assert ds.parse_input(bytes([1, 1, 0xB1])).aid_name == "F13"
    assert ds.parse_input(bytes([1, 1, 0xBD])).aid_name == "CLEAR"
    assert ds.parse_input(bytes([1, 1, 0xF1])).fields == []


def test_parse_input_rejects_short_and_truncated_sba():
    with pytest.raises(ds.ProtocolError):
        ds.parse_input(b"\x01\x01")
    with pytest.raises(ds.ProtocolError):
        ds.parse_input(bytes([1, 1, 0xF1, ds.ORDER_SBA, 3]))


def test_render_exact_bytes_for_a_small_screen():
    s = Screen([Text(1, 2, "Hi", ds.ATTR_WHITE), Input(3, 10, 5, "x")], cursor="x")
    out = render(s)
    expected = (
        bytes([0x04, 0x40])                                  # clear unit
        + bytes([0x04, 0x11, 0x00, 0x18])                    # write to display, unlock
        + bytes([0x11, 2, 2, 0x22]) + ebcdic.encode("Hi")    # attr cell at col 1 -> wire col 2
        + bytes([0x11, 4, 10, 0x1D, 0x40, 0x00, 0x24, 0, 5])  # input field starts after attr cell
        + bytes([0x11, 4, 16, 0x20])                         # closing attribute cell
        + bytes([0x13, 4, 11])                               # cursor in the field
        + bytes([0x04, 0x52, 0x00, 0x00])                    # read MDT fields
    )
    assert out == expected


def test_render_hidden_field_is_nondisplay():
    out = render(Screen([Input(2, 5, 4, "pw", hidden=True)]))
    assert bytes([0x1D, 0x40, 0x00, 0x27, 0, 4]) in out


def test_render_prefilled_value_is_padded_to_length():
    out = render(Screen([Input(2, 5, 6, "u", value="AB")]))
    assert ebcdic.encode("AB    ") in out


def test_cursor_defaults_to_first_input():
    out = render(Screen([Input(5, 20, 3, "a"), Input(6, 20, 3, "b")]))
    assert bytes([0x13, 6, 21]) in out


@pytest.mark.parametrize("bad", [
    Screen([Text(0, 0, "x")]),                              # no room for the attribute cell
    Screen([Text(30, 5, "x")]),                             # off the screen
    Screen([Text(0, 70, "x" * 20)]),                        # off the right edge
    Screen([Input(23, 75, 10, "a")]),                       # runs off the bottom of the screen
    Screen([Input(5, 5, 0, "a")]),                          # empty field
    Screen([Text(0, 0, "x")]),                              # no cell before the very first one
    Screen([Input(0, 5, 3, "a"), Input(1, 5, 3, "a")]),     # duplicate names
    Screen([Input(0, 5, 3, "a")], cursor="nope"),           # cursor names nothing
])
def test_validate_rejects(bad):
    with pytest.raises(ValueError):
        render(bad)


def test_signon_screen_is_valid_and_has_the_expected_inputs():
    s = signon_screen("QPADEV0001")
    s.validate()
    assert [i.name for i in s.inputs()] == ["user", "password", "program", "menu", "library"]
    assert next(i for i in s.inputs() if i.name == "password").hidden


def test_monocase_sets_the_second_ffw_byte():
    out = render(Screen([Input(2, 5, 4, "a", monocase=True), Input(3, 5, 4, "b")]))
    assert bytes([0x1D, 0x40, 0x20, 0x24, 0, 4]) in out   # monocase
    assert bytes([0x1D, 0x40, 0x00, 0x24, 0, 4]) in out   # plain


def test_text_at_column_zero_puts_its_attribute_in_the_last_cell_of_the_row_above():
    out = render(Screen([Text(23, 0, "msg", ds.ATTR_WHITE)]))
    assert bytes([ds.ORDER_SBA, 23, 80, ds.ATTR_WHITE]) + ebcdic.encode("msg") in out


def test_field_longer_than_a_row_wraps():
    from silverlake.oracle.terminal import Terminal
    out = render(Screen([Input(5, 24, 128, "pw", hidden=True)]))
    t = Terminal()
    t.apply(out)
    [f] = t.snapshot()["fields"]
    assert (f["row"], f["col"], f["length"], f["hidden"]) == (5, 24, 128, True)


def test_signon_user_is_monocase_and_password_is_not():
    s = signon_screen("QPADEV0001")
    flags = {i.name: (i.monocase, i.hidden) for i in s.inputs()}
    assert flags["user"] == (True, False)
    assert flags["password"] == (False, True)


def test_signon_message_takes_the_bottom_row_in_white():
    s = signon_screen("QPADEV0001", message="CPF0000 - test")
    [msg] = [f for f in s.fields if isinstance(f, Text) and f.row == 23]
    assert (msg.col, msg.attr, msg.text) == (0, ds.ATTR_WHITE, "CPF0000 - test")
    quiet = signon_screen("QPADEV0001")
    assert any(isinstance(f, Text) and f.row == 23 and "Not IBM" in f.text for f in quiet.fields)
