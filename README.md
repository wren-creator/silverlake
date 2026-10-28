# Silverlake

A clean-room IBM i (AS/400) security range. You sign on with a real 5250 client, poke around a simulated system that looks and behaves like the real thing, and break it on purpose in a place where nobody gets hurt.

Silverlake was the AS/400's internal development codename. Nothing here is IBM code, and nothing here needs IBM media.

## Why this exists

The mainframe side has Hercules and GIBSON. The IBM i side has a handful of hosted accounts and a training mock buried inside a terminal emulator. If you want to learn how an IBM i gets attacked, or teach it, you either need a Power box or you need to trust someone else's hobby system with your curiosity.

A true AS/400 emulator is off the table. The licensed internal code is proprietary, there is no public domain OS to boot, and the only way to run one would be pirated media. So Silverlake is a behavioral simulator instead: it speaks 5250, it answers like IBM i, and its weak spots are the ones real systems have.

## Status

Phases 0 to 2, 3a, 3b, 3c-1, 3c-2, 3c-3a, 3c-3b and 3c-3c (jobs, spool files and message queues) done, with most of the work list options built (display, rename, owner, edit authority, delete, describe). A 5250 client can connect, sign on as any of the seed profiles, and see the access that profile holds. A `*SECADM` user can create, change, display, delete and list profiles from a command line, and the changes survive a restart. The starting access of each user is set in a seed file ([docs/access-model.md](docs/access-model.md)). Sign-on has teeth: three bad passwords disable a profile and an expired password forces a change. Jobs, job logs, spool files, output queues and message queues work, and a basic profile can read more about its neighbors than it should, as on the real thing. Libraries, a per-job library list, and object authority work from the command line (`CRTLIB`, `GRTOBJAUT`, `DSPOBJAUT` and friends). Menus work (`GO`, the menu stack, `LMTCPB`, command entry), with a seeded limited user whose menu has a way out. There is no general CL yet. A capture-and-diff harness measures how close the screens are to a real IBM i ([docs/oracle.md](docs/oracle.md)). See [ROADMAP.md](ROADMAP.md) for the plan and [docs/architecture.md](docs/architecture.md) for how the pieces fit.

RPG programs run: `CALL PGM(APPLIB/ADVENTURE)` after `./setup.sh` has installed [rpgle_library](https://github.com/wren-creator/rpgle_library) (see [docs/rpg.md](docs/rpg.md)). Adopted authority and `QCMDEXC` work, with a seeded privilege escalation and its fix (`APPLIB/RUNCMD`, `RUNCMDX`). Programs read and write PF files with the authority checked on every operation (a seeded payroll file, a lookup that adopts a reader and an adjust program that adopts too much). Printer files print to the spool, and a seeded payroll register shows how a queue leaks a report (`REGRPT`, `REGRPTX`). The compile commands (`CRTSRCPF`, `CRTBNDRPG`, `CRTPF`, `CRTDSPF`, `CRTPRTF`) build programs and files from source members. `STRPDM`, `WRKMBRPDM` and `STRSEU` give a PDM and a source editor to write them with.

## Safety

Everything binds to `127.0.0.1` and `start.sh` refuses to launch otherwise. A deliberately vulnerable IBM i has no business being reachable from anywhere but the machine running it.

## Clean-room rules

- No IBM code, no IBM media, no IBM manuals pasted in.
- Screen text and messages are written fresh. Captures taken from a real system for comparison stay local and gitignored in `captures/`.
- Tests assert structure (field positions, attributes, message IDs), not copied wording.
- What we will not fake is written down in [docs/not-faked.md](docs/not-faked.md).

## Quick start

```
./setup.sh      # make a venv and install (needs Python 3.12+; PYTHON=/path/to/python ./setup.sh if python3 is older)
./start.sh      # listen on 127.0.0.1:5250
./start.sh --port 5251   # or another port, if 5250 is taken
./status.sh     # is it up, is it loopback only
./stop.sh
./reset.sh      # back to the golden seed state
./scenario.sh list                       # the lessons and which are fixed
./scenario.sh set runcmd-qcmdexc secure  # fix one (stops and restarts the server)
./scenario.sh reset runcmd-qcmdexc       # vulnerable again, exploit leftovers cleared
./scenario.sh mode secure                # the whole range
# or, with the range running and no restart, as QSECOFR on a command line:
#   SLSCENARIO ID(runcmd-qcmdexc) STATE(*SECURE)    (also *VULNERABLE, *RESET, and ID(*ALL))
./check-flags.sh submission.txt          # score a trainee (--show for the instructor's answers)
```

The lessons are written up in [docs/scenarios.md](docs/scenarios.md) (instructor, with fixes) and [docs/scenarios-trainee.md](docs/scenarios-trainee.md), both generated from the scenario files by `python -m silverlake.scenario_docs`.

The network services (the HTTP Admin console, FTP and the host servers) are opt in: `./start.sh --services`. Ports are not all the standard ones: 5250 for the 5250 session (real: 23), 2001 for the console (same), 2121 for FTP (real: 21), 4449 for the host server mapper (real: 449) 8476 for the sign-on server (same) and 2222 for ssh into the PASE shell (real: 22, needs `./setup.sh --ssh`), with TLS on 5992, 2010, 2990 and 9476 once `./setup.sh` has made a certificate. All are loopback only and can be moved, see the table in [docs/services.md](docs/services.md#ports).

PASE is simulated: `CALL PGM(QP2TERM)` (or ssh on 2222 with `./setup.sh --ssh`) opens a small shell over a virtual IFS, with a writable IFS, scripts, `$PATH` lookup, `system` for CL, `db2` for SQL (inside `qsh -c`, as on the real host), 95 commands in all from `sort` and `sed` to `awk`, `tar` and `ssh-keygen`, and eight lessons built on it. No host process is ever started. See [docs/pase.md](docs/pase.md).

Teaching it? [instructor/](instructor/) has the agenda, answer key, rubric, setup runbook and session slides.

Connect with any 5250 client, for example `tn5250 127.0.0.1:5250`. `start.sh` refuses a port that is already in use and tells you the next one to try, and it only says "up" once the server reports it is listening, so a crash during startup shows up as a failure with the log tail instead of a false "up". It always binds to 127.0.0.1. `SILVERLAKE_PORT` does the same as `--port`.

## License

GPL-3.0-or-later. See [LICENSE](LICENSE).
