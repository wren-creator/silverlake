# Silverlake roadmap

## v1

- [x] Phase 0: repo scaffold, lifecycle scripts, loopback guard, docs skeleton
- [x] Phase 1: 5250 core, telnet + TN5250E negotiation, encoder/decoder, declarative screens
- [ ] Phase 1 follow-ups: TLS listener, try real tn5250 and IBM Access clients, Query reply handling, 27x132 screens
- [x] Phase 2: oracle harness, capture on a real IBM i, replay on Silverlake, diff structure
- [ ] Phase 2 follow-ups: confirm title and label columns and colors from a stock capture (positions came from a photo), configurable password length, authenticated captures, Query path against a real host, more scenarios as Phase 3 lands
- [x] Phase 3a: user profiles and the access model (five classes, eight special authorities, object authority), sign-on checks, seed-file assignment of any access level (docs/access-model.md)
- [x] Phase 3b: CRTUSRPRF, CHGUSRPRF, DSPUSRPRF, DLTUSRPRF, WRKUSRPRF, SIGNOFF from a command line as *SECADM, profiles as secured objects, changes saved in SQLite
- [ ] Phase 3b follow-ups: F4 prompting and keyword abbreviation, limited capabilities enforcement, password expiry and forced change, MAXSIGN lockout, adopted authority, more WRKUSRPRF options, DSPUSRPRF types
- [ ] Confirm the profile command message IDs and which condition raises each (CPF2204, CPF2217, CPF2228 and the rest are documented, not seen); safe read-only checks on PUB400 are an unknown command and DSPUSRPRF on your own profile
- [ ] Phase 3c: menus, the rest of the CL dispatcher, QSYS.LIB object model in SQLite
- [ ] Confirm CPF1107, CPF1118, CPF1394 on a real system (needs a deliberate wrong-password attempt, so a human decides)
- [ ] Phase 4: RPG and DDS through rpgle_library (EXFMT programs, seeded samples)
- [ ] Phase 5: vulnerable and secure modes, seeded weak configs, exposed services, scenarios, flag checker, instructor and trainee docs
- [ ] Silverlake 101 EPUB, same format as the Mainframe 10x series

## v2 and beyond

- Subfiles and windows once rpgle_library supports them
- Host servers (sign-on, database, file) as attack surface
- Exit points and adopted authority scenarios
- Blue-team dataset export (audit journal, QAUDJRN-style)
