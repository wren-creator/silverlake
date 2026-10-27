"""Flags: proof that a trainee did the lesson, and the checker that scores them.

Every range has an instance secret, kept in `.instance-secret` at the repo root (never committed, and not in
`state/`, so `reset.sh` does not change it). A flag is derived from it, one per scenario:

    FLAG{<first 12 hex of HMAC-SHA256(secret, scenario id)>}

so flags cannot be guessed from the repo, differ between ranges, and come out the same after a reset. Two
kinds of lesson:

  * `text`: the flag is planted in the object the exploit reaches (a spooled report, a locked file, a message,
    a printed heading). The seed holds `@@FLAG:<scenario id>@@` where it goes and the loader fills it in. The
    trainee submits the flag.
  * `state`: the win is a change (a security officer made, authority granted, a salary moved). The checker reads
    the saved state and nothing is submitted.

  * `fact`: the lesson is recon, so the answer is something the trainee reads off the wire (an OS release, a
    password level) and submits. The checker compares it with what the saved state holds now.

Secure-state passwords are derived the same way (`secret:<label>` in a scenario value) so they are not in the
repo either. `python -m silverlake.flags show` prints everything an instructor needs.

A submission is lines like `runcmd-qcmdexc=done` (any text for a `state` lesson),
`qsysopr-recon=FLAG{0123456789ab}` or `hostsvr-recon=V7R4M0/0` (a `fact`). The checker reads the saved state, so it works with the server running."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import os
import re
import secrets
import sys
from pathlib import Path

from .system import profiles, state
from .system.authority import Auth

SECRET_FILE = Path(__file__).resolve().parent.parent.parent / ".instance-secret"
PLACEHOLDER = re.compile(r"@@FLAG:([a-z0-9-]+)@@")


def secret() -> bytes:
    """The instance secret: SILVERLAKE_INSTANCE_SECRET if set (tests use it), else the file, made on first use."""
    env = os.environ.get("SILVERLAKE_INSTANCE_SECRET")
    if env:
        return env.encode()
    path = Path(os.environ.get("SILVERLAKE_SECRET_FILE", SECRET_FILE))
    if not path.exists():
        path.write_text(secrets.token_hex(32) + "\n")
        path.chmod(0o600)
    return path.read_text().strip().encode()


def _mac(label: str) -> str:
    return hmac.new(secret(), label.encode(), hashlib.sha256).hexdigest()


def flag(scenario_id: str) -> str:
    return f"FLAG{{{_mac(scenario_id)[:12]}}}"


def password(label: str) -> str:
    """A secure-state password: 9 characters, with a digit, inside the seed's 10 character limit."""
    return f"Sl{_mac('pw:' + label)[:6]}9"


def fill(text: str) -> str:
    """The seed text with each @@FLAG:id@@ replaced by that scenario's flag."""
    return PLACEHOLDER.sub(lambda m: flag(m.group(1)), text)


# -- what each state lesson looks at --------------------------------------------------------------------------------

def _payroll(store):
    return store.objects.get(("APPLIB", "PAYROLL", "*FILE"))


def _new_privileged_profile(store):
    seed = set(profiles.load().profiles)
    for p in store.profiles.values():
        if p.name not in seed and profiles.SpecialAuthority.ALLOBJ in store.special_authorities(p):
            return True, f"profile {p.name} exists and holds *ALLOBJ"
    return False, "no new profile with *ALLOBJ"


def _salary_raised(store):
    pay = _payroll(store)
    row = next((r for r in (pay.data.get("records", []) if pay else []) if r.get("EMPNO") == 10004), None)
    return bool(row and row.get("SALARY") == 99999), "EMPNO 10004 SALARY is " + (str(row.get("SALARY")) if row else "missing")


def _student_reads_payroll(store):
    pay, student = _payroll(store), store.get("STUDENT")
    ok = bool(pay and student and Auth.READ in store.authority_to_object(student, pay))
    return ok, "STUDENT " + ("can" if ok else "cannot") + " read APPLIB/PAYROLL"


