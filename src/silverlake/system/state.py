"""Runtime state, saved to SQLite so changes made inside a session survive a
restart. Libraries, objects and authorization lists are real tables, keyed the
way QSYS.LIB keys them. Profiles and system values are still one JSON row, and
move to tables when something needs to query them. The seed file is the golden state; reset.sh deletes
the state directory and the next start reads the seed again.

Passwords are stored as given. This is a training range with deliberately weak
credentials, not a place to keep a secret."""

import json
import sqlite3
from pathlib import Path

from .commandobjs import ensure_commands
from .authority import AuthList, SecuredObject, SpecialAuthority, UserClass, name_auth, parse_auth
from . import ifs
from .spool import ensure_queues, from_row, to_row
from .profiles import DEFAULT_SEED, Profile, ProfileStore, System, load

DB_NAME = "silverlake.sqlite"


def to_dict(store: ProfileStore) -> dict:
    sysd = store.system
    return {
        "system": {"qsecurity": sysd.qsecurity, "qpwdlvl": sysd.qpwdlvl, "mode": sysd.mode,
                   "default_profile_owner": sysd.default_profile_owner,
                   "qmaxsign": sysd.qmaxsign, "qmaxsgnacn": sysd.qmaxsgnacn, "qpwdexpitv": sysd.qpwdexpitv,
                   "qpwdexpwrn": sysd.qpwdexpwrn, "qpwdminlen": sysd.qpwdminlen, "qpwdmaxlen": sysd.qpwdmaxlen,
                   "qpwdrqddgt": sysd.qpwdrqddgt, "qpwdlmtajc": sysd.qpwdlmtajc, "qpwdlmtrep": sysd.qpwdlmtrep,
                   "qpwdrqddif": sysd.qpwdrqddif, "require_tls": sysd.require_tls, "console_cert": sysd.console_cert},
        "scenarios": dict(store.scenarios),
        "ifs": ifs.to_rows(store.ifs),
        "profiles": [{
            "name": p.name, "user_class": p.user_class.value,
            "special": None if p.special_authorities is None else sorted(a.value for a in p.special_authorities),
            "password": p.password, "status": p.status, "password_expired": p.password_expired,
            "password_changed": p.password_changed, "password_history": p.password_history,
            "pwd_expitv": p.pwd_expitv,
            "limited_capabilities": p.limited_capabilities, "group_profile": p.group_profile,
            "supplemental_groups": p.supplemental_groups, "initial_program": p.initial_program,
            "initial_menu": p.initial_menu, "current_library": p.current_library, "text": p.text,
            "owner": p.owner, "public_authority": name_auth(p.public_authority),
            "private_authority": {k: name_auth(v) for k, v in p.private_authority.items()},
        } for p in store.profiles.values()],
        "objects": [{
            "library": o.library, "name": o.name, "type": o.type, "text": o.text, "data": o.data,
            "owner": o.owner, "owner_auth": name_auth(o.owner_auth),
            "private": {k: name_auth(v) for k, v in o.private.items()},
            "public": "*AUTL" if o.public is None else name_auth(o.public), "autl": o.autl,
        } for o in sorted(store.objects.values(), key=lambda o: o.key)],
        "autls": [{"name": a.name, "entries": {k: name_auth(v) for k, v in a.entries.items()},
                   "public": name_auth(a.public), "owner": a.owner, "text": a.text}
                 for a in sorted(store.autls.values(), key=lambda a: a.name)],
        "spool": [to_row(f) for f in store.spool],
    }


def from_dict(data: dict) -> ProfileStore:
    profiles = [Profile(
        name=p["name"], user_class=UserClass(p["user_class"]),
        special_authorities=None if p["special"] is None else frozenset(SpecialAuthority(a) for a in p["special"]),
        password=p["password"], status=p["status"], password_expired=p["password_expired"],
        password_changed=p.get("password_changed"), password_history=list(p.get("password_history", [])),
        pwd_expitv=p.get("pwd_expitv"),
        limited_capabilities=p["limited_capabilities"], group_profile=p["group_profile"],
        supplemental_groups=list(p["supplemental_groups"]), initial_program=p["initial_program"],
        initial_menu=p["initial_menu"], current_library=p["current_library"], text=p["text"],
        owner=p["owner"], public_authority=parse_auth(p["public_authority"]),
        private_authority={k: parse_auth(v) for k, v in p["private_authority"].items()},
    ) for p in data["profiles"]]
    objects = [SecuredObject(
        library=o["library"], name=o["name"], type=o["type"], text=o["text"], data=o.get("data", {}),
        owner=o["owner"], owner_auth=parse_auth(o["owner_auth"]),
        private={k: parse_auth(v) for k, v in o["private"].items()},
        public=None if o["public"] == "*AUTL" else parse_auth(o["public"]), autl=o["autl"],
    ) for o in data["objects"]]
    autls = [AuthList(a["name"], {k: parse_auth(v) for k, v in a["entries"].items()}, parse_auth(a["public"]),
                      a.get("owner", "QSECOFR"), a.get("text", ""))
             for a in data["autls"]]
    store = ProfileStore(System(**data["system"]), profiles, objects, autls,
                         [from_row(r) for r in data.get("spool", [])])
    store.scenarios = dict(data.get("scenarios", {}))
    store.ifs = ifs.from_rows(data["ifs"]) if "ifs" in data else ifs.load_seed()      # an older state gets the seed IFS
    ensure_queues(store)
    ensure_commands(store)      # a state saved before a command existed gets its object now
    return store


