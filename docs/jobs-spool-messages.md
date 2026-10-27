# Jobs, spool files and messages

Phase 3c-3c. The smallest model that teaches something, built in three steps.

## The model

A job is a row, not a process: name, user, six digit number, type, subsystem, status, function. Nothing is scheduled and no CPU is used. The table lives in memory, so a restart gives the seeded system jobs and no sessions.

- **Live sessions are interactive jobs**, named after the display device (as on a real system), in subsystem `QINTER`, ended when the session signs off or the connection drops.
- **A seeded set of system jobs** stands beside them (`QSYSSCD`, `QTCPIP`, `QZDASOINIT` and the like) in the shape of a real system's. The names and numbers are ours, not copied from a capture.
- **Spool files and message queues** (steps 2 and 3) will be secured objects with an owner and authority, so `GRTOBJAUT` and `RVKOBJAUT` work on them like on anything else, and a default of public `*CHANGE` on a queue is a misconfiguration a trainee can find and exploit.

Not modeled on purpose: CPU percentages, thread states, batch queues, job schedule entries, anything about time passing inside a job.

## Step 1: WRKACTJOB (built)

Laid out like the real display captured from PUB400 (title, CPU and elapsed header, option legend, `Opt Subsystem/Job User Type CPU % Function Status`, `Parameters or command`, keys). `SBS(name)` narrows the list, a missing subsystem is refused.

What the capture settled, and what is the point of the range: **a basic profile lists every active job on the system, other people's included.** Users, job names and what each job is running (the function column, such as `PGM-ARCPSTDA` or `CMD-STRQSH`) are visible without `*JOBCTL`. That is quiet reconnaissance, and it is on purpose. Your own job shows `CMD-WRKACTJOB` and `RUN` while the list is drawn.

Options 2, 3, 4, 6 and 8 work (see Job control below), and 5, 7 and 13 are laid out as on the real display and say "not available yet". F7, F10, F11, F23 and F24 are on the screen and do nothing yet. The elapsed time, CPU % and per job CPU are always zero.

## Step 2: spool files (built)

`WRKSPLF`, `DSPSPLF` and `DLTSPLF`, with the Work with All Spooled Files, Display Spooled File and Work with Spooled File Attributes displays laid out like the ones captured from PUB400. Options 5 (display), 8 (attributes), 3 (hold) and 6 (release) work from the list. 3 and 6 run `HLDSPLF` and `RLSSPLF`, which follow the same control rule as delete (inferred, those pages were not read for authority). 4 deletes at once (the real confirm was never captured), 7 says there are no messages, 1, 2 and 9 open prompts described in the section below. `WRKSPLF` takes `JOB(number/user/name)` when `SELECT` names `*ALL` users, and an empty result says "No spooled files found." on the message line. F19, F20, Find and Control on the display are not built. `WRKOUTQ` and the page-two attributes are not built, and their screens were not captured.

**The model.** A spool file belongs to a job (number, user, name), has a file number within it, and sits on an output queue. Queues are `*OUTQ` objects in the object table, so `GRTOBJAUT`, `RVKOBJAUT` and `DSPOBJAUT` work on them. Spool files persist in the state file (a `spool` table), and job numbers do not restart under a saved job log. Two queues are seeded: `QUSRSYS/QEZJOBLOG` for job logs and `QGPL/QPRINT`.

**Job logs.** Every session files a `QPJOBLOG` on `QEZJOBLOG` when it ends, a dropped connection included, holding each command typed and the message it raised, in the layout of the captured log. A real log contained the commands the test session ran, which is why a job log is worth reading. A `PASSWORD` parameter is logged as asterisks, our choice.

**Who sees what.** Each queue has `DSPDTA`, `OPRCTL` and `AUTCHK` settings (from CRTOUTQ's page, parts of which only came through as a summary).

| Queue setting | Effect |
|---|---|
| `DSPDTA(*NO)`, the command default | with authority to the queue you display only your own files unless you hold a special authority |
| `DSPDTA(*YES)` | anyone who may read the queue may display any file on it |
| `DSPDTA(*OWNER)` | the file's owner, `*SPLCTL`, and (the page's example) the queue's owner |
| `OPRCTL(*YES)`, the default | `*JOBCTL` controls the queue's files |

