# PASE

PASE is the AIX runtime inside IBM i: a shell, `ls`, `cat`, scripts, ssh. Silverlake has a **simulated** one. No process is ever started, no host file is read, and a line that is not one of the built commands is refused. It is a Python shell over a virtual IFS, so it cannot touch the machine it runs on and `reset.sh` puts everything back exactly. This is the first slice: the IFS and a small shell. More comes in stages (see ROADMAP.md, Phase 4b).

## Using it

```
CALL PGM(QP2TERM)
```

opens the terminal. Type commands at the `$`, F3 or `exit` leaves. The top row says it is simulated.

Built commands: `pwd`, `cd`, `ls` (`-l`, `-a`), `cat`, `id`, `echo` (with `$VAR`), `env`, `export`, `exit`, and the writing set: `mkdir` (`-p`), `touch`, `rm` (`-r`, `-f`), `cp`, `mv`, `chmod`, `> file` and `>> file` at the end of a command, and `system 'CL command'`. Shell features: a line can hold several commands joined by `;`, `&&` and `||`, read left to right (`a && b || c` runs `c` when either `a` or `b` fails). Every command leaves an exit status, `$?` shows the last one, and over ssh the command's status is the session's. Words may use `*`, `?` and `[...]` (`[!a-c]` for not), matched one path part at a time against what the profile may list; a name starting with a dot only matches a part that starts with one (and `.*` also matches `.` and `..`), and a pattern that matches nothing stays as typed. There is **no `~` expansion**: `echo ~` prints `~` and `cat ~/x` looks for a directory called `~`, because bsh does not have it. `cd` with no argument goes to `$HOME`. Quoting follows the usual rules: single quotes keep everything, double quotes keep spaces and let `$VAR` and `$?` through, a backslash quotes one character, and a `#` that starts a word ends the line. A line is capped at 100 commands and a pattern at 1000 names. **Pipes and input** (P2): `a | b` feeds `b` what `a` printed, up to 20 commands in a pipeline, and `cat`, `head`, `tail`, `wc` and `grep` read it when no file is named (`cat -` and a `-` file name mean standard input too; a named file wins over the pipe, and `< file` wins over it as well). A pipeline's status is its last command's. What a command says to stderr (every error message) is shown but never piped or written to a `>` file, so `cat /nosuchfile | wc -l` prints the error and `0`. A command between **backticks** is run by a nested copy of the shell and replaced by what it printed, minus the trailing newlines; unquoted it splits into words and may glob, in double quotes it stays one word. The nested run cannot change the directory or variables or end the shell, can nest five deep, and brings back at most 64 KB. **`$(...)` does not exist in bsh**: `echo $(id)` is ``bsh: syntax error at line 1: `(' unexpected`` and nothing in the line runs, but inside double or single quotes it is just text. `> /dev/null` and `< /dev/null` work (not captured). Not built: `&`, subshells with `( )`, here documents (`<<`), `2>` and `2>&1`, `if` and `for`, and every other command (they answer `bsh: name: not found`).

Exit statuses, copied from the PUB400 batch run where it gave one: `ls` or `cat` on a missing path 2, `cd` 1, `head` or `tail` on a missing file 1, `wc` or `grep` on a missing file 2, `grep` with no match 1, `printenv` of a name that is not set 1, `logname` 1, and `ps` 1 (it printed its header and still exited 1). A command that is not found is 1 (`bsh: nosuchcmd: not found`, not the 127 other shells give), a line that does not parse is 2, and `exit 7` exits 7. **Guesses:** 1 for the write commands when they fail, 1 for `system` when the CL command ended with a CPF, CPD, CPE or MCH message, 4 for a `db2` SQL error (from IBM's page, not seen), 2 for a usage message, and `exit N` taken modulo 256. In a script `exit` ends the script and not the shell.

Two behaviors that surprise people, both from the P1 run below: a line that does not parse is refused whole and nothing in it runs (``bsh: syntax error at line 1: `;;' unexpected``, naming the operator after the empty command, `end of file` at the end of the line and, oddly, for a `;` that starts it), and with no terminal a failed `cd` or `export` ends the shell, so `cd /nosuchdir || echo recovered` prints the error and nothing else, exit 1. Silverlake does that for a command run over ssh and for a script. **At a prompt it carries on, which is a guess**; the run had no terminal to try it.

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

