"""The services beyond 5250, off unless asked for (`./start.sh --services` or SILVERLAKE_SERVICES=1).

They live in the same process and event loop as the 5250 listener, so they answer from the same profiles
and authority and see a lesson toggle the moment it is saved. Every one binds to the loopback address the
5250 listener was already checked against, and nothing here ever runs a shell."""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Callable

from ..config import check_loopback
from ..system.profiles import ProfileStore
from . import ftpd, httpd

log = logging.getLogger("silverlake.services")

DEFAULT_PORTS = {"httpadmin": 2001, "ftp": 2121}
ENV_PORTS = {"httpadmin": "SILVERLAKE_HTTPADMIN_PORT", "ftp": "SILVERLAKE_FTP_PORT"}


def wanted(env: dict[str, str] | None = None) -> bool:
    return (env if env is not None else os.environ).get("SILVERLAKE_SERVICES", "") not in ("", "0", "off", "no")


def ports(env: dict[str, str] | None = None) -> dict[str, int]:
    env = env if env is not None else os.environ
    out = {}
    for name, default in DEFAULT_PORTS.items():
        port = int(env.get(ENV_PORTS[name], default))
        if not 1 <= port <= 65535:
            raise ValueError(f"bad port for {name}: {port}")
        out[name] = port
    return out


async def start(host: str, store_of: Callable[[], ProfileStore], env: dict[str, str] | None = None) -> list[asyncio.Server]:
    """Start every service on `host`, which must be loopback. Returns the servers so the caller can keep them
    open; a service that cannot bind stops the rest and raises, so a half started range is never left up."""
    check_loopback(host)
    chosen = ports(env)
    servers: list[asyncio.Server] = []
    try:
        servers.append(await httpd.serve(host, chosen["httpadmin"], store_of))
        log.info("HTTP Server Administration listening on %s:%d", host, chosen["httpadmin"])
        servers.append(await ftpd.serve(host, chosen["ftp"], store_of))
        log.info("FTP listening on %s:%d", host, chosen["ftp"])
    except OSError:
        for s in servers:
            s.close()
        raise
    return servers