def _readable_copy(store):
    seed = set(profiles.load().objects)
    pay, student = _payroll(store), store.get("STUDENT")
    for key, obj in store.objects.items():
        if (key not in seed and obj.type == "*FILE" and obj.data.get("records") == pay.data.get("records")
                and Auth.READ in store.authority_to_object(student, obj)):
            return True, f"{key[0]}/{key[1]} is a copy of PAYROLL that STUDENT can read"
    return False, "no readable copy of PAYROLL"


def _release_and_pwdlevel(store) -> str:
    from .net import hostsvr
    return f"{hostsvr.OS_LEVEL}/{store.system.qpwdlvl}"


FACTS = {"release_and_pwdlevel": _release_and_pwdlevel}

CHECKS = {"new_privileged_profile": _new_privileged_profile, "salary_raised": _salary_raised,
          "student_reads_payroll": _student_reads_payroll, "readable_copy": _readable_copy}


# -- scoring --------------------------------------------------------------------------------------------------------

def lessons(reg=None) -> list:
    from . import scenarios
    return [s for s in (reg or scenarios.registry()).values() if s.flag]


def parse_submission(text: str) -> dict[str, str]:
    out = {}
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            out[k.strip().lower()] = v.strip()
    return out


def score(store, submission: dict[str, str], reg=None) -> list[tuple[str, bool, str]]:
    """(scenario id, solved, detail) for every lesson that has a flag."""
    rows = []
    for s in lessons(reg):
        if s.flag["kind"] == "text":
            given = submission.get(s.id, "")
            ok = bool(given) and hmac.compare_digest(given.encode(), flag(s.id).encode())
            rows.append((s.id, ok, "flag correct" if ok else f"wrong or missing (got: {given or '<none>'})"))
        elif s.flag["kind"] == "fact":
            given, want = submission.get(s.id, ""), FACTS[s.flag["fact"]](store)
            ok = bool(given) and hmac.compare_digest(given.upper().encode(), want.upper().encode())
            rows.append((s.id, ok, "answer correct" if ok else f"wrong or missing (got: {given or '<none>'})"))
        else:
            ok, detail = CHECKS[s.flag["check"]](store)
            rows.append((s.id, ok, detail))
    return rows


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="silverlake.flags", description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init", help="make the instance secret if there is none")
    sub.add_parser("show", help="instructor: every flag, state check and secure password")
    ck = sub.add_parser("check", help="score a submission")
    ck.add_argument("submission", nargs="?", default="submission.txt")
    args = ap.parse_args(argv)
    from . import scenarios
    reg = scenarios.registry()
    if args.cmd == "init":
        secret()
        print(f"instance secret is in {os.environ.get('SILVERLAKE_SECRET_FILE', SECRET_FILE)}")
        return 0
    if args.cmd == "show":
        store_for_show, db = state.open_store(os.environ.get("SILVERLAKE_PROFILES"),
                                              os.environ.get("SILVERLAKE_STATE_DIR", "state"))
        db.close()
        for s in lessons(reg):
            what = {"text": lambda: flag(s.id), "fact": lambda: FACTS[s.flag["fact"]](store_for_show)}.get(
                s.flag["kind"], lambda: f"state check {s.flag['check']}")()
            print(f"{s.id:<26} {what:<22} {s.flag['task']}")
        print("\nsecure state passwords:")
        for label in ("QSECOFR", "SECADMIN", "OPERATOR", "DEVELOPER"):
            print(f"  {label:<10} {password(label)}")
        return 0
    path = Path(args.submission)
    submission = parse_submission(path.read_text()) if path.exists() else {}
    if not path.exists() and any(s.flag["kind"] in ("text", "fact") for s in lessons(reg)):
        print(f"no submission file {path}; only the lessons the state can prove are scored", file=sys.stderr)
    store, db = state.open_store(os.environ.get("SILVERLAKE_PROFILES"), os.environ.get("SILVERLAKE_STATE_DIR", "state"))
    try:
        rows = score(store, submission, reg)
    finally:
        db.close()
    for sid, ok, detail in rows:
        print(f"  [{'+' if ok else 'x'}] {sid:<26} {detail}")
    solved = sum(1 for _, ok, _ in rows if ok)
    print(f"\n{solved} of {len(rows)}")
    return 0 if solved == len(rows) else 1


if __name__ == "__main__":
    sys.exit(main())
