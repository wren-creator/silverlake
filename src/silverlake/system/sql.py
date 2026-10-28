"""A small SQL runner over the physical files, for the PASE `db2` command.

One statement at a time, as the signed on profile, in this process. Each run builds a private in-memory SQLite
database from the files the statement names, runs the statement there, and writes back the files it changed.
Nothing else is reachable: the statement can only name physical files (a name is a file in the library list or
`LIB.FILE` / `LIB/FILE`), SQLite's own authorizer refuses everything but SELECT, INSERT, UPDATE and DELETE on
those tables, and no host file or process is ever involved.

Authority is the IBM i model the rest of Silverlake uses, checked before anything runs: SELECT needs *USE on
the file, INSERT *OBJOPR and *ADD, UPDATE *OBJOPR and *UPD (and *USE to read the columns it names), DELETE
*OBJOPR and *DLT, plus *EXECUTE on the library. *ALLOBJ passes. Like CPYF, this reaches data without going
through the program that normally guards it, which is the point of teaching it.

`CALL QSYS2.QCMDEXC('cmd')` runs a CL command through the dispatcher as the same profile. That is how SQL
reaches commands on a real system, and it ignores limited capability, as everything outside the 5250 menu does.

Not from a real system: the message IDs used (SQL0104, SQL0204, SQL0551, SQL0199) are IBM's, but the wording is
ours and the layout of the result is not captured. SQL dialect is SQLite's, so Db2 for i functions are not there.
Not built: DDL, joins across libraries with the same file name, catalog views (QSYS2.*), transactions."""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field

from . import dbfiles, objects
from .authority import Auth, SpecialAuthority
from .profiles import Profile, ProfileStore

MAX_ROWS = 500
_NAME = r"[A-Za-z_][A-Za-z0-9_]*"
_TABLE_REF = re.compile(rf"\b(FROM|JOIN|INTO|UPDATE)\s+({_NAME})(?:\s*[./]\s*({_NAME}))?", re.I)
_QCMDEXC = re.compile(r"^\s*CALL\s+QSYS2\s*\.\s*QCMDEXC\s*\(\s*'((?:[^']|'')*)'\s*(?:,\s*\d+\s*)?\)\s*;?\s*$", re.I)
_KEYWORD_AFTER_FROM = {"SELECT", "VALUES", "WHERE", "SET", "ON"}

NEED = {"select": Auth.READ, "insert": Auth.OBJOPR | Auth.ADD, "update": Auth.OBJOPR | Auth.UPD,
        "delete": Auth.OBJOPR | Auth.DLT}


@dataclass
class Result:
    columns: list[str] = field(default_factory=list)
    rows: list[tuple] = field(default_factory=list)
    count: int = 0                       # rows selected or changed
    kind: str = "select"                 # select, change or command
    text: str = ""                       # for a command, what it said
    error: str = ""                      # a message line, with its ID, when the statement was refused


def _fail(id_: str, text: str) -> Result:
    return Result(error=f"{id_} - {text}")


def _allowed(store: ProfileStore, actor: Profile, obj, need: Auth) -> bool:
    if SpecialAuthority.ALLOBJ in store.special_authorities(actor):
        return True
    return not (need & ~store.authority_to_object(actor, obj))


