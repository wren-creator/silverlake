"""EBCDIC conversion. Code page 037 (US/Canada), which is what the standard
terminal types negotiate. Other code pages can slot in here later."""

CODEPAGE = "cp037"

BLANK = 0x40  # EBCDIC space


def encode(text: str) -> bytes:
    return text.encode(CODEPAGE, errors="replace")


def decode(data: bytes) -> str:
    return data.decode(CODEPAGE, errors="replace")
