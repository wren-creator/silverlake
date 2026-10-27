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

## What IBM's pages say about adopted authority

From two IBM support pages, [Adopted Authority](https://www.ibm.com/support/pages/adopted-authority) and [Using Adopted Authority for the CRTUSRPRF without *SECADM](https://www.ibm.com/support/pages/using-adopted-authority-crtusrprf-without-secadm-special-authority). The adopted authority milestone follows them.

- `USRPRF(*OWNER)` makes the program run "combining the authorities of the Owner of the program with those of the User Profile running the program". The user keeps their own.
- `USEADPAUT(*YES)` means adopt from the *prior program in the call stack*, not from the owner. If B is `USEADPAUT(*YES)` and `USRPRF(*USER)`, whatever A adopted flows to B. `USEADPAUT(*NO)` cuts that off.
- Adopted authority is only there while the program is active, and is suspended if it is interrupted.
- Not covered by adopted authority: system request, the attention key, break handling programs, and debug functions. `TFRGRPJOB` does not pass it to the group job. The IFS does not support it at all.
- When a program adopts to run `CRTUSRPRF` and assigns a group profile, the user still needs `*CHANGE` and `*OBJMGT` to that group profile by their own authority. Adoption does not supply it (a refusal shows as `CPF9802`).
- IBM's advice is to adopt an application owner's authority, not QSECOFR's or any `*ALLOBJ` profile's.

## Adopted authority and QCMDEXC

A `*PGM` with `USRPRF(*OWNER)` adds its owner to whoever called it, for as long as it is on the call stack.

- **What is added.** The owner's object authority and special authorities. The user keeps their own, so the result is the two combined. That the special authorities count is inferred from IBM's pages, not stated, and sits on the verification list.
- **What passes down.** `adopted_owners` in `system/rpg.py` walks the stack outermost first. `USEADPAUT(*YES)` lets a program keep what the one before it held, `*NO` cuts that off, and a program with `USRPRF(*OWNER)` adds its own owner on top.
- **Nothing sticks.** The profile is copied for the duration of the call (`ProfileStore.adopting`) and the copy keeps the user's name. Objects it creates are the user's, as on IBM i. The job log says which owner a program ran as.
- **The one place it does not apply.** Assigning a group profile in `CRTUSRPRF` still needs the user's own `*CHANGE` and `*OBJMGT` to the group (IBM). Silverlake uses the existing "not authorized to user profile" message where a real system shows CPF9802.
- **`CALL 'QCMDEXC'`** is answered inside Silverlake. The command string goes to the same dispatcher the command line uses, as the profile the stack holds right now, and never to a shell. Parameter two is the length and only that many characters are read. An unknown command says "Command X in library *LIBL not found." (captured). A length that cuts a command mid-parenthesis says "A matching parenthesis not found." (captured). A command that works says nothing. A failure ends the program with that message, which is a guess at how a real program sees it, and a command that needs a whole screen (WRKACTJOB, DSPLIBL) is refused, because a program has no screen to give it.
- **The seeded hole.** `APPLIB/RUNCMD` is a support helper owned by QSECOFR, compiled to adopt its owner, that hands whatever is typed to QCMDEXC. STUDENT types `CRTUSRPRF USRPRF(EVIL) PASSWORD(EVIL) USRCLS(*SECOFR)` and the helper makes it. `APPLIB/RUNCMDX` is the fix: a short allow-list, and an owner (QDFTOWN) that holds no special authority, so a hole in the list gives away nothing. Read the source with `DSPPGM` and the `data` of the object, edit it, and watch the difference.

## What it is not (yet)

- **No compile step.** Source is parsed when the program is called, not by `CRTBNDRPG`. A syntax error shows as "ended abnormally" at call time instead of a compile listing. Nothing can create a program yet except the seed.
- **Adopted authority and `QCMDEXC` are built** (next section). Not covered: system request, the attention key, break handling programs and debug (nothing here starts one), and `TFRGRPJOB` (not built). The IFS does not support adoption either, and the simulated PASE will have to keep that true.
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
- Whether adopted authority passes the owner's **special** authorities as well as object authority. IBM's two support pages (read 2026-10-27) do not say it in one sentence. One describes the program as combining the owner's authorities with the user's, and its QSECOFR example says the owner's authority "flows down the stack giving the user the same All Object authority". The other is a how-to that wraps `CRTUSRPRF` (which needs `*SECADM`) in a `USRPRF(*OWNER)` program so users without it can run the command, which only works if the owner's special authority counts. Silverlake will treat the owner's special authorities as effective while an `*OWNER` program is on the stack, and this entry stays open until a real test confirms it. The Security Reference chapter 5, "Objects that adopt the owner's authority", is the primary source and was not read.
- Whether `CALL` needs `*USE` or `*EXECUTE` to the program (Silverlake uses `*USE`, as it does for menus).
