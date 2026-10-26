# Silverlake roadmap

## v1

- [x] Phase 0: repo scaffold, lifecycle scripts, loopback guard, docs skeleton
- [x] Phase 1: 5250 core, telnet + TN5250E negotiation, encoder/decoder, declarative screens
- [ ] Phase 1 follow-ups: TLS listener, try real tn5250 and IBM Access clients, Query reply handling, 27x132 screens
- [ ] Phase 2: oracle harness, capture on a real IBM i, replay on Silverlake, diff structure
- [ ] Phase 3: sign-on, user profiles (*SECOFR vs normal), menus, CL dispatcher, QSYS.LIB object model in SQLite
- [ ] Phase 4: RPG and DDS through rpgle_library (EXFMT programs, seeded samples)
- [ ] Phase 5: vulnerable and secure modes, seeded weak configs, exposed services, scenarios, flag checker, instructor and trainee docs
- [ ] Silverlake 101 EPUB, same format as the Mainframe 10x series

## v2 and beyond

- Subfiles and windows once rpgle_library supports them
- Host servers (sign-on, database, file) as attack surface
- Exit points and adopted authority scenarios
- Blue-team dataset export (audit journal, QAUDJRN-style)
