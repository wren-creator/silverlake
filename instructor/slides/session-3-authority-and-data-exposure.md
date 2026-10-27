# Session 3: Authority and data exposure (group B)

## Slide 1: Data leaves through normal features
- Menus, spool queues, copies. Nothing here breaks in, it just reads or copies what it was allowed to.

## Slide 2: the clerk's menu
- Sign on as CLERK. There is no command line.
- Choose option 9. Command entry opens. `DSPPFM FILE(APPLIB/MAINTLOG)` reads what the clerk may read.
- The profile was limited, the menu was not.

## Slide 3: the default queue
- As STUDENT: `WRKOUTQ OUTQ(QGPL/QPRINT)`. Open the payroll register.
- `DSPDTA(*YES)` shows data to anyone who can reach the queue.

## Slide 4: the report that prints to the wrong place
- As OPERATOR: `CALL PGM(REGRPT)`. As STUDENT, find it on QPRINT and read the heading.
- Compare `REGRPTX`, which prints to a queue with restricted authority.

## Slide 5: CPYF
- As OPERATOR: `CPYF FROMFILE(APPLIB/PAYROLL) TOFILE(SCRATCH/LOOT) CRTFILE(*YES)`.
- As STUDENT: `DSPPFM FILE(SCRATCH/LOOT)`. The copy is yours and nobody locked it.

## Slide 6: Debrief
- What is common to all four? Read access was enough. Authority to read is authority to move.
