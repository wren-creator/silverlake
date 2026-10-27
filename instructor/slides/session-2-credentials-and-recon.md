# Session 2: Credentials and recon (group A)

## Slide 1: No exploit needed
- The most common IBM i finding is not a clever attack. It is a password that equals the profile name.

## Slide 2: every password is the profile name
- Sign on as OPERATOR with OPERATOR. Then QSECOFR with QSECOFR.
- Find the security officer's job log among its spooled files and read it.
- Look at `QPWDMINLEN` and `QPWDRQDDGT`. Why does the system allow this?

## Slide 3: service and legacy accounts
- SVCACCT, LEGACY and DEVADMIN hold special authorities nobody needs.
- Sign on as SVCACCT and read the vault file in APPLIB. Then ask who ever reviews this account.

## Slide 4: the operator's queue
- As STUDENT: `DSPMSG MSGQ(QSYSOPR)`.
- Job names, users, and a message with a passphrase in it. Public `*CHANGE` made it readable.

## Slide 5: Debrief
- What did each of these need? A guess, a forgotten account, a default.
- Flags: record the three you found. Say what authority or setting made each reachable.