`*SPLCTL` always controls and displays. Inferred, because no page said it: listing other users' entries needs `*READ` to the queue, deleting follows the same control rule as holding, and a file's owner can always display, hold and delete it. A refusal is `CPF3492`, "Not authorized to spooled file."

**What the range seeds.** `QPRINT` is `DSPDTA(*YES)` with public `*USE`, and holds a payroll register: the classic mistake, readable by a profile with no special authority. `QEZJOBLOG` is `DSPDTA(*OWNER)`, and holds an old `QSECOFR` job log with admin commands in it, readable by `*SPLCTL` and `*JOBCTL` profiles (SPOOLMAN, JOBMAN) and nobody else. Both are our picks.

## Step 3: message queues (built)

`DSPMSG`, `SNDMSG` and `CLRMSGQ`, with the Display Messages screen laid out from two captures (a user queue and `QSYSOPR`). A queue is a `*MSGQ` object, so `GRTOBJAUT`, `RVKOBJAUT` and `DSPOBJAUT` work on it, its messages live in the object's data and are saved with the state, and `QSYSOPR` is seeded. Every profile has a queue named after it in `QUSRSYS`, made the first time anyone reaches for it and removed with the profile.

| Command | Needs (IBM's page) |
|---|---|
| `SNDMSG` | `*OBJOPR` and `*ADD` to the queue, `*USE` to the queue and its library |
| `CLRMSGQ` (and `F13` and `F16` on the display) | `*CHANGE` to the queue, `*USE` to the library |
| `DSPMSG` | the page has no authority section, only `CPF2408`; `*USE` is inferred and fits the capture |

**What the capture showed, and what the range seeds.** A basic profile on PUB400 read `QSYSOPR` and learned other people's job names and users from it. Silverlake seeds `QSYSOPR` public `*CHANGE` (our pick, matching what was seen) with a few events and a note from QSECOFR, so a plain profile reads it. User queues take the library's create authority, as CRTMSGQ's page says, and `QUSRSYS` is public `*CHANGE` in the seed, so by default anyone can read and write anyone's queue (an inference, flagged). Revoke public authority on a queue and the plain profile gets `CPF2408`, "Not authorized to message queue X."

**CRTMSGQ, CHGMSGQ, DLTMSGQ (built).** From IBM's three pages. `CRTMSGQ` makes a `*MSGQ` object owned by the creator, delivery `*HOLD`, severity 00 (the page says those are fixed at create). `AUT` sets the public authority, and the default `*LIBCRTAUT` takes the library's, which here means the library's own public authority (inferred). The page has no restrictions section, so needing `*ADD` to the library is inferred. A name that is already there is `CPF2112`, a missing library `CPF2402`. `CHGMSGQ` changes `DLVRY`, `SEV` and `TEXT` and needs `*USE` and `*DLT` to the queue (the page says nothing about the library), refusal `CPF2408`. `MSGQ(*USRPRF)` is your own queue. `DLTMSGQ` needs `*USE`, `*OBJEXIST` and `*DLT` to the queue and `*EXECUTE` to the library, and QSYSOPR cannot be deleted. Worth noticing: `*CHANGE` has no `*OBJEXIST`, so the default public authority lets anyone write to a queue and change it, but not delete it. WRKOBJ option 4 on a queue runs `DLTMSGQ`.

**Not modeled.** Delivery and severity are shown and not acted on, so nothing interrupts a session. Inquiry messages and replies, `*ALLACT` and `*REQUESTER` as recipients, the work station queue, `RMVMSG` (the page says compiled CL only), F11 (remove one message, needs a cursor on a message), `WRKMSGQ`, and the rest of `CHGMSGQ` (break program, `*DFT` delivery, locks). The real `*WRKUSR` default showed a device queue in one capture and the user queue in another, so Silverlake always shows the user queue.

## Job control (built)

`HLDJOB`, `RLSJOB`, `ENDJOB` and `CHGJOB`, behind `WRKACTJOB` options 3, 6, 4 and 2. The rules are quoted from IBM's pages: the issuer must run under the job's own user profile or hold `*JOBCTL`, and `ENDJOB` enforces that "even when ending the current job". `*SPLCTL` and `*ALLOBJ` on their own do nothing here, which a test pins. `CHGJOB` changes `JOBPTY`, `OUTPTY`, `RUNPTY`, `TIMESLICE`, `PURGE`, `DFTWAIT`, `CPUTIME` and `MAXTMPSTG`, with the limits the page gives.

In `CHGJOB`, `RUNPTY`, `TIMESLICE`, `PURGE`, `DFTWAIT`, `CPUTIME` and `MAXTMPSTG` need `*JOBCTL`. `JOBPTY` and `OUTPTY` do not. Values are stored and shown and change nothing, because there is no scheduler. A bad value changes nothing at all.

**Ending a session** from another session works: the ended session notices on its next key, files its job log, and lands on the sign-on screen. Ending a seeded system job removes it until the next restart (our choice). A subsystem monitor is refused as "not valid job type" (inferred). Option 4 runs `ENDJOB` straight away: the real display asks first, and that screen was not captured, so Silverlake has no confirm. Option 2 opens the Change Job prompt (captured, see the leftovers section below) when nothing is typed on the command line, and runs `CHGJOB` with what is typed there otherwise, as in `JOBPTY(3)`.

Message IDs (`CPF1321`, `CPF1342`, `CPF1343`, `CPF1344`, `CPF1346`, `CPF1349`) are from the pages, with the condition for each inferred. A refused `JOBCTL`-only change uses `CPF1337`, which came from a summary of CHGJOB's page.

## DSPJOBLOG and WRKJOB (built)

Both laid out from a read-only capture of the profile's own job on PUB400. `DSPJOBLOG` shows the **live** log: each command as `3>> COMMAND` and the message it raised as plain text, with the command itself last, as the real one shows. Roll, F5, F17 and F18 work, F10 (detailed messages) says it is not built. A live session's log is the same list its job log is written from at sign-off, so `DSPJOBLOG JOB(n/u/name)` reads another session's commands as they happen.

`WRKJOB` is the Work with Job menu (ten options, `Selection or command` line, as captured). Option 4 lists that job's spool files, 10 is `DSPJOBLOG`, 13 is the library list for your own job. Options 1, 2 and 3 open the three attribute pages below. The other options are described in the sections below. `WRKACTJOB` option 5 opens it.

Rules, quoted from IBM's pages: `DSPJOBLOG` needs `*JOBCTL` or the job's own user name, and "to display a job log for a job that has all object (*ALLOBJ) special authority, you must have *ALLOBJ" (or a function usage entry that is not modeled). So JOBMAN reads a plain user's log but not QSECOFR's, and LEGACY (`*ALLOBJ` and `*JOBCTL`) reads both. The refusal is `CPF2441`, "Not authorized to display job log." `WRKJOB` needs the same user or `*JOBCTL`, refused as `CPF1071`. `*SPLCTL` is mentioned on neither page. A seeded system job has no log (`CPF2523`) and a job that has ended says `CPF2443`, because its log is a spool file by then (inferred, read it with `DSPSPLF`).

`DSPJOB` is the same job seen through the Display Job menu, captured the same way. It differs from Work with Job in three small ways: option 4 reads "Display spooled files" and 12 "Display locks", the selection is a two character field with no command line, and the keys are only F3 and F12. Same rules as `WRKJOB`, same options built, same refusal (`CPF1071`, which is the WRKJOB page's ID and is used here without having seen DSPJOB's own).

The three attribute pages, from the capture of the profile's own job, are shared by both menus. **Status** (job, user and number, status, user identity, entered and started date and time, subsystem, pool, type, special environment, return code), **definition** (job description and library, priorities, end severity, message logging, job log output) and **run** (run priority, time slice, purge, default wait, CPU and storage limits, threads). The run page shows what `CHGJOB` set, so a trainee can see their change land. F5 redraws, F16 goes back to the job menu, Enter and F12 go back one level. Status and definition have a second page that is not built. Nothing is measured, so CPU time and storage used are small made up numbers, the pool id is a pick (2 for an interactive job, 1 otherwise), the type of job is only seen as `INTER` (batch jobs show `BATCH`, the other types show their code), and an interactive job's description is named after its user, as it was in the capture, with `QDFTJOBD` for the rest.

F12 on a list opened from another screen now goes back one level instead of straight to the menu. F3 still leaves everything.

## The rest of the job screens (built)

From a second read-only capture of the profile's own job. **Page two of both menus** (Roll Up and Roll Down): Display Job has options 17 to 22 and 30, Work with Job has the same with 19 to 21 as "Work with" plus 40, 41 and 42. 41 runs `ENDJOB` and 42 runs `HLDJOB` on the job, under the same rules as the commands. 40 (change job) and options 17 to 22 and 30 say they are not available, and Work with Job's third page is not built.

**Page two of the status and definition pages**, and the detail displays behind options **11** (call stack), **12** (locks, titled Work with Job Locks from Work with Job), **14** (open files), **15** (file overrides) and **16** (commitment control). Silverlake knows what a session holds, so the locks are real: every library on the job's library list shared read, the menu it is on and the display file shared no update. The call stack is the captured five programs for an interactive job (a command line or another menu is assumed to look the same), open files are the display file and its companion, and no job has overrides or commitment definitions because nothing here can start them. A system job has nothing to show. Same rule as the menu: whoever may open DSPJOB on a job may open these.

Left out on purpose, because each is a feature and not a position: the option column on the locks display (5 and 8), F10 and F11 there, F11 and F22 on the call stack, the I/O details on open files. Drawing them would be dead keys.

## WRKOUTQ (built)

Work with Output Queue, laid out from two PUB400 captures (the default printer queue and the job log queue): queue, library and status on row 2, the nine options on two rows, nine files from row 9 (file, user, user data, status, pages, copies, form type, priority), and a parameter line. `WRKOUTQ OUTQ(LIB/NAME)` or a name found on the library list. Options 3, 5, 6 and 8 work as they do on Work with All Spooled Files (hold, display, release, attributes), 1, 2, 4, 7 and 9 work as on Work with All Spooled Files, and F12 from a displayed file comes back to the queue. Bare `WRKOUTQ` (the real default is every queue on the host) says it is not built: no capture of it exists, because on a shared host it did not answer in 15 seconds.

The rule worth teaching, from the capture: **a profile that may read the queue sees every file on it, with the owner and the job name, whatever DSPDTA says.** The job log queue is DSPDTA(*OWNER), and a basic profile still listed other people's job logs by name. The setting hides the contents (option 5 on someone else's log is refused), not the list. Reading the queue needs *READ to it and *EXECUTE to its library, which is inferred, not read on the page. A queue or library that is not there gets the same message, `Output queue NOQUEUE in library SLNOSUCH not found.`, as captured, so nobody can tell which was missing. Not drawn, because they are not built: F11 (view 2), F20 (writers), F22 (printers) and F24.