In both, the victim is a second session: the trainee signs on as QSECOFR or OPERATOR in another 5250 window and runs `CALL PGM(QP2TERM)`.

The two ssh lessons are described below.

## ssh

With `./start.sh --services` and asyncssh installed (`./setup.sh --ssh`), an ssh listener answers on `127.0.0.1:2222` (real: 22). `ssh -p 2222 STUDENT@127.0.0.1` gives the same simulated shell as QP2TERM, as that profile: a login runs the profiles and shows what they print, and `ssh host 'command'` runs one line. No host shell is ever reached, so `ssh host uname` says `not found`, and `scp` and port forwarding are not offered. A password login follows the 5250 sign-on rules (a wrong password counts toward the lockout), and a key login uses the public keys listed in `~/.ssh/authorized_keys` in the virtual IFS. The host key is made on first use in `.tls/`.

The daemon's settings are `/QOpenSys/etc/ssh/sshd_config` and the `.conf` files in `sshd_config.d/` beside it, re-read at every login, first value wins. It reads `PasswordAuthentication`, `PubkeyAuthentication`, `StrictModes`, `DenyUsers` and `AllowUsers`, and ignores the rest. With `StrictModes yes` a key file, its `.ssh` directory or the home directory that others can write is not trusted. Two lessons use it (group E):

- **ssh-strictmodes.** `StrictModes no` and a world writable `/home/DEVELOPER/.ssh/authorized_keys`. STUDENT appends a public key and logs in as DEVELOPER.
- **ssh-limited-bypass.** CLERK has no command line at the 5250 and a shell over ssh, with the shell's `cat`, `db2` and `system`. The fix is `DenyUsers CLERK`.

The version banner says AsyncSSH, not OpenSSH, so a scanner can tell it is not a real sshd.

## What PUB400 showed (2026-10-27)

One read-only ssh run against PUB400 (port 2222, one connection, nine commands that only read, three seconds apart; the capture stays local and gitignored). QP2TERM over 5250 never answered there, so ssh was the way in. It is a shared host, so some of this is its setup and not an IBM i default. What came back:

- **The shell is `bsh`**, not ksh (`$SHELL` is `/QOpenSys/usr/bin/bsh`). The sshd banner is `SSH-2.0-OpenSSH_9.6`. The login starts in `/home/<PROFILE>`.
- **`id`** prints `uid=<n>(name) gid=0`: the profile name in lower case, a five digit UID, and a group id with no name. Silverlake prints the name in upper case and a made up gid.
- **`PATH`** is `/QOpenSys/usr/bin:/usr/ccs/bin:/QOpenSys/usr/bin/X11:/usr/sbin:.:/usr/bin`. The current directory (`.`) is on it, which is itself a finding.
- **Errors:** `ls /nosuchdir` says `/nosuchdir not found` (exit 2), `cat /nosuchfile` says `cat: cannot open /nosuchfile` (exit 2), `cd /nosuchdir` says `/nosuchdir: No such file or directory` (exit 1). The AIX style `0653-341` and `0652-050` wording Silverlake uses was a guess and did not match.
- **`whoami` is not there:** `bsh: whoami: not found`.
- **Top level permissions:** `/` is `drwxrwsr-x`, `/QOpenSys` and `/home` are `drwxrwsrwx` and `/tmp` is `drwxrwsrwt`, all owned by QSYS. Everything is group writable or world writable, with setgid, and `/tmp` is sticky. Silverlake's seed is much tighter. A shared public host may be looser than a stock system.

**Matched in the simulator** (the same day): the shell is `bsh` (the prefix of its own messages and `$SHELL`), a missing path in `ls` is `X not found`, `cat` says `cat: cannot open X` for any open that fails, `cd` says `X: No such file or directory`, an unknown command says `bsh: name: not found`, `id` prints `uid=N(name) gid=0` with the name in lower case, and there is no `whoami`. Single quotes now keep `$VAR` as typed, as a shell does. **Kept on purpose:** the tighter seeded permissions (a real shared host had `/home` and `/QOpenSys` world writable, which would make every lesson trivial) and a `PATH` without `.`. **Still a guess:** the wording of `ls` on a directory you may not read, and of the write commands (`mkdir`, `rm`, `cp`, `mv`, `chmod`, `>`), which were not run on PUB400 because they write.

## The commands PUB400 has (2026-10-27)

