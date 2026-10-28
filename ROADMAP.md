# Silverlake roadmap

## v1

- [x] Phase 0: repo scaffold, lifecycle scripts, loopback guard, docs skeleton
- [x] Phase 1: 5250 core, telnet + TN5250E negotiation, encoder/decoder, declarative screens
- [ ] Phase 1 follow-ups: try a real tn5250 over the new TLS port (5992), try real tn5250 and IBM Access clients, Query reply handling, 27x132 screens
- [x] Phase 2: oracle harness, capture on a real IBM i, replay on Silverlake, diff structure
- [ ] Phase 2 follow-ups: confirm title and label columns and colors from a stock capture (positions came from a photo), configurable password length, authenticated captures (harness done, first real run pending), Query path against a real host, more scenarios as Phase 3 lands
- [x] Phase 3a: user profiles and the access model (five classes, eight special authorities, object authority), sign-on checks, seed-file assignment of any access level (docs/access-model.md)
- [x] Phase 3b: CRTUSRPRF, CHGUSRPRF, DSPUSRPRF, DLTUSRPRF, WRKUSRPRF, SIGNOFF from a command line as *SECADM, profiles as secured objects, changes saved in SQLite
- [ ] Phase 3b follow-ups: F4 prompting and keyword abbreviation, limited capabilities enforcement, adopted authority, more WRKUSRPRF options, DSPUSRPRF types
- [ ] Confirm the profile command message IDs and which condition raises each (CPF2204, CPF2217, CPF2228 and the rest are documented, not seen); safe read-only checks on PUB400 are an unknown command and DSPUSRPRF on your own profile
- [x] Phase 3c-1: libraries and objects as real SQLite tables keyed by library, name and type; library authority checked before object authority; CRTLIB, DLTLIB, WRKLIB, DSPLIBL, ADDLIBLE, RMVLIBLE, DSPOBJAUT, GRTOBJAUT, RVKOBJAUT
- [ ] Phase 3c-1 follow-ups: generic names and *ALL on GRTOBJAUT and RVKOBJAUT, more object types, WRKLIB options, CRTAUT on libraries, REFOBJ, *OUTFILE for DSPOBJAUT, DSPLIB, primary group on objects
- [ ] Check on a real system: the library-gate rule for *ALLOBJ, what authority a new library gets, and whether QSYS authority matters to CRTLIB once the command is allowed (needs a profile that may run CRTLIB). Done already: QSYS and QGPL authority, the default library list, what DSPOBJAUT shows a basic user, and that a basic PUB400 profile is refused CRTLIB at the command
- [x] Phase 3c-2: commands as *CMD objects, *MENU objects, GO and the menu stack, INLMNU and INLPGM (QCMD only) at sign-on, LMTCPB enforcement, CHGPRF, CALL QCMD, the real MAIN menu geometry
- [ ] Phase 3c-2 follow-ups: bring DSPLIBL and DSPOBJAUT to the real layouts (option column, Group column, F11 detail, Top and Bottom keys); F4 prompting; Command Entry fidelity (compare against a real one); programs behind INLPGM and CALL; confirm the LMTCPB message wording and the "Not authorized to command" ID on a real system
- [x] Phase 3c-3a: authorization lists (CRTAUTL, DLTAUTL, ADDAUTLE, CHGAUTLE, RMVAUTLE, DSPAUTL, WRKAUTL), *AUTLMGT, list owner
- [ ] Phase 3c-3a follow-ups: generic list names, WRKAUTL options, DSPAUTL *PRINT and *OUTFILE, lists owned by a deleted profile, QIBM_DB_SECADM, CHGOBJOWN, *AUTL as an object type for DSPOBJAUT
- [x] Phase 3c-3b: WRKOBJ, WRKOBJOWN, CHGOBJOWN
- [x] Work list options and layouts from the PUB400 capture: WRKOBJ 5, 7, 13, WRKOBJOWN 5, 7, 9, WRKAUTL 1, 5, 8, plus RNMOBJ and CHGOBJD
- [x] Work list options 2 (EDTOBJAUT edit screen), 4 (delete with confirm: DLTF, DLTCMD, DLTMNU, DLTPGM, DLTLIB) and 8 (DSPOBJD) on WRKOBJ and WRKOBJOWN, from the PUB400 captures
- [x] WRKAUTL 4 (confirm, DLTAUTL), 9 and 13, and creation dates on libraries made with CRTLIB
- [x] Phase 3c-3c step 1: job table (sessions as interactive jobs, seeded system jobs) and WRKACTJOB, see docs/jobs-spool-messages.md
- [x] Phase 3c-3c step 2: spool files (WRKSPLF, DSPSPLF, DLTSPLF, QPJOBLOG per session, *OUTQ objects, DSPDTA/OPRCTL rules), from the PUB400 captures
- [x] HLDSPLF, RLSSPLF and WRKSPLF options 3 and 6, WRKSPLF JOB filter, WRKACTJOB option 8, F17 and F18 on WRKOBJOWN and the edit screen
- [x] HLDJOB, RLSJOB, ENDJOB, CHGJOB gated on the job's owner or *JOBCTL, behind WRKACTJOB options 2, 3, 4, 6; an ended session notices and signs itself off
- [x] DSPJOBLOG (live log, *JOBCTL or same user, *ALLOBJ jobs need *ALLOBJ) and WRKJOB (menu, options 4, 10, 13), WRKACTJOB option 5, from the PUB400 captures
- [x] DSPJOB and its status, definition and run attribute pages (first pages), also behind WRKJOB options 1, 2, 3, from a PUB400 capture of the profile's own job
- [x] Job screens: page two of the DSPJOB and WRKJOB menus (WRKJOB 41 and 42 run ENDJOB and HLDJOB), page two of the status and definition pages, and options 11, 12, 14, 15, 16, from a second PUB400 capture
- [x] Job leftovers, from auth-dspjob3 and auth-dspjob4: options 17 to 22, the third WRKJOB page (43 runs RLSJOB), the Change Job prompt behind WRKJOB 40 and WRKACTJOB 2, F11 views on the call stack, open files and locks, F10 record locks
- [ ] Job leftovers still open: option 30, 45, the option columns (locks, files, threads, environment variables), F22 on the call stack, CHGJOB page two and F4/F10/F13, DSPJOBLOG F10, WRKACTJOB options 7, 13 and keys F7, F10, F11, and the real confirm for option 4 (the oracle will not end jobs)
- [x] Colors: every captured screen now draws what the real host draws (labels, values, list rows and options green, titles, column headings and More... and Bottom white, prompts and keys blue), with a test holding the rules. Screens with no capture follow the same rules by analogy
- [x] WRKOUTQ OUTQ(lib/name), from the PUB400 captures: the list, options 3, 5, 6, 8, the not found wording, and a profile that may read the queue sees every file in it (user and job name) whatever DSPDTA says
- [x] CRTOUTQ and DLTOUTQ, from IBM's pages (AUT defaults to *USE, only the owner can delete by default, a queue with entries cannot be deleted)
- [x] Spool options 1, 2, 4, 7, 9 on WRKSPLF and WRKOUTQ, from the auth-splopts capture (SNDNETSPLF and CHGSPLFA prompts first pages, no messages, printing status), plus CHGSPLFA
- [ ] WRKOUTQ leftovers: F11 view 2, F20, F22, F24, status HLD for a held queue, and the bare form (Work with All Output Queues, needs a quieter capture)
- [ ] Spool leftovers: option 4 confirm (real one never captured, ours deletes at once), SNDNETSPLF and CHGSPLFA page two plus F4/F10/F13, inner options on Work with Printing Status, Find and F19/F20 on the display, attributes page two and F13, HLDSPLF/RLSSPLF
- [x] Phase 3c-3c step 3: message queues (DSPMSG, SNDMSG, CLRMSGQ, QSYSOPR, per-user queues in QUSRSYS), from the PUB400 captures
- [x] CRTMSGQ, CHGMSGQ (DLVRY, SEV, TEXT) and DLTMSGQ from IBM's command pages, rules and inferences in docs/jobs-spool-messages.md
- [ ] Message leftovers: the real SNDMSG prompt (needs a longer wait), inquiry messages and replies, F11 remove one, WRKMSGQ, CHGMSGQ break program and *DFT delivery, RMVMSG, break delivery to a live session, work station queues
- [x] DSPOBJD basic list, full page two, and Add New Users (F6), from the PUB400 captures
- [ ] Work list options still to build: 3 (copy, CRTDUPOBJ), WRKAUTL 2 (needs a capture from a profile that may edit a list); edit screen F10 and F11 (the real host did not answer F10, retry with a longer wait); DSPOBJD page three and option 8, creation dates for non-library objects; F4 prompting, F11, F16 and F17 positioning, F17 and F18 top and bottom on WRKOBJOWN; capture the real WRKAUTL delete confirm and the F6 Add new users screen
- [ ] More object types (*DTAARA and *USRSPC next), *AUTL in the object table, generic names on RNMOBJ and CHGOBJD
- [ ] Confirm CPF1107, CPF1118, CPF1394 on a real system (needs a deliberate wrong-password attempt, so a human decides)
- [x] Sign-on lockout (QMAXSIGN, QMAXSGNACN) and password expiry (PWDEXP, QPWDEXPITV) with a Change Password display, built from IBM's descriptions, not a capture
- [ ] Layout leftovers: DSPLIBL option 5 and Opt column, DSPOBJAUT F11 (detail authorities, no capture yet) and the Group column, WRKLIB and the other list screens with no capture, Top and Bottom on the remaining paged lists
- [x] CHGPWD, password rules (QPWDMINLEN/MAXLEN/RQDDGT/LMTAJC/LMTREP/RQDDIF), per-profile PWDEXPITV, expiry warning (QPWDEXPWRN)
- [ ] Lockout leftovers: device lockout (QMAXSGNACN 1), QSECOFR exempt at the console, a warning before the last attempt if the real host has one
- [x] Phase 3c-3c complete: jobs, spool files and message queues, merged to main 2026-10-27
- [x] Phase 4a: RPG programs run. CALL starts a `*PGM` with RPG source, EXFMT screens land on the 5250, keys and numeric fields behave like a display file, programs call programs through the library list and authority, a step cap stops runaway loops, DSPPGM from a capture (docs/rpg.md)
- [x] Phase 4b: adopted authority and QCMDEXC (done; seeded APPLIB/RUNCMD and RUNCMDX). A program runs with USRPRF(*OWNER) authority through a stack of effective profiles, and CALL 'QCMDEXC' (hook already in rpgle_library) runs a CL string through the same dispatcher, reproducing the captured messages. Seed a vulnerable wrapper (an *OWNER program owned by a powerful profile that passes a string to QCMDEXC) and its fix. IBM's pages (read) combine the owner's authority with the user's, USEADPAUT passes the prior program's, group profile assignment still needs the user's own *CHANGE and *OBJMGT, system request, attention key, break handling and debug do not use adoption, and the IFS does not support it. Special authorities flowing from the owner are implied by IBM's CRTUSRPRF example, not stated, so build it that way and keep it on the verification list
- [x] Phase 4c-1: DISK files. PF `*FILE` objects carry DDS and records, a run loads them into SQLite, authority is checked at open and on every read, add, update and delete against the effective profile (adopted authority applies), writes go back to the objects. Seeded PAYROLL, CUSTOMERS, PAYLOOK, PAYADJ
- [x] Phase 4c-2: printer files into the spool (PRTF `*FILE` objects, output lands on the queue as the job's own spooled file, queue rules decide who reads it). Seeded REGRPT (prints to QPRINT, readable by anyone) and REGRPTX (prints to a queue that hides contents), with APPLIB/PAYOUTQ
- [ ] Phase 4c later, printer side: CHGPRTF and OVRPRTF (redirect a report to another queue), page size and copies from the printer file, a spool file that stays OPN while the program runs
- [x] Phase 4c-3: DSPF objects instead of one DDS string per program (found through the library list, need *USE, shared between programs; the old inline form still works when no object is found)
- [x] Phase 4c-4: OVRDBF and DLTOVR, QTEMP per job (shadowing by library list order), seeded EMPDIR/EMPDIRX (override redirects an adopting program's file) and PAYRUN/PAYRUNX (a program in QTEMP runs in place of the one called by name)
- [x] Phase 4c-5: CPYF (member options, CRTFILE, FMTOPT, record range) and DSPPFM (control, shift), authority from IBM's pages as remembered, wording and layout ours
- [ ] Phase 4c later: logical files (keyed access paths over a PF, select/omit), DSPOVR and printer file overrides, USROPN in the runtime so a program can override before it opens, QTEMP filtered by job in WRKOBJ and DSPOBJD, DSPPFM hex and Find, CPYSRCF, CPYTOIMPF, file commands (CHGPF, RGZPFM, CLRPFM), and record level locking
- [x] Phase 4d-1: source files with members (CRTSRCPF), CRTBNDRPG, CRTPF, CRTDSPF, CRTPRTF, compile listing to the spool as QSYSPRT. Seeded SRCLIB/QRPGLESRC and QDDSSRC with HELLO, HELLOD, CUSTPF. Oracle capture `auth-pdm`
- [x] Phase 4d-2: STRPDM, WRKMBRPDM, WRKOBJPDM (alias to WRKOBJ) and STRSEU, with a SEU-like editor (line commands, blocks, FIND and CHANGE, F3 exit display, browse, member locks). The menu and refusals are captured, the Work with Members and editor layouts are ours
- [x] Phase 4d-3: F4 prompts for CRTBNDRPG, CRTPF, CRTDSPF, CRTPRTF and CRTSRCPF on the captured layouts, from any command line and from PDM (option 14 with F4 fills in the member)
- [ ] Phase 4d later: F4 prompts for the other commands and F10 additional parameters, PDM options 1, 2 and 3 as real screens, options 6, 8 and 9, WRKOBJPDM with its own screen, SEU syntax prompts, column shift and F11, CRTRPGMOD and CRTPGM, CPYSRCF and CPYF, RMVM and ADDPFM, PF with no source (RCDLEN), a compile that names its own program in the H-spec, sequence numbers and dates on source lines
- [ ] Phase 4e: RPG leftovers: several inputs per row (needs rpgle_library to key input by field), function checks, a program dump, DSPPGM options (program references, source member), the real Change/Display Program attributes
- [ ] Phase 4b: PASE, a simulated one. No real processes, ever: a Python shell over a virtual IFS, so it cannot touch the host and `reset.sh` stays exact. Stages: (1) an IFS (`/QOpenSys`, `/home`, `/tmp`, `/QSYS.LIB` mapped onto the existing library and object store) with rwx permissions tied to profiles and *ALLOBJ; (2) the shell behind `CALL QP2TERM`, `QSH` and a loopback SSH listener, with a whitelist (ls, cat, cd, pwd, id, whoami, ps, env, echo, export); (3) `system` to run CL from the shell and `db2util` or a small SQL runner for `QSYS2.QCMDEXC`; (4) seeded weaknesses: world writable `.ssh/authorized_keys`, a writable directory early in `$PATH`, writable `/etc/profile` and `~/.profile`, and CL reachable from a PASE shell by a limited-capability profile
- [ ] Phase 4b PASE first slice is built (virtual IFS, QP2TERM, pwd cd ls cat id echo env export exit, docs/pase.md). Second slice built: a writable IFS (mkdir touch rm cp mv chmod, `>` and `>>`) and `system`. Third slice built: scripts, PATH lookup, a login that reads the profiles, and two lessons (pase-profile-plant, pase-path-hijack). Fourth slice built: `db2` (SELECT, INSERT, UPDATE, DELETE, CALL QSYS2.QCMDEXC) over the physical files with real authority checks. Later: catalog services (QSYS2.USER_INFO and friends), STRSQL, a lesson on SQL as a way around the program that guards the data. Fifth slice built: the loopback ssh listener (asyncssh, optional, port 2222) with password and key logins, an sshd_config in the IFS, and the lessons ssh-strictmodes and ssh-limited-bypass. Small read-only batch built from a third PUB400 capture (uname hostname date logname printenv ps head tail wc grep). Later: sftp, scp, QSH/STRQSH, and the PUB400 check of the PASE facts (QP2TERM gave no screen over 5250, so ssh on 2222 is the likelier way to capture them)
- [ ] PASE facts to check on a real system before teaching them: whether adopted authority carries into PASE (believed not to, unconfirmed), what `id` and `ps` really print, default IFS authorities on `/QOpenSys` and `/home`, and how a LMTCPB(*YES) profile fares with QP2TERM (read-only checks on PUB400, human decides)
- [ ] PASE commands, ten at a time (plan and reasons in docs/pase-commands-plan.md). 26 built. Each batch starts with one read-only PUB400 capture, copies its wording, and ships as one commit:
  - [x] Batches 0 and 1: pwd cd ls cat id echo env printenv export exit; mkdir touch rm cp mv chmod system db2; uname hostname date logname ps head tail wc grep
  - [ ] P1, shell features part one: exit statuses and `$?`, `;` `&&` `||`, globbing, `~`. Lands alone, existing tests unchanged
  - [ ] B2, files and lookup: rmdir basename dirname which type test file find du umask. Lesson: pase-find-writable
  - [ ] P2, shell features part two: pipes, `<`, standard input for cat head tail wc grep, command substitution
  - [ ] B3, the IBM i side: dspmsg catsplf dataq datarea getjobid sysval clrtmp setccsid Rfile getconf. Needs *DTAARA, *DTAQ and message file objects. Lessons: system values, spool files and data areas read from the shell
  - [ ] B4, text filters: sort uniq cut tr sed nl fold rev tee xargs. Lesson: pase-secrets-in-profile
  - [ ] B5, heavier filters: awk (a small subset) diff cmp comm join paste od strings split pr
  - [ ] B6, archives and odds and ends: tar zcat compress uncompress pax ar more qsh sleep time. First to be cut
  - [ ] B7, keys and names, against Silverlake only: ssh-keygen ssh-keyscan ssh scp sftp dig nslookup host openssl ldapsearch. Lesson: pase-key-hygiene
  - [ ] B8, process control, mostly wording: kill jobs ulimit nice nohup wait fg bg alias unalias, real rows for ps. Optional
  - [ ] Never: java javac node npm bash ksh csh vi ed make and the compilers, real network, anything needing a real process
- [x] Phase 5a: scenario registry (`scenarios/*.toml`, one per lesson, with a vulnerable and a secure state as object patches on one base seed), `./scenario.sh list|set <id> vulnerable|secure|reset` (stops the server, patches the database, restarts, so open sessions end), a global `SILVERLAKE_MODE` for the whole range, per scenario reset
- [x] Phase 5b: flags. A per instance secret made by `setup.sh` (never in the repo), flags derived from it per scenario (HMAC), planted in the protected object an exploit reaches (a PAYROLL record, a data area, a spool file) and checked from state where the win is a change (authority granted, profile created). `./check-flags.sh submission.txt`, instructor `--show`
- [x] Phase 5c: scenario docs generated from the registry so they cannot drift: instructor `docs/scenarios.md` (Where, Real-world parallel, Vulnerability, MITRE ATT&CK, Exploit, Consequence, Fix) and `docs/scenarios-trainee.md` with Fix stripped
- [x] Phase 5d: a test per scenario that runs the exploit against the vulnerable state and asserts it fails against the secure one, so a code change cannot quietly break a lesson
- [x] Phase 5e: instructor kit (agenda, answer key, rubric, setup runbook, session slides) in the format of Cross Creek
- [ ] Phase 5a later: a live toggle, a QSECOFR-only command in the simulator that flips a scenario without a restart, so an instructor can apply a fix mid-class
- [ ] Phase 5f: exposed services on loopback only, opt in with `./start.sh --services`, all in the one server process so they share the store and the lesson toggles. Services answer from the same profiles and authority as the 5250 side, and nothing ever reaches a shell. Broken into steps:
  - [x] 5f-1: service plumbing plus the HTTP Admin console on 2001 (Basic auth against the profile store, a Create HTTP Server form whose description evaluates `exec` directives against the simulator's own commands as QTMHHTTP, and a fix flag), lesson `httpadmin-ssi-injection`, new lesson group D
  - [x] 5f-2: FTP on 2121 (cleartext sign-on, naming formats, file get through the normal authority checks), lesson `ftp-limited-bypass` (limited capability does not stop FTP); RCMD added afterwards
  - [x] 5f-3: host servers, the mapper on 4449 and the sign-on server on 8476 answering exchange attributes before any sign-on, lesson `hostsvr-recon`
  - [x] 5f TLS: a throwaway certificate (`./setup.sh`, `.tls/`) and TLS ports for 5250 (5992), the console (2010), FTP (explicit AUTH TLS with PROT P on 2121, implicit on 2990) and the sign-on server (9476)
  - [ ] 5f later: a lesson on requiring TLS (cleartext FTP and console sign-on refused), a certificate audit lesson on 2010, the real low ports (21, 449, 23, 992, 990) for people who run as root, TLS 1.3 only option
- [ ] Silverlake 101 EPUB, same format as the Mainframe 10x series

## Needs verification on a real system

- [ ] RPG runner: that a function key a display file never named is refused with a message (Silverlake says "Function key not allowed."), whether adopted authority passes special authorities (read IBM's page, then test with a program owned by a profile that holds the authority), how a program sees a failed QCMDEXC (Silverlake ends it with the command's message), what a compile error listing looks like, and whether CALL needs *USE or *EXECUTE, whether adding to an output queue needs *READ to it (inferred), who owns a program that is replaced by CRTBNDRPG and whether it keeps its authorities, what a real compile listing and its completion messages say, and the wording of a refusal to open a file (Silverlake reuses the not-authorized-to-object text; a real job says something else) (writes, human decision)

Things Silverlake does from IBM's pages, memory or inference and has not seen on a real IBM i. Tick one when it has been checked, and fix the docs if the real system disagrees. "Write" means it changes something on a shared system, so it needs a human decision and fresh approval first (PUB400 rules: read only, human paced).

- [ ] CRTMSGQ, CHGMSGQ, DLTMSGQ: the completion messages (IDs and text), what authority a new queue gets under *LIBCRTAUT, whether *ADD to the library is what CRTMSGQ needs, and that *CHANGE cannot delete a queue. Write: one throwaway queue in the test account's own library, DSPOBJAUT on it, change its text, delete it
- [ ] Message queue reads: that DSPMSG needs only *USE (inferred, the page has no authority section), and that a user queue gets the library's create authority so QUSRSYS makes every queue world readable
- [ ] DSPJOB: that its refusal is CPF1071 like WRKJOB (used without seeing it), the pool id and type of job for non interactive jobs, and the stack, locks and open files we show for non interactive jobs (a system job shows nothing)
- [ ] DSPJOBLOG and WRKJOB: CPF2441 and CPF1071 wording, CPF2443 for an ended job (inferred), CPF2523 for a system job, and the QIBM_ACCESS_ALLOBJ_JOBLOG function usage that can also grant reading an *ALLOBJ job's log (not modeled)
- [ ] CHGJOB: that RUNPTY, TIMESLICE, PURGE, DFTWAIT, CPUTIME and MAXTMPSTG need *JOBCTL even on your own job, and CPF1337 as the refusal (inferred). Write
- [ ] CRTOUTQ and DLTOUTQ: that *ADD to the library is what creating takes, which message a queue with entries raises (CPF3360 stands in), that QPRINT and QEZJOBLOG are undeletable (CPF3469, inferred), and that *OBJEXIST is what deleting takes. Write, so a human decides
- [ ] CHGSPLFA: moving a file with OUTQ() needing *READ to the target queue, and the control rule matching hold and delete, are inferred; option 4 on a spooled file may ask for confirmation on the real host
- [ ] Password rules: real message IDs and wording, the QPWDRQDDIF history sizes (from memory), whether CRTUSRPRF and CHGUSRPRF enforce the rules, the expiry warning text and where it appears
- [ ] WRKOUTQ: the IDs CPF3357 (queue not found) and CPF3330 (not authorized) are from memory of IBM's lists, not seen; that *READ to the queue and *EXECUTE to its library are what listing takes; what a held queue shows in Status; that options 3 and 6 follow the same rule as on WRKSPLF
- [ ] Spool rules: the parts of CRTOUTQ's page that only came through as a summary, and the inferred OPRCTL, DSPDTA and AUTCHK behavior for other people's files
- [ ] Job log filing: that passwords are masked is Silverlake's choice, not something seen. Check what a real QPJOBLOG holds for a typed password
- [ ] Lockout and expiry: what the real host does on the QMAXSIGN-th bad password (which message, which screen), what the disabled profile says, and the real Change Password display. All inferred. Needs a made-up or deliberately sacrificed profile, so a human decides
- [ ] Confirm CPF1107, CPF1118, CPF1394 (needs a deliberate wrong-password attempt, so a human decides, with a made-up user)
- [ ] Profile command message IDs and which condition raises each (CPF2204, CPF2217, CPF2228 and the rest are documented, not seen); safe read-only checks are an unknown command and DSPUSRPRF on your own profile
- [ ] The ID of "Not authorized to command" and what a limited user sees at a command line; the LMTCPB message wording
- [ ] The library gate rule for *ALLOBJ, what authority a new library gets, and whether QSYS authority matters to CRTLIB once the command is allowed (needs a profile that may run CRTLIB)
- [ ] Captures still missing for screens: the bare WRKOUTQ (Work with All Output Queues, did not answer on a shared host, needs a quieter way), WRKOUTQ options and F11 view 2, the third page of the Work with Job menu, the real SNDMSG prompt (no host answer last time, retry with a longer wait), ENDJOB confirm, CHGJOB prompt, option 3 copy (CRTDUPOBJ), WRKAUTL 2, F10 and F11 on the edit screen

## v2 and beyond

- Subfiles and windows once rpgle_library supports them
- Host servers (sign-on, database, file) as attack surface
- Exit points and adopted authority scenarios
- Blue-team dataset export (audit journal, QAUDJRN-style)
