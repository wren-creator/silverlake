# PASE commands: the plan

The simulated PASE shell has 46 commands. PUB400's real one has about 290 in `/QOpenSys/usr/bin` alone. This plan adds commands ten at a time, in the order that teaches the most for the least work, and says what will never be built. The checkable version is in [ROADMAP.md](../ROADMAP.md).

## Where it stands

Built (46): `pwd cd ls cat id echo env printenv export exit` and `mkdir touch rm cp mv chmod` and `system db2` and the read-only batch `uname hostname date logname ps head tail wc grep` and B2, `basename dirname which type test [ file rmdir umask du find` (`[` is `test`), and B3, `qsh datarea dataq catsplf getjobid sysval getconf dspmsg setccsid Rfile` (not `clrtmp`, which deletes). The first ten are the first slice, the next sixteen came with the writing set, SQL and the PUB400 batch, and the last ten with B2.

Built in P2: pipes, `<`, standard input for `cat head tail wc grep`, and backticks; no `$()`, because bsh has none (the P2 capture). Built in P1: exit statuses and `$?`, `;` `&&` `||`, and globbing (no `~`: bsh has no tilde expansion, as the P1 capture showed). `Shell.run` still returns a list of lines, and the status is read from `Shell.status`, so nothing that calls the shell changed. Not built, and it limits what the commands can do: pipes, input redirection, command substitution, and scripts with `if` or `for`. `head`, `tail`, `wc` and `grep` need a file name today because there is nothing to pipe into them.

## The rules for every batch

1. **Capture first.** One read-only ssh run against PUB400 per batch, as before: one connection, about twenty commands that only read, three seconds apart, results saved after each command, empty input so nothing waits. Ask before each run. Keep the output local. A command that writes is not run on a shared host; its wording stays a guess and the docs say so.
2. **Copy what it said**: the wording, the layout, the exit status. A guess is labelled a guess in `docs/pase.md`.
3. **No real process, no host file, no outbound network, no `eval`.** Every command is a Python function over the virtual IFS and the object store. Anything with a pattern (`grep`, `sed`, `find`, `awk`) has a cap on work, like `db2` has.
4. **One batch, one commit**, after the tests, the docs (`docs/pase.md`, `CHANGELOG.md`, the roadmap checkbox) and `commit_gate`.
5. **A command earns its place** by teaching something or by being what a student types by reflex. If neither, it goes on the never list.

## Order, and why

The order follows what each batch needs. Text filters are useless without pipes, so the shell has to grow first. The IBM i commands are the most distinctive thing PASE has, so they come before the generic Unix ones.

| Step | What | Why here |
|---|---|---|
| **P1** | Shell features, part one: exit statuses and `$?`, `;` `&&` `||`, globbing (`*` `?` `[...]`). Checked on PUB400 afterwards: no `~` | `test` and `find` are not much use without them, and PUB400 gave exit codes for everything already captured |
| **B2** | `rmdir basename dirname which type test file find du umask` | Finding things and reading permissions. No pipes needed |
| **P2** | Shell features, part two: pipes, `<`, standard input for `cat head tail wc grep`, command substitution `$()` and backticks (a nested run of the same shell, never a host shell) | Everything after this assumes it |
| **B3** | `dspmsg catsplf dataq datarea getjobid sysval clrtmp setccsid Rfile getconf` | The IBM i side of PASE, and where the lessons are (see below). Several need an object type Silverlake does not model yet (`*DTAARA`, `*DTAQ`, message files) |
| **B4** | `sort uniq cut tr sed nl fold rev tee xargs` | The text filters. `sed` only `s///`, `d` and `p`, `xargs` only runs commands the shell already has |
| **B5** | `awk diff cmp comm join paste od strings split pr` | The heavier filters. `awk` is a small subset (`print $N`, `-F`, a pattern, `NR`, `BEGIN` and `END`), not the language |
| **B6** | `tar zcat compress uncompress pax ar more qsh sleep time` | Archives and odds and ends. Likely the first to be cut: `compress`, `pax` and `ar` have little to teach |
| **B7** | `ssh-keygen ssh-keyscan ssh scp sftp dig nslookup host openssl ldapsearch` | Keys and names, only against the simulator itself: `ssh` goes to Silverlake's own listener and nowhere else, `dig` and its cousins read a small static table in the IFS, `openssl` does `version` and reading a certificate. `sftp` and `scp` need a subsystem the listener does not have yet. `ldapsearch` is the weakest fit |
| **B8** | `kill jobs ulimit nice nohup wait fg bg alias unalias`, and real rows for `ps` | Process control with nothing real behind it, so mostly wording. Optional |

## Lessons that come with the batches

A batch ships a lesson only when it makes something findable that was not.

- **B2**, `pase-find-writable`: `find / -perm -002` shows the world writable directories and files that make the PATH and profile lessons work. `umask` and `which` tie into the PATH lesson. Also gives the "I found it myself" path into the lessons already there.
- **B3**, built with `pase-datarea-secret` (a key in a data area, read through `qsh -c datarea`); the `sysval` and `catsplf` lessons are still open. `sysval QPWDLVL` reads a system value from the shell (the same fact the sign-on server gave away), `catsplf` reads someone's spool file if the authority is loose, and `datarea` reads a secret from a data area. Two or three lessons, depending on what the object model can carry.
- **B4**, `pase-secrets-in-profile`: a password left in a `.profile` or a script, found with `grep`, `sed` and `cut`.
- **B7**, `pase-key-hygiene`: a private key left in a readable directory, found with `find` and `ssh-keygen -l`.
- **B5, B6 and B8** ship commands only.

## What will not be built

- **Runtimes and editors:** `java javac jar node npm bash ksh ksh93 csh psh vi view vedit ed edit make ld` and the compilers. Too big, and teaching nothing PASE-specific. `node -v` style version lines may come later.
- **Real network:** anything that opens a socket to a host that is not Silverlake. `rsync`, `curl` and `wget` too (the real host has no `curl` or `wget` either).
- **Anything that needs a real process:** `nohup` and `nice` are wording only, and so is the rest of B8.
- **The classic admin tools:** `chroot`, `mknod`, `restore`, `dump`, `trace`, `sshd`, `syslogd` and the other `/usr/sbin` files.

## Risks

1. **The shell rewrite.** (P1 is done, and kept the return type by putting the status on the shell. Pipes will need a stream between commands.) Exit statuses and pipes change what `Shell.run` returns, from a list of lines to lines and a status. That touches every command and the PASE terminal, the ssh listener and the tests. P1 should land alone, with the existing tests unchanged, before any new command.
2. **Runaway work.** Regular expressions, `find` on a big tree, `xargs` and `awk` can all loop. Each needs a step cap and a size cap from the start, tested with a hostile input, as `db2` has.
3. **Teaching a guess.** The IBM i commands behave in ways the docs describe and a real system may not. Capture first, and when a command cannot be captured safely, say so in `docs/pase.md`.
4. **Scope creep.** About 290 commands exist. Each batch has to justify itself, and B6 and B8 are the first candidates to drop.
5. **PUB400 manners.** Eight batches is eight or more runs against a shared host. Keep each short, keep them apart, and skip a capture when the existing ones already answer it.