## CRTOUTQ and DLTOUTQ (built)

Built from IBM's two pages, and the CRTOUTQ page has no Restrictions section, so the rules are thin and say so. `CRTOUTQ OUTQ(lib/name)` takes TEXT, DSPDTA (`*NO`, `*YES`, `*OWNER`), OPRCTL, AUTCHK and AUT, and accepts and ignores the printer and remote parameters. The creator owns the queue, and **AUT defaults to `*USE`, not the library's create authority**, which is the page's default and differs from CRTMSGQ. A queue in QTEMP is refused (`CPF3352`), a duplicate is `CPF3353`, a missing library `CPF2402`. Needing `*ADD` to the library is inferred, as for CRTMSGQ.

`DLTOUTQ OUTQ(lib/name)` follows the page's restrictions: the queue cannot hold entries ("printed, deleted, or moved to a different output queue"), and cannot be one the system made for a printer. The page names no authority, so the general rule stands: `*OBJEXIST` on the queue and `*EXECUTE` on the library. That is the same lesson as the message queue: `*USE` and even `*CHANGE` have no `*OBJEXIST`, so only the owner can delete a queue made with the defaults. A queue with entries is refused with `CPF3360` (the page does not say which message), and QPRINT and QEZJOBLOG are refused with `CPF3469` as if the system made them (inferred). WRKOBJ option 4 on a queue runs DLTOUTQ. Not built: generic names and `*ALL` on DLTOUTQ, writers (so no "in use by a writer"), SEQ, MAXPAGES and the remote printing parameters.