A second read-only ssh run listed the directories on the login `PATH` (`ls` only, six commands, one connection; the full listing stays in the local capture). Counts: 293 files in `/QOpenSys/usr/bin`, 163 in `/usr/bin`, 23 in `/usr/ccs/bin`, 12 in `/usr/sbin`, 16 in `/QOpenSys/usr/bin/X11`. A few things worth knowing:

- **Shells:** `bsh` (the login shell), `sh`, `ksh`, `ksh93`, `csh`, `psh` and `qsh` in `/QOpenSys/usr/bin`, and `bash` in `/usr/bin` (installed on this host, not stock).
- **Builtins:** `type` says `echo`, `cd` and `pwd` are shell builtins, and `ls`, `cat` and `id` are separate programs in `/QOpenSys/usr/bin`. Silverlake treats `cd`, `pwd`, `echo`, `export` and `exit` as the shell's own, which agrees.
- **The classics are all there:** `ls cat cp mv rm mkdir rmdir touch chmod chown ln find grep sed awk sort uniq head tail wc cut tr tar pax diff more vi ed make xargs env printenv date uname hostname logname ps kill sleep time test expr printf`.
- **IBM i bridges:** `system` (run CL), `qsh`, `db2` (in `/usr/bin`, so the name Silverlake uses is right, and its output layout is still unchecked), `dspmsg`, `catsplf`, `dataq`, `datarea`, `getjobid`, `setccsid`, `sysval`, `clrtmp`, `Rfile`.
- **Network and remote:** `ssh ssh-keygen ssh-copy-id ssh-keyscan ssh-agent scp sftp slogin rsync`, `dig host nslookup`, `ldapsearch`, and `sshd` in `/usr/sbin`.
- **Runtimes:** `java javac jar`, and `node` and `npm`.
- **Not there:** `whoami`, `who`, `curl`, `wget`, `nc`, `ping`.

A third read-only run (eighteen commands, wording below) captured the small batch, and Silverlake now has it: `uname`, `hostname`, `date`, `logname`, `printenv`, `ps`, `head`, `tail`, `wc` and `grep`. What PUB400 said, copied:

- `uname` is `OS400`, and `uname -a` is `OS400 <node> <release> <version> <machine id>` (the host showed `5 7` for V7R5, so Silverlake says `4 7` for V7R4M0). `hostname` is the full name (`WWW.PUB400.COM` there, `SILVERLAKE.LOCALDOMAIN` here, the node name being `SILVERLAKE`).
- `date` is `Wed Oct 28 01:14:40 UTC 2026`, with the day padded by a space when it is one digit.
- `logname` over ssh says `logname: getlogin failed`, because there is no terminal. `printenv NAME` prints the value, or nothing when it is not set. `ps` printed only the header `    PID    TTY  TIME CMD` for the login.
- `head` and `tail` on a missing file say `X: No such file or directory`, `wc` says `wc: cannot open X`, `grep` says `grep: can't open X`. `wc` prints each count in an eight wide column and then the name.
- `grep x` with no file waits for input, and timed out after twenty seconds. With a pipe or `<` Silverlake reads that; with neither, `head`, `tail`, `wc` and `grep` print nothing where the real ones would wait.

Not captured, so a guess: any option beyond `-n N`, `-l -w -c`, and `-i -v -n -c`; `grep` output with several files; and what `logname` and `ps` say on a terminal (QP2TERM) instead of over ssh.

## The shell syntax run (2026-10-28)

A fourth read-only ssh run against PUB400 (twenty-six commands, one connection, three seconds apart, empty stdin, nothing written; the capture is `ssh-pase-p1.json`, local and gitignored) tested P1 before it was called done. It corrected five things in what had been built from memory:

