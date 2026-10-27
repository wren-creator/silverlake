# Architecture

Silverlake is a behavioral simulator. It does not emulate hardware, SLIC, or TIMI. It reimplements the surface an IBM i user, administrator, or attacker touches.

## Layers

```
5250 client (tn5250, TN5250E, s3270)
        |
  telnet + TN5250E negotiation        silverlake/net
        |
  5250 data stream encode/decode      silverlake/proto
        |
  declarative screens                 silverlake/screens
        |
  CL dispatcher + command handlers    silverlake/cl
        |
  system model (QSYS.LIB-style)       silverlake/system   <- SQLite
        |
  RPG / DDS runtime                   rpgle_library run_program
```

## Decisions

- **Python.** rpgle_library's reference runtime is Python, and its `run_program` generator (yields at EXFMT, resumes with the key and field values) maps directly onto a 5250 session.
- **Screens are data.** A screen is a description (rows, fields, attributes, function keys). The encoder turns it into bytes. Screen content is never hand-assembled into bytes.
- **CL is table driven.** One table maps a command name to its parameters and handler, so prompting (F4) and error messages come from the same source.
- **State lives in SQLite.** Objects, libraries, profiles, jobs, spool. That is what makes `reset.sh` a file copy.
- **Two modes.** `vulnerable` seeds weak configuration on purpose. `secure` applies the fixes. Same code, different seed.

## Fidelity oracle

A real IBM i (PUB400, read-only, human paced, no scans) is the reference for how screens and messages look. Captures are local and gitignored. The harness replays a command on Silverlake and diffs structure against the capture.

## Network posture

Loopback only. The listener refuses to bind to anything but 127.0.0.1, and `start.sh` checks it again before launching.

## What exists today (through Phase 3b)

```
src/silverlake/
  config.py            loopback-only listen address
  proto/telnet.py      telnet framing, NEW-ENVIRON parsing
  proto/datastream.py  GDS records, AID keys, terminal input decoder
  proto/ebcdic.py      code page 037
  screens/model.py     Text and Input fields, validation
  screens/render.py    Screen -> Clear Unit + Write To Display + Read MDT Fields
  screens/signon.py    sign-on screen and the session controller (command line, views)
  screens/menu.py      menu and command entry screens (real MAIN menu layout)
  screens/home.py      wrap(), shared by the display screens
  system/menus.py      *MENU data: title, options, validation
  system/autls.py      authorization list commands and their rules
  system/objlist.py    WRKOBJ, WRKOBJOWN, CHGOBJOWN
  screens/usrprf.py    DSPUSRPRF and WRKUSRPRF screens
  cl/parser.py         splits a command line into command, positional and keyword values
  cl/commands.py       binds parameters, runs the profile, library and object authority commands
  cl/session.py        what a job carries: its library list
  screens/objects.py   DSPLIBL, WRKLIB, DSPOBJAUT screens
  net/server.py        asyncio listener, one Connection per client
  system/authority.py  user classes, special authorities, object authority resolution
  system/profiles.py   profile store, TOML seed loader, sign-on check
  system/admin.py      create, change, display, delete profiles with IBM's authority rules
  system/objects.py    libraries, library list, DSPOBJAUT/GRTOBJAUT/RVKOBJAUT with IBM's rules
  system/state.py      SQLite persistence (object tables keyed by library/name/type), seed on first start, wiped by reset.sh
  system/messages.py   message IDs and our wording, with where each ID came from
  data/profiles.toml   the seed: who exists and what access they hold
  oracle/              capture client, host stream decoder, diff, CLI (see oracle.md)
```

A controller is anything with `first()`, `handle(aid, values)` and `close()`. The first two return a Screen, and `close()` runs when the connection ends so the session is counted out even when the line just drops. The network and rendering code does not know what a command is.

## What has been verified, and what has not

- Unit tests cover framing split at every size, record round trips, exact rendered bytes, and screen validation.
- An independent client, web3270's tn5250 session class, connects, sees the sign-on screen with the right fields and a hidden password, types, and gets the reply back (`tests/test_interop_web3270.py`).
- The decoder reads a real PUB400 sign-on record correctly (two fields, a 128 long hidden password, cursor homed to the first field), and the structural diff against live PUB400 captures is how generic behavior gets confirmed (`docs/oracle.md`).
- **Not yet checked:** lib5250's `tn5250`, IBM Access Client Solutions, or any real terminal. TLS is not built. Anything past the sign-on screen has not been compared with a real IBM i.
