from silverlake.proto import telnet as tn


def feed_all(parser, data, step=None):
    out = []
    if step is None:
        return parser.feed(data)
    for i in range(0, len(data), step):
        out += parser.feed(data[i:i + step])
    return out


def test_command_subneg_record():
    data = (
        tn.command(tn.WILL, tn.OPT_TTYPE)
        + tn.subneg(bytes([tn.OPT_TTYPE, tn.TTYPE_IS]) + b"IBM-3179-2")
        + tn.record(b"\x12\xa0hello")
    )
    events = tn.Parser().feed(data)
    assert events == [
        tn.Command(tn.WILL, tn.OPT_TTYPE),
        tn.Subneg(bytes([tn.OPT_TTYPE, tn.TTYPE_IS]) + b"IBM-3179-2"),
        tn.Record(b"\x12\xa0hello"),
    ]


def test_split_at_every_size_gives_same_events():
    data = (
        tn.command(tn.DO, tn.OPT_EOR)
        + tn.subneg(bytes([tn.OPT_NEWENV, tn.ENV_IS, tn.ENV_USERVAR]) + b"DEVNAME" + bytes([tn.ENV_VALUE]) + b"DEV1")
        + tn.record(bytes(range(256)))
    )
    whole = tn.Parser().feed(data)
    assert len(whole) == 3
    for step in (1, 2, 3, 7):
        assert feed_all(tn.Parser(), data, step) == whole


def test_iac_in_record_is_escaped_and_collapsed():
    rec = b"\x01\xff\x02\xff\xff\x03"
    wire = tn.record(rec)
    assert wire == b"\x01\xff\xff\x02\xff\xff\xff\xff\x03\xff\xef"
    assert tn.Parser().feed(wire) == [tn.Record(rec)]


def test_iac_in_subneg_is_collapsed():
    wire = tn.subneg(b"\x27\x00\xff\x01")
    assert tn.Parser().feed(wire) == [tn.Subneg(b"\x27\x00\xff\x01")]


def test_empty_record_is_dropped():
    assert tn.Parser().feed(bytes([tn.IAC, tn.EOR])) == []


def test_nop_is_ignored():
    assert tn.Parser().feed(bytes([tn.IAC, tn.NOP])) == []


def test_parse_environ_uservars_and_var():
    payload = (
        bytes([tn.ENV_USERVAR]) + b"DEVNAME" + bytes([tn.ENV_VALUE]) + b"QPADEV0001"
        + bytes([tn.ENV_USERVAR]) + b"CODEPAGE" + bytes([tn.ENV_VALUE]) + b"037"
        + bytes([tn.ENV_VAR]) + b"USER" + bytes([tn.ENV_VALUE]) + b"TESTER"
    )
    assert tn.parse_environ(payload) == {"DEVNAME": "QPADEV0001", "CODEPAGE": "037", "USER": "TESTER"}


def test_parse_environ_escape_and_empty_value():
    payload = (
        bytes([tn.ENV_USERVAR]) + b"A" + bytes([tn.ENV_VALUE, tn.ENV_ESC, tn.ENV_VALUE]) + b"x"
        + bytes([tn.ENV_USERVAR]) + b"EMPTY"
    )
    assert tn.parse_environ(payload) == {"A": "\x01x", "EMPTY": ""}
