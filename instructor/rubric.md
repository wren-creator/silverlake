# Silverlake 101: capstone grading rubric

The deliverable is a write-up: the eleven lessons attacked on the vulnerable range, then proof that each one dies on the secure range. Score out of 100.

## Exploits executed (30)

| Points | Criteria |
|---|---|
| 30 | At least ten lessons run, each with the screen or output that proves it and what it means for the data |
| 20 | Seven to nine lessons, evidence shown |
| 10 | Exploits run but the evidence is missing or not tied to a consequence |
| 0 | Not attempted, or run against something other than the range |

Flags can back this up: `./check-flags.sh` gives a per lesson result.

## Write-up quality (25)

| Points | Criteria |
|---|---|
| 25 | Narrative, evidence, impact and remediation for each lesson, readable by a manager and an auditor, exact commands included |
| 15 | All four parts present, thin in impact or remediation |
| 8 | Reads as a command log |
| 0 | Not submitted |

## Remediation and mechanism (25)

| Points | Criteria |
|---|---|
| 25 | Every lesson names the mechanism (adopted authority, library list order, public authority on a queue, special authority held by a service account, and so on) and the fix, in terms of what to change on a real system |
| 15 | Fixes named, mechanism vague |
| 8 | Generic advice ("tighten security") |
| 0 | Absent |

## Secure range proof (20)

| Points | Criteria |
|---|---|
| 20 | Re-ran every exploit after the fix and recorded where it dies: refused sign-on, `Not authorized` message, empty queue, no such program |
| 10 | Showed that they fail but not why |
| 0 | Not attempted |

## Automatic deductions

- minus 20: any command or finding aimed at a real system rather than the range
- minus 10: no statement of the authorised use rule
- minus 5 each: a claimed effect the simulator does not produce (check against `docs/scenarios.md`)

## Notes for the grader

Honest limits earn credit. Silverlake is a behavioral simulator written clean room. Some wording and some authority rules come from IBM's documentation, not from a real system, and `ROADMAP.md` keeps a list of what has not been verified on real hardware. A report that says "this is what the simulator does, check it on a real system before you tell a client" has understood the tool. A report that presents simulator output as proof about a real IBM i has not.
