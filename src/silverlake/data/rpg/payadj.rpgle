     * PAYADJ.RPGLE -- sets one employee's salary. Written for HR, owned by
     * SECADMIN (who holds *ALL on PAYROLL) and compiled to adopt its owner.
     * It checks nothing about who is calling. The only thing between a
     * user and a raise is whether the user may CALL it.

     FPAYADJ    CF   E             WORKSTN
     FPAYROLL   UF   E           K DISK



     C                   DOW       *in03 = *off
     C                   EXFMT     PAYADJ
     C                   IF        *in03 = *off
     C     EMPNO         CHAIN     PAYROLL                            71
     C                   IF        *in71 = *on
     C                   EVAL      msg = 'No such employee'
     C                   ELSE
     C                   EVAL      salary = newsal
     C                   UPDATE    PAYREC
     C                   EVAL      msg = 'Salary changed'
     C                   ENDIF
     C                   ENDIF
     C                   ENDDO
     C                   EVAL      *inlr = *on
     C                   RETURN
