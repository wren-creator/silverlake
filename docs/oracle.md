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
- **Real displays have options Silverlake does not.** `WRKOBJ`: 2=Edit authority, 3=Copy, 4=Delete, 5=Display authority, 7=Rename, 8=Display description, 13=Change description, with an Opt column, columns Object, Type, Library, Attribute, Text, a 73 long command line at row 20, column 6, and keys F4, F5, F9, F11, F12, F16, F17. `WRKOBJOWN` adds 9=Change owner and shows Object, Library, Type, Attribute and Device. `WRKAUTL`: 1=Create, 2=Edit, 4=Delete, 5=Display, 8=Display objects in list, 9=Display documents/folders in list, 13=Change description, with a position-to row. The work lists now follow these layouts and the options that are cheap and safe to build (see docs/access-model.md for which); a `compare` against this capture matches the `WRKOBJ` fields exactly. The option field is monocase everywhere, one character at column 2 on `WRKOBJOWN`, and the command line is not monocase.
- **Real `WRKOBJOWN` sorts and shows the profile at the top** (`User profile . . . :`), and the entries carry an `ASP` device column of `*SYSBAS`.

## What the object option captures taught us

One more write, approved on its own: the `auth-objopts` scenario (2026-10-27) made a throwaway data area in the job's own QTEMP, pressed 2, 8 and 4 on a list holding only that object, and deleted it. Nothing outside the job existed afterwards. `auth-edtautl` ran `EDTAUTL` on a list the profile does not own.

- **Edit Object Authority is real and has a fixed layout.** Object, Owner, Library, Primary group, Object type and ASP device in the top block, the authorization list field at row 8, then User, Group and Authority columns from row 12 with `*PUBLIC` first and the owner next. A new QTEMP object got `*PUBLIC *EXCLUDE` and the owner `*ALL`. Keys F5, F6 (add new users), F10, F11, F12, F17 and F18. Silverlake's screen now matches field for field, except that F6, F10 and F11 are not built.
- **Display Object Description - Full** has the Library n of n counter, the creation block, Created by user, System created on, and Object domain, and a second page ("More..."). Silverlake does not keep a creation date or time, so those stay blank.
- **Confirm Delete of Objects** shows the rows marked 4 and two instruction lines. After F12 the 4 stays typed in the option field. After Enter the list reports "(Cannot find object to match specified name.)" and the message line says the object was deleted.
- **EDTAUTL as a basic user** is refused with "Not authorized to change authorities." on the message line, with no screen.
- "Bottom" and "More..." sit right aligned at column 73 and 72, which we had a few columns off.

## What the second option capture taught us

Two more runs on 2026-10-27: `auth-objdesc` (read-only, `DSPOBJD` on QGPL, basic and full, then Roll Up) and `auth-objopts2` (the second approved QTEMP write: a throwaway data area, F6, F10, F11 and option 3 pressed and backed out of, nothing filled in).

- **`DSPOBJD DETAIL(*BASIC)` is a list**, not a short version of the full display: one row per object with an option field (5=Display full attributes, 8=Display service attributes) and Attribute, Size and Text columns. Silverlake has no attributes or sizes, so those stay blank.
- **The full description has more than two pages.** Page two (Change/Usage and Auditing/Integrity information) says "More..." too, so a third page exists. Silverlake models two. The object auditing value on a system library was `*NOTAVL`, Silverlake shows `*NONE`, our guess for a user object.
- **F6 on Edit Object Authority opens Add New Users:** ten rows of user (10) and authority (8) fields, F11 and F17 and F18 on it. It is modeled and grants through the normal rules.
- **F10 got no answer from the host.** The harness waited 15 seconds, saw nothing, and stopped with nothing more sent, so F11 and option 3 were never pressed and `CRTDUPOBJ`'s screen is still unseen. The scenario's job was left to time out on the host. The harness now keeps what it gathered and says which action stopped it.

## What the jobs capture taught us

The read-only `auth-jobs` scenario (2026-10-27) ran `WRKACTJOB`, `WRKSPLF` and `DSPMSG` as the test profile.

- **`WRKACTJOB` is open to a basic profile and shows everyone.** 876 active jobs, system jobs and other users', with the function each is running. Silverlake's version does the same (see docs/jobs-spool-messages.md). Its layout is matched field for field: header block, options legend, nine job rows from row 9, option field of length 2 at column 1, a 73 long command line, the F3, F5, F7, F10, F11, F12, F23, F24 keys.
- **`WRKSPLF` showed only the profile's own spool files**, one `QPJOBLOG` per past session, in `QEZJOBLOG`, with the device name in User Data. Layout and options (1 through 9) are noted for step 2.
- **`DSPMSG` opened a queue named after the display device**, with a message from `QPGMR`, delivery `*NOTIFY`, and the keys F11, F13, F16. Noted for step 3.
- The capture holds other people's job names and stays local, as every capture does.