- **No tilde expansion.** `echo ~`, `echo ~/x` and `echo a~` all print what was typed. Silverlake had expanded it. Commands that took `~/x` as a path (`cat ~/notes.txt`) now look for a directory named `~`, as bsh does.
- **Command not found is status 1**, with `bsh: nosuchcmd: not found` on stderr. (`/nosuchdir/x` is the same.) Silverlake had said 127.
- **A failed `cd` or `export` ends a shell with no terminal.** `cd /nosuchdir && echo no`, `cd /nosuchdir || echo recovered` and `echo a && cd /nosuchdir || echo c; echo d` each printed the error and stopped (the last one after printing `a`), exit 1. `export 9bad=1; echo $?` printed `bsh: 9bad=1: is not an identifier` and no `1`.
- **Bad lines are refused whole**, nothing in them runs, exit 2, with ``bsh: syntax error at line 1: `X' unexpected``. Captured: `;echo a` says `end of file`, `echo a ;; echo b` says `;;`, `echo a && && echo b` says `&&`, `echo a &&` says `end of file`. Doubled `||` and a spaced `; ;` were not run, so their tokens are the same rule applied.
- **`.*` matches `.` and `..`** (`/QOpenSys/etc/.*` printed both), and a pattern with no match, or a quoted one, stays as typed.

What matched the first guess: `a;b` and `x#y` inside quotes or in a word are text, `# comment` ends the line, `"$W"` and `$W` print the same but the first is one word, `"$NOPE"x` is `x`, `echo a;` is fine, `ls /nosuchdir && echo a || echo b` prints `b`, `$?` starts at 0, and `exit 7` exits 7. The `[!p]rofile` form matched nothing there, so whether bsh reads `!` as negation is not settled either way.

## The pipe and input run (2026-10-28)

A fifth read-only ssh run (thirty-four commands, one connection, nothing written, capture `ssh-pase-p2.json`, local and gitignored) tested P2 before it was built, and a replay of the commands that do not depend on the host's own files now matches it exactly on stdout, stderr and status. What it showed:

- **`$(...)` is a syntax error**, ``bsh: syntax error at line 1: `(' unexpected``, status 2, and bsh runs nothing. Backticks work, including inside double quotes.
- **A pipeline's status is its last command's:** `cat /nosuchfile | cat; echo $?` printed the error and `0`, `nosuchcmd | cat` the same, `echo hi | nosuchcmd` gave 1.
- **Errors stay out of the pipe.** They go to stderr, so a consumer sees nothing from the command that failed.
- **`wc` on standard input** prints the three counts, eight wide, and no name; `wc -l` prints the one. `grep -c` on input prints the count with no file prefix.
- **`cat < /nosuchfile`** is `bsh: /nosuchfile: cannot open`, status 1, and `cat` does not run.
- **A backtick command that fails** prints its error, brings back nothing, and the outer command's `$?` is the outer command's (`echo `nosuchcmd`; echo $?` printed an empty line and `0`).
- **A trailing `|`** (`echo a |`) printed nothing and exited 0: the line was swallowed. `| cat` and `echo a | | cat` are ``syntax error ... `|' unexpected``, and `cat <` is `end of file`.
- `echo a | echo b` prints `b`, `cat -` reads standard input, and `echo a | grep a FILE` searches the file and ignores the pipe.

Guesses: a trailing `|` in a line with other commands swallows the whole line, `/dev/null` works as a sink and as empty input, and a `cd` inside a pipeline stage still changes the shell's directory (a real shell runs the stage in a subshell).

## What is not confirmed on a real system

These are guesses from how AIX and IBM i are documented to behave. They are written down here so nobody teaches them as fact. A read-only check against PUB400, a person at the keyboard, would settle each one.

- The wording of `ls` on a directory the profile may not read (`ls: 0653-345 X: Permission denied.` is a guess) and of the write commands. The wording of missing paths, `cat`, `cd` and unknown commands is copied from PUB400.
- The UID numbers. The format of `id` is copied from PUB400, but Silverlake numbers QSECOFR as 0 and everyone else from 500, in the order the profiles were made, and a real system assigns UIDs when a profile is created.
- The default permissions and owners of `/`, `/QOpenSys`, `/home`, `/tmp` and the home directories. Chosen to be plausible, not read off a machine.
- Whether adopted authority carries into PASE (believed not to, and not modeled).
- How a `LMTCPB(*YES)` profile fares with `QP2TERM`. Here the profile needs a way to type `CALL QP2TERM`, which a limited profile does not have, but that is not the same as the real rule.
- The layout of the QP2TERM display. This one is ours.
- What `db2` prints. The command exists on PUB400 (`/usr/bin/db2`), but the layout here (a header, a dashed line, the rows, a count) is a guess, and the message IDs are IBM's with wording of ours.
- The path of the sshd config files (`/QOpenSys/etc/ssh/`), which is ours, and whether a `LMTCPB(*YES)` profile is stopped by sshd or by its login shell on a real IBM i. Here nothing stops it, which is the lesson and is believed but not confirmed.
- The prompt (`$ `) and the environment variables `env` prints.
