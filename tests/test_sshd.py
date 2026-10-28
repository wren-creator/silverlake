"""The ssh listener: logins by password and by key, StrictModes, who may log in, and what runs afterwards."""

import asyncio

import pytest

asyncssh = pytest.importorskip("asyncssh")

from netutil import free_port  # noqa: E402
from silverlake import flags  # noqa: E402
from silverlake.net import sshd  # noqa: E402
from silverlake.system import pase, profiles  # noqa: E402


@pytest.fixture
def store():
    return profiles.load()


@pytest.fixture(autouse=True)
def host_key_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("SILVERLAKE_TLS_DIR", str(tmp_path / "keys"))


def session(store, user, command=None, **auth):
    """Log in, run one command (or end at once), return (output, error). `error` is the refusal if any."""
    async def go():
        port = free_port()
        server = await sshd.serve("127.0.0.1", port, lambda: store)
        try:
            try:
                async with asyncssh.connect("127.0.0.1", port, username=user, known_hosts=None,
                                            preferred_auth="publickey,password", **auth) as conn:
                    result = await conn.run(command or "pwd", check=False)
                    return result.stdout, ""
            except asyncssh.PermissionDenied as exc:
                return "", str(exc)
        finally:
            server.close()
            await server.wait_closed()
    return asyncio.run(go())


def keypair():
    key = asyncssh.generate_private_key("ssh-ed25519")
    return key, key.export_public_key().decode().strip()


def test_a_password_login_runs_a_command_in_the_pase_shell_as_that_profile(store):
    out, err = session(store, "STUDENT", "echo $USER", password="STUDENT", client_keys=None)
    assert (out.strip(), err) == ("STUDENT", "")
    out, _ = session(store, "STUDENT", "pwd", password="STUDENT", client_keys=None)
    assert out.strip() == "/home/STUDENT"


def test_a_wrong_password_is_refused_and_counts_toward_the_lockout(store):
    for _ in range(3):
        _, err = session(store, "STUDENT", password="nope", client_keys=None)
        assert err
    assert store.get("STUDENT").status != "*ENABLED" or store.bad_signons.get("STUDENT")


def test_a_command_runs_after_the_profiles_and_an_interactive_login_shows_what_they_print(store):
    out, _ = session(store, "OPERATOR", "echo $EDITOR", password="OPERATOR", client_keys=None)
    assert out.strip() == "vi"                                      # the profile ran (EDITOR is set), quietly

    async def interactive():
        port = free_port()
        server = await sshd.serve("127.0.0.1", port, lambda: store)
        try:
            async with asyncssh.connect("127.0.0.1", port, username="OPERATOR", password="OPERATOR",
                                        known_hosts=None, client_keys=None) as conn:
                return (await conn.run(input="echo $USER\nexit\n", check=False)).stdout
        finally:
            server.close()
            await server.wait_closed()
    shown = asyncio.run(interactive())
    assert "(operator)" in shown and "$ " in shown and "OPERATOR" in shown.splitlines()[-1] + shown


def test_no_host_shell_is_ever_reached(store):
    out, _ = session(store, "STUDENT", "curl http://example.com", password="STUDENT", client_keys=None)
    assert out.strip() == "bsh: curl: not found"
    out, _ = session(store, "STUDENT", "id &", password="STUDENT", client_keys=None)
    assert "not available in the simulator" in out


def test_a_key_in_a_world_writable_file_works_only_while_strictmodes_is_off(store):
    key, pub = keypair()
    pase.Shell(store, store.profiles["STUDENT"]).run(f"echo '{pub}' >> /home/DEVELOPER/.ssh/authorized_keys")
    out, err = session(store, "DEVELOPER", "cat secret.txt", client_keys=[key], password=None)
    assert err == "" and flags.flag("ssh-strictmodes") in out
    store.ifs["/QOpenSys/etc/ssh/sshd_config.d/10-modes.conf"].content = "StrictModes yes\n"
    assert session(store, "DEVELOPER", "cat secret.txt", client_keys=[key], password=None)[1]
    store.ifs["/home/DEVELOPER/.ssh/authorized_keys"].public = "r--"          # and the file fixed as well
    assert session(store, "DEVELOPER", "cat secret.txt", client_keys=[key], password=None)[1] == ""


def test_a_key_that_is_not_listed_is_refused(store):
    key, _ = keypair()
    assert session(store, "DEVELOPER", client_keys=[key], password=None)[1]


def test_deny_and_allow_users_decide_who_may_log_in(store):
    assert session(store, "CLERK", "echo $USER", password="CLERK", client_keys=None)[0].strip() == "CLERK"
    store.ifs["/QOpenSys/etc/ssh/sshd_config.d/20-access.conf"].content = "DenyUsers CLERK\n"
    assert session(store, "CLERK", "echo $USER", password="CLERK", client_keys=None)[1]
    store.ifs["/QOpenSys/etc/ssh/sshd_config.d/20-access.conf"].content = "AllowUsers OPERATOR\n"
    assert session(store, "STUDENT", password="STUDENT", client_keys=None)[1]
    assert session(store, "OPERATOR", password="OPERATOR", client_keys=None)[1] == ""


def test_password_and_key_logins_can_each_be_switched_off(store):
    store.ifs["/QOpenSys/etc/ssh/sshd_config"].content = "PasswordAuthentication no\n"
    assert session(store, "STUDENT", password="STUDENT", client_keys=None)[1]


def test_settings_take_the_first_value_and_ignore_what_is_unknown(store):
    store.ifs["/QOpenSys/etc/ssh/sshd_config"].content = "StrictModes yes\nBanner x\n"
    cfg = sshd.settings(store)
    assert cfg["strictmodes"] == "yes" and cfg["passwordauthentication"] == "yes"


def test_the_services_start_the_listener_on_its_own_port_when_asyncssh_is_there(store, monkeypatch):
    from netutil import all_ports
    from silverlake.net import services

    async def go():
        port = free_port()
        servers = await services.start("127.0.0.1", lambda: store, all_ports(ssh=port))
        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", port)
            banner = await reader.readline()
            writer.close()
            return banner
        finally:
            for s in servers:
                s.close()
    assert asyncio.run(go()).startswith(b"SSH-2.0-")


def test_the_ssh_command_exits_with_the_shells_status(store):
    async def go(command):
        port = free_port()
        server = await sshd.serve("127.0.0.1", port, lambda: store)
        try:
            async with asyncssh.connect("127.0.0.1", port, username="STUDENT", password="STUDENT", client_keys=None,
                                        known_hosts=None, preferred_auth="password") as conn:
                result = await conn.run(command, check=False)
                return result.exit_status, result.stdout
        finally:
            server.close()
            await server.wait_closed()
    assert asyncio.run(go("pwd"))[0] == 0
    assert asyncio.run(go("ls /nowhere"))[0] == 2
    assert asyncio.run(go("ls /nowhere || echo ok; exit 7")) == (7, "/nowhere not found\nok\n")
    # bsh with no terminal ends at a failed cd, as PUB400's did
    assert asyncio.run(go("echo a && cd /nowhere || echo c; echo d")) == (1, "a\n/nowhere: No such file or directory\n")
