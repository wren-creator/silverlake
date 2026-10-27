"""The services beyond 5250, off unless asked for (`./start.sh --services` or SILVERLAKE_SERVICES=1).

They live in the same process and event loop as the 5250 listener, so they answer from the same profiles
and authority and see a lesson toggle the moment it is saved. Every one binds to the loopback address the
5250 listener was already checked against, and nothing here ever runs a shell.

TLS ports start when `.tls/cert.pem` exists (`./setup.sh` makes it, see certs.py) and are skipped, with a
log line, when it does not. The plain and TLS ports of a service share one state."""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Callable

from ..config import check_loopback
from ..system.profiles import ProfileStore
from . import certs, ftpd, hostsvr, httpd, httpadmin
from . import server as telnet

log = logging.getLogger("silverlake.services")

DEFAULT_PORTS = {"httpadmin": 2001, "ftp": 2121, "mapper": 4449, "signon": 8476,
                 "tls5250": 5992, "httpadmin_tls": 2010, "ftp_tls": 2990, "signon_tls": 9476}
ENV_PORTS = {"httpadmin": "SILVERLAKE_HTTPADMIN_PORT", "ftp": "SILVERLAKE_FTP_PORT",
             "mapper": "SILVERLAKE_MAPPER_PORT", "signon": "SILVERLAKE_SIGNON_PORT",
             "tls5250": "SILVERLAKE_TLS_PORT", "httpadmin_tls": "SILVERLAKE_HTTPADMIN_TLS_PORT",
             "ftp_tls": "SILVERLAKE_FTP_TLS_PORT", "signon_tls": "SILVERLAKE_SIGNON_TLS_PORT"}


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
    if len(set(out.values())) != len(out):
        raise ValueError("two services were given the same port")
    return out


async def start(host: str, store_of: Callable[[], ProfileStore], env: dict[str, str] | None = None,
                make_controller: Callable | None = None) -> list[asyncio.Server]:
    """Start every service on `host`, which must be loopback. Returns the servers so the caller can keep them
    open; a service that cannot bind stops the rest and raises, so a half started range is never left up."""
    check_loopback(host)
    chosen = ports(env)
    tls = certs.server_context()
    if tls is None:
        log.info("no TLS certificate in %s: the TLS ports are not started (run ./setup.sh)", certs.cert_dir())
    servers: list[asyncio.Server] = []
    web_state = httpadmin.State()
    try:
        servers.append(await httpd.serve(host, chosen["httpadmin"], store_of, state=web_state))
        log.info("HTTP Server Administration listening on %s:%d", host, chosen["httpadmin"])
        servers.append(await ftpd.serve(host, chosen["ftp"], store_of, ssl_context=tls))
        log.info("FTP listening on %s:%d", host, chosen["ftp"])
        servers += await hostsvr.serve(host, chosen["mapper"], chosen["signon"], store_of,
                                       tls_port=chosen["signon_tls"], ssl_context=tls)
        log.info("host server mapper on %s:%d, sign-on server on %s:%d", host, chosen["mapper"], host, chosen["signon"])
        if tls is not None:
            servers.append(await httpd.serve(host, chosen["httpadmin_tls"], store_of, ssl_context=tls, state=web_state))
            servers.append(await ftpd.serve(host, chosen["ftp_tls"], store_of, ssl_context=tls, implicit=True))
            if make_controller is not None:
                servers.append(await telnet.serve(host, chosen["tls5250"], make_controller, ssl_context=tls))
            log.info("TLS: 5250 on %d, console on %d, FTP on %d, sign-on on %d", chosen["tls5250"],
                     chosen["httpadmin_tls"], chosen["ftp_tls"], chosen["signon_tls"])
    except OSError:
        for s in servers:
            s.close()
        raise
    return servers
