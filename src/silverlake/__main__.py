"""Entry point: listen for 5250 clients on loopback."""

import asyncio
import logging
import os
import sys

from . import __version__
from .config import ConfigError, listen_address
from .net import services
from .net.server import serve
from .screens.signon import SignonController
from .system import profiles, state


async def run(host: str, port: int) -> None:
    store, db = state.open_store(os.environ.get("SILVERLAKE_PROFILES"),
                                 os.environ.get("SILVERLAKE_STATE_DIR", "state"))
    server = await serve(host, port, lambda display: SignonController(display, store))
    # Before the line start.sh waits for, so a service that cannot bind fails the start instead of following it.
    extra = await services.start(host, lambda: store) if services.wanted() else []
    logging.getLogger("silverlake").info("silverlake %s listening on %s:%d", __version__, host, port)
    try:
        async with server:
            await server.serve_forever()
    finally:
        for s in extra:
            s.close()
        db.close()


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
    except profiles.SeedError as exc:
        print(f"silverlake: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"silverlake: cannot listen on {host}:{port}: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
