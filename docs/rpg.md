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

## Files

An RPG program's externally described `DISK` files are `*FILE` objects (attribute PF) that carry their record layout (`dds`, the DDS source) and their `records`. Both seeded files have them: `APPLIB/PAYROLL` (employees, locked down by the PAYAUTL authorization list) and `APPLIB/CUSTOMERS`.

- **Finding the file.** The F-spec name is resolved through the job's library list, the way a program name is. A name that is not there, or a library the user cannot reach, stops the program before it starts.
- **Authority at open.** Opening for input needs `*OBJOPR` and `*READ`, for update also `*UPD`, for output `*OBJOPR` and `*ADD`. After that each READ, WRITE, UPDATE and DELETE is checked for `*READ`, `*ADD`, `*UPD` and `*DLT`. The check uses whoever the call stack holds at that moment, so a program that adopts its owner reaches a file the user cannot, only while it runs, and a program that does not adopt, or that sits under `USEADPAUT(*NO)`, does not. A refusal ends the program with "Not authorized to use object ..." (the wording is ours, see below).
- **Where the data lives.** A run copies the records into a private SQLite database, and what the program writes goes back into the object after each screen and when the program ends, so it survives `./stop.sh` and goes away with `./reset.sh`. Only one file of a given name can be open in a job, because the library keys its tables by name.
- **The seeded lesson.** `PAYLOOK` is owned by OPERATOR, who holds `*USE` on PAYROLL through the list, and adopts its owner: anyone can look an employee up and nobody can change one through it. `PAYADJ` is owned by SECADMIN, who holds `*ALL`, adopts its owner, and checks nothing about who is calling. A basic user who may call it can set anyone's salary. The fix is not in the program: take `*PUBLIC` off the program (`RVKOBJAUT OBJ(APPLIB/PAYADJ) OBJTYPE(*PGM) USER(*PUBLIC) AUT(*USE)`) and grant it to who should have it.

## Printer files

A program that declares a `PRINTER` file in its F-spec prints through a `*FILE` object with attribute PRTF, which carries the printer DDS (`dds`) and the queue its output goes to (`outq`, `LIB/NAME`, default `QGPL/QPRINT`).