## The job screen leftovers (built)

From two more read-only captures of the profile's own job (`auth-dspjob3` and `auth-dspjob4`, which never press option 30, 4, or Enter on a prompt). Options 17 to 22 on Display Job and Work with Job open communications status, activation groups, mutexes, threads, media library attributes and environment variables, in the captured layout. Communications and media libraries are always empty. There is one thread per job (an id of our own in the captured eight digit form), no mutexes, the four captured activation groups, and the captured environment variables, which are fixed until there is a PASE. A job that is not interactive gets empty lists. Work with Job words options 19 and 20 as "Work with ..." with the extra options listed on the real display, which are not built, and Work with Job rolls to a third page with 43 (runs `RLSJOB`) and 45 (JVM, not built). Option 30, "all of the above", is not built: it may print to a spool file and was not captured.

**Change Job prompt** (Work with Job option 40, and Work with Active Jobs option 2 when nothing is typed on the command line). First page only: job priority, output priority, print device, output queue and library, run priority. Enter runs `CHGJOB` with the changed JOBPTY, OUTPTY and RUNPTY, so the rules and the job log line are the command's. Print device and output queue are accepted and ignored with a message. F4, F10 (additional parameters, which would carry TIMESLICE, PURGE and the rest), F13 and F24 are not drawn.

