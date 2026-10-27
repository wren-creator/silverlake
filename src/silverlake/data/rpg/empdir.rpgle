     * EMPDIR.RPGLE -- the staff directory. It reads STAFF, a public file, and
     * adopts its owner (OPERATOR) because it was copied from the payroll
     * lookup. It opens STAFF by name and trusts that the name means STAFF.
     * An override from the caller says otherwise.

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
