"""Reads the oracle's credentials from a local .env, so a password never has to
be typed into a command line, a shell history, or a chat.

Only SILVERLAKE_ORACLE_* names are read, a variable already in the environment
wins, and a file that other users can read is refused, the way ssh refuses a
loose private key. The value is never printed."""

import os
import stat
from pathlib import Path

PREFIX = "SILVERLAKE_ORACLE_"


class EnvFileError(RuntimeError):
    pass


def load(path: Path | str = ".env") -> list[str]:
    """Set variables from the file. Returns the names it set (never the values)."""
    path = Path(path)
    if not path.exists():
        return []
    if path.stat().st_mode & (stat.S_IRWXG | stat.S_IRWXO):
        raise EnvFileError(f"{path} can be read by other users. Run: chmod 600 {path}")
    names = []
    for n, raw in enumerate(path.read_text().splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.partition("=")
        key = key.strip().removeprefix("export ").strip()
        if not sep or not key.startswith(PREFIX):
            continue        # not ours: ignored, and never echoed
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if value and key not in os.environ:
            os.environ[key] = value
            names.append(key)
    return names
