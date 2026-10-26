"""Entry point: listen for 5250 clients on loopback."""

import asyncio
import logging
import sys

from . import __version__
from .config import ConfigError, listen_address
from .net.server import serve


async def run(host: str, port: int) -> None:
    server = await serve(host, port)
    logging.getLogger("silverlake").info("silverlake %s listening on %s:%d", __version__, host, port)
    async with server:
        await server.serve_forever()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    try:
        host, port = listen_address()
    except ConfigError as exc:
        print(f"silverlake: {exc}", file=sys.stderr)
        return 1
    try:
        asyncio.run(run(host, port))
    except KeyboardInterrupt:
        pass
    except OSError as exc:
        print(f"silverlake: cannot listen on {host}:{port}: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
