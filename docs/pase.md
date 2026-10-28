# PASE

PASE is the AIX runtime inside IBM i: a shell, `ls`, `cat`, scripts, ssh. Silverlake has a **simulated** one. No process is ever started, no host file is read, and a line that is not one of the built commands is refused. It is a Python shell over a virtual IFS, so it cannot touch the machine it runs on and `reset.sh` puts everything back exactly. This is the first slice: the IFS and a small shell. More comes in stages (see ROADMAP.md, Phase 4b).

## Using it

```
CALL PGM(QP2TERM)
```

opens the terminal. Type commands at the `$`, F3 or `exit` leaves. The top row says it is simulated.

Built commands: `pwd`, `cd`, `ls` (`-l`, `-a`), `cat`, `id`, `whoami`, `echo` (with `$VAR`), `env`, `export`, `exit`, and the writing set: `mkdir` (`-p`), `touch`, `rm` (`-r`, `-f`), `cp`, `mv`, `chmod`, `> file` and `>> file` at the end of a command, and `system 'CL command'`. Not built: pipes, input redirection, `;`, `&`, command substitution, globbing, scripts, and every other command (they answer `ksh: name: not found.`).

**Writing.** A change needs `w` and `x` on the directory it lands in, and `x` all the way down the path. A new directory is `rwx` for its owner and `r-x` for everyone, a new file `rw-` and `r--`. `chmod` takes octal (`644`; the group digit is accepted and not kept) or `u+w`, `o-r`, `a+x`; only the owner or `*ALLOBJ` may use it. `/QSYS.LIB` is never written from the shell, objects there are made with CL. Everything is saved with the store, and `reset.sh` puts it back.

**`system`.** `system 'DSPLIBL'` runs a CL command through the same dispatcher as the command line, as the signed on profile, in this process. It gets that profile's authority and nothing more, and it never reaches a host shell.

## The virtual IFS

A node is data: a directory or a stream file, with an owner, owner bits, public bits, optional private entries per profile, and (for files) text. It is kept in the store and saved with the rest of the state, from the seed in `src/silverlake/data/ifs.toml`. `/QSYS.LIB` is not stored but mapped onto the library and object store that the 5250 side uses.

Who may do what:

- `*ALLOBJ` gets `rwx` everywhere.
- The owner gets the owner bits.
- A profile with a private entry gets that.
- Everyone else gets the public bits.
- On a directory, `r` lists, `w` adds and removes, `x` searches. Every directory on the way to a node needs `x`, which is IBM's own rule for IFS paths.
- Under `/QSYS.LIB`, a library's authority gives its directory bits (`READ` is `r`, `ADD` or `UPD` is `w`, `EXECUTE` is `x`) and an object's authority gives the file bits, so a file in `APPLIB` reads in the shell exactly when `DSPPFM` would let you read it. A physical file reads as its records.

Not modeled: group bits (the long listing repeats the public bits there), authorization lists on IFS objects, and adopted authority, which IBM documents the IFS as not honoring.

## SQL: `db2`

`db2 "select name from applib.payroll where empno = 10003"` runs one SQL statement as the signed on profile over the physical files (system/sql.py). A file is named `LIB.FILE`, `LIB/FILE` or just `FILE` through the library list. SELECT, INSERT, UPDATE and DELETE are built, and so is `CALL QSYS2.QCMDEXC('CL command')`, which runs CL through the dispatcher as the same profile.

Authority is checked before anything runs: SELECT needs `*USE` on the file, INSERT `*OBJOPR` and `*ADD`, UPDATE `*OBJOPR` and `*UPD`, DELETE `*OBJOPR` and `*DLT`, with `*EXECUTE` on the library and `*ALLOBJ` passing. So a profile that may read a file reads it through SQL without going through the program that guards it (the same lesson as CPYF). A refusal is `SQL0551`, a missing file `SQL0204`, anything else the runner will not do `SQL0104`.

Under the statement is a private in-memory SQLite database made from the files it names, with SQLite's own authorizer refusing everything but those four statements on those tables, one statement at a time, a cap on value size and a cap on work. No host file or process is reachable. The dialect is SQLite's, so Db2 for i functions are not there. Not built: DDL, catalog views (`QSYS2.*`), transactions, a file named in two libraries in one statement, and STRSQL.

## Scripts, PATH and login

A name is found the way a shell finds it. A word with a slash is a path. `cd`, `pwd`, `echo`, `export` and `exit` belong to the shell. Anything else is looked for as an executable stream file in each `$PATH` directory, in order, before the simulator's own `ls`, `cat`, `id` and the rest are tried. A script is a stream file the profile has `x` on (`chmod 755`), and each line runs as that profile through this same shell, five levels deep at most. There is no interpreter: `#!` lines are only comments.

`CALL PGM(QP2TERM)` is a login. The shell reads `/QOpenSys/etc/profile`, then `~/.profile`, as the profile that signed on, and shows what they print. `NAME=value` sets a variable.

That is what makes two seeded weaknesses real. Both are lessons in group E (docs/scenarios.md):

- **pase-profile-plant.** `/QOpenSys/etc/profile` is writable by everyone. Whoever logs in next runs what was appended, with their own authority.
- **pase-path-hijack.** OPERATOR's `.profile` puts `/tmp/opsbin` first on `PATH` and runs `id`. `/tmp/opsbin` is writable by everyone, so a planted `id` runs as OPERATOR.

In both, the victim is a second session: the trainee signs on as QSECOFR or OPERATOR in another 5250 window and runs `CALL PGM(QP2TERM)`. Not seeded yet: a world writable `authorized_keys` and a limited profile reaching CL through ssh, both of which wait for the ssh listener.

## What is not confirmed on a real system

These are guesses from how AIX and IBM i are documented to behave. They are written down here so nobody teaches them as fact. A read-only check against PUB400, a person at the keyboard, would settle each one.

- The exact wording of errors: `ls: 0653-341 The file X does not exist.`, `ls: 0653-345 X: Permission denied.`, `cat: 0652-050 Cannot open X.`, `ksh: cd: X: [No such file or directory]`, `ksh: X: not found.`
- What `id` prints. Silverlake prints `uid=N(NAME) gid=N(NAME)`, with QSECOFR as 0 and everyone else numbered from 500 in the order the profiles were made. A real system assigns UIDs when a profile is created.
- The default permissions and owners of `/`, `/QOpenSys`, `/home`, `/tmp` and the home directories. Chosen to be plausible, not read off a machine.
- Whether adopted authority carries into PASE (believed not to, and not modeled).
- How a `LMTCPB(*YES)` profile fares with `QP2TERM`. Here the profile needs a way to type `CALL QP2TERM`, which a limited profile does not have, but that is not the same as the real rule.
- The layout of the QP2TERM display. This one is ours.
- Whether `db2` is the right command name and what its output looks like. IBM i has a `db2` in QShell and a `db2util` from open source; the layout here (a header, a dashed line, the rows, a count) is a guess, and the message IDs are IBM's with wording of ours.
- The prompt (`$ `) and the environment variables `env` prints.
