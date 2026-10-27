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

## Slide 4: Fix and re-run
- `./scenario.sh set httpadmin-ssi-injection secure`. The About page shows the PTF and the description is escaped.
- Ask: what else should limit who can reach the console?

## Slide 5: Debrief
- Nothing here needed an exploit kit. A browser, a profile and a field that was trusted.
