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


# -- the LAN opt in ---------------------------------------------------------------------------------------------

from silverlake.config import check_bind, lan_allowed

LAN = {"SILVERLAKE_ALLOW_LAN": "1"}


def test_lan_refused_without_the_opt_in():
    with pytest.raises(ConfigError, match="ALLOW_LAN"):
        check_bind("192.168.1.68", {})


@pytest.mark.parametrize("host", ["192.168.68.125", "10.1.2.3", "172.16.0.9", "172.31.255.1", "169.254.1.1"])
def test_private_ipv4_accepted_with_the_opt_in(host):
    assert check_bind(host, LAN) == host


@pytest.mark.parametrize("host", ["0.0.0.0", "::", "8.8.8.8", "172.32.0.1", "224.0.0.1", "fd00::1", "localhost", "192.168.1"])
def test_never_a_wildcard_public_or_name(host):
    with pytest.raises(ConfigError):
        check_bind(host, LAN)


def test_loopback_needs_no_opt_in():
    assert check_bind("127.0.0.1", {}) == "127.0.0.1"


@pytest.mark.parametrize("value,expected", [("1", True), ("yes", True), ("", False), ("0", False), ("off", False)])
def test_lan_flag_values(value, expected):
    assert lan_allowed({"SILVERLAKE_ALLOW_LAN": value}) is expected


def test_env_lan_address_needs_both_variables(monkeypatch):
    monkeypatch.setenv("SILVERLAKE_HOST", "192.168.68.125")
    monkeypatch.delenv("SILVERLAKE_ALLOW_LAN", raising=False)
    with pytest.raises(ConfigError):
        listen_address()
    monkeypatch.setenv("SILVERLAKE_ALLOW_LAN", "1")
    assert listen_address()[0] == "192.168.68.125"


def test_cert_names_include_lan_ips():
    from silverlake.net.certs import san
    assert san({}) == "DNS:localhost,IP:127.0.0.1"
    assert san({"SILVERLAKE_CERT_IPS": "192.168.68.125, 10.0.0.2"}) == "DNS:localhost,IP:127.0.0.1,IP:192.168.68.125,IP:10.0.0.2"
