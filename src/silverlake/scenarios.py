"""Scenarios: the range's lessons, each switchable between a vulnerable and a secure state.

The base seed (data/profiles.toml) is the vulnerable range. Every lesson is a file in data/scenarios/ that
lists what its fix changes, each change with both its vulnerable and its secure value:

    [[change]]
    target = "object:APPLIB/RUNCMD/*PGM"      # object:LIB/NAME/TYPE, profile:NAME or system
    field = "owner"                           # a dotted path: owner, public, data.usrprf, private.STUDENT
    vulnerable = "QSECOFR"
    secure = "QDFTOWN"

so a lesson can be flipped either way and a test can check the vulnerable values still match the seed. The
value "*UNSET" means the field is absent, and "file:name.rpgle" for data.source reads that file from data/rpg.
`[cleanup]` says what an exploit leaves behind that `reset` should clear: objects to restore from the seed
(`restore`), objects it made (`remove_new`, with * allowed in the library and name), profiles it made
(`remove_new_profiles`) and spooled files it made (`remove_new_spool`).

The state of each lesson lives in the store (`store.scenarios`), so it is saved with everything else. The
command line, `python -m silverlake.scenarios`, changes the saved state and refuses while the server runs,
because a running server would write its own copy over the change. `./scenario.sh` stops the server, runs
this, and starts it again."""

from __future__ import annotations

import argparse
import fnmatch
import os
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from . import flags
from .system import profiles, state
from .system.authority import UserClass, parse_auth
from .system.profiles import ProfileStore

DATA = Path(__file__).resolve().parent / "data"
UNSET = "*UNSET"
STATES = ("vulnerable", "secure")
GROUPS = {"A": "Reconnaissance and credentials", "B": "Authority and data exposure", "C": "Programs and the library list",
          "D": "Network services (start with ./start.sh --services)"}


class ScenarioError(ValueError):
    pass


@dataclass
class Change:
    target: str
    field: str
    vulnerable: object
    secure: object


@dataclass
class Scenario:
    id: str
    title: str
    group: str
    summary: str
    changes: list[Change] = field(default_factory=list)
    cleanup: dict = field(default_factory=dict)
    flag: dict = field(default_factory=dict)       # {kind: text|state, check: name, task: what to do}
    doc: dict = field(default_factory=dict)        # the prose of docs/scenarios.md, see scenario_docs.py


def registry(directory: Path | None = None) -> dict[str, Scenario]:
    """Every scenario in the directory, by id, in file order."""
    found: dict[str, Scenario] = {}
    for path in sorted((directory or DATA / "scenarios").glob("*.toml")):
        try:
            raw = tomllib.loads(path.read_text())
        except (OSError, tomllib.TOMLDecodeError) as exc:
            raise ScenarioError(f"cannot read {path.name}: {exc}") from exc
        sid = raw.get("id", "")
        if not sid or sid != path.stem:
            raise ScenarioError(f"{path.name}: id must be {path.stem!r}")
        if raw.get("group") not in GROUPS:
            raise ScenarioError(f"{path.name}: group must be one of {', '.join(GROUPS)}")
        changes = []
        for c in raw.get("change", []):
            if not {"target", "field", "vulnerable", "secure"} <= set(c):
                raise ScenarioError(f"{path.name}: a change needs target, field, vulnerable and secure")
            changes.append(Change(c["target"], c["field"], c["vulnerable"], c["secure"]))
        found[sid] = Scenario(sid, raw.get("title", sid), raw["group"], raw.get("summary", ""), changes,
                              raw.get("cleanup", {}), raw.get("flag", {}), raw.get("doc", {}))
    return found


# -- reading and writing one field ----------------------------------------------------------------------------

def _object(store: ProfileStore, target: str):
    lib, name, typ = (target.split(":", 1)[1].split("/") + ["", "", ""])[:3]
    obj = store.objects.get((lib.upper(), name.upper(), typ.upper()))
    if obj is None:
        raise ScenarioError(f"{target}: no such object")
    return obj


def _value(raw):
    if isinstance(raw, str) and raw.startswith("file:"):
        return flags.fill((DATA / "rpg" / raw[5:]).read_text())
    if isinstance(raw, str) and raw.startswith("secret:"):
        return flags.password(raw[7:])
    return raw


