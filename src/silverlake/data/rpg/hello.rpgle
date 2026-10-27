     * HELLO.RPGLE -- the smallest program that shows a screen. Compile it
     * with CRTBNDRPG PGM(yourlib/HELLO) SRCFILE(SRCLIB/QRPGLESRC), then
     * CALL it. HELLOD, its display file, is a member of QDDSSRC.

     FHELLOD    CF   E             WORKSTN

     C                   EVAL      who = 'world'
     C                   EXFMT     GREET
     C                   EVAL      *inlr = *on
     C                   RETURN
