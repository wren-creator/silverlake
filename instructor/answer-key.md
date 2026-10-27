# Silverlake 101: instructor answer key

The full per lesson key is `docs/scenarios.md`, which is generated from the scenario files and cannot drift from the range. `./check-flags.sh --show` prints every flag and the secure-state passwords for the machine in front of you. This file is the teaching notes around them.

## The things students get wrong

- **Lessons tangle in secure mode.** `default-passwords` secure rotates the OPERATOR and DEVELOPER passwords, so later exploits that sign on as them need the new passwords from `--show`. Fix one lesson at a time and `reset` between them.
- **A flag is not the lesson.** The text flags prove a student reached the data. Ask what authority made it reachable. A student who found the vault flag but cannot say "SVCACCT holds `*ALLOBJ`" got lucky.
- **Adopted authority is not magic.** RUNCMD, PAYADJ and EMPDIR all adopt their owner. The question each time is whose authority runs, and what the program lets the caller choose (a command, a salary, a file name).
- **QTEMP first.** The library list puts QTEMP ahead of a library added with `ADDLIBLE ... *LAST`. That is why the PAYRUN hijack works, and why the fix is to name the library on the call.

## Session by session emphasis

| Session | The point to land |
|---|---|
| 1 | On IBM i everything is an object with an owner and an authority, and a library list decides what a bare name means. |
| 2 | Credentials and recon: guessable passwords, service accounts holding more than they need, a message queue everyone can read. No exploits, just looking. |
| 3 | Data leaves through ordinary features: a menu option that opens command entry, a default output queue that shows data to everyone, a copy that does not carry the original's protection. |
| 4 | Programs that adopt an owner turn a caller's input into the owner's power: a command, a salary, a file override, a program found by library list order. |
| 6 (optional) | A web console and an FTP server are doors too. They check the same passwords and the same authority, so a weak password or an over trusted service account follows the attacker in. |
| 5 | Every fix was one setting or one line, none exotic. The gap between how little the attack needed and how ordinary the fix was is the course. |

## Lesson notes

| Lesson | Mechanism in one line | Fix in one line |
|---|---|---|
| default-passwords | password equals profile name, rules off | rotate, `QPWDMINLEN` 8, `QPWDRQDDGT` 1 |
| overprivileged-accounts | service profiles hold `*ALLOBJ` and `*SECADM` | remove what they do not need |
| qsysopr-recon | operator queue is `*CHANGE` to public | public `*EXCLUDE`, no secrets in messages |
| clerk-menu-escape | menu option 9 calls `QCMD` | take the option off the menu |
| qprint-report-leak | default queue shows data to anyone | `DSPDTA(*OWNER)` |
| regrpt-outq | printer file sends the register to QPRINT | send it to a queue with restricted authority |
| cpyf-escape | the copy is public, in a library that hands that out | library `CRTAUT(*EXCLUDE)` |
| runcmd-qcmdexc | adopts QSECOFR, runs any command | no adoption of a powerful owner, allow list |
| payadj-overadopt | adopts an owner with authority on the payroll file | `USRPRF(*USER)`, take public off the program |
| empdir-override | adopted open honours the caller's override | owner who holds nothing on PAYROLL |
| payrun-qtemp | calls a program with no library | call it with its library |
| ftp-limited-bypass | limited capability is a 5250 rule, FTP ignores it (needs `--services`) | register a request exit program, require TLS |
| httpadmin-ssi-injection | the web console evaluates exec directives in a description, as QTMHHTTP (needs `--services`) | install the console fix, which escapes the field |

## Verification caveat

The exploit mechanics match what is documented about IBM i, but they have not all been confirmed on real hardware. `ROADMAP.md` has the checklist. Tell students that, and that PUB400 and similar public systems are not places to try these.
