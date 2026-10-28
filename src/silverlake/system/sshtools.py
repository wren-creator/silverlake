"""PASE batch B7, keys and names: ssh-keygen ssh-keyscan ssh scp sftp openssl, and the refusals dig nslookup host ldapsearch.

Usage lines, error text and statuses come from the PUB400 run of 2026-10-28 (ssh-pase-b7, kept local); what the run did not
reach (a failed name lookup, the ssh-keygen usage, a key file that is not a key) is a guess and docs/pase.md says so.

Keys are real: asyncssh makes, reads and fingerprints them, so a key made here works with a real ssh client against the
loopback listener, and the fingerprint and randomart match a real `ssh-keygen -lv`. Without asyncssh these commands say so.
`ssh` goes to this simulator and nowhere else: a local name and port 22 or 2222 run a command in-process as the target
profile, checked against its authorized_keys, its StrictModes and the same user rules as the listener. Any other name
fails to resolve, and no socket is ever opened. `scp` and `sftp` reach the listener's missing subsystem, as a real client does.
`dig`, `nslookup` and `host` exist on PUB400 and an ordinary profile may not run them, so they say so here. `ldapsearch`
is a QSH program."""

from __future__ import annotations

import hashlib
import re

from . import ifs
from .textfilters import Err

try:
    import asyncssh
except ImportError:          # the optional ssh extra
    asyncssh = None

LOCAL_NAMES = {"localhost", "127.0.0.1", "::1"}
LISTEN_PORTS = {22, 2222}
DEFAULT_IDS = ("id_ed25519", "id_ecdsa", "id_rsa")
NEEDS_ASYNCSSH = "needs asyncssh, which is not installed here (./setup.sh --ssh adds it)."
VERSION_LINE = "OpenSSH_9.6p1, OpenSSL 3.0.10 1 Aug 2023"

SSH_USAGE = ("usage: ssh [-46AaCfGgKkMNnqsTtVvXxYy] [-B bind_interface] [-b bind_address]\n"
             "           [-c cipher_spec] [-D [bind_address:]port] [-E log_file]\n"
             "           [-e escape_char] [-F configfile] [-I pkcs11] [-i identity_file]\n"
             "           [-J destination] [-L address] [-l login_name] [-m mac_spec]\n"
             "           [-O ctl_cmd] [-o option] [-P tag] [-p port] [-R address]\n"
             "           [-S ctl_path] [-W host:port] [-w local_tun[:remote_tun]]\n"
             "           destination [command [argument ...]]\n"
             "       ssh [-Q query_option]")
SCP_USAGE = ("usage: scp [-346ABCOpqRrsTv] [-c cipher] [-D sftp_server_path] [-F ssh_config]\n"
             "           [-i identity_file] [-J destination] [-l limit] [-o ssh_option]\n"
             "           [-P port] [-S program] [-X sftp_option] source ... target")
SFTP_USAGE = ("usage: sftp [-46AaCfNpqrv] [-B buffer_size] [-b batchfile] [-c cipher]\n"
              "          [-D sftp_server_command] [-F ssh_config] [-i identity_file]\n"
              "          [-J destination] [-l limit] [-o ssh_option] [-P port]\n"
              "          [-R num_requests] [-S program] [-s subsystem | sftp_server]\n"
              "          [-X sftp_option] destination")
KEYSCAN_USAGE = ("usage: ssh-keyscan [-46cDHv] [-f file] [-O option] [-p port] [-T timeout]\n"
                 "                   [-t type] [host | addrlist namelist]")
OPENSSL_HELP = """help:

Standard commands
asn1parse         ca                ciphers           cmp
cms               crl               crl2pkcs7         dgst
dhparam           dsa               dsaparam          ec
ecparam           enc               engine            errstr
fipsinstall       gendsa            genpkey           genrsa
help              info              kdf               list
mac               nseq              ocsp              passwd
pkcs12            pkcs7             pkcs8             pkey
pkeyparam         pkeyutl           prime             rand
rehash            req               rsa               rsautl
s_client          s_server          s_time            sess_id
smime             speed             spkac             srp
storeutl          ts                verify            version
x509
"""
OPENSSL_BUILT = {"version", "help", "x509", "s_client"}
OPENSSL_KNOWN = {w for w in OPENSSL_HELP.split()[2:] if w.isidentifier()} - {"commands"}

