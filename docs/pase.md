# PASE

PASE is the AIX runtime inside IBM i: a shell, `ls`, `cat`, scripts, ssh. Silverlake has a **simulated** one. No process is ever started, no host file is read, and a line that is not one of the built commands is refused. It is a Python shell over a virtual IFS, so it cannot touch the machine it runs on and `reset.sh` puts everything back exactly. This is the first slice: the IFS and a small shell. More comes in stages (see ROADMAP.md, Phase 4b).

## Using it

```
CALL PGM(QP2TERM)
```

opens the terminal. Type commands at the `$`, F3 or `exit` leaves. The top row says it is simulated.

Built commands: `pwd`, `cd`, `ls` (`-l`, `-a`), `cat`, `id`, `whoami`, `echo` (with `$VAR`), `env`, `export`, `exit`. Not built: pipes, redirection, `;`, `&`, command substitution, globbing, scripts, and every other command (they answer `ksh: name: not found.`). Nothing can write to the IFS yet.

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

## What is not confirmed on a real system

These are guesses from how AIX and IBM i are documented to behave. They are written down here so nobody teaches them as fact. A read-only check against PUB400, a person at the keyboard, would settle each one.

- The exact wording of errors: `ls: 0653-341 The file X does not exist.`, `ls: 0653-345 X: Permission denied.`, `cat: 0652-050 Cannot open X.`, `ksh: cd: X: [No such file or directory]`, `ksh: X: not found.`
- What `id` prints. Silverlake prints `uid=N(NAME) gid=N(NAME)`, with QSECOFR as 0 and everyone else numbered from 500 in the order the profiles were made. A real system assigns UIDs when a profile is created.
- The default permissions and owners of `/`, `/QOpenSys`, `/home`, `/tmp` and the home directories. Chosen to be plausible, not read off a machine.
- Whether adopted authority carries into PASE (believed not to, and not modeled).
- How a `LMTCPB(*YES)` profile fares with `QP2TERM`. Here the profile needs a way to type `CALL QP2TERM`, which a limited profile does not have, but that is not the same as the real rule.
- The layout of the QP2TERM display. This one is ours.
- The prompt (`$ `) and the environment variables `env` prints.
