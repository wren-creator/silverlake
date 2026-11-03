"""Runtime configuration. Loopback only by default; a private LAN address needs an explicit opt in."""

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


def lan_allowed(env: dict[str, str] | None = None) -> bool:
    return (env if env is not None else os.environ).get("SILVERLAKE_ALLOW_LAN", "").strip().lower() not in ("", "0", "off", "no")


def check_bind(host: str, env: dict[str, str] | None = None) -> str:
    """Return host if Silverlake may bind it. Loopback always. A private IPv4 address (10/8, 172.16/12, 192.168/16, or
    link-local) only when SILVERLAKE_ALLOW_LAN is set, for a lab server a student reaches over the LAN. Never a wildcard
    (0.0.0.0, ::), a public address or a hostname: the range is vulnerable on purpose and must not be one typo from the
    internet."""
    try:
        addr = ipaddress.ip_address(host)
    except ValueError as exc:
        raise ConfigError(f"not an IP address: {host!r}") from exc
    if addr.is_loopback:
        return host
    if not lan_allowed(env):
        raise ConfigError(f"refusing to bind {host}: loopback only (set SILVERLAKE_ALLOW_LAN=1 to serve a private LAN address)")
    if addr.version != 4 or addr.is_unspecified or addr.is_multicast or not (addr.is_private or addr.is_link_local):
        raise ConfigError(f"refusing to bind {host}: with SILVERLAKE_ALLOW_LAN only a single private IPv4 address "
                          "(10.x, 172.16-31.x, 192.168.x) is allowed, never 0.0.0.0 or a public address")
    return host


def listen_address() -> tuple[str, int]:
    host = check_bind(os.environ.get("SILVERLAKE_HOST", LOOPBACK))
    port = int(os.environ.get("SILVERLAKE_PORT", DEFAULT_PORT))
    if not 1 <= port <= 65535:
        raise ConfigError(f"bad port: {port}")
    return host, port
