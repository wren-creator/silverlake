"""Helpers for the tests that open real sockets: free ports for every service, so nothing collides with a
range that is already running, and a throwaway certificate in a temp folder."""

import shutil
import socket

import pytest

from silverlake.net import certs, services


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def all_ports(**fixed) -> dict[str, str]:
    """An env mapping that puts every service on a free port, with any named ones set as given."""
    env = {var: str(free_port()) for var in services.ENV_PORTS.values()}
    env.update({services.ENV_PORTS[name]: str(port) for name, port in fixed.items()})
    return env


needs_openssl = pytest.mark.skipif(shutil.which("openssl") is None, reason="openssl is not installed")


@pytest.fixture
def tls_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("SILVERLAKE_TLS_DIR", str(tmp_path / "tls"))
    assert certs.make(), "openssl could not make a certificate"
    return tmp_path / "tls"
