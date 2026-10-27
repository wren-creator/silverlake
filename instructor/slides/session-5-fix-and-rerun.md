# Session 5: Fix and re-run

## Slide 1: The other half of the course
- You attacked a range with eleven weaknesses. Now you close them and prove it.

## Slide 2: Switching
- `./scenario.sh list` shows each lesson and its state.
- `./scenario.sh set <id> secure` fixes one. `./scenario.sh reset <id>` puts it back and clears what the exploit left.
- Every switch restarts the server and signs everyone off.

## Slide 3: The routine
- Pick a lesson. Run the exploit. Fix the lesson. Run it again. Write down where it dies and why.
- Dies at sign-on, at a `Not authorized` message, at an empty queue, at a program that is not found. Name the mechanism.

## Slide 4: Gotchas
- `default-passwords` secure rotates OPERATOR and DEVELOPER. Get the new ones from the instructor.
- Reset between lessons so leftovers do not confuse the result.

## Slide 5: The write-up
- Each lesson: narrative, evidence, impact, remediation. Hand out `rubric.md`.
- Be honest about what is simulated. Check on a real system before telling anyone it is true there.

## Slide 6: Close
- None of the fixes were exotic. The attacks needed almost nothing. That gap is the course.
