# Network services

Everything in Silverlake is reached through 5250 unless you start it with `./start.sh --services`. That adds listeners for the other doors an IBM i has. They are off by default, bind only to 127.0.0.1 (the same guard as the 5250 listener, checked again in `net/services.py`), and live in the same process and event loop, so they answer from the same profiles and authority and see a lesson toggle the moment it is saved. `./scenario.sh` keeps them on across its restart.

| Service | Port | Real port | Status |
|---|---|---|---|
| HTTP Server Administration console | 2001 (`SILVERLAKE_HTTPADMIN_PORT`) | 2001 | built |
| FTP | 2121 (`SILVERLAKE_FTP_PORT`) | 21 | built |
| Server mapper and sign-on server | 4449 and 8476 | 449 and 8476 | planned (5f-3) |

## FTP

`ftp 127.0.0.1 2121`. Sign-on is the profile store's, in clear text (TLS is not built, so `AUTH` is refused), and bad attempts count against the profile. After that it is the same authority as the 5250 side: `RETR` reads a physical file only if the profile may, through the finder `DSPPFM` uses, and a listing leaves out what the profile has no authority to. Naming format 0 (`LIB/FILE`) and 1 (`/QSYS.LIB/LIB.LIB/FILE.FILE`) both work. A file comes back as its raw record text.

The `ftp-limited-bypass` lesson: FTP does not know what limited capability is, so a profile with no command line can still list and get what it may read. The secure state registers a request exit program (a record on `QUSRSYS/FTPEXIT`) that turns away limited capability profiles. That is a simplification of a real exit point, which can refuse any single request.

Read only on purpose: there is no `STOR`, `DELE`, `MKD`, `RMD` or `RNFR`. Not built: members other than the first, IFS directories, `SITE`, active mode (`PORT`), TLS.

## The HTTP console

`http://127.0.0.1:2001/HTTPAdmin`, HTTP Basic. Sign-in goes through the profile store, so the password that works at the 5250 sign-on works here, and bad attempts count against the profile and can disable it. Any enabled profile gets in. A real console needs `*IOSYSCFG` and `*ALLOBJ` and says `ZUI_50044` otherwise, which Silverlake does not model, because the published vector for this class of bug is a low privilege account.

Pages: Welcome, Manage (the server list), Create HTTP Server, About (OS release and whether the fix is installed).

Lesson `httpadmin-ssi-injection`: the server description is put on the Manage page after `<!--#exec cmd="..." -->` directives in it are evaluated, with no escaping, as the profile QTMHHTTP. The commands go to Silverlake's own dispatcher in this process. They never reach a shell, and the result is limited to what the dispatcher can say as text (messages, `DSPMSG`, `WRKUSRPRF`, `DSPUSRPRF`; anything that needs a screen says so). The fix is a PTF recorded on `QHTTPSVR/QZHBADMIN`, after which the field is escaped and never evaluated.

What is not faked: IBM has not published the vulnerable parameter of CVE-2026-96119, so this models the weakness class (CWE-94), not the real bug. Servers created in the console live in memory and a restart puts the three seeded ones back. No TLS port yet.

Real systems differ here. A real console on PUB400 answers `Server: Apache` and realm `HTTP Admin`, and Silverlake's headers are the mock's, not that capture.
