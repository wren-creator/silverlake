# Session 6 (optional): Network services (group D)

Needs `./start.sh --services`. Everything still binds to 127.0.0.1.

## Slide 1: Doors besides 5250
- An IBM i also answers on the network: a web console on 2001, FTP, and the host servers.
- They check the same profiles and the same authority as the 5250 side. A weak password follows the attacker in.

## Slide 2: Find it
- Scan 127.0.0.1 for 2001, or just browse to `http://127.0.0.1:2001/HTTPAdmin`. Sign in as STUDENT, password STUDENT.
- Note what the console tells you before and after sign-in: server header, realm, the About page.

## Slide 3: httpadmin-ssi-injection
- Create HTTP Server, description `<!--#exec cmd="DSPMSG MSGQ(QTMHHTTP)" -->`. Open Manage.
- The command ran as QTMHHTTP, not as STUDENT. Try the same command at the 5250 as STUDENT and compare.
- Silverlake models the class of bug, not IBM's real parameter, which is unpublished.

## Slide 4: ftp-limited-bypass
- Sign on to the 5250 as CLERK: no command line. Now `ftp 127.0.0.1 2121`, same user and password.
- `cd APPLIB`, `ls`, `get DAILYOPS`. Limited capability only ever applied to the menu.
- The password crossed the wire in clear text. Say so out loud.

## Slide 5: hostsvr-recon
- The mapper on 4449 names the sign-on server (`as-signon`), and the sign-on server on 8476 answers before any password.
- Read the release and the password level. Level 0 means case does not matter: try `student` in lower case at the 5250.
- Submit `V7R4M0/0`. Raise QPWDLVL with the lesson's secure state and the answer, and the lower case guess, both change.

## Slide 6: Fix and re-run
- `./scenario.sh set httpadmin-ssi-injection secure`. The About page shows the PTF and the description is escaped.
- Ask: what else should limit who can reach the console?

## Slide 7: Debrief
- Nothing here needed an exploit kit. A browser, a profile and a field that was trusted.
