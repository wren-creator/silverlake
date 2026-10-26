# The fidelity oracle

"Looks like a real IBM i" is only worth claiming if we can measure it. The oracle is a small 5250 client that signs on to a host, records what the host puts on the screen, reduces it to structure, and diffs two captures. Point it at a real IBM i for the reference, then at Silverlake.

## Use

```
python -m silverlake.oracle scenarios
python -m silverlake.oracle capture local signon --out captures/silverlake/signon.json
SILVERLAKE_ORACLE_HOSTS=pub400.com \
  python -m silverlake.oracle capture pub400.com:23 signon --out captures/pub400/signon.json
python -m silverlake.oracle compare captures/pub400/signon.json
python -m silverlake.oracle diff A.json B.json [--fields-only] [--text]
```

`compare` runs the same scenario on an in-process Silverlake and diffs it against a saved reference. A is always the reference.

## What is compared

Structure, not wording: geometry, cursor, every input field (row, column, length, attribute, hidden, monocase, shift), where each text run starts and in what attribute, and which message IDs appear (`CPF1120` and friends). Wording is ours to write, so it is only compared with `--text`, and that is for local use.

## Etiquette, enforced in code

- A host that is not loopback has to be named in `SILVERLAKE_ORACLE_HOSTS`, or the harness refuses. It cannot be pointed at a system by accident.
- One connection per run, and at least 10 seconds between connections to the same host.
- Sign-on scenarios that fail use a made-up user, so a real profile never counts a failed attempt.
- Field values can use `${NAME}` to read a password from the environment. Nothing secret goes in a scenario file.
- No scans, no probing, nothing that is not a normal person at a terminal.

## Captures stay local

`captures/` is gitignored. A capture holds a real system's wording and its raw host records, and those are not ours to publish. Snapshots are re-derived from the raw records every time a capture is loaded, so an old capture stays comparable as the decoder improves.

## What the first captures taught us

Taken from PUB400 on 2026-10-26, opening sign-on and one unknown user.

Generic facts, now built into Silverlake:

- The sign-on user field carries the monocase flag (second field format byte `0x20`), so the terminal upper-cases what is typed. The password field does not.
- Input fields can be longer than a row. A real password field is 128 long and wraps. The model now allows that.
- After a bad user, the message goes on the bottom row, column 0, in white, and it replaces the copyright line there. The typed user stays in the field, the password clears, and the cursor returns to the user field.
- A real host writes a field's attribute cell a second time as a bare attribute. A decoder that treats that as a new cell loses the field. (This bug was ours, and the real record caught it.)

Specific to PUB400, so deliberately not copied:

- It runs a customized sign-on: two fields where a stock screen has five, at different positions. That is why `compare` still reports layout differences. PUB400 is a poor oracle for the stock sign-on layout.

## Still open

- **A stock sign-on sample.** We need a capture from a system with the default sign-on display to settle the layout.
- **Authenticated screens.** Menus and commands need a real sign-on. That means the user's own profile, with the password read from the environment, and a human deciding each run.
- **The Query path against a real host.** The client answers a 5250 Query, and a test proves it, but PUB400's sign-on never sent one. It will appear after sign-on.
- **Orders not yet seen on real streams.** Erase To Address attribute-count handling is unverified.
- **Message text for IDs.** Phase 3 gives Silverlake real message IDs to compare.
