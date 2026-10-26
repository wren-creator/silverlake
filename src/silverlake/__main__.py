"""Entry point. Phase 0: validate config and stop; the 5250 listener lands in Phase 1."""

import sys

from . import __version__
from .config import ConfigError, listen_address


def main() -> int:
    try:
        host, port = listen_address()
    except ConfigError as exc:
        print(f"silverlake: {exc}", file=sys.stderr)
        return 1
    print(f"silverlake {__version__}: would listen on {host}:{port} (5250 core not built yet)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
