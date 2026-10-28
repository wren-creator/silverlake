# Network services

Everything in Silverlake is reached through 5250 unless you start it with `./start.sh --services`. That adds listeners for the other doors an IBM i has. They are off by default, bind only to 127.0.0.1 (the same guard as the 5250 listener, checked again in `net/services.py`), and live in the same process and event loop, so they answer from the same profiles and authority and see a lesson toggle the moment it is saved. `./scenario.sh` keeps them on across its restart.

## Ports

Silverlake does not use the standard ports for everything. Some are on a different port because the real one is below 1024 and needs root, and 5250 is its own choice. Every port below can be moved, and every one binds to 127.0.0.1 only.

| Service | Silverlake port | Real IBM i port | Why it differs | How to move it |
|---|---|---|---|---|
| 5250 (Telnet) | 5250 | 23 | not a standard port, picked to be memorable and above 1024 | `./start.sh --port N` or `SILVERLAKE_PORT` |
| 5250 over TLS | 5992 | 992 | 992 is privileged | `SILVERLAKE_TLS_PORT` |
| HTTP Server Administration console | 2001 | 2001 | same as real | `SILVERLAKE_HTTPADMIN_PORT` |
| Console over TLS | 2010 | 2010 | same as real | `SILVERLAKE_HTTPADMIN_TLS_PORT` |
| FTP (and explicit TLS by `AUTH TLS`) | 2121 | 21 | 21 is privileged | `SILVERLAKE_FTP_PORT` |
| FTP, implicit TLS | 2990 | 990 | 990 is privileged | `SILVERLAKE_FTP_TLS_PORT` |
| Host server mapper | 4449 | 449 | 449 is privileged | `SILVERLAKE_MAPPER_PORT` |
| Sign-on server | 8476 | 8476 | same as real | `SILVERLAKE_SIGNON_PORT` |
| Sign-on server over TLS | 9476 | 9476 | same as real | `SILVERLAKE_SIGNON_TLS_PORT` |
| ssh (PASE shell, needs asyncssh) | 2222 | 22 | 22 is privileged | `SILVERLAKE_SSH_PORT` |

Two services cannot share a port, and `start.sh` and the server both say so. The mapper names the sign-on servers' ports in its answers (`as-signon`, `as-signon-s`), so if you move one the mapper follows. It also names the standard ports (8470 to 8475, and 9471) for the other host servers, and nothing listens on them.

The 5250 TLS port, the console TLS port, the FTP implicit port and the sign-on TLS port start only when a certificate exists (see below), and only with `--services`.

Things to know when you point a tool at it:

- **The real numbers.** `./start.sh --services --real-ports` (or `SILVERLAKE_REAL_PORTS=1`) uses 23, 992, 21, 990, 449 and 22 where they differ, and keeps the ones that already match (2001, 2010, 8476, 9476). A `SILVERLAKE_*_PORT` you set yourself still wins. Those ports are below 1024, so the account has to be allowed to bind them: root (and then the files in `state/` and `.venv/` should not be created by root, so start it as your user where you can), or on Linux `sudo sysctl net.ipv4.ip_unprivileged_port_start=0`. Recent macOS lets a normal user bind a low port on loopback, but that has not been checked here. If the bind fails the server says which port and nothing else starts. `./status.sh` and the loopback guard still apply, so the ports stay on 127.0.0.1.

- **Clients with a port option** just need it: `tn5250 ssl:127.0.0.1:5992`, `ftp 127.0.0.1 2121`, a browser at `http://127.0.0.1:2001/HTTPAdmin` or `https://127.0.0.1:2010/HTTPAdmin`.
- **Clients that hard code the real ports** (an FTP client that insists on 21, a host server client that goes to 449 first, a 5250 client that goes to 23 or 992) will not find anything. Either give them the port or forward the real one to ours, loopback only and needing root for a low port, for example `sudo socat TCP-LISTEN:21,bind=127.0.0.1,fork TCP:127.0.0.1:2121`. Silverlake does not do this for you.
- **Scanners** need the port list: `nmap -p 5250,5992,2001,2010,2121,2990,4449,8476,9476,2222 127.0.0.1`. A default scan of 127.0.0.1 will not find 5250, 5992, 2121, 2990, 2222 or 4449, and a scan of the real port numbers will find nothing at 23, 992, 21, 990 or 449. The `ibmi-httpadmin-nse` script works as is, because 2001 and 2010 are the real ports.
- **A port in use:** `start.sh` checks the 5250 port and each service port before it starts and names the variable to change.
- **Restarts:** `./scenario.sh` restarts with `--services` if the range was started with it, but it does not remember a custom port. Export the `SILVERLAKE_*_PORT` variables in the shell you run it from.
- `./status.sh` lists every socket the process holds and fails if any is beyond loopback.

## TLS

`./setup.sh` makes one throwaway certificate with the openssl command line tool: self-signed, 2048 bit RSA, SHA-256, for SILVERLAKE, valid for `localhost` and 127.0.0.1, kept in `.tls/` (gitignored, mode 0600 for the key). `./setup.sh --force-tls` makes a new one, `reset.sh` never touches it, and `SILVERLAKE_TLS_DIR` moves it. With no certificate, or no openssl, the TLS ports are skipped and the log says so.

It is a self-signed certificate on purpose, as on a stock IBM i. A client has to be told to trust it (`curl --cacert .tls/cert.pem`, `ssl.create_default_context(cafile=".tls/cert.pem")`, or an explicit "accept" in a browser). TLS 1.2 is the minimum, and `SILVERLAKE_TLS_MIN=1.3` makes it 1.3 (a client that offers only 1.2 is then refused in the handshake; any other value is an error at start).

