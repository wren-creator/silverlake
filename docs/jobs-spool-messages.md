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

## Step 2: spool files (next)

WRKSPLF, DSPSPLF, option 8 from WRKACTJOB. Every job gets a `QPJOBLOG` spool file (the real capture shows one per past session, in `QEZJOBLOG`). The real `WRKSPLF` for a basic user listed only that user's own files. The rules to model, each flagged read or inferred in access-model.md when built: own files visible, other users' files need `*SPLCTL` (all) or `*JOBCTL` (job logs and files of controllable jobs) plus the output queue rules, and `*SPLCTL` and `*JOBCTL` stay separate.

## Step 3: messages

DSPMSG, SNDMSG, and a queue per user and per device (the real capture opened one named after the display device, from `QPGMR`, delivery `*NOTIFY`). Reading a queue needs `*USE`, sending needs `*ADD`, and a world writable queue can be spoofed into. `QSYSOPR` is the interesting one.

## Later

`ENDJOB`, `HLDJOB`, `CHGJOB`, `WRKJOB`, `DSPJOBLOG`, gated on `*JOBCTL` and on owning the job. The confirm screens for these are not captured, and ending a job on a shared system is not something the oracle will do, so they are built from IBM's pages when we get there.