SSH_VALUE_OPTS = set("BbcDEeFIiJLlmOoPpRSWw")
KEY_NAMES = {"ssh-ed25519": ("ED25519", 256), "ssh-rsa": ("RSA", 0), "ecdsa-sha2-nistp256": ("ECDSA", 256),
             "ecdsa-sha2-nistp384": ("ECDSA", 384), "ecdsa-sha2-nistp521": ("ECDSA", 521)}
KEYGEN_TYPES = {"ed25519": "ssh-ed25519", "rsa": "ssh-rsa", "ecdsa": "ecdsa-sha2-nistp256"}


def _bits(key) -> tuple[str, int]:
    """(type label, size) the way ssh-keygen prints them: the RSA size is read from the key's own modulus."""
    name = key.algorithm.decode()
    label, size = KEY_NAMES.get(name, (name.upper(), 0))
    if name == "ssh-rsa":
        blob, pos, parts = key.public_data, 0, []
        while pos + 4 <= len(blob):
            n = int.from_bytes(blob[pos:pos + 4], "big")
            parts.append(blob[pos + 4:pos + 4 + n])
            pos += 4 + n
        size = int.from_bytes(parts[2], "big").bit_length() if len(parts) >= 3 else 0
    return label, size


def randomart(key) -> list[str]:
    """OpenSSH's drunken bishop, checked line for line against a real `ssh-keygen -lv`."""
    width, height = 17, 9
    field = [[0] * width for _ in range(height)]
    x, y = width // 2, height // 2
    for byte in hashlib.sha256(key.public_data).digest():
        for _ in range(4):
            x = max(0, min(width - 1, x + (1 if byte & 1 else -1)))
            y = max(0, min(height - 1, y + (1 if byte & 2 else -1)))
            field[y][x] += 1
            byte >>= 2
    chars = " .o+=*BOX@%&#/^SE"
    start, end = (height // 2, width // 2), (y, x)

    def border(text: str) -> str:
        text = f"[{text}]"
        left = (width - len(text)) // 2
        return "+" + "-" * left + text + "-" * (width - len(text) - left) + "+"

    label, size = _bits(key)
    rows = []
    for r in range(height):
        cells = "".join("E" if (r, c) == end else "S" if (r, c) == start else chars[min(field[r][c], 14)] for c in range(width))
        rows.append("|" + cells + "|")
    return [border(f"{label} {size}")] + rows + [border("SHA256")]


def _octal(entry) -> int:
    def bits(m: str) -> int:
        return sum(1 << (2 - i) for i, c in enumerate(m[:3]) if c != "-")
    return (bits(entry.owner_mode) << 6) | (bits(entry.public) << 3) | bits(entry.public)


class SshTools:
    """Mixed into the Shell beside Filters, Heavy and Archives."""

    def _no_asyncssh(self, name: str) -> list[str]:
        self.status = 1
        return [Err(f"{name}: {NEEDS_ASYNCSSH}")]

    def _read_key(self, given: str):
        """(key, is_private) from a file, or None when the file is not a key. Raises IfsError when it cannot be read."""
        text = ifs.read(self.store, self.actor, self.path(given))
        try:
            return asyncssh.import_private_key(text), True
        except Exception:
            pass
        try:
            return asyncssh.import_public_key(text), False
        except Exception:
            return None

    def _comment(self, key) -> str:
        return (key.get_comment() or "no comment") if hasattr(key, "get_comment") else "no comment"

    def _fp_line(self, key) -> str:
        label, size = _bits(key)
        return f"{size} {key.get_fingerprint()} {self._comment(key)} ({label})"

    # -- ssh-keygen -------------------------------------------------------------------------------------------------

    def cmd_ssh_keygen(self, args: list[str]) -> list[str]:
        if asyncssh is None:
            return self._no_asyncssh("ssh-keygen")
        opts: dict[str, str] = {}
        flags: set[str] = set()
        i = 0
        while i < len(args):
            a = args[i]
            if a in ("-t", "-f", "-N", "-C", "-b") and i + 1 < len(args):
                opts[a[1]], i = args[i + 1], i + 1
            elif a in ("-l", "-y", "-q", "-v"):
                flags.add(a[1])
            else:
                self.status = 1
                return [Err(f"ssh-keygen: unknown option -- {a.lstrip('-')[:1]}"), Err("usage: ssh-keygen [-q] [-b bits] [-C comment] [-f output_keyfile] [-N new_passphrase]"),
                        Err("                  [-t dsa | ecdsa | ecdsa-sk | ed25519 | ed25519-sk | rsa]")]
            i += 1
        if "l" in flags or "y" in flags:
            return self._keygen_show(opts.get("f"), "l" in flags)
        return self._keygen_make(opts, "q" in flags)

    def _keygen_show(self, given: str | None, fingerprint: bool) -> list[str]:
        given = given or ifs.normalize(".ssh/id_rsa", self.env["HOME"], self.env["HOME"])
        try:
            found = self._read_key(given)
            if found is None:
                raise ValueError
        except ifs.IfsError as exc:
            self.status = 255
            if exc.kind == "EACCES":
                return [Err(f"{given}: Permission denied")] if not fingerprint else [Err(f"ssh-keygen: {given}: Permission denied")]
            return [Err(f"ssh-keygen: {given}: No such file or directory" if fingerprint else f"{given}: No such file or directory")]
        except ValueError:
            found = None
        if found is None:
            self.status = 255
            return [Err(f"{given} is not a public key file.")]                               # a guess: no bad key was tried
        key = found[0]
        self.status = 0
        if fingerprint:
            return [self._fp_line(key)]
        return [key.export_public_key().decode().strip()]

    def _keygen_make(self, opts: dict[str, str], quiet: bool) -> list[str]:
        kind = opts.get("t", "rsa")
        if kind not in KEYGEN_TYPES:
            self.status = 1
            return [Err(f"unknown key type {kind}")]
        bits = int(opts["b"]) if opts.get("b", "").isdigit() else 3072
        out: list[str] = [] if quiet else [f"Generating public/private {kind} key pair."]
        target = opts.get("f")
        if target is None:
            target = f"{self.env['HOME']}/.ssh/id_{kind}"
            out.append(f"Enter file in which to save the key ({target}): ")
            if ifs.normalize(self.env["HOME"] + "/.ssh") not in self.store.ifs:
                try:
                    ifs.make(self.store, self.actor, self.env["HOME"] + "/.ssh", "dir", umask=0o077)
                    out.append(f"Created directory '{self.env['HOME']}/.ssh'.")
                except ifs.IfsError:
                    pass
        passphrase = opts.get("N")
        if passphrase is None and not quiet:
            out += ["Enter passphrase (empty for no passphrase): ", "Enter same passphrase again: "]
        comment = opts.get("C", f"{self.actor.name.lower()}@SILVERLAKE.LOCALDOMAIN")
        path = self.path(target)
        if path in self.store.ifs:
            self.status = 1
            return out + [f"{target} already exists.", "Overwrite (y/n)? "]
        extra = {"key_size": max(1024, min(bits, 4096))} if kind == "rsa" else {}
        key = asyncssh.generate_private_key(KEYGEN_TYPES[kind], comment=comment, **extra)
        try:
            ifs.write(self.store, self.actor, path, key.export_private_key(passphrase=passphrase or None).decode(), umask=0o077)
            ifs.chmod(self.store, self.actor, path, "600")
            ifs.write(self.store, self.actor, path + ".pub", key.export_public_key().decode(), umask=self.umask)
            ifs.chmod(self.store, self.actor, path + ".pub", "644")
        except ifs.IfsError as exc:
            self.status = 1
            why = {"EACCES": "Permission denied", "ENOENT": "No such file or directory", "ENOTDIR": "Not a directory"}.get(exc.kind, exc.kind)
            return out + [Err(f'Saving key "{target}" failed: {why}')]
        self.status = 0
        if quiet:
            return out
        return out + [f"Your identification has been saved in {target}", f"Your public key has been saved in {target}.pub",
                      "The key fingerprint is:", f"{key.get_fingerprint()} {comment}", "The key's randomart image is:"] + randomart(key)

    # -- ssh-keyscan ------------------------------------------------------------------------------------------------

    def cmd_ssh_keyscan(self, args: list[str]) -> list[str]:
        hosts, i, port = [], 0, 22
        while i < len(args):
            a = args[i]
            if a in ("-p", "-t", "-T", "-f", "-O") and i + 1 < len(args):
                port = int(args[i + 1]) if a == "-p" and args[i + 1].isdigit() else port
                i += 1
            elif not a.startswith("-"):
                hosts.append(a)
            i += 1
        if not hosts:
            self.status = 1
            return [Err(l) for l in KEYSCAN_USAGE.split("\n")]
        if asyncssh is None:
            return self._no_asyncssh("ssh-keyscan")
        from ..net import sshd
        self.status = 0
        out: list[str] = []
        key = asyncssh.read_public_key(str(sshd.ensure_host_key())) if hosts else None
        for host in hosts:
            if self._is_local(host):
                out.append(Err(f"# {host}:{port} SSH-2.0-OpenSSH_9.6"))
                out.append(f"{host} " + " ".join(key.export_public_key().decode().split()[:2]))
            else:
                out.append(Err(f"getaddrinfo {host}: Name or service not known"))
        return out

    # -- ssh, scp, sftp ---------------------------------------------------------------------------------------------

    def _is_local(self, host: str) -> bool:
        return host.lower() in LOCAL_NAMES | {"silverlake", "silverlake.localdomain"}

    def cmd_ssh(self, args: list[str]) -> list[str]:
        port, ident, login, words, i, config = 22, [], None, [], 0, {}
        while i < len(args):
            a = args[i]
            if a == "-V":
                self.status = 0
                return [Err(VERSION_LINE)]
            if a.startswith("-") and len(a) > 1 and not words:
                letter = a[1]
                value = args[i + 1] if letter in SSH_VALUE_OPTS and len(a) == 2 and i + 1 < len(args) else a[2:]
                if letter in SSH_VALUE_OPTS and len(a) == 2:
                    i += 1
                if letter == "p" and value.isdigit():
                    port = int(value)
                elif letter == "i":
                    ident.append(value)
                elif letter == "l":
                    login = value
                elif letter == "o" and "=" in value:
                    config[value.split("=", 1)[0].lower()] = value.split("=", 1)[1]
            else:
                words.append(a)
            i += 1
        if not words:
            self.status = 255
            return [Err(l) for l in SSH_USAGE.split("\n")]
        dest, command = words[0], words[1:]
        user, _, host = dest.rpartition("@")
        user = user or login or self.actor.name
        if not self._is_local(host):
            self.status = 255
            return [Err(f"ssh: Could not resolve hostname {host}: Name or service not known")]      # a guess: PUB400 hung here
        if port not in LISTEN_PORTS:
            self.status = 255
            return [Err(f"ssh: connect to host {host} port {port}: Connection refused")]
        if asyncssh is None:
            return self._no_asyncssh("ssh")
        warnings: list[str] = []
        key = self._ssh_identity(ident, warnings)
        remote = self._ssh_login(user, key)
        if remote is None:
            self.status = 255
            return warnings + [Err(f"{user}@{host}: Permission denied (publickey,password).")]
        if not command:
            self.status = 255
            return warnings + [Err("Pseudo-terminal will not be allocated because stdin is not a terminal."),
                               Err("This shell cannot start an interactive session; ssh to 127.0.0.1 port 2222 from outside, or give a command.")]
        remote.batch = True
        remote.login()
        out = remote.run(" ".join(command))
        self.status = remote.status
        return warnings + list(out)

    def _ssh_identity(self, given: list[str], warnings: list) :
        """The first identity file that is readable, safe and a private key, the way ssh tries them."""
        names = given or [f"{self.env['HOME']}/.ssh/{n}" for n in DEFAULT_IDS]
        for name in names:
            path = self.path(name)
            try:
                entry = ifs.lookup(self.store, self.actor, path)
                text = ifs.read(self.store, self.actor, path)
            except ifs.IfsError as exc:
                if given:
                    why = "Permission denied" if exc.kind == "EACCES" else "No such file or directory"
                    warnings.append(Err(f"Warning: Identity file {name} not accessible: {why}."))
                continue
            mode = _octal(entry)
            if mode & 0o077:
                bar = "@" * 59
                warnings += [Err(bar), Err("@         WARNING: UNPROTECTED PRIVATE KEY FILE!          @"), Err(bar),
                             Err(f"Permissions {mode:04o} for '{name}' are too open."),
                             Err("It is required that your private key files are NOT accessible by others."),
                             Err("This private key will be ignored."), Err(f'Load key "{name}": bad permissions')]
                continue
            try:
                return asyncssh.import_private_key(text)
            except Exception:
                warnings.append(Err(f'Load key "{name}": invalid format'))
        return None

    def _ssh_login(self, user: str, key):
        """A shell for the target profile when the listener would let this key in, else None."""
        from ..net import sshd
        from . import pase
        profile = self.store.get(user)
        if key is None or profile is None or profile.status != "*ENABLED" or not sshd.user_allowed(self.store, user):
            return None
        if sshd.settings(self.store)["pubkeyauthentication"].lower() != "yes":
            return None
        if not sshd.key_files_trusted(self.store, user) or key.public_data not in sshd.authorized_keys(self.store, user):
            return None
        return pase.Shell(self.store, profile)

    def _remote_spec(self, word: str) -> str | None:
        m = re.fullmatch(r"(?:[^@/:]+@)?([^/:@.][^/:@]*):.*", word)
        return m.group(1) if m else None

    def cmd_scp(self, args: list[str]) -> list[str]:
        operands, i = [], 0
        while i < len(args):
            a = args[i]
            if a.startswith("-") and len(a) > 1:
                i += 1 if a[1] in "cDFiJloPSX" and len(a) == 2 else 0
            else:
                operands.append(a)
            i += 1
        if len(operands) < 2:
            self.status = 1
            return [Err(l) for l in SCP_USAGE.split("\n")]
        remote = [self._remote_spec(o) for o in operands if self._remote_spec(o)]
        if not remote:
            for given in operands[:-1]:                          # PUB400's scp ran cp for two local names, and cp's own wording
                try:
                    ifs.lookup(self.store, self.actor, self.path(given))
                except ifs.IfsError:
                    self.status = 1
                    return [Err(f"cp: {given}: No such file or directory")]
            return self.cmd_cp(operands)
        for host in remote:
            if not self._is_local(host):
                self.status = 255
                return [Err(f"ssh: Could not resolve hostname {host}: Name or service not known"), Err("scp: Connection closed")]
        self.status = 255
        return [Err("subsystem request failed on channel 0"), Err("scp: Connection closed")]    # the listener has no sftp subsystem

    def cmd_sftp(self, args: list[str]) -> list[str]:
        words = [a for a in args if not a.startswith("-")]
        if not words:
            self.status = 1
            return [Err(l) for l in SFTP_USAGE.split("\n")]
        host = words[0].rpartition("@")[2].split(":")[0]
        self.status = 255
        if not self._is_local(host):
            return [Err(f"ssh: Could not resolve hostname {host}: Name or service not known"), Err("Connection closed")]
        return [Err("subsystem request failed on channel 0"), Err("Connection closed")]

    # -- openssl ----------------------------------------------------------------------------------------------------

    def cmd_openssl(self, args: list[str]) -> list[str]:
        sub = args[0] if args else "help"
        self.status = 0
        if sub == "version":
            return ["OpenSSL 3.0.10 1 Aug 2023 (Library: OpenSSL 3.0.10 1 Aug 2023)"]
        if sub == "help" or not args:
            return [Err(l) for l in OPENSSL_HELP.split("\n")[:-1]]                # PUB400 wrote its help to stderr
        if sub == "s_client":
            self.status = 1
            return [Err("00000001:error:8000004F:system library:BIO_connect:Connection refused:crypto/bio/bio_sock2.c:114:calling connect()"),
                    Err("00000001:error:10000067:BIO routines:BIO_connect:connect error:crypto/bio/bio_sock2.c:116:"),
                    Err("connect:errno=79")]
        if sub == "x509":
            return self._openssl_x509(args[1:])
        self.status = 1
        if sub in OPENSSL_KNOWN:
            return [Err(f"openssl: {sub} is not built into the simulator.")]
        return [Err(f"Invalid command '{sub}'; type \"help\" for a list.")]

    def _openssl_x509(self, args: list[str]) -> list[str]:
        want, given, i, quiet = [], None, 0, False
        while i < len(args):
            a = args[i]
            if a == "-in" and i + 1 < len(args):
                given, i = args[i + 1], i + 1
            elif a == "-noout":
                quiet = True
            elif a in ("-subject", "-issuer", "-dates", "-serial", "-fingerprint", "-enddate", "-startdate"):
                want.append(a)
            i += 1
        try:
            from cryptography import x509
            from cryptography.hazmat.primitives import hashes, serialization
        except ImportError:
            self.status = 1
            return [Err("x509: " + NEEDS_ASYNCSSH)]
        try:
            text = ifs.read(self.store, self.actor, self.path(given)) if given else "\n".join(self.stdin or [])
        except ifs.IfsError as exc:
            self.status = 1
            return [Err(f"Could not open file or uri for loading certificate from {given}"),
                    Err("00000001:error:16000069:STORE routines:ossl_store_get0_loader_int:unregistered scheme:crypto/store/store_register.c:237:scheme=file"),
                    Err(f"00000001:error:80000002:system library:file_open:{'Permission denied' if exc.kind == 'EACCES' else 'No such file or directory'}:providers/implementations/storemgmt/file_store.c:267:calling stat({given})"),
                    Err("Unable to load certificate")]
        try:
            cert = x509.load_pem_x509_certificate(text.encode())
        except ValueError:
            self.status = 1
            return [Err(f"Could not read certificate from {given or 'stdin'}"), Err("Unable to load certificate")]       # a guess

        def name(n) -> str:
            return ", ".join(f"{a.rfc4514_attribute_name} = {a.value}" for a in n)

        def when(d) -> str:
            return d.strftime("%b %e %H:%M:%S %Y GMT")

        out = []
        for w in want:
            if w == "-subject":
                out.append("subject=" + name(cert.subject))
            elif w == "-issuer":
                out.append("issuer=" + name(cert.issuer))
            elif w in ("-dates", "-startdate"):
                out.append("notBefore=" + when(cert.not_valid_before_utc))
            if w in ("-dates", "-enddate"):
                out.append("notAfter=" + when(cert.not_valid_after_utc))
            elif w == "-serial":
                out.append(f"serial={cert.serial_number:X}")
            elif w == "-fingerprint":
                digest = cert.fingerprint(hashes.SHA1()).hex().upper()
                out.append("SHA1 Fingerprint=" + ":".join(digest[n:n + 2] for n in range(0, len(digest), 2)))
        if not quiet:
            out += cert.public_bytes(serialization.Encoding.PEM).decode().strip().split("\n")
        return out

    # -- the ones an ordinary profile may not run ------------------------------------------------------------------

    def _denied(self, name: str) -> list[str]:
        self.status = 1
        return [Err(f"bsh: {name}: execute permission denied")]

    def cmd_dig(self, args: list[str]) -> list[str]:
        return self._denied("dig")

    def cmd_nslookup(self, args: list[str]) -> list[str]:
        return self._denied("nslookup")

    def cmd_host(self, args: list[str]) -> list[str]:
        return self._denied("host")

    def cmd_ldapsearch(self, args: list[str]) -> list[str]:
        self.status = 255
        return [Err("ldap_sasl_bind(SIMPLE): Can't contact LDAP server (-1)")]          # a guess: only `cannot execute` in bsh was seen