- **FTP** offers `AUTH TLS` on 2121: the control connection upgrades in place, then `PBSZ 0` and `PROT P` make data connections TLS too (`PROT C` keeps them clear). Port 2990 is TLS from the first byte. Clear text sign-on is accepted on 2121 in the vulnerable state, which is what a stock IBM i does too; the `ftp-console-cleartext` lesson turns on `require_tls`, after which `USER` before `AUTH TLS` answers 534 and the console on 2001 answers 403 without asking for credentials.
- **The console** serves the same pages on 2001 and 2010 from one state, so a server created on one shows on the other.
- **The sign-on server** answers the same exchange on 9476.
- **5250** on 5992 negotiates telnet inside TLS, the way `tn5250 ssl:` and Access Client Solutions do.

What is checked and what is not: all of it is tested with Python's `ssl` and `ftplib` clients and with curl for the console. No real 5250 client or ACS has been tried on 5992, and the cipher list is Python's default, not an IBM i's. A scanner's `ssl-enum-ciphers` will show what Python's OpenSSL offers, not what a real box offers.

## What exists

| Service | Status |
|---|---|
| HTTP Server Administration console | built |
| FTP | built, with RCMD |
| Server mapper and sign-on server | built |
| TLS on the 5250 port, the console, FTP and the sign-on server | built, with a self-signed certificate |

## FTP

`ftp 127.0.0.1 2121`. Sign-on is the profile store's, in clear text (TLS is not built, so `AUTH` is refused), and bad attempts count against the profile. After that it is the same authority as the 5250 side: `RETR` reads a physical file only if the profile may, through the finder `DSPPFM` uses, and a listing leaves out what the profile has no authority to. Naming format 0 (`LIB/FILE`) and 1 (`/QSYS.LIB/LIB.LIB/FILE.FILE`) both work. A file comes back as its raw record text.

The `ftp-limited-bypass` lesson: FTP does not know what limited capability is, so a profile with no command line can still list and get what it may read. The secure state registers a request exit program (a record on `QUSRSYS/FTPEXIT`) that turns away limited capability profiles. That is a simplification of a real exit point, which can refuse any single request.

`RCMD` (`quote rcmd <CL command>`) runs a CL command as the signed on profile through Silverlake's own dispatcher, in this process, never a shell. It is the profile's own authority and nothing more, it answers 250 with the text of the result (messages, `DSPMSG`, `WRKUSRPRF`, `DSPUSRPRF`; a command that needs a screen says so) and 550 when the command fails, and the exit program of the `ftp-limited-bypass` lesson turns it away for limited profiles as it does the file commands.

Read only on purpose for files: there is no `STOR`, `DELE`, `MKD`, `RMD` or `RNFR`. Not built: members other than the first, IFS directories, `SITE`, active mode (`PORT`), TLS.

## ssh

Described in [pase.md](pase.md#ssh): the PASE shell on port 2222, password and public key logins, and the `sshd_config` files in the virtual IFS. It starts only when asyncssh is installed (`./setup.sh --ssh`); without it the log says so and the other services run as usual.

## Host servers

The mapper (4449, since 449 is privileged) answers a service name such as `as-signon` with `0x2B` and a four byte port, and `0x2D` for a name it does not know. The sign-on server (8476) answers the exchange of attributes every client opens with, before any sign-on: release, datastream level, a seed, the password level and the answering job. The reply shapes follow what a live IBM i 7.5 sent, as captured for web3270's mock. The values come from the saved state, so changing QPWDLVL changes what the wire says.

Only those two exist. There is no database, file, data queue, central or remote command server, and the mapper names ports for them that nothing listens on. The lesson is `hostsvr-recon`: the password level is free to anyone who asks. Its flag is a fact the trainee reads off the wire and submits (`V7R4M0/0`), checked against the state, so the answer changes once QPWDLVL is raised. Not built: TLS (9476), the signon request that carries a password.

## The HTTP console

`http://127.0.0.1:2001/HTTPAdmin`, HTTP Basic. Sign-in goes through the profile store, so the password that works at the 5250 sign-on works here, and bad attempts count against the profile and can disable it. Any enabled profile gets in. A real console needs `*IOSYSCFG` and `*ALLOBJ` and says `ZUI_50044` otherwise, which Silverlake does not model, because the published vector for this class of bug is a low privilege account.

Pages: Welcome, Manage (the server list), Create HTTP Server, About (OS release and whether the fix is installed).

Lesson `httpadmin-ssi-injection`: the server description is put on the Manage page after `<!--#exec cmd="..." -->` directives in it are evaluated, with no escaping, as the profile QTMHHTTP. The commands go to Silverlake's own dispatcher in this process. They never reach a shell, and the result is limited to what the dispatcher can say as text (messages, `DSPMSG`, `WRKUSRPRF`, `DSPUSRPRF`; anything that needs a screen says so). The fix is a PTF recorded on `QHTTPSVR/QZHBADMIN`, after which the field is escaped and never evaluated.

What is not faked: IBM has not published the vulnerable parameter of CVE-2026-96119, so this models the weakness class (CWE-94), not the real bug. Servers created in the console live in memory and a restart puts the three seeded ones back. No TLS port yet.

Real systems differ here. A real console on PUB400 answers `Server: Apache` and realm `HTTP Admin`, and Silverlake's headers are the mock's, not that capture.