- **Authority.** The printer file needs `*USE`, and the queue needs `*READ` (inferred from IBM's output queue pages, not a captured refusal). Both are checked when the program is loaded, as whoever the call stack holds then. A missing queue stops the program before it prints.
- **The spooled file.** What the program writes becomes a spooled file named for the printer file, on the queue, in the job that ran the program, with the next file number in that job. It belongs to the **user**, never to an owner the program adopts, because the job is the user's. It is updated after every screen and when the program ends, so output survives a program that stops half way, and then WRKSPLF, WRKOUTQ, DSPSPLF and the hold, delete and change options work on it like any other.
- **Who can read it** is the queue's business, which is the lesson. `REGRPT` prints the payroll register to QPRINT, which is `DSPDTA(*YES)`, so a basic user can open the file payroll staff just printed. `REGRPTX` is the same program with a printer file that names `APPLIB/PAYOUTQ`, `DSPDTA(*NO)`: the entry is still listed, the contents are not shown to anyone but the file's owner and users with `*SPLCTL`.
- Page length is 66 lines and overflow is at line 60, the CRTPRTF defaults. Not modeled: printer file attributes beyond the queue (copies, form type, page size), CHGPRTF and OVRPRTF.

## Display files

A program's `WORKSTN` file is a `*FILE` object with attribute DSPF that carries the DDS (`dds`). The F-spec name is looked up through the library list, needs `*USE`, and several programs can name the same file: `RUNCMD` and `RUNCMDX` both open the display file `RUNCMD`, so there is one screen layout to read and one to change. Edit the object's DDS and every program that uses it shows the new screen.

- **A simplification.** After the library list, the program's own library is tried. A real job would fail to open a display file whose library is not on the list, and that would make `CALL APPLIB/ADVENTURE` fail for anyone who had not run ADDLIBLE first. Programs and files that are not on the list otherwise follow the list.
- **Older form.** A program object may still carry its DDS inline in `data["dspf"]`. It is used only when no display file of that name is on the list, so programs made before this change keep working.
- **Seeded.** `SCREEN` (ADVENTURE), `REPORT` (SALESRPT), `EMPINQ` (PAYLOOK), `SALADJ` (PAYADJ) and `RUNCMD`, all in APPLIB. The first two are named after the F-specs in the library's example programs.
- A program with more than one display file gets their record formats merged, since the runtime takes one set.

## Source and compiling

Programs can now be made without editing a seed file. Source lives in source physical files and is compiled with the real command names.

- **Source files and members.** `CRTSRCPF FILE(SCRATCH/QRPGLESRC)` makes a `*FILE` with attribute `PF-SRC` (record length 92 by default, which leaves 80 characters of line). Its `members` hold the lines, a type and a text. A line is the data of a source record, columns 1 to 80 of an RPG or DDS line. `SRCLIB` has `QRPGLESRC` (HELLO) and `QDDSSRC` (HELLOD, CUSTPF) to start from, and anyone may `CRTSRCPF` in a library they can add to. Members are written with STRSEU or PDM (next section), or come from the seed.
- **CRTBNDRPG** `PGM(lib/name) SRCFILE(lib/QRPGLESRC) SRCMBR(*PGM) TEXT(*SRCMBRTXT) USRPRF(*USER) USEADPAUT(*YES)`. It reads the member, parses it with the runtime, checks that every file the program declares exists on the library list, is the right kind and may be used, and makes the `*PGM`. The F4 prompt is in the F4 section below. A program that already exists is replaced: the compiling user becomes the owner and the old public and private authorities are kept, and replacing needs `*OBJEXIST` to the old program. That replacement rule is from memory of IBM's REPLACE(*YES), not a page, and is on the verification list.
- **CRTPF, CRTDSPF and CRTPRTF** `FILE(lib/name) SRCFILE(lib/QDDSSRC) SRCMBR(*FILE)` build a `*FILE` of that kind from a DDS member, checked by the runtime's DDS parsers. A file that exists is not replaced. A file with no source (`SRCFILE(*NONE)`, record length only) is not built. IBM's default for the source file is QDDSSRC, which is what is used here. The captured host showed `*NONE` for CRTDSPF and CRTPRTF, which looks like a local default.
- **The listing.** Every compile prints QSYSPRT to QGPL/QPRINT as the user's spooled file in the job, with the source and the messages. A failed compile makes no object and says "Compilation failed. Program NAME not created in library LIB." (ours).
- **From the real system.** The prompts of the five commands and their defaults, and the one message a compile gives for a member it cannot open: "Unable to open member NOPGM of file QRPGLESRC in library NOSUCH." That wording is used for any member that cannot be opened.
- **Why it matters for the range.** Compiling a program that adopts (`USRPRF(*OWNER)`) makes *you* the owner, so it adopts you and nobody else. The way to get someone else's authority is to replace a program they own, which needs authority to it, or to be handed one. Adoption has to be the owner's decision.

## PDM and the source editor

`STRPDM`, `WRKMBRPDM FILE(lib/file) MBR(name or generic*)`, `WRKOBJPDM LIB(lib)` and `STRSEU SRCFILE(lib/file) SRCMBR(name) TYPE(type) OPTION(2 or 5)` are the way in. Code is in `screens/pdm.py`.

- **STRPDM** draws the captured menu (1 libraries, 2 objects, 3 members, 9 user-defined options). Options 1, 2 and 3 only point at the command to type, since the real prompts are not built. `WRKOBJPDM` is an alias for `WRKOBJ` for now.
- **Work with Members.** Options 2 edit, 3 copy, 4 delete (with a confirm display, F12 keeps them), 5 browse, 7 rename, 13 change text and 14 compile. 14 picks the command from the member type: RPGLE to CRTBNDRPG, PF to CRTPF, DSPF to CRTDSPF, PRTF to CRTPRTF, into the source file's library. Options 3, 7 and 13 read their value from the command line. F6 creates a member, Position to scrolls, and a command typed on the line runs.
- **The editor** is SEU-shaped. Line commands I, D, C, M, R take a count, DD, CC, MM and RR mark blocks, A and B place a copy or move. The command line takes TOP, BOTTOM, FIND, CHANGE 'old' 'new' [ALL], SAVE, FILE and CANCEL. F3 on a changed member opens the exit display (change or create, member name, text, return to editing). Browse shows the member and changes nothing.
- **Authority and locks.** Editing needs authority to write the file, browsing only to read it, and a member is locked to one editor at a time (in memory, released at F3 and at sign off).
- **From the real system.** The menu and the refusals: "Library NOSUCH was not found.", "You do not have authority to file QRPGLESRC in LIB.", "Library NOSUCH not found." (STRSEU says it without "was"). The Work with Members and editor layouts, positions and messages are ours.
- **Known limits.** The sequence numbers are line numbers, not SEU's `NNNN.00` with dates, and a typed prefix is read by comparing the field to the number it started as. There are no syntax prompts, no column shift, no F11, and F4 inside the editor does nothing.

## Overrides and QTEMP

Two ways a caller can change what an adopting program touches, both about what a name means at the moment the program uses it.

- **QTEMP is per job.** Anything made in QTEMP carries the job that made it, only that job can find it (`objects.visible`, which `locate` applies, with the job carried on the search list `Session.search_order()` returns), and it is deleted at sign-off. The library itself is still one shared object, so two jobs cannot both make a `*FILE` of the same name in QTEMP, a simplification that costs nothing on a loopback range with one student. Listings such as WRKOBJ do not filter QTEMP by job yet. The default library list puts QTEMP after QGPL and before anything added with `ADDLIBLE ... *LAST`, which is where a site's application library usually goes.
- **OVRDBF and DLTOVR.** `OVRDBF FILE(STAFF) TOFILE(APPLIB/PAYROLL)` makes any program that opens STAFF in this job open PAYROLL instead. It needs no authority and is not checked when issued. The open is checked, as whoever the call stack holds, so an adopting program opens the caller's choice with its *owner's* authority. The job log says "File STAFF overridden to APPLIB/PAYROLL." `SECURE(*YES)` protects an override from later overrides (IBM's wording, from the web, not captured). All three OVRSCOPE values act as `*JOB` here, and MBR is ignored. Not built: DSPOVR, overrides for printer files, an override on a file the program names with EXTFILE.
- **Seeded.** `EMPDIR` adopts OPERATOR and reads `STAFF`, a public directory with the same layout as PAYROLL and a zero salary column. A basic user overrides STAFF to PAYROLL and the lookup shows real salaries. `EMPDIRX` is the same code owned by QDFTOWN, which has nothing on PAYROLL, so the redirected open is refused. `PAYRUN` adopts SECADMIN and calls `PAYCALC` by name alone. A basic user compiles their own `PAYCALC` into QTEMP, which is ahead of APPLIB on the list, and PAYRUN runs it with SECADMIN's authority. In the test it grants the user `*USE` on PAYROLL with QCMDEXC. `PAYRUNX` calls `APPLIB/PAYCALC`, so the list cannot choose.
- **Why the fix for EMPDIR is the owner and not an override.** A real RPG program opens its files before its first statement, so it cannot override its own files in time. The real defenses are a CL driver that overrides with SECURE(*YES) (CL programs are not built here), an owner who can reach only what the program needs, and USROPN with the override first (USROPN is not in the runtime). The seed uses the least-privilege one.

## CPYF and DSPPFM

Files can now be copied and read without writing RPG. Code is in `system/dbfiles.py` and `screens/pfm.py`. Nothing here was captured from a real system: the authority each needs is from IBM's pages as remembered and the completion wording and the display layout are ours.

- **CPYF** `FROMFILE(lib/file) TOFILE(lib/file) MBROPT(*NONE|*ADD|*REPLACE|*UPDADD) CRTFILE(*NO|*YES) FROMRCD NBRRCDS FMTOPT(*NONE|*MAP|*NOCHK)`. `*USE` on the from-file, `*OBJOPR` and `*ADD` on the to-file, plus `*DLT` to replace and `*UPD` to update. A to-file that already has records is refused unless MBROPT says what to do. A unique key refuses a duplicate. `FMTOPT(*NONE)` needs the same field names, `*MAP` and `*NOCHK` copy the fields the two share. Source files are refused (CPYSRCF is not built), FROMMBR and TOMBR are accepted and ignored.
- **The lesson.** A file made by CRTFILE(*YES) belongs to the person who copied and gets the library's create authority, so it is not on the original's authorization list. `*USE` on a locked file is enough to leave with a copy nobody locks. In QTEMP the copy leaves no trace after sign-off.
- **DSPPFM** `FILE(lib/file)` needs `*USE` and shows each record as its raw characters (numbers as zero-filled digits, no decimal point and no sign zone). Control takes a record number, T or B, Roll moves a page, F19 and F20 shift 71 columns. Not built: F10, F11 (hex), F21, Find, a member other than the first.

## F4 prompts

F4 on the command line (the menu, command entry, PDM) with a command name typed opens its prompt (`screens/prompt.py`), for 72 commands (71 from the captures, plus CRTLIB): the compile and create commands, the user, library, authority, job, spool, message and PDM commands, and the rest of what Silverlake has. Anything already typed fills its fields, F4 with option 14 beside a member in Work with Members prompts the right compile command filled in for that member, and Enter builds a command line from the fields (only what is not the default goes in, a required parameter always does, so the job log reads like something a person typed) and runs it. A command that finished goes back where F4 was pressed, one that was refused stays on the prompt with its message.

Every layout is drawn from `screens/promptspecs.py`, which is generated from read-only PUB400 captures (`auth-pdm`, `auth-prompts-a` to `h`, `auth-prompts-pages`) by `python -m silverlake.oracle.promptspec`. Rerun the generator when a capture is retaken, do not edit the table.

- **From the real system.** The title, rows, labels, columns, lengths and defaults; the Bottom or More... marker and the key lines (29 prompts offer F10, the rest do not), and what F10 shows; required parameters drawn brighter; "Parameter X required." on Enter and on Roll Up while one is empty, with every field of every empty required parameter redrawn in reverse image and the cursor on the first; Roll Up paging a long prompt (WRKSPLF and HLDSPLF have two pages, OVRDBF three); "Already at bottom of area." on the last page; "+ for more values" lines that carry a field; CHGPWD, which has nothing to prompt for and says `No parameters to show; press Enter to run, F3 to exit.`; and the colors ("Type choices" and the key lines blue, titles and the marker white).
- **Checked against the capture.** Each of the 71 prompts, rendered and decoded the way the oracle decodes the host, has the same input fields, attributes and cursor as the real screen, and 69 have the same text and color in every cell. The two that differ are the CRTDSPF and CRTPRTF default below. `python -m silverlake.oracle compare captures/pub400/auth-prompts-b.json --fields-only` replays one of the runs locally and shows only the sign-on screen differing. Roll Down at the top says "Already at top of area." (captured).
- **Ours.** How a refused command reads on the prompt, the wording of "not built" for F9, F11, F13, F14 and for a second F10, and the key line coming back on a second F24 (and being the same line on every prompt, it was only seen on CRTPF), whether a filled-in required parameter is flagged after a refusal (it is not), which page comes up when the missing name is on another one, and the guess that tells a finished command from a refused one when the message has no ID. Where the captured host offered `*NONE` and a blank library for SRCFILE on CRTDSPF and CRTPRTF (which looks like a local setting) the field holds QDDSSRC and `*LIBL`, IBM's default, so Enter works.
- **F10, Additional parameters.** F10 goes straight there with no check of the required names, keeps what was typed, and shows the whole prompt again with the further parameters under an "Additional Parameters" line, on as many pages as the host had (CRTPRTF has eleven, CHGJOB four). Its key lines drop F10. F12 from there leaves the prompt altogether, as it did on the host. CHGSPLFA stops after its first page, because the host would not page it without a real spooled file. The values a change command shows as current (CHGPRF, CHGJOB) are the signed-on profile's here, not the profile the capture was taken with.
- **F24, more keys.** F24 swaps the two key lines for one, `F9=All parameters   F11=Choices   F14=Command string   F24=More keys`, as the host did on CRTPF. F9, F11 and F14 are not captured, so they say they are not built, and so does any other key that is not Enter, Roll, F3, F5, F10, F12 or F24. (Before this, such a key was taken as Enter and ran the command.)
- **Laid out but refused.** RCDLEN on CRTPF (a file with no source) and SRCSTMF on CRTBNDRPG say they are not built. F13 and F24 say so too.
- **Refused before any prompt.** F4 on a command the profile may not use says `Not authorized to command X in library *LIBL.` on the line where it was typed and opens nothing, the way PUB400 did for CRTLIB. It is the same check running the command makes (*USE to the `*CMD` object), so locking a command locks its prompt too.
- **CRTLIB's layout is ours.** The host refused it before showing one, so it has LIB, TYPE and TEXT in the columns CRTMSGQ uses and no F10 page. Commands outside the 72 say F4 is not built for them.

## What it is not (yet)

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
