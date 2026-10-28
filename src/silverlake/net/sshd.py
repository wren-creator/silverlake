"""An ssh listener for the PASE shell, off unless the services are on and asyncssh is installed.

It answers on loopback only (2222 here, 22 on a real system). A login is checked against the profiles, either
with the password (the same sign-on rules as the 5250 side and FTP, so a wrong password counts toward the
lockout) or with a public key listed in the profile's `~/.ssh/authorized_keys` in the virtual IFS. What runs
after that is never a host shell: `ssh host cmd` runs one line and an interactive login reads lines, both through
the simulated PASE shell (system/pase.py) as that profile, and a login reads the profiles first.

The settings are the lines of `/QOpenSys/etc/ssh/sshd_config` and every file in `sshd_config.d/` beside it,
re-read at each login so a lesson toggle or a change made from the shell counts at once. The first value of a
keyword wins, as in OpenSSH. Read: PasswordAuthentication, PubkeyAuthentication, StrictModes, DenyUsers and
AllowUsers. Everything else is ignored.

StrictModes is the lesson. With it on, a key file (or the `.ssh` directory, or the home directory) that anyone but
the owner may write is not trusted and the key is refused, as OpenSSH does. With it off, whoever can write
`authorized_keys` can add a key and log in as its owner.

Not from a real system: the path of the config files, the reply wording, and the version banner, which says
AsyncSSH, not OpenSSH. A host key is made on first use in the certificate directory (`.tls/`, gitignored)."""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from ..system import ifs, pase
from ..system.profiles import ProfileStore
from . import certs

log = logging.getLogger("silverlake.sshd")

try:
    import asyncssh
except ImportError:                                           # optional, like the RPG runtime
    asyncssh = None

CONFIG = "/QOpenSys/etc/ssh/sshd_config"
CONFIG_DIR = "/QOpenSys/etc/ssh/sshd_config.d"
DEFAULTS = {"passwordauthentication": "yes", "pubkeyauthentication": "yes", "strictmodes": "yes"}
MAX_LINE = 4000


def available() -> bool:
    return asyncssh is not None


def settings(store: ProfileStore) -> dict[str, str]:
    """The effective settings: the main file, then the files of sshd_config.d in name order, first value wins."""
    out: dict[str, str] = {}
    paths = [CONFIG] + sorted(p for p in store.ifs if p.startswith(CONFIG_DIR + "/") and p.endswith(".conf"))
    for path in paths:
        node = store.ifs.get(path)
        for raw in (node.content.splitlines() if node and not node.is_dir else []):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            key, _, value = line.partition(" ")
            out.setdefault(key.lower(), value.strip())
    return {**DEFAULTS, **out}


def _listed(cfg: dict[str, str], key: str) -> set[str]:
    return {u.upper() for u in cfg.get(key, "").split()}


def user_allowed(store: ProfileStore, username: str) -> bool:
    cfg = settings(store)
    name = username.upper()
    if name in _listed(cfg, "denyusers"):
        return False
    allow = _listed(cfg, "allowusers")
    return not allow or name in allow


def _too_open(node) -> bool:
    """StrictModes' test: anyone but the owner may write it."""
    return "w" in node.public.replace("-", "")


def key_files_trusted(store: ProfileStore, username: str) -> bool:
    """With StrictModes on, the home directory, ~/.ssh and authorized_keys must not be writable by others."""
    if settings(store)["strictmodes"].lower() != "yes":
        return True
    home = f"/home/{username.upper()}"
    return not any((n := store.ifs.get(p)) is None or _too_open(n)
                   for p in (home, home + "/.ssh", home + "/.ssh/authorized_keys"))


def authorized_keys(store: ProfileStore, username: str) -> list[bytes]:
    """The public key blobs listed for the profile. The daemon reads the file whoever may read it."""
    node = store.ifs.get(f"/home/{username.upper()}/.ssh/authorized_keys")
    if node is None or node.is_dir:
        return []
    blobs = []
    for raw in node.content.splitlines():
        parts = raw.split()
        for i, part in enumerate(parts[:-1]):
            if part.startswith(("ssh-", "ecdsa-", "sk-")):
                try:
                    blobs.append(asyncssh.import_public_key(" ".join(parts[i:i + 2])).public_data)
                except (asyncssh.KeyImportError, ValueError):
                    pass
                break
    return blobs


def _server_class(store_of: Callable[[], ProfileStore]):
    class Server(asyncssh.SSHServer):
        def connection_made(self, conn) -> None:
            self.conn = conn

        def begin_auth(self, username: str) -> bool:
            return True

        def password_auth_supported(self) -> bool:
            return settings(store_of())["passwordauthentication"].lower() == "yes"

        def public_key_auth_supported(self) -> bool:
            return settings(store_of())["pubkeyauthentication"].lower() == "yes"

        def validate_password(self, username: str, password: str) -> bool:
            store = store_of()
            if not user_allowed(store, username):
                return False
            result = store.check_signon(username, password)
            ok = result.profile is not None
            log.info("ssh password login for %s: %s", username, "accepted" if ok else "refused")
            return ok

        def validate_public_key(self, username: str, key) -> bool:
            store = store_of()
            profile = store.get(username)
            if profile is None or profile.status != "*ENABLED" or not user_allowed(store, username):
                return False
            if not key_files_trusted(store, username):
                log.info("ssh key login for %s refused: StrictModes and a writable key file", username)
                return False
            ok = key.public_data in authorized_keys(store, username)
            log.info("ssh key login for %s: %s", username, "accepted" if ok else "refused")
            return ok

    return Server


def _process_handler(store_of: Callable[[], ProfileStore]):
    async def handle(process) -> None:
        store = store_of()
        profile = store.get(process.get_extra_info("username"))
        if profile is None:
            process.exit(1)
            return
        shell = pase.Shell(store, profile)
        if process.command is not None:
            shell.login()                                   # a login shell would, so its lines run too
            for line in shell.run(process.command)[:MAX_LINE]:
                process.stdout.write(line + "\n")
            process.exit(0)
            return
        for line in shell.login():
            process.stdout.write(line + "\n")
        while not shell.done:
            process.stdout.write(shell.prompt)
            try:
                line = await process.stdin.readline()
            except asyncssh.BreakReceived:
                continue
            except asyncssh.TerminalSizeChanged:
                continue
            if not line:
                break
            for out in shell.run(line.rstrip("\r\n")[:MAX_LINE]):
                process.stdout.write(out + "\n")
        process.exit(0)
    return handle


def host_key_path() -> Path:
    return certs.cert_dir() / "ssh_host_ed25519_key"


def ensure_host_key() -> Path:
    path = host_key_path()
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        asyncssh.generate_private_key("ssh-ed25519").write_private_key(str(path))
        path.chmod(0o600)
    return path


async def serve(host: str, port: int, store_of: Callable[[], ProfileStore]):
    """Start the listener. Returns an object with close(), like the other servers."""
    if asyncssh is None:
        raise RuntimeError("asyncssh is not installed")
    return await asyncssh.create_server(_server_class(store_of), host, port, server_host_keys=[str(ensure_host_key())],
                                        process_factory=_process_handler(store_of), encoding="utf-8",
                                        line_editor=True, login_timeout=30)
