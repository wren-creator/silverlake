     * PAYRUNX.RPGLE -- the pay run, fixed. The same program, but it names the
     * library of the program it calls, so the list cannot choose for it.

     D prog            S             20    INZ('APPLIB/PAYCALC')

     C                   CALL      prog
     C                   EVAL      *inlr = *on
     C                   RETURN
