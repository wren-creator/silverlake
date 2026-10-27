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
- [ ] Spool leftovers: WRKOUTQ and its capture, WRKSPLF options 1, 2, 4 (confirm), 7, 9, Find and F19/F20 on the display, attributes page two and F13, HLDSPLF/RLSSPLF, CRTOUTQ
- [x] Phase 3c-3c step 3: message queues (DSPMSG, SNDMSG, CLRMSGQ, QSYSOPR, per-user queues in QUSRSYS), from the PUB400 captures
- [ ] Message leftovers: the real SNDMSG prompt (needs a longer wait), inquiry messages and replies, F11 remove one, WRKMSGQ, CRTMSGQ/CHGMSGQ/DLTMSGQ, RMVMSG, break delivery to a live session, work station queues
- [x] DSPOBJD basic list, full page two, and Add New Users (F6), from the PUB400 captures
- [ ] Work list options still to build: 3 (copy, CRTDUPOBJ), WRKAUTL 2 (needs a capture from a profile that may edit a list); edit screen F10 and F11 (the real host did not answer F10, retry with a longer wait); DSPOBJD page three and option 8, creation dates for non-library objects; F4 prompting, F11, F16 and F17 positioning, F17 and F18 top and bottom on WRKOBJOWN; capture the real WRKAUTL delete confirm and the F6 Add new users screen
- [ ] More object types (*DTAARA and *USRSPC next), *AUTL in the object table, generic names on RNMOBJ and CHGOBJD
- [ ] Confirm CPF1107, CPF1118, CPF1394 on a real system (needs a deliberate wrong-password attempt, so a human decides)
- [x] Phase 3c-3c complete: jobs, spool files and message queues, merged to main 2026-10-27
- [ ] Phase 4: RPG and DDS through rpgle_library (EXFMT programs, seeded samples)
- [ ] Phase 5: vulnerable and secure modes, seeded weak configs, exposed services, scenarios, flag checker, instructor and trainee docs
- [ ] Silverlake 101 EPUB, same format as the Mainframe 10x series

## v2 and beyond

- Subfiles and windows once rpgle_library supports them
- Host servers (sign-on, database, file) as attack surface
- Exit points and adopted authority scenarios
- Blue-team dataset export (audit journal, QAUDJRN-style)
