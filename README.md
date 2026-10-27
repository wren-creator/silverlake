# Silverlake

A clean-room IBM i (AS/400) security range. You sign on with a real 5250 client, poke around a simulated system that looks and behaves like the real thing, and break it on purpose in a place where nobody gets hurt.

Silverlake was the AS/400's internal development codename. Nothing here is IBM code, and nothing here needs IBM media.

## Why this exists

The mainframe side has Hercules and GIBSON. The IBM i side has a handful of hosted accounts and a training mock buried inside a terminal emulator. If you want to learn how an IBM i gets attacked, or teach it, you either need a Power box or you need to trust someone else's hobby system with your curiosity.

A true AS/400 emulator is off the table. The licensed internal code is proprietary, there is no public domain OS to boot, and the only way to run one would be pirated media. So Silverlake is a behavioral simulator instead: it speaks 5250, it answers like IBM i, and its weak spots are the ones real systems have.

## Status

Phases 0 to 2, 3a, 3b, 3c-1, 3c-2 and 3c-3a done. A 5250 client can connect, sign on as any of the seed profiles, and see the access that profile holds. A `*SECADM` user can create, change, display, delete and list profiles from a command line, and the changes survive a restart. The starting access of each user is set in a seed file ([docs/access-model.md](docs/access-model.md)). Libraries, a per-job library list, and object authority work from the command line (`CRTLIB`, `GRTOBJAUT`, `DSPOBJAUT` and friends). Menus work (`GO`, the menu stack, `LMTCPB`, command entry), with a seeded limited user whose menu has a way out. There is no general CL yet. A capture-and-diff harness measures how close the screens are to a real IBM i ([docs/oracle.md](docs/oracle.md)). See [ROADMAP.md](ROADMAP.md) for the plan and [docs/architecture.md](docs/architecture.md) for how the pieces fit.

## Safety

Everything binds to `127.0.0.1` and `start.sh` refuses to launch otherwise. A deliberately vulnerable IBM i has no business being reachable from anywhere but the machine running it.

## Clean-room rules

- No IBM code, no IBM media, no IBM manuals pasted in.
- Screen text and messages are written fresh. Captures taken from a real system for comparison stay local and gitignored in `captures/`.
- Tests assert structure (field positions, attributes, message IDs), not copied wording.
- What we will not fake is written down in [docs/not-faked.md](docs/not-faked.md).

## Quick start

```
./setup.sh      # make a venv and install
./start.sh      # listen on 127.0.0.1:5250
./status.sh     # is it up, is it loopback only
./stop.sh
./reset.sh      # back to the golden seed state
```

Connect with any 5250 client, for example `tn5250 127.0.0.1:5250`.

## License

GPL-3.0-or-later. See [LICENSE](LICENSE).
