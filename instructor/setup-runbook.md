# Silverlake 101: setup runbook

## Before the class

1. On a machine like the students' machines:
   ```bash
   git clone <the repo>
   cd silverlake
   ./setup.sh        # venv, install, makes .instance-secret
   ./start.sh
   ./status.sh       # up, loopback only
   ```
2. Connect a client and sign on as STUDENT with the password STUDENT. If you reach the sign-on screen, the range is good.
3. Run the whole exploit set once so you know what a good run looks like: `.venv/bin/python -m pytest tests/test_exploits.py -q`.
4. Print `docs/scenarios-trainee.md` and `instructor/rubric.md`. Keep `docs/scenarios.md` to yourself.

## How flags work in a room

Every machine has its own `.instance-secret`, so every machine has its own flags. A flag found on one student's machine is no good on another's. Score on the machine the student worked on:

```bash
./check-flags.sh submission.txt      # with the server running, for the state lessons
./check-flags.sh --show              # the instructor's answers, including the secure-state passwords
```

The submission file is one `lesson-id = FLAG{...}` per line. State lessons (a new `*ALLOBJ` profile, a changed salary, STUDENT able to read PAYROLL, a readable copy of PAYROLL) need no submission, they are read from the saved state. Never commit or share `.instance-secret`.

## Host requirements

- Python 3.12 or newer, and about 200 MB of disk. No Docker, no IBM media.
- Port 5250 free on 127.0.0.1. `./start.sh --port 5251` if it is not.
- Linux, macOS, or WSL2.

## Common failures

| Symptom | Cause | Fix |
|---|---|---|
| `start.sh` says the port is in use | something else on 5250 | use the port it suggests |
| A lesson behaves oddly after a few tries | exploit leftovers (a copy, a profile, a changed salary) | `./scenario.sh reset <id>`, or `./reset.sh` for everything |
| Sign-on as OPERATOR or DEVELOPER fails in secure mode | `default-passwords` rotated them | passwords are in `./check-flags.sh --show`, derived from the instance secret |
| `scenario.sh` refuses | the server is running and would overwrite the change | use `scenario.sh`, not `python -m silverlake.scenarios`, it stops and restarts the server |
| New seeded objects are missing after an update | the saved state is older than the seed | `./reset.sh` |
| Students see flags that do not match your `--show` | they are on a different machine | score on the student's own machine |
