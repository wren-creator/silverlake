# RPG programs

Silverlake runs RPG IV programs on [rpgle_library](https://github.com/wren-creator/rpgle_library), the same interpreter that runs them from a terminal. A program is a `*PGM` object whose attribute is `RPGLE`. Its source is in the object (`data["source"]`), and so is the DDS of its display file (`data["dspf"]`). `CALL PGM(APPLIB/ADVENTURE)` starts it. Every `EXFMT` becomes a screen on the 5250 until the program ends, and then the menu or command line comes back.

This is the first milestone of the RPG phase. It is a runner, not a compiler.

## What works

- **CALL** of a program you hold `*USE` to, qualified or found through the library list. The seeded programs are `APPLIB/ADVENTURE` (a text adventure) and `APPLIB/SALESRPT` (one screen of calculations), both from rpgle_library's examples. APPLIB is not on a basic profile's library list, so type the library.
- **The screen** lands where the DDS put it. Constants and output fields draw as text, input fields as input. Text that would run off the edge is clipped.
- **Keys.** Enter always goes to the program. A function key goes to it only if the display file names it (`CF03(03)` or `CA03(03)`), the way a real display file works. Any other key is refused where it stands with "Function key not allowed." The program decides when it ends, so F3 means nothing unless the DDS asked for it.
- **Number fields.** A real 5250 keyboard will not let a letter into a numeric field. Ours checks on Enter, says "Field X takes numbers only." and shows the screen again without the program seeing the input.
- **Calls between programs.** `CALL 'APPLIB/SR'` from RPG resolves the program against the caller's library list and authority, so a program you cannot use cannot be reached through one you can. An unqualified name uses the library list, the real behaviour: a program in APPLIB is not found by a profile whose list does not have it. Fixed-form factor 2 holds fourteen characters, so a qualified name needs a short program name or free-form source.
- **Runaway programs.** A program that runs more than 200,000 instructions without showing a screen is stopped with "ended abnormally". The interpreter runs in the server's own thread, so without the cap one `DOW *IN01 = *OFF` would freeze every session.
- **Signing off** with a program on the screen closes it with the session.
- **DSPPGM** shows the two pages captured from the system's own `QCMDEXC`: owner, attribute, type, observable information, **user profile** and **use adopted authority**. Those last two are the reason to look: `*OWNER` means the program runs with its owner's authority.

Source and attributes are saved in the state file like any object, so a student's edits would survive a restart, and `reset.sh` puts the seeds back.

## What it is not (yet)

- **No compile step.** Source is parsed when the program is called, not by `CRTBNDRPG`. A syntax error shows as "ended abnormally" at call time instead of a compile listing. Nothing can create a program yet except the seed.
- **No adopted authority and no `QCMDEXC`.** The `usrprf` and `useadpaut` attributes are stored and shown, and not acted on. A program runs with the caller's authority. This is the next milestone, and the teaching value of the whole phase: an `*OWNER` program owned by someone powerful that hands a string to `QCMDEXC` is the classic privilege escalation.
- **No files.** DISK files, printer files and the spool are not connected to Silverlake's object store, so a program can show screens and calculate and cannot read or write a `*FILE`.
- **One input per row.** The runtime keys input by screen row, so a second input field on the same row shows as text. Real DDS often has several per row.
- **One display file per program.** The DDS in the object is the program's display file, whatever name the program gives it.
- **Errors are not function checks.** An error in a running program ends it with a plain message in the job log. A real system raises a function check (CPF or MCH message) and offers a dump.

## Checked on PUB400

Taken read-only on 2026-10-27 (`auth-callpgm`, local capture). Nothing was created, because compiling a program is a write.

- `CALL PGM(NOSUCHPGM)` says **"Program NOSUCHPGM in library *LIBL not found."** Silverlake uses that wording for CALL only. The message ID was not captured, and the one `locate` uses for other commands stays.
- `DSPPGM PGM(QSYS/QCMDEXC)` is two pages (above). The system's own `QCMDEXC` is user profile `*USER`, use adopted authority `*YES`, type OPM, owned by QSYS.
- `CALL PGM(QSYS/QCMDEXC) PARM('NOSUCHCMD' 9)` says "Command NOSUCHCMD in library *LIBL not found." A command that works says nothing at all. A length that cuts the command short ("CHKOBJ OBJ(Q") says "A matching parenthesis not found." These are the messages the next milestone will reproduce.

## Needs a real system with a program in a library of its own

Writes, so each needs a human decision first (PUB400 rules: read only):

- Whether a function key the display file never named is refused with a message, or ignored, or raises an error. "Function key not allowed." is ours.
- What a compile error looks like (`CRTBNDRPG` listing, message IDs) and what the compiler produces for a source member.
- Whether adopted authority passes the owner's **special** authorities as well as object authority, which decides what a program owned by a powerful profile can do through `QCMDEXC`. IBM's page is the first place to check, and a real test needs a program owned by a profile that holds the authority.
- Whether `CALL` needs `*USE` or `*EXECUTE` to the program (Silverlake uses `*USE`, as it does for menus).