## What the spool capture taught us

The read-only `auth-spool` scenario (2026-10-27) opened the profile's first spool file with option 5 and option 8, and backed out.

- **Display Spooled File** has a four line header (File, Page/Line, Control, Columns, Find), a ruler at row 4, sixteen lines of the file from row 5, and `F3=Exit F12=Cancel F19=Left F20=Right F24=More keys`. Silverlake's screen matches its field positions.
- **A real job log lists the commands the session ran**, each as a `*NONE Command` line with a timestamp and the program, then a `Message` line carrying the command text, and the messages they raised with ID, type and severity. This is why Silverlake files a log at sign-off and why a trainee reading someone else's is the point of the exercise.
- **Work with Spooled File Attributes** has job, user, number, creation date and time, status, output queue and library, form type, priority, copies, and a second page. Silverlake follows the first page.
- The capture holds the test profile's own job names and stays local.

## What the message captures taught us

The read-only `auth-msgs` scenario (2026-10-27) ran `DSPMSG`, `DSPMSG MSGQ(QSYSOPR)` and opened `SNDMSG`.

- **`QSYSOPR` is open to a basic profile.** Severity 99, delivery `*HOLD`, with system events naming other people's jobs and users (`Job message queue for N/USER/JOB has been wrapped`, jobs held and released, work stations ended). That is free reconnaissance and Silverlake reproduces it.
- **A user's own queue is in `QUSRSYS`, delivery `*BREAK`, severity 00,** and showed `(No messages available)` when empty. A messages from a user shows a `From` line and the text, a system event only the text. There were no input fields, since nothing needed a reply.
- **`SNDMSG` typed with no parameters got no answer in 15 seconds,** so the prompt screen was not captured, the harness stopped and sent nothing more, and the job was left to time out on the host. Silverlake's SNDMSG asks for TOUSR or TOMSGQ in a message line instead.
- The capture holds other people's job and user names and stays local.

## What the DSPJOB capture taught us

- **Colors are not what Silverlake had been drawing.** On the real display the labels and the values and the numbered options are all green, the title and the `More...` marker are white, and the prompt, `Select one of the following:`, `Press Enter to continue.` and the key lines are blue. Silverlake's older screens drew values and options white, and list rows turquoise. Every screen with a capture now follows the real colors, and `tests/test_screen_colors.py` holds the rules. Turquoise is left only on the sign-on screen's own information block, which PUB400 really draws that way. The screens with no capture (user profile list and display, the main menu, command entry) got the same rules by analogy, so they are unconfirmed. After the pass, a `compare` against every capture shows about a dozen color differences, and they are not color bugs: the replay was on a different screen at that step (an object the real system has and the seed does not), so the same position holds something else.
- **Display Job has no command line.** It asks `Selection` with a two character field at row 20, column 6, where Work with Job has `Selection or command` and a 153 wide line.
- **The attribute pages end with `Press Enter to continue.`** and offer F3, F5, F12 and F16 (back to the job menu). Status and definition show `More...`, run does not.

## What the second job capture and the output queue capture taught us

Taken from PUB400 on 2026-10-27, read only, the test profile's own job and two output queues.

- **A decoder bug.** The host's Display Open Files record begins with a Start of Header that carries seven bytes after its length byte. The decoder skipped the length plus one and read the last header byte as an order, which failed on a bad address. It skips the length plus two now (web3270's client always did), with a test. No earlier capture had a header.
- **The menus have a second page.** Display Job continues with 17 to 22 and 30 ("All of the above"), ending in `Bottom`. Work with Job has the same list with 19, 20 and 21 reading "Work with" and 40, 41, 42 (change, end, hold the job) added, and it ends in `More...`, so there is a third page nobody has seen.
- **Page two of the status page** holds two rows (controlled end requested, system). **Page two of the definition page** holds the printer device, default output queue and library, the job date, formats and separators, and the clock with the day of the week.
- **Call stack, locks, open files, overrides, commitment control** all have their own displays. A job at the main menu has a five program stack, holds a shared read lock on each library on its list, a no-update lock on its menu and display file, has two files open, and no overrides or commitment definitions. The locks, call stack and open files displays take options and keys we do not build (5 and 8 on locks, F10 and F11).
- **A run of the bare `WRKOUTQ` did not answer in 15 seconds.** It lists every output queue on the host, and on a shared system that is load nobody asked for. The scenario no longer runs it, names one queue each time, and the harness now keeps what it gathered when a record cannot be read, the same as when nothing answers.
- **Work with Output Queue** is a list with a status line (queue, library, status), options 1 to 9 on two rows, columns File, User, User Data, Sts, Pages, Copies, Form Type and Pty, a parameter line, and keys F3, F11 (view 2), F12, F20 (writers), F22 (printers), F24. A queue that does not exist answers `Output queue NOQUEUE in library SLNOSUCH not found.` on the menu's message line.
- **The recon point.** A basic profile listing the job log queue sees every file in it, with the user and the job name of each, not only its own. The queue's display rule hides the contents, not the list. WRKOUTQ in Silverlake has to show the same thing.

