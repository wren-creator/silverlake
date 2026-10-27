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

## Signing on as a test profile

Menus and commands need a real sign-on, so the oracle can sign on as a **test profile**, never a real account. Put its name and password in `.env`:

```
cp .env.example .env && chmod 600 .env     # then fill in SILVERLAKE_ORACLE_USER and _PASS
SILVERLAKE_ORACLE_HOSTS=pub400.com \
  python -m silverlake.oracle capture pub400.com --tls --out captures/pub400/auth-probe.json auth-probe
```

(`--tls` connects on port 992 unless you give a port. Put the scenario name before `--out`.) The guard rails, all enforced in code and tested:

- `.env` is gitignored, and the loader refuses a file other users can read, the way ssh refuses a loose key. It reads only `SILVERLAKE_ORACLE_*` names, a variable already in the shell wins, and it never prints a value.
- A scenario that sends a password refuses to run over cleartext telnet to anything but loopback. TLS verifies the certificate and the host name, and there is no switch to turn that off.
- Every value is resolved before connecting, so a missing variable cannot leave a half finished session on a shared system.
- One sign-on attempt per run. If the host answers with a message ID or another password prompt, the run stops and sends nothing more.
- The scenarios only run `DSPLIBL` and `DSPOBJAUT`, and a test enforces that. Captures record what the host sends and never what we type, so the password cannot reach a capture file.
- Scenarios end with F3 on the menu, which signs the job off so it does not linger. A run that dies midway leaves a disconnected job until the host's timeout.

`auth-probe` signs on, snapshots the first screen, and signs off. Run it first and look at the capture before running `auth-libs` (the library list and the authority to `QSYS` and `QGPL`). `compare` on an authenticated capture replays the scenario on local Silverlake as a seed profile (`--local-user`, default `STUDENT`), so the real credentials never meet our server.

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

- It runs a customized sign-on: two fields where a stock screen has five, at different positions. That is why `compare` still reports layout differences on the left half. PUB400 is a poor oracle for the stock sign-on layout, but its right hand block and bottom row are stock.

## The stock sign-on

A photo of a default sign-on display (Italian language, copyright 1980, 1996) settled the layout. It was consulted, not stored in this repo, and only positions were taken from it, never wording. Its status bar read `6/53`, the cursor at row 6, column 53, 1-based. That fixes the input field column exactly at `(5, 52)` zero-based. The right hand block (labels at col 47, values at col 69) and the copyright column (39) agree with PUB400 to the cell. Label columns (14) and the title column (34) are read off the photo and good to about one column. Colors come from PUB400, since a monochrome photo cannot confirm them.

## What the first authenticated captures taught us

A test profile on PUB400 signed on over TLS and ran `DSPLIBL` and `DSPOBJAUT` (2026-10-27).

- **A real menu.** The main menu has its command line at row 19, column 6, 153 long, and not monocase. F3 on it did not sign the job off, so the first run left a disconnected job behind. Every scenario now ends with `SIGNOFF`, which worked.
- **Real facts for the seed.** `QSYS` and `QGPL` owner and public authority, the default library list, and what a basic user sees from `DSPOBJAUT` (see `docs/access-model.md`).
- **Commands are objects.** A guarded test (`auth-crtlib`) tried to create a throwaway library, look at its authority, delete it, and sign off. The host answered `Not authorized to command CRTLIB in library *LIBL.`, so the harness did not go on to display or delete anything and signed off. The create-gate, which skips everything but sign-off when the host does not say the library was created, is what made a refusal harmless. The run created and changed nothing.
- **Real screens to match.** `DSPLIBL` has an option column (`5=Display objects in library`), a device column, and `F17=Top`/`F18=Bottom`. `DSPOBJAUT` has a Group column, a line for the authorization list, and `F11=Display detail object authorities`. Neither matches Silverlake's screens yet, and the menu now matches the real MAIN menu on field positions (the wording is ours). `compare` on the capture reports every difference.

## What the object and authorization list captures taught us

The same test profile ran the read-only `auth-objects` scenario (2026-10-27): `WRKOBJ`, `WRKOBJOWN`, `WRKAUTL` and `DSPAUTL` against PUB400, plus two refusals on purpose. Nothing was created or changed.

- **Message lines show text only.** After sign-on, a refusal shows `Library SLNOSUCH not found.` and `Not authorized to user profile QSYS.` with no `CPFxxxx -` in front. The ID lives in the second level text. Silverlake printed the ID on the message line, which was wrong, and now shows the text alone after sign-on. The sign-on screen keeps its IDs. The wording of both messages matched ours exactly.
- **Public authority counts as some authority.** A basic profile's `WRKAUTL` listed dozens of lists it neither owns nor has an entry on, and `DSPAUTL` on a system list worked with only a `*PUBLIC *USE` row. Silverlake required the owner or an entry, which was wrong. It now also shows a list whose public authority is not `*EXCLUDE`. The long list is also the default `*CHANGE` public authority doing what it does.
- **Real `DSPAUTL` layout.** Two header rows (`Object`/`List` over `Authority`/`Mgt`), user at column 1, object authority at 13, a mark in the Mgt column at 24, and `Primary group`, `Owner` and `Library` in the top block. Silverlake's screen now follows it. The Mgt mark being an `X` is assumed, since the capture only had a `*PUBLIC` row.
- **Real displays have options Silverlake does not.** `WRKOBJ`: 2=Edit authority, 3=Copy, 4=Delete, 5=Display authority, 7=Rename, 8=Display description, 13=Change description, with an Opt column, columns Object, Type, Library, Attribute, Text, a 73 long command line at row 20, column 6, and keys F4, F5, F9, F11, F12, F16, F17. `WRKOBJOWN` adds 9=Change owner and shows Object, Library, Type, Attribute and Device. `WRKAUTL`: 1=Create, 2=Edit, 4=Delete, 5=Display, 8=Display objects in list, 9=Display documents/folders in list, 13=Change description, with a position-to row. None of that is built yet, and the command pages did not list it, which is why a capture was needed.
- **Real `WRKOBJOWN` sorts and shows the profile at the top** (`User profile . . . :`), and the entries carry an `ASP` device column of `*SYSBAS`.

## Still open

- **A stock sign-on capture.** The photo settled positions, but a real capture would confirm the title and label columns and the colors. The password field length is also unsettled: stock is 10, PUB400 shows 128 at its password level.
- **Authenticated screens.** The harness can now sign on as a test profile (see above). What it has not done yet is run against a real host, so the post-sign-on screens are still unseen.
- **The Query path against a real host.** The client answers a 5250 Query, and a test proves it, but PUB400's sign-on never sent one. It will appear after sign-on.
- **Orders not yet seen on real streams.** Erase To Address attribute-count handling is unverified.
- **Message text for IDs.** Phase 3 gives Silverlake real message IDs to compare.
