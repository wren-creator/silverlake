"""Runtime configuration. Loopback only, by design."""

import ipaddress
import os

LOOPBACK = "127.0.0.1"
DEFAULT_PORT = 5250


class ConfigError(ValueError):
    pass


def check_loopback(host: str) -> str:
    """Return host if it is a loopback address, else refuse.

    A deliberately vulnerable IBM i has no business being reachable from
    anywhere but the machine running it.
    """
    try:
        addr = ipaddress.ip_address(host)
    except ValueError as exc:
        raise ConfigError(f"not an IP address: {host!r}") from exc
    if not addr.is_loopback:
        raise ConfigError(f"refusing to bind {host}: loopback only")
    return host


def listen_address() -> tuple[str, int]:
    host = check_loopback(os.environ.get("SILVERLAKE_HOST", LOOPBACK))
    port = int(os.environ.get("SILVERLAKE_PORT", DEFAULT_PORT))
    if not 1 <= port <= 65535:
        raise ConfigError(f"bad port: {port}")
    return host, port
