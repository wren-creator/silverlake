     * PAYRUN.RPGLE -- the pay run. It adopts SECADMIN, who holds *ALL on
     * PAYROLL, and calls PAYCALC for the arithmetic. It calls PAYCALC by name
     * alone, so the library list decides which PAYCALC runs, and the first
     * library on the list that has one wins. QTEMP is on every list and nobody
     * but its own job can see into it.

     C                   CALL      'PAYCALC'
     C                   EVAL      *inlr = *on
     C                   RETURN
