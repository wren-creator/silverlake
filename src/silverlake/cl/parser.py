"""Splits a CL command line into a command name, positional values and keyword
values: `CRTUSRPRF USRPRF(BOB) PASSWORD('Mixed Case') SPCAUT(*JOBCTL *SAVSYS)`.

Unquoted values are upper-cased, the way a real command line does it. Quoted
values keep their case. Nested parentheses are not supported yet (qualified
names like LIB/OBJ are plain tokens)."""

from dataclasses import dataclass, field


class ParseError(ValueError):
    pass


@dataclass
class Parsed:
    command: str
    positional: list[str] = field(default_factory=list)
    keywords: dict[str, list[str]] = field(default_factory=dict)


def _word(text: str, i: int) -> tuple[str, int]:
    """Read one value starting at text[i]: a quoted string or a bare word."""
    if text[i] == "'":
        out, i = [], i + 1
        while i < len(text):
            if text[i] == "'":
                if text[i + 1:i + 2] == "'":   # '' is an apostrophe inside a string
                    out.append("'")
                    i += 2
                    continue
                return "".join(out), i + 1
            out.append(text[i])
            i += 1
        raise ParseError("Apostrophe not matched.")
    j = i
    while j < len(text) and not text[j].isspace() and text[j] not in "()'":
        j += 1
    return text[i:j].upper(), j


def parse(line: str) -> Parsed | None:
    text = line.strip()
    if not text:
        return None
    name, i = _word(text, 0)
    if not name:
        raise ParseError("Command not valid.")
    name = name.split("/")[-1]            # QSYS/CRTUSRPRF means CRTUSRPRF
    parsed = Parsed(name)
    n = len(text)
    while i < n:
        if text[i].isspace():
            i += 1
            continue
        if text[i] == ")":
            raise ParseError("Right parenthesis not expected.")
        if text[i] == "(":
            raise ParseError("Left parenthesis not expected.")
        word, j = _word(text, i)
        if j < n and text[j] == "(" and text[i] != "'":
            values, j = _values(text, j + 1)
            if word in parsed.keywords:
                raise ParseError(f"Keyword {word} specified more than once.")
            parsed.keywords[word] = values
            i = j
        else:
            if parsed.keywords:
                raise ParseError("Positional value not allowed after a keyword.")
            parsed.positional.append(word)
            i = j
    return parsed


def _values(text: str, i: int) -> tuple[list[str], int]:
    values: list[str] = []
    n = len(text)
    while i < n:
        if text[i].isspace():
            i += 1
        elif text[i] == ")":
            return values, i + 1
        elif text[i] == "(":
            raise ParseError("Nested parentheses are not supported.")
        else:
            word, i = _word(text, i)
            values.append(word)
    raise ParseError("Right parenthesis not found.")