def run(store: ProfileStore, actor: Profile, session, statement: str) -> Result:
    statement = statement.strip().rstrip(";").strip()
    if not statement:
        return _fail("SQL0104", "No SQL statement was given.")
    m = _QCMDEXC.match(statement)
    if m:
        return _command(store, actor, session, m.group(1).replace("''", "'"))
    verb = statement.split(None, 1)[0].lower()
    if verb not in NEED:
        return _fail("SQL0104", f"{verb.upper()} is not available in the simulated runner. "
                                "SELECT, INSERT, UPDATE, DELETE and CALL QSYS2.QCMDEXC are.")
    if ";" in statement:
        return _fail("SQL0104", "One statement at a time.")

    # Which files does it name? Each is found through the library list and checked before anything runs.
    objs: dict[str, object] = {}
    spans: list[tuple[int, int, str]] = []
    for ref in _TABLE_REF.finditer(statement):
        first, second = ref.group(2), ref.group(3)
        if first.upper() in _KEYWORD_AFTER_FROM and not second:
            continue
        spec = f"{first}/{second}" if second else first
        obj, err = objects.locate(store, actor, spec, "*FILE", session.search_order())
        if err:
            return _fail("SQL0204", f"{(second or first).upper()} in {(first if second else '*LIBL').upper()} "
                                    "type *FILE not found.")
        if not dbfiles.is_data_file(obj):
            return _fail("SQL0204", f"{obj.name} in {obj.library} type *FILE is not a physical file with a record layout.")
        if obj.name in objs and objs[obj.name] is not obj:
            return _fail("SQL0199", f"File {obj.name} is named in two libraries and only one can be used per statement.")
        objs[obj.name] = obj
        spans.append((ref.start(2), ref.end(), obj.name))
    if not objs:
        return _fail("SQL0104", "The statement names no file.")
    for pos, end, name in reversed(spans):
        statement = statement[:pos] + name + statement[end:]

    tables = {n.upper(): o for n, o in objs.items()}
    conn = None
    denied: list[str] = []
    changed: set[str] = set()

    def authorizer(action, arg1, arg2, dbname, source):
        if action == sqlite3.SQLITE_SELECT or action == sqlite3.SQLITE_FUNCTION or action == sqlite3.SQLITE_RECURSIVE:
            return sqlite3.SQLITE_OK
        kind = {sqlite3.SQLITE_READ: "select", sqlite3.SQLITE_INSERT: "insert", sqlite3.SQLITE_UPDATE: "update",
                sqlite3.SQLITE_DELETE: "delete"}.get(action)
        if kind is None:
            return sqlite3.SQLITE_DENY
        table = (arg1 or "").upper()
        obj = tables.get(table)
        if obj is None:
            return sqlite3.SQLITE_DENY
        if not _allowed(store, actor, obj, NEED[kind]):
            denied.append(obj.name)
            return sqlite3.SQLITE_DENY
        if kind != "select":
            changed.add(obj.name)
        return sqlite3.SQLITE_OK

    # Authority first, by the verb and the files, so a refusal never depends on what SQLite happens to read.
    target = next((n for pos, end, n in spans), None)
    for name, obj in tables.items():
        need = NEED[verb] if name == (target or "").upper() and verb != "select" else NEED["select"]
        if not _allowed(store, actor, obj, need):
            return _fail("SQL0551", f"Not authorized to object {obj.name} in {obj.library} type *FILE.")
    try:
        conn = sqlite3.connect(":memory:")
        layouts = {}
        for obj in objs.values():
            pf = layouts[obj.name] = dbfiles.layout(obj)
            cols = ", ".join(f'"{f.name}" ' + ("TEXT" if f.dtype == "A" else "INTEGER" if f.dec == 0 else "REAL")
                             for f in pf.fields)
            conn.execute(f'CREATE TABLE "{obj.name}" ({cols})')
            marks = ", ".join("?" for _ in pf.fields)
            conn.executemany(f'INSERT INTO "{obj.name}" VALUES ({marks})',
                             [tuple(r.get(f.name, "" if f.dtype == "A" else 0) for f in pf.fields)
                              for r in obj.data.get("records", [])])
        conn.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, 1_000_000)        # a value, a blob or a string, never a gigabyte
        ticks = [0]

        def too_long() -> int:
            ticks[0] += 1
            return 1 if ticks[0] > 5000 else 0                       # about five million steps, then give up
        conn.set_progress_handler(too_long, 1000)
        conn.set_authorizer(authorizer)
        cur = conn.execute(statement)
        if verb == "select":
            cols = [d[0] for d in cur.description or []]
            rows = [tuple(r) for r in cur.fetchmany(MAX_ROWS + 1)]
            return Result(cols, rows[:MAX_ROWS], min(len(rows), MAX_ROWS))
        conn.set_authorizer(None)
        count = cur.rowcount
        for name in changed:
            names = [f.name for f in layouts[name].fields]
            objs[name].data["records"] = [dict(zip(names, row)) for row in
                                          conn.execute(f'SELECT * FROM "{name}" ORDER BY rowid')]
        if changed:
            store.on_change()
        return Result(count=max(count, 0), kind="change")
    except sqlite3.DatabaseError as exc:
        if denied:
            obj = tables[denied[0].upper()]
            return _fail("SQL0551", f"Not authorized to object {obj.name} in {obj.library} type *FILE.")
        if "not authorized" in str(exc):
            return _fail("SQL0104", "That statement reaches something the simulated runner does not allow.")
        return _fail("SQL0104", f"The statement was not valid ({str(exc).rstrip('.')}).")
    finally:
        if conn is not None:
            conn.close()


def _command(store: ProfileStore, actor: Profile, session, line: str) -> Result:
    from ..cl import commands
    from ..net import textview
    outcome = commands.execute(store, actor, line, session)
    return Result(kind="command", text=textview.outcome_text(store, outcome, line))


def render(result: Result) -> list[str]:
    """The lines a command-line client prints."""
    if result.error:
        return [result.error]
    if result.kind == "command":
        return result.text.splitlines() or ["Command completed."]
    if result.kind == "change":
        return [f"  {result.count} record(s) changed."]
    cols = result.columns
    cells = [[("" if v is None else str(v)) for v in row] for row in result.rows]
    widths = [max([len(c)] + [len(r[i]) for r in cells]) for i, c in enumerate(cols)]
    out = [" ".join(c.ljust(w) for c, w in zip(cols, widths)).rstrip(),
           " ".join("-" * w for w in widths)]
    out += [" ".join(v.ljust(w) for v, w in zip(row, widths)).rstrip() for row in cells]
    out += ["", f"  {result.count} record(s) selected."]
    return out
