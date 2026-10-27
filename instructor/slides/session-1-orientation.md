# Session 1: Orientation, objects and authority

## Slide 1: What you are looking at
- Silverlake is a simulator of an IBM i security range. Nothing here is IBM code.
- It binds to 127.0.0.1 only. `./status.sh` proves it.
- Everything you do works on the range and nowhere else. That is the authorised use rule.

## Slide 2: Sign on
- Connect a 5250 client to 127.0.0.1:5250. Sign on as STUDENT, password STUDENT.
- Three bad passwords disable a profile. An expired password forces a change.

## Slide 3: Everything is an object
- Libraries hold objects: files, programs, queues, menus. Each has an owner and an authority.
- `WRKOBJ`, `DSPOBJAUT OBJ(APPLIB/PAYROLL) OBJTYPE(*FILE)`, `WRKUSRPRF`
- Public authority is what everyone gets. Private authority is a named exception. Special authorities (`*ALLOBJ`, `*SECADM`, `*JOBCTL`) skip the object checks.

## Slide 4: The library list
- A bare program name is found by walking the library list. `DSPLIBL` shows it.
- QTEMP is every job's own library and sits ahead of a library added with `ADDLIBLE ... *LAST`.
- Remember this for Session 4.

## Slide 5: Adopted authority
- A program can run with its owner's authority instead of the caller's.
- Useful: a clerk can run a payroll report without touching the file. Dangerous: whatever the program lets the caller choose, runs as the owner.

## Slide 6: Exercise
- As STUDENT, write down what you can and cannot read in APPLIB, and what you can run.
- Collect the notes. Compare them with your results after Session 4.
