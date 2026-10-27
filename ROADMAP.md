# Silverlake roadmap

## v1

- [x] Phase 0: repo scaffold, lifecycle scripts, loopback guard, docs skeleton
- [x] Phase 1: 5250 core, telnet + TN5250E negotiation, encoder/decoder, declarative screens
- [ ] Phase 1 follow-ups: TLS listener, try real tn5250 and IBM Access clients, Query reply handling, 27x132 screens
- [x] Phase 2: oracle harness, capture on a real IBM i, replay on Silverlake, diff structure
- [ ] Phase 2 follow-ups: confirm title and label columns and colors from a stock capture (positions came from a photo), configurable password length, authenticated captures (harness done, first real run pending), Query path against a real host, more scenarios as Phase 3 lands
- [x] Phase 3a: user profiles and the access model (five classes, eight special authorities, object authority), sign-on checks, seed-file assignment of any access level (docs/access-model.md)
- [x] Phase 3b: CRTUSRPRF, CHGUSRPRF, DSPUSRPRF, DLTUSRPRF, WRKUSRPRF, SIGNOFF from a command line as *SECADM, profiles as secured objects, changes saved in SQLite
- [ ] Phase 3b follow-ups: F4 prompting and keyword abbreviation, limited capabilities enforcement, password expiry and forced change, MAXSIGN lockout, adopted authority, more WRKUSRPRF options, DSPUSRPRF types
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
- [ ] Job leftovers: WRKJOB and DSPJOB options 11, 12, 14, 15, 16, page two of the menus and of the status and definition pages, DSPJOBLOG F10, WRKACTJOB options 7, 13 and keys F7, F10, F11, the real confirm for option 4 and prompt for option 2 (need captures, the oracle will not end or change jobs)
- [ ] Colors: a compare against the captures shows Silverlake draws option and value text white where the real host draws green (labels and values green, titles and More... white, prompts and keys blue). The job screens now match, most older screens do not. Do one pass over every screen against its capture
- [ ] Spool leftovers: WRKOUTQ and its capture, WRKSPLF options 1, 2, 4 (confirm), 7, 9, Find and F19/F20 on the display, attributes page two and F13, HLDSPLF/RLSSPLF, CRTOUTQ
- [x] Phase 3c-3c step 3: message queues (DSPMSG, SNDMSG, CLRMSGQ, QSYSOPR, per-user queues in QUSRSYS), from the PUB400 captures
- [x] CRTMSGQ, CHGMSGQ (DLVRY, SEV, TEXT) and DLTMSGQ from IBM's command pages, rules and inferences in docs/jobs-spool-messages.md
- [ ] Message leftovers: the real SNDMSG prompt (needs a longer wait), inquiry messages and replies, F11 remove one, WRKMSGQ, CHGMSGQ break program and *DFT delivery, RMVMSG, break delivery to a live session, work station queues
- [x] DSPOBJD basic list, full page two, and Add New Users (F6), from the PUB400 captures
- [ ] Work list options still to build: 3 (copy, CRTDUPOBJ), WRKAUTL 2 (needs a capture from a profile that may edit a list); edit screen F10 and F11 (the real host did not answer F10, retry with a longer wait); DSPOBJD page three and option 8, creation dates for non-library objects; F4 prompting, F11, F16 and F17 positioning, F17 and F18 top and bottom on WRKOBJOWN; capture the real WRKAUTL delete confirm and the F6 Add new users screen
- [ ] More object types (*DTAARA and *USRSPC next), *AUTL in the object table, generic names on RNMOBJ and CHGOBJD
- [ ] Confirm CPF1107, CPF1118, CPF1394 on a real system (needs a deliberate wrong-password attempt, so a human decides)
- [x] Phase 3c-3c complete: jobs, spool files and message queues, merged to main 2026-10-27
- [ ] Phase 4: RPG and DDS through rpgle_library (EXFMT programs, seeded samples)
- [ ] Phase 5: vulnerable and secure modes, seeded weak configs, exposed services, scenarios, flag checker, instructor and trainee docs
- [ ] Silverlake 101 EPUB, same format as the Mainframe 10x series

## Needs verification on a real system

Things Silverlake does from IBM's pages, memory or inference and has not seen on a real IBM i. Tick one when it has been checked, and fix the docs if the real system disagrees. "Write" means it changes something on a shared system, so it needs a human decision and fresh approval first (PUB400 rules: read only, human paced).

- [ ] CRTMSGQ, CHGMSGQ, DLTMSGQ: the completion messages (IDs and text), what authority a new queue gets under *LIBCRTAUT, whether *ADD to the library is what CRTMSGQ needs, and that *CHANGE cannot delete a queue. Write: one throwaway queue in the test account's own library, DSPOBJAUT on it, change its text, delete it
- [ ] Message queue reads: that DSPMSG needs only *USE (inferred, the page has no authority section), and that a user queue gets the library's create authority so QUSRSYS makes every queue world readable
- [ ] DSPJOB: that its refusal is CPF1071 like WRKJOB (used without seeing it), the pool id and type of job for non interactive jobs, and what page two of the status and definition pages holds
- [ ] DSPJOBLOG and WRKJOB: CPF2441 and CPF1071 wording, CPF2443 for an ended job (inferred), CPF2523 for a system job, and the QIBM_ACCESS_ALLOBJ_JOBLOG function usage that can also grant reading an *ALLOBJ job's log (not modeled)
- [ ] CHGJOB: that RUNPTY, TIMESLICE, PURGE, DFTWAIT, CPUTIME and MAXTMPSTG need *JOBCTL even on your own job, and CPF1337 as the refusal (inferred). Write
- [ ] Spool rules: the parts of CRTOUTQ's page that only came through as a summary, and the inferred OPRCTL, DSPDTA and AUTCHK behavior for other people's files
- [ ] Job log filing: that passwords are masked is Silverlake's choice, not something seen. Check what a real QPJOBLOG holds for a typed password
- [ ] Confirm CPF1107, CPF1118, CPF1394 (needs a deliberate wrong-password attempt, so a human decides, with a made-up user)
- [ ] Profile command message IDs and which condition raises each (CPF2204, CPF2217, CPF2228 and the rest are documented, not seen); safe read-only checks are an unknown command and DSPUSRPRF on your own profile
- [ ] The ID of "Not authorized to command" and what a limited user sees at a command line; the LMTCPB message wording
- [ ] The library gate rule for *ALLOBJ, what authority a new library gets, and whether QSYS authority matters to CRTLIB once the command is allowed (needs a profile that may run CRTLIB)
- [ ] Captures still missing for screens: WRKOUTQ, the real SNDMSG prompt (no host answer last time, retry with a longer wait), ENDJOB confirm, CHGJOB prompt, option 3 copy (CRTDUPOBJ), WRKAUTL 2, F10 and F11 on the edit screen

## v2 and beyond

- Subfiles and windows once rpgle_library supports them
- Host servers (sign-on, database, file) as attack surface
- Exit points and adopted authority scenarios
- Blue-team dataset export (audit journal, QAUDJRN-style)
