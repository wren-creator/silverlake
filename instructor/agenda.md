# Silverlake 101: instructor agenda

Two days, about six contact hours each, or four half days for a part time cohort. Every block is a short brief, hands on, and a debrief. Keep the talking under a third of each block. Students attack as STUDENT unless a lesson says otherwise.

## Day 1: the attack half (range in its vulnerable state)

| Time | Block | Notes |
|---|---|---|
| 0:00 | Welcome, what IBM i is, the ethics line | Session 1. Get verbal buy in on the authorised use rule. This is a simulator, so say out loud that what works here is practice for systems they are allowed to test. |
| 0:20 | Bring the range up and prove containment | `./setup.sh && ./start.sh && ./status.sh`. Everyone connects a 5250 client to 127.0.0.1 and signs on as STUDENT. |
| 0:45 | Session 1: sign-on, objects, authority, the library list | Students map what STUDENT can see by hand: `WRKOBJ`, `DSPOBJAUT`, `DSPLIBL`. Collect the notes. |
| 1:30 | Break | |
| 1:45 | Session 2: credentials and recon | Everyone signs on as QSECOFR with the password QSECOFR and reads the job log. |
| 2:45 | Lunch | |
| 3:30 | Session 3: authority and data exposure | Pair them. One drives, one reads the screen and writes down what the exploit needed. Swap. |
| 4:45 | Break | |
| 5:00 | Session 4: programs and the library list | RUNCMD is the "aha". Make sure everyone sees a profile with `*ALLOBJ` appear from an account that could not make one. |
| 5:45 | Day 1 debrief: what did any of that actually require? | The answer is "a password anyone could guess" and "an authority nobody meant to give". Set up Day 2. |

## Day 2: the defense half

| Time | Block | Notes |
|---|---|---|
| 0:00 | Recap, then `./scenario.sh mode secure` | It restarts the server and signs everyone off. Say so first. |
| 0:20 | Session 5: fix and re-run | Students re-run each Day 1 exploit and record exactly where it dies. They fix one lesson at a time with `./scenario.sh set <id> secure` and `./scenario.sh reset <id>` to go back. |
| 2:30 | Lunch | |
| 3:15 | Session 5 continued: the write-up | Hand out `rubric.md`. Start it here, finish as homework. |
| 4:30 | Tabletop: "an auditor finds RUNCMD in production" | No keyboards. Who owns it, who can call it, what would you check on a real system first? |
| 5:30 | Flag scoring, close | `./check-flags.sh submission.txt` on each student's machine. |

## Materials checklist

- One machine per student with Python 3.12 or newer, a 5250 client (`tn5250`, `x3270` in 5250 mode, or a web terminal) and the repo cloned.
- Printed `docs/scenarios-trainee.md` and `instructor/rubric.md`.
- The instructor keeps `docs/scenarios.md` and the output of `./check-flags.sh --show`.