def _from_object(obj, path: str):
    head, _, rest = path.partition(".")
    if head == "data":
        return obj.data.get(rest, UNSET)
    if head == "private":
        return _auth_name(obj.private[rest]) if rest in obj.private else UNSET
    if head == "public":
        return "*AUTL" if obj.public is None else _auth_name(obj.public)
    return getattr(obj, head)


def _auth_name(auth) -> str:
    from .system.authority import name_auth
    return name_auth(auth)


def get(store: ProfileStore, change: Change):
    """The current value of the field a change names."""
    kind = change.target.split(":", 1)[0]
    if kind == "object":
        return _from_object(_object(store, change.target), change.field)
    if kind == "profile":
        p = store.get(change.target.split(":", 1)[1])
        if p is None:
            raise ScenarioError(f"{change.target}: no such profile")
        v = getattr(p, change.field)
        if change.field == "special_authorities":
            return "*USRCLS" if v is None else (sorted(a.value for a in v) or "*NONE")
        return v.value if isinstance(v, UserClass) else v
    return getattr(store.system, change.field)


def put(store: ProfileStore, change: Change, raw) -> None:
    """Set the field a change names to `raw`, one of its two values."""
    kind = change.target.split(":", 1)[0]
    raw = _value(raw)
    if kind == "object":
        obj = _object(store, change.target)
        head, _, rest = change.field.partition(".")
        if head == "data":
            if raw == UNSET:
                obj.data.pop(rest, None)
            else:
                obj.data[rest] = raw
        elif head == "private":
            if raw == UNSET:
                obj.private.pop(rest, None)
            else:
                obj.private[rest] = parse_auth(raw)
        elif head == "public":
            obj.public = None if raw == "*AUTL" else parse_auth(raw)
        elif head == "owner":
            obj.owner = raw
        elif head in ("autl", "text"):
            setattr(obj, head, None if raw == UNSET else raw)
        else:
            raise ScenarioError(f"{change.target}: cannot change {change.field}")
    elif kind == "profile":
        p = store.get(change.target.split(":", 1)[1])
        if p is None:
            raise ScenarioError(f"{change.target}: no such profile")
        if change.field == "special_authorities":
            p.special_authorities = profiles._special(None if raw == "*USRCLS" else raw, p.name)
        elif change.field == "user_class":
            p.user_class = UserClass(raw)
        elif change.field in ("password", "status", "limited_capabilities", "group_profile", "initial_menu"):
            setattr(p, change.field, None if raw == "*NONE" and change.field == "password" else raw)
        else:
            raise ScenarioError(f"{change.target}: cannot change {change.field}")
    elif kind == "system":
        if not hasattr(store.system, change.field):
            raise ScenarioError(f"system has no {change.field}")
        setattr(store.system, change.field, raw)
    else:
        raise ScenarioError(f"{change.target}: target must start object:, profile: or system")


# -- applying a state ---------------------------------------------------------------------------------------------

def apply(store: ProfileStore, scenario: Scenario, to: str) -> None:
    if to not in STATES:
        raise ScenarioError(f"state must be one of {', '.join(STATES)}")
    for change in scenario.changes:
        put(store, change, getattr(change, to))
    store.scenarios[scenario.id] = to


def current(store: ProfileStore, sid: str) -> str:
    return store.scenarios.get(sid, "vulnerable")


def _seed_store() -> ProfileStore:
    return profiles.load()