SCHEMA = """
CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS objects (
    library TEXT NOT NULL, name TEXT NOT NULL, type TEXT NOT NULL,
    owner TEXT NOT NULL, owner_auth TEXT NOT NULL, public TEXT NOT NULL,
    autl TEXT, text TEXT NOT NULL DEFAULT '', data TEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY (library, name, type));
CREATE TABLE IF NOT EXISTS object_auth (
    library TEXT NOT NULL, name TEXT NOT NULL, type TEXT NOT NULL,
    grantee TEXT NOT NULL, auth TEXT NOT NULL,
    PRIMARY KEY (library, name, type, grantee));
CREATE TABLE IF NOT EXISTS autls (name TEXT PRIMARY KEY, public TEXT NOT NULL,
    owner TEXT NOT NULL DEFAULT 'QSECOFR', text TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS spool (id INTEGER PRIMARY KEY, body TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS autl_entries (
    autl TEXT NOT NULL, grantee TEXT NOT NULL, auth TEXT NOT NULL, PRIMARY KEY (autl, grantee));
"""


class StateDB:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.executescript(SCHEMA)
        if "data" not in {r[1] for r in self.db.execute("PRAGMA table_info(objects)")}:
            self.db.execute("ALTER TABLE objects ADD COLUMN data TEXT NOT NULL DEFAULT '{}'")   # older state file
        cols = {r[1] for r in self.db.execute("PRAGMA table_info(autls)")}
        if "owner" not in cols:                                                         # older state file
            self.db.execute("ALTER TABLE autls ADD COLUMN owner TEXT NOT NULL DEFAULT 'QSECOFR'")
            self.db.execute("ALTER TABLE autls ADD COLUMN text TEXT NOT NULL DEFAULT ''")
        self.db.commit()

    def read(self) -> dict | None:
        row = self.db.execute("SELECT value FROM kv WHERE key = 'state'").fetchone()
        if not row:
            return None
        data = json.loads(row[0])
        q = self.db.execute
        private: dict[tuple, dict] = {}
        for lib, name, typ, who, auth in q("SELECT library, name, type, grantee, auth FROM object_auth"):
            private.setdefault((lib, name, typ), {})[who] = auth
        data["objects"] = [
            {"library": lib, "name": name, "type": typ, "text": text, "data": json.loads(data),
             "owner": owner, "owner_auth": oa, "private": private.get((lib, name, typ), {}),
             "public": pub, "autl": autl}
            for lib, name, typ, owner, oa, pub, autl, text, data in q(
                "SELECT library, name, type, owner, owner_auth, public, autl, text, data FROM objects "
                "ORDER BY library, name, type")]
        entries: dict[str, dict] = {}
        for autl, who, auth in q("SELECT autl, grantee, auth FROM autl_entries"):
            entries.setdefault(autl, {})[who] = auth
        data["autls"] = [{"name": n, "entries": entries.get(n, {}), "public": pub, "owner": owner, "text": text}
                         for n, pub, owner, text in q("SELECT name, public, owner, text FROM autls ORDER BY name")]
        data["spool"] = [json.loads(b) for (b,) in q("SELECT body FROM spool ORDER BY id")]
        return data

    def write(self, store: ProfileStore) -> None:
        d = to_dict(store)
        with self.db:      # one transaction, so a crash never leaves half a state
            self.db.execute("INSERT OR REPLACE INTO kv (key, value) VALUES ('state', ?)",
                            (json.dumps({"system": d["system"], "profiles": d["profiles"], "scenarios": d["scenarios"],
                                        "ifs": d["ifs"]}),))
            for table in ("objects", "object_auth", "autls", "autl_entries", "spool"):
                self.db.execute(f"DELETE FROM {table}")
            for o in d["objects"]:
                self.db.execute("INSERT INTO objects VALUES (?,?,?,?,?,?,?,?,?)",
                                (o["library"], o["name"], o["type"], o["owner"], o["owner_auth"],
                                 o["public"], o["autl"], o["text"], json.dumps(o["data"])))
                self.db.executemany("INSERT INTO object_auth VALUES (?,?,?,?,?)",
                                    [(o["library"], o["name"], o["type"], k, v) for k, v in o["private"].items()])
            self.db.executemany("INSERT INTO spool (body) VALUES (?)", [(json.dumps(r),) for r in d["spool"]])
            for a in d["autls"]:
                self.db.execute("INSERT INTO autls VALUES (?,?,?,?)", (a["name"], a["public"], a["owner"], a["text"]))
                self.db.executemany("INSERT INTO autl_entries VALUES (?,?,?)",
                                    [(a["name"], k, v) for k, v in a["entries"].items()])

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
