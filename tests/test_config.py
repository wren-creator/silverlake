import pytest

from silverlake.config import ConfigError, check_loopback, listen_address


def test_loopback_accepted():
    assert check_loopback("127.0.0.1") == "127.0.0.1"
    assert check_loopback("::1") == "::1"


@pytest.mark.parametrize("host", ["0.0.0.0", "192.168.1.5", "10.0.0.1", "::"])
def test_non_loopback_refused(host):
    with pytest.raises(ConfigError):
        check_loopback(host)


def test_hostname_refused():
    with pytest.raises(ConfigError):
        check_loopback("localhost")


def test_default_address(monkeypatch):
    monkeypatch.delenv("SILVERLAKE_HOST", raising=False)
    monkeypatch.delenv("SILVERLAKE_PORT", raising=False)
    assert listen_address() == ("127.0.0.1", 5250)


def test_env_cannot_open_the_door(monkeypatch):
    monkeypatch.setenv("SILVERLAKE_HOST", "0.0.0.0")
    with pytest.raises(ConfigError):
        listen_address()


def test_bad_port(monkeypatch):
    monkeypatch.setenv("SILVERLAKE_PORT", "70000")
    with pytest.raises(ConfigError):
        listen_address()
