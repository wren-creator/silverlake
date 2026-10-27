     * RUNCMDX.RPGLE -- the same helper, fixed. Two changes: it only runs
     * commands from a short list it knows are harmless, and its owner is
     * QDFTOWN, which holds no special authority, so even a mistake in the
     * list cannot hand out QSECOFR.

     FRUNCMD    CF   E             WORKSTN

     D len             S             15  0 INZ(70)

     C                   EXFMT     RUNCMD
     C                   IF        CMD = 'CHGJOB JOBPTY(5)'
     C                   CALL      'QCMDEXC'
     C                   PARM                    CMD
     C                   PARM                    LEN
     C                   ENDIF
     C                   IF        CMD = 'RMVLIBLE LIB(APPLIB)'
     C                   CALL      'QCMDEXC'
     C                   PARM                    CMD
     C                   PARM                    LEN
     C                   ENDIF
     C                   EVAL      *inlr = *on
     C                   RETURN