## What the third and fourth job captures taught us

Taken from PUB400 on 2026-10-27, read only, the test profile's own job. `auth-dspjob3` and `auth-dspjob4` never press option 30 ("all of the above", which may print), never option 4, and never Enter on a prompt.

- **F11 on the locks display does not open a screen, it flips the view.** The first run assumed it opened another display and sent an F12 to come back, which went straight past the locks list to the menu. Every check in that run was gated on the screen it expected, so the run stopped there instead of pressing anything unplanned. The same flip happens on the call stack (activation group view) and on Display Open Files (I/O details). The scenario was split in two so one surprise only costs what comes after it.
- **Options 17 to 22 all answer on a job at the main menu.** Communications status and media library attributes are empty lists, there is one thread and no mutexes, the job holds four activation groups, and its environment variables are PASE's (the long names and values are cut and marked with a `>` in the next column).
- **Work with Job has a third page**, 43 (release job) and 45 (work with the JVM, if active). Option 40 opens the Change Job prompt, with job priority shown as `*SAME` and output priority as the job's own value.
- **The local compare is noisy** when a scenario's step order differs from the local flow, since it pairs screens by position. A direct comparison of each screen's text positions against the matching capture screen is the quicker check, and left only the deliberately omitted keys, the job name and thread id.

## What the program call capture taught us

Taken from PUB400 on 2026-10-27, read only (`auth-callpgm`). It runs `DSPPGM` on the system's own QCMDEXC and three `CALL`s that change nothing, and compiles nothing, since that would be a write.

- **DSPPGM is two pages.** The first holds creation date and time, type of program, source file and member, observable information, **user profile** and **use adopted authority**, fix decimal data and teraspace. The system's QCMDEXC is `*USER` with adopted authority `*YES`, OPM, owned by QSYS.
- **A CALL on a missing program** says "Program NOSUCHPGM in library *LIBL not found." (second level text follows).
- **QCMDEXC prints nothing when the command works**, says "Command NOSUCHCMD in library *LIBL not found." for an unknown one, and "A matching parenthesis not found." when the length parameter cuts the command in the middle of its parentheses.

## What the development capture taught us

Taken from PUB400 on 2026-10-27, read only (`auth-pdm`). It opens the PDM menu, runs `WRKMBRPDM`, `WRKOBJPDM` and `STRSEU` and one `CRTBNDRPG` against a library that does not exist (all refused before anything is made or locked), and opens the prompts of `CRTBNDRPG`, `CRTPF`, `CRTDSPF`, `CRTPRTF` and `CRTSRCPF` with F4 and leaves them with F12. Nothing is created, compiled, edited or locked.

- **The PDM menu** (STRPDM) has four lines: 1 Work with libraries, 2 Work with objects, 3 Work with members, 9 Work with user-defined options, with F4, F9, F10 (command entry), F12 and F18 (change defaults).
- **Refusals.** `WRKMBRPDM` on a library that is not there says "Library NOSUCH was not found." On QGPL/QCLSRC it says "You do not have authority to file QCLSRC in QGPL." (the file was either not readable or not there, and the message does not say which). `WRKOBJPDM LIB(QGPL)` said "PDM cannot complete the display list." `STRSEU` on a missing library says "Library NOSUCH not found."
- **CRTBNDRPG on a missing member** says "Unable to open member NOPGM of file QRPGLESRC in library NOSUCH." even when the library is the thing that is missing.
- **The prompts.** CRTBNDRPG: PGM (*CTLSPEC, library *CURLIB), SRCFILE (QRPGLESRC, *LIBL), SRCMBR (*PGM), SRCSTMF, GENLVL 10, TEXT (*SRCMBRTXT), DFTACTGRP (*YES), then F10 for more. CRTPF: FILE, SRCFILE QDDSSRC, SRCMBR *FILE, RCDLEN, GENLVL 20, FLAG 0, FILETYPE *DATA, MBR *FILE, TEXT. CRTDSPF and CRTPRTF both showed SRCFILE `*NONE` where IBM's default is QDDSSRC (a local default on that host). CRTSRCPF: FILE, RCDLEN 92, MBR *NONE, TEXT *BLANK. Enter with FILE empty says "Parameter FILE required." and a roll key at the end says "Already at bottom of area."