**Keys.** F11 flips the call stack to its activation group view, Display Open Files to I/O details (the 13 and 9 counts are the captured ones, nothing counts I/O here), and the locks display to the thread view with Scope and Thread columns. The real thread view offers a third, member lock data, which is not drawn, so F11 there goes back to the first view. F10 on the locks display opens the record locks display, which is always empty because nothing opens a file for update. Not built: the option columns (5 on a lock or file, the thread options), F22 on the call stack, F11 on communications status and environment variables, F9, and the job log's F10.


The real confirm and prompt screens for `WRKACTJOB` options 2 and 4 once captured (the oracle will not end or change jobs on a shared system), `DSPJOB`, and `WRKJOB`'s other options.

## Spooled file options 1, 2, 4, 7, 9 (built)

Laid out from the `auth-splopts` capture, which opens each prompt and backs out with F12 and never presses option 4. **1** is Send Network Spooled File: Enter says "Network spooling is not modeled. Nothing was sent." **2** is Change Spooled File Attributes, first page only. Enter runs `CHGSPLFA` with the changed form type and copies, logged like any command. Printer, print sequence and restart are accepted and ignored with a message, and Roll Up says page two is not available. You need the same control rights as for hold and delete, otherwise "Not authorized to spooled file." **4** runs `DLTSPLF` straight away. **7** puts "No messages for file X number N." on the list's message line. **9** is Work with Printing Status: with no printers modeled, every file is "not associated with a started printer". Not drawn: F4, F10, F13, F24, the Opt column and options 2 and 5 on the status screen.

`CHGSPLFA FILE() JOB() SPLNBR()` takes FORMTYPE, COPIES (1 to 255), USRDTA, OUTPTY (1 to 9) and OUTQ. Moving a file needs read authority to the target queue (inferred).
