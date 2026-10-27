# Session 4: Programs and the library list (group C)

## Slide 1: One idea, four times
- A program runs with its owner's authority. What the caller controls, the caller controls with that authority.

## Slide 2: RUNCMD
- `ADDLIBLE APPLIB`, `CALL PGM(APPLIB/RUNCMD)`.
- Type `CRTUSRPRF USRPRF(EVIL) PASSWORD(EVIL) USRCLS(*SECOFR)`.
- A user who could not make a profile just made a security officer.

## Slide 3: PAYADJ
- `CALL PGM(APPLIB/PAYADJ)`, employee 10004, salary 99999.
- The caller chose a number, the owner's authority wrote it.

## Slide 4: EMPDIR and OVRDBF
- `OVRDBF FILE(STAFF) TOFILE(APPLIB/PAYROLL)`, then `CALL PGM(APPLIB/EMPDIR)`, employee 10099.
- The caller chose the file. The program opened it as its owner.

## Slide 5: PAYRUN and QTEMP
- PAYRUN calls PAYCALC with no library. Put your own PAYCALC in QTEMP, then call PAYRUN.
- The caller chose the program by choosing the library list.
- Students write the PAYCALC with `CRTSRCPF`, the editor and `CRTBNDRPG`. Give a hint, not the source.

## Slide 6: Debrief
- The four fixes: no powerful owner, run as the caller, an owner who holds nothing, a program called with its library.