def cleanup(store: ProfileStore, scenario: Scenario) -> list[str]:
    """What an exploit left behind, put back. Returns a line for each thing done."""
    done = []
    c = scenario.cleanup
    if c.get("restore"):
        seed = _seed_store()
        for target in c["restore"]:
            lib, name, typ = target.split(":", 1)[1].split("/")
            key = (lib, name, typ)
            if key in seed.objects:
                store.objects[key] = seed.objects[key]
                done.append(f"restored {target}")
    for pattern in c.get("remove_new", []):
        lib, name, typ = pattern.split(":", 1)[1].split("/")
        seed_keys = set(_seed_store().objects)
        for key in [k for k in store.objects if k not in seed_keys and fnmatch.fnmatchcase(k[0], lib)
                    and fnmatch.fnmatchcase(k[1], name) and fnmatch.fnmatchcase(k[2], typ)]:
            del store.objects[key]
            done.append(f"removed {key[0]}/{key[1]} {key[2]}")
    if c.get("remove_new_profiles"):
        seed_names = set(_seed_store().profiles)
        for name in [n for n in store.profiles if n not in seed_names]:
            del store.profiles[name]
            done.append(f"removed profile {name}")
    if c.get("remove_new_spool"):
        seed_ids = {(f.name, f.user, f.job_number) for f in _seed_store().spool}
        keep = [f for f in store.spool if (f.name, f.user, f.job_number) in seed_ids]
        if len(keep) != len(store.spool):
            done.append(f"removed {len(store.spool) - len(keep)} spooled files")
            store.spool[:] = keep
    return done


def reset(store: ProfileStore, scenario: Scenario) -> list[str]:
    """Back to the vulnerable state with the exploit's leftovers cleared."""
    apply(store, scenario, "vulnerable")
    return cleanup(store, scenario)


def set_mode(store: ProfileStore, to: str, reg: dict[str, Scenario] | None = None) -> None:
    """The whole range one way or the other."""
    for s in (reg or registry()).values():
        apply(store, s, to)
    store.system.mode = to


# -- command line ----------------------------------------------------------------------------------------------------

def _open():
    return state.open_store(os.environ.get("SILVERLAKE_PROFILES"), os.environ.get("SILVERLAKE_STATE_DIR", "state"))


def _server_running(state_dir: str) -> bool:
    pid = Path(state_dir) / "silverlake.pid"
    try:
        os.kill(int(pid.read_text()), 0)
        return True
    except (OSError, ValueError):
        return False


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="silverlake.scenarios", description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="every scenario and its state")
    show = sub.add_parser("show", help="one scenario in full")
    show.add_argument("id")
    st = sub.add_parser("set", help="put one scenario in a state")
    st.add_argument("id")
    st.add_argument("state", choices=STATES)
    rs = sub.add_parser("reset", help="one scenario back to vulnerable, with its exploit's leftovers cleared")
    rs.add_argument("id")
    md = sub.add_parser("mode", help="the whole range, vulnerable or secure")
    md.add_argument("state", choices=STATES)
    args = ap.parse_args(argv)
    try:
        reg = registry()
        state_dir = os.environ.get("SILVERLAKE_STATE_DIR", "state")
        writes = args.cmd in ("set", "reset", "mode")
        if writes and _server_running(state_dir):
            print("the server is running and would overwrite this change. Use ./scenario.sh, which stops it first.",
                  file=sys.stderr)
            return 1
        store, db = _open()
        try:
            if args.cmd == "list":
                print(f"range mode: {store.system.mode}")
                for s in reg.values():
                    print(f"  {current(store, s.id):<10} {s.group} {s.id:<26} {s.title}")
            elif args.cmd == "show":
                s = _find(reg, args.id)
                print(f"{s.id} ({current(store, s.id)}): {s.title}\n{s.summary}")
                for c in s.changes:
                    print(f"  {c.target} {c.field}: {_short(c.vulnerable)} -> {_short(c.secure)}   now {_short(get(store, c))}")
            elif args.cmd == "set":
                apply(store, _find(reg, args.id), args.state)
                store.on_change()
                print(f"{args.id} is now {args.state}")
            elif args.cmd == "reset":
                for line in reset(store, _find(reg, args.id)):
                    print(line)
                store.on_change()
                print(f"{args.id} reset to vulnerable")
            else:
                set_mode(store, args.state, reg)
                store.on_change()
                print(f"the whole range is now {args.state}")
        finally:
            db.close()
    except (ScenarioError, profiles.SeedError) as exc:
        print(f"silverlake.scenarios: {exc}", file=sys.stderr)
        return 1
    return 0


def _short(value) -> str:
    text = repr(value)
    return text if len(text) <= 60 else text[:57] + "..."


def _find(reg: dict[str, Scenario], sid: str) -> Scenario:
    if sid not in reg:
        raise ScenarioError(f"no scenario {sid!r}. ./scenario.sh list shows them")
    return reg[sid]


if __name__ == "__main__":
    sys.exit(main())
