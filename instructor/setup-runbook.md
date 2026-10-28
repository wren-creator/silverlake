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
- For the optional network session, `./start.sh --services` also needs 2001, 2121, 4449, 8476 and 2222 (ssh, only with asyncssh from `./setup.sh --ssh`) free, plus 5992, 2010, 2990 and 9476 if `./setup.sh` made a certificate (it needs openssl). Several ports differ from a real IBM i (5250 vs 23, 5992 vs 992, 2121 vs 21, 2990 vs 990, 4449 vs 449, 2222 vs 22), so students must give their tools the port. The table and the variables that move each port are in `docs/services.md`. `scenario.sh` keeps services on across its restart but not a custom port.
- Linux, macOS, or WSL2.

## Common failures

| Symptom | Cause | Fix |
|---|---|---|
| `start.sh` says the port is in use | something else on 5250, or on 2001, 2121, 4449 or 8476 with `--services` | use the port it suggests, or set the `SILVERLAKE_*_PORT` variable it names |
| TLS ports are off | no certificate, usually openssl was missing at setup | install openssl, then `./setup.sh --force-tls`; the log says "no TLS certificate" |
| A tool finds nothing on the standard port | Silverlake is on 5250, 2121 and 4449, not 23, 21 and 449 | give the tool the port, or see the table in `docs/services.md` |
| A lesson behaves oddly after a few tries | exploit leftovers (a copy, a profile, a changed salary) | `./scenario.sh reset <id>`, or `./reset.sh` for everything |
| Sign-on as OPERATOR or DEVELOPER fails in secure mode | `default-passwords` rotated them | passwords are in `./check-flags.sh --show`, derived from the instance secret |
| `scenario.sh` refuses | the server is running and would overwrite the change | use `scenario.sh`, not `python -m silverlake.scenarios`, it stops and restarts the server |
| New seeded objects are missing after an update | the saved state is older than the seed | `./reset.sh` |
| Students see flags that do not match your `--show` | they are on a different machine | score on the student's own machine |
