     * PAYLOOK.RPGLE -- looks one employee up in PAYROLL. PAYROLL is locked
     * to everyone except payroll staff, so this program is compiled to adopt
     * its owner (OPERATOR, who may read the file) and anyone may call it to
     * see a record. It cannot change anything, because its owner cannot.

     FPAYLOOK   CF   E             WORKSTN
     FPAYROLL   IF   E           K DISK

     C                   DOW       *in03 = *off
     C                   EXFMT     PAYLOOK
     C                   IF        *in03 = *off
     C     EMPNO         CHAIN     PAYROLL                            71
     C                   IF        *in71 = *on
     C                   EVAL      msg = 'No such employee'
     C                   ELSE
     C                   EVAL      msg = ' '
     C                   ENDIF
     C                   ENDIF
     C                   ENDDO
     C                   EVAL      *inlr = *on
     C                   RETURN
