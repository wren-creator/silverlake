     * RUNCMD.RPGLE -- a helper somebody wrote so support staff could
     * "run a command without a command line". It passes whatever is
     * typed to QCMDEXC. Compiled to adopt its owner, QSECOFR, so the
     * command runs with QSECOFR's authority. That is the whole bug.

     FRUNCMD    CF   E             WORKSTN

     D len             S             15  0 INZ(70)

     C                   EXFMT     RUNCMD
     C                   CALL      'QCMDEXC'
     C                   PARM                    CMD
     C                   PARM                    LEN
     C                   EVAL      *inlr = *on
     C                   RETURN
