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
