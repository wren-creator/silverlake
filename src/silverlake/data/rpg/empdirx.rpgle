     * EMPDIRX.RPGLE -- the staff directory, fixed. The code is the same, and an
     * override from the caller still redirects STAFF. What changed is the
     * owner: QDFTOWN holds no authority to PAYROLL, so the redirected open
     * is refused. Nothing a caller does can lend the program more than its
     * owner has.

     FEMPINQ    CF   E             WORKSTN
     FSTAFF     IF   E           K DISK

     C                   DOW       *in03 = *off
     C                   EXFMT     PAYLOOK
     C                   IF        *in03 = *off
     C     EMPNO         CHAIN     STAFF                              71
     C                   IF        *in71 = *on
     C                   EVAL      msg = 'No such employee'
     C                   ELSE
     C                   EVAL      msg = ' '
     C                   ENDIF
     C                   ENDIF
     C                   ENDDO
     C                   EVAL      *inlr = *on
     C                   RETURN