## PASE terminal (`auth-qp2term`), tried 2026-10-27, nothing captured

`CALL PGM(QP2TERM)` on PUB400 never produced a screen the client could read. The first run died on `ESC 02` (Save Screen), which the decoder now handles. The next two runs, at 15 and then 45 seconds per screen (`--timeout`), got no record at all after the call. So the guess that the start was only slow is wrong, and no further runs were made: it is a shared host. Likely causes, none confirmed: PUB400 steers PASE users to SSH on port 2222 and blocks the 5250 route, or the terminal waits on something this client does not send. The PASE items in docs/pase.md stay unverified.

## What the F4 prompt captures taught us

Nine read-only runs on 2026-10-29 (`auth-prompts-a` to `auth-prompts-h`, then `auth-prompts-pages`) typed 67 command names bare, pressed F4, rolled the prompt up once and backed out with F12. Enter is never pressed on a prompt, so nothing runs, and a test holds that. Each run signs off at the end.

- **66 of the 67 opened a prompt.** `CRTLIB` did not: the host answered on the menu with `Not authorized to command CRTLIB in library *LIBL.` and no prompt, because the test profile may not use it. A command you may not use is refused at F4, not on Enter.
- **`CHGPWD` has nothing to prompt for.** It draws its title and keys and says `No parameters to show; press Enter to run, F3 to exit.`
- **Roll Up checks the required name first.** On `HLDSPLF` and `OVRDBF` with the first field empty, Roll Up answered `Parameter FILE required.` and stayed put. With a made-up name typed (never run, never Entered) it pages: `HLDSPLF` and `WRKSPLF` have two pages, `OVRDBF` three.
- **29 prompts offer F10=Additional parameters.** Captured by `auth-f10-a` to `auth-f10-c`, then `auth-f10-pages-a/b`, `auth-f10-deep` and `auth-f10-deep2` for the pages a single Roll Up did not reach. F10 needs no check first; the view repeats the prompt and adds an `Additional Parameters` line and the rest, and its key lines lack F10. Roll Up then checks required names as before, so the later pages needed a made-up name typed in (never Enter). Two surprises: CHGUSRPRF and CHGSPLFA look up the current values of what they are given, so a made-up name stopped at `Current values could not be ...` (CHGUSRPRF got the signed-on profile, CHGSPLFA has no page past the first), and a change command's defaults are the current values of the profile it was run as (name, library, text, printer), which the extractor now swaps for tokens before they reach the table. CRTPRTF turned out to have eleven pages, CHGJOB four.
- **A notice can sit in front of the first screen.** Signed on at the same time as another session of the same profile, the host shows `Message queue X is allocated to another job. Press Enter to continue.` with no input field. The harness now presses Enter once, and only on a screen like that. Before it did, a run would stop there and leave its job signed on.
- **A screen with no field stops a run and keeps what it gathered.** The harness used to throw its captures away on that, and now it saves them and says which action stopped it, the way it already did when the host went quiet.

The layouts are in `screens/promptspecs.py`, generated from the captures by `python -m silverlake.oracle.promptspec captures/pub400/auth-prompts-*.json`. Change the generator, not the table.

Those scenarios are `auth-f10-a` to `auth-f10-c`: type the bare command, F4, F10, Roll Up once, then F12 out. Nothing is typed into a prompt and Enter is never pressed, and a test checks the list against the prompts that show the F10 key. The follow ups type only a made-up name (`SLPLACE`) or the signed-on profile before a Roll Up. Regenerate the table with `python -m silverlake.oracle.promptspec captures/pub400/auth-pdm.json captures/pub400/auth-prompts-*.json captures/pub400/auth-f10-*.json`.

`auth-f13` is written for the prompt keys still answered with "not built" (F13, F24) and for Roll Down at the top of a prompt: CRTPF, CHGJOB, CHGPWD, DSPMSG, WRKSPLF and CRTUSRPRF, each F4, Roll Down, F24, F13, Roll Up, then F12 out. Never Enter, nothing typed but the bare name. Not run yet.

## Still open

- **A stock sign-on capture.** The photo settled positions, but a real capture would confirm the title and label columns and the colors. The password field length is also unsettled: stock is 10, PUB400 shows 128 at its password level.
- **Authenticated screens.** The harness can now sign on as a test profile (see above). What it has not done yet is run against a real host, so the post-sign-on screens are still unseen.
- **The Query path against a real host.** The client answers a 5250 Query, and a test proves it, but PUB400's sign-on never sent one. It will appear after sign-on.
- **Orders not yet seen on real streams.** Erase To Address attribute-count handling is unverified.
- **Message text for IDs.** Phase 3 gives Silverlake real message IDs to compare.
