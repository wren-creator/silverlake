"""Runtime state: the profile store, saved to SQLite so changes made inside a
session survive a restart. The seed file is the golden state; reset.sh deletes
the state directory and the next start reads the seed again.

Passwords are stored as given. This is a training range with deliberately weak
credentials, not a place to keep a secret."""

import json
import sqlite3
from pathlib import Path

from .authority import AuthList, SecuredObject, SpecialAuthority, UserClass, name_auth, parse_auth
from .profiles import DEFAULT_SEED, Profile, ProfileStore, System, load

DB_NAME = "silverlake.sqlite"


def to_dict(store: ProfileStore) -> dict:
    sysd = store.system
    return {
        "system": {"qsecurity": sysd.qsecurity, "qpwdlvl": sysd.qpwdlvl, "mode": sysd.mode,
                   "default_profile_owner": sysd.default_profile_owner},
        "profiles": [{
            "name": p.name, "user_class": p.user_class.value,
            "special": None if p.special_authorities is None else sorted(a.value for a in p.special_authorities),
            "password": p.password, "status": p.status, "password_expired": p.password_expired,
            "limited_capabilities": p.limited_capabilities, "group_profile": p.group_profile,
            "supplemental_groups": p.supplemental_groups, "initial_program": p.initial_program,
            "initial_menu": p.initial_menu, "current_library": p.current_library, "text": p.text,
            "owner": p.owner, "public_authority": name_auth(p.public_authority),
            "private_authority": {k: name_auth(v) for k, v in p.private_authority.items()},
        } for p in store.profiles.values()],
        "objects": [{
            "name": o.name, "owner": o.owner, "owner_auth": name_auth(o.owner_auth),
            "private": {k: name_auth(v) for k, v in o.private.items()},
            "public": "*AUTL" if o.public is None else name_auth(o.public), "autl": o.autl,
        } for o in store.objects.values()],
        "autls": [{"name": a.name, "entries": {k: name_auth(v) for k, v in a.entries.items()},
                   "public": name_auth(a.public)} for a in store.autls.values()],
    }


def from_dict(data: dict) -> ProfileStore:
    profiles = [Profile(
        name=p["name"], user_class=UserClass(p["user_class"]),
        special_authorities=None if p["special"] is None else frozenset(SpecialAuthority(a) for a in p["special"]),
        password=p["password"], status=p["status"], password_expired=p["password_expired"],
        limited_capabilities=p["limited_capabilities"], group_profile=p["group_profile"],
        supplemental_groups=list(p["supplemental_groups"]), initial_program=p["initial_program"],
        initial_menu=p["initial_menu"], current_library=p["current_library"], text=p["text"],
        owner=p["owner"], public_authority=parse_auth(p["public_authority"]),
        private_authority={k: parse_auth(v) for k, v in p["private_authority"].items()},
    ) for p in data["profiles"]]
    objects = [SecuredObject(
        name=o["name"], owner=o["owner"], owner_auth=parse_auth(o["owner_auth"]),
        private={k: parse_auth(v) for k, v in o["private"].items()},
        public=None if o["public"] == "*AUTL" else parse_auth(o["public"]), autl=o["autl"],
    ) for o in data["objects"]]
    autls = [AuthList(a["name"], {k: parse_auth(v) for k, v in a["entries"].items()}, parse_auth(a["public"]))
             for a in data["autls"]]
    return ProfileStore(System(**data["system"]), profiles, objects, autls)


class StateDB:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.execute("CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        self.db.commit()

    def read(self) -> dict | None:
        row = self.db.execute("SELECT value FROM kv WHERE key = 'state'").fetchone()
        return json.loads(row[0]) if row else None

    def write(self, store: ProfileStore) -> None:
        self.db.execute("INSERT OR REPLACE INTO kv (key, value) VALUES ('state', ?)", (json.dumps(to_dict(store)),))
        self.db.commit()

    def close(self) -> None:
        self.db.close()


def open_store(seed: Path | str | None = None, state_dir: Path | str = "state") -> tuple[ProfileStore, StateDB]:
    """Load saved state if there is any, else the seed, and keep saving changes."""
    db = StateDB(Path(state_dir) / DB_NAME)
    saved = db.read()
    store = from_dict(saved) if saved else load(seed or DEFAULT_SEED)
    store.on_change = lambda: db.write(store)
    if not saved:
        db.write(store)
    return store, db
