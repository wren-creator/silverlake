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

Options 2, 3, 4, 5, 6, 7, 8 and 13 are laid out as on the real display and say "not available yet". F7, F10, F11, F23 and F24 are on the screen and do nothing yet. The elapsed time, CPU % and per job CPU are always zero.

## Step 2: spool files (built)

`WRKSPLF`, `DSPSPLF` and `DLTSPLF`, with the Work with All Spooled Files, Display Spooled File and Work with Spooled File Attributes displays laid out like the ones captured from PUB400. Options 5 (display) and 8 (attributes) work from the list. 1, 2, 3, 4, 6, 7 and 9 are drawn and say "not available yet". F19, F20, Find and Control on the display are not built. `WRKOUTQ` and the page-two attributes are not built, and their screens were not captured.

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

**Not modeled.** Delivery and severity are shown and not acted on, so nothing interrupts a session. Inquiry messages and replies, `*ALLACT` and `*REQUESTER` as recipients, the work station queue, `RMVMSG` (the page says compiled CL only), F11 (remove one message, needs a cursor on a message), `WRKMSGQ`, and `CRTMSGQ`/`CHGMSGQ`. The real `*WRKUSR` default showed a device queue in one capture and the user queue in another, so Silverlake always shows the user queue.

## Later

`ENDJOB`, `HLDJOB`, `CHGJOB`, `WRKJOB`, `DSPJOBLOG`, gated on `*JOBCTL` and on owning the job. The confirm screens for these are not captured, and ending a job on a shared system is not something the oracle will do, so they are built from IBM's pages when we get there.
