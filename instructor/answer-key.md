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
| hostsvr-recon | the sign-on server reports QPWDLVL (0, case does not matter) before sign-on (needs `--services`) | QPWDLVL 2 or 3, limit who reaches the host servers |
| ftp-limited-bypass | limited capability is a 5250 rule, FTP ignores it (needs `--services`) | register a request exit program, require TLS |
| ftp-console-cleartext | FTP on 2121 and the console on 2001 take a password in clear text beside their TLS ports (needs `--services`); the answer is `ftp,httpadmin` | require TLS (FTP 534 before `AUTH TLS`, console 403 on 2001), then close the clear ports |
| httpadmin-ssi-injection | the web console evaluates exec directives in a description, as QTMHHTTP (needs `--services`) | install the console fix, which escapes the field |
| pase-profile-plant | `/QOpenSys/etc/profile` is world writable and every login runs it (the victim is a second session as QSECOFR) | profile owned by the system, read only for the rest |
| pase-datarea-secret | `APPLIB/PAYXFER` is a data area with public `*USE` and the transfer key in its value; from a shell `qsh -c 'datarea -r /QSYS.LIB/APPLIB.LIB/PAYXFER.DTAARA'` prints it (bsh alone says `cannot execute`) | take public authority off the area (`*EXCLUDE`), keep keys out of data areas, rotate the key |
| pase-find-writable | `backup.sh`, `jobs.conf` and `spool` under `/QOpenSys/var/ops` are writable by everyone; `find /QOpenSys/var/ops -perm -002` lists them (the answer is those three paths, sorted) | take the write bit off for others, umask 022, audit with find on a schedule |
| pase-path-hijack | `/tmp/opsbin` is world writable and first on the operator's PATH, so a planted `id` runs as OPERATOR (the victim is a second session as OPERATOR) | no writable directory on PATH, `/tmp/opsbin` read only |
| ssh-strictmodes | `authorized_keys` is world writable and `StrictModes no`, so a planted key logs in as DEVELOPER (needs `--services` and asyncssh) | `StrictModes yes`, key files writable only by their owner |
| ssh-limited-bypass | limited capability is a 5250 rule, ssh gives CLERK a shell, SQL and CL (needs `--services` and asyncssh) | `DenyUsers CLERK` or an `AllowUsers` list |

## Verification caveat

The exploit mechanics match what is documented about IBM i, but they have not all been confirmed on real hardware. `ROADMAP.md` has the checklist. Tell students that, and that PUB400 and similar public systems are not places to try these.
