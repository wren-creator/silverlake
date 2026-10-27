"""Running RPG IV programs inside a session, on the rpgle runtime.

A program object (`*PGM`, attribute RPGLE) keeps its source in `data["source"]`. Its display files are
`*FILE` objects (attribute DSPF) found by the F-spec name; a program may still carry its DDS inline in
`data["dspf"]`, used only when no such file is on the library list. CALL starts it as a generator, and every EXFMT becomes a screen on
the terminal until the program ends. Nothing here compiles anything yet: the source is parsed when
the program is called, which on a real system would be CRTBNDRPG's job.

Safe by construction: the interpreter never reaches a shell, a file or the network, and a program is
capped on how many instructions run between screens, so one trainee's `DOW` cannot freeze the server
(the interpreter runs in the server's own thread).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from ..proto import datastream as ds
from ..screens.model import COLS, ROWS, Input, Screen, Text
from . import messages, overrides, spool as spoolmod
from .authority import USE, Auth

try:
    from rpgle import (CallError, Database, LoadedProgram, ProgramLoader, Resume, RpgleError, parse_dds,
                       parse_pf, parse_prtf, parse_rpgle, run_program, Spool)
    AVAILABLE = True
except ImportError:                       # the RPG runtime is optional: Silverlake runs without it
    AVAILABLE = False

DEFAULT_OUTQ = "QGPL/QPRINT"      # where a printer file with no queue of its own prints
MAX_STEPS = 200_000      # instructions between screens before a program is stopped
_FAILED = ("not found", "not authorized", "not valid", "does not exist", "already exists", "not correct",
           "cannot", "not allowed", "parenthesis", "not available", "not modeled")


def not_installed() -> messages.Message:
    return messages.info("The RPG runtime (rpgle_library) is not installed, so RPG programs cannot run.")


def is_rpg(obj) -> bool:
    return obj.type == "*PGM" and obj.data.get("attr") in ("RPGLE", "RPG") and bool(obj.data.get("source"))


class Run:
    """One running program: its generator, the screen it is showing, and how it ended."""

    def __init__(self, obj, gen, files: "Files | None" = None) -> None:
        self.obj = obj
        self.gen = gen
        self.files = files
        self.data = None            # the ScreenData being shown
        self.done = False
        self.error = ""

    @property
    def label(self) -> str:
        return f"{self.obj.library}/{self.obj.name}"

    def _advance(self, resume) -> None:
        try:
            self.data = next(self.gen) if resume is None else self.gen.send(resume)
        except StopIteration:
            self.data, self.done = None, True
        except RpgleError as exc:
            self.data, self.done, self.error = None, True, str(exc)
        except RecursionError:
            self.data, self.done, self.error = None, True, "calls nested too deeply"
        if self.files:
            self.files.save()          # what the program has written so far is kept, even if it stops here

    def start(self) -> "Run":
        self._advance(None)
        return self

    def send(self, key: str, values: dict[str, str]) -> None:
        self._advance(Resume(key=key, values=values))

    def close(self) -> None:
        self.gen.close()
        self.done = True
        if self.files:
            self.files.save()


# What opening a file for each usage needs, and each operation after that (IBM: object operational
# plus the data rights the mode and the operation use).
OPEN_NEEDS = {"I": Auth.OBJOPR | Auth.READ, "U": Auth.OBJOPR | Auth.READ | Auth.UPD,
              "C": Auth.OBJOPR | Auth.READ | Auth.UPD | Auth.ADD, "O": Auth.OBJOPR | Auth.ADD}
OP_NEEDS = {"read": Auth.READ, "add": Auth.ADD, "update": Auth.UPD, "delete": Auth.DLT}


def effective(store, actor, stack: list[str]):
    """The profile as it is with these programs on the stack: its own authority plus whoever they adopt."""
    return store.adopting(actor, adopted_owners(store, stack))


class Files:
    """The DISK files a run opens: `*FILE` objects found through the library list, loaded into a private
    SQLite database for the run and written back to the objects as the program goes. Every open and every
    read, add, update and delete is checked against the profile the stack holds at that moment, so a
    program that adopts its owner reaches a file the user cannot, and only while it is running."""

    def __init__(self, store, actor, session) -> None:
        self.store, self.actor, self.session = store, actor, session
        self.loader = None                              # set by start(): its stack says who is running
        self.db = Database(authorize=self._authorize)
        self.objs: dict[str, Any] = {}
        self.spool = Spool()
        self.printers: dict[str, Any] = {}               # PRTF name -> its *FILE object
        self._spooled: dict[int, Any] = {}               # id of an open printer file -> the SpoolFile it fills

    def attach(self, prog, stack: list[str]) -> dict:
        """The record layouts for the DISK files a program declares, loading each file's records."""
        from . import objects
        who = effective(self.store, self.actor, stack)
        pfs = {}
        for fs in prog.files:
            device = (fs.device or "").upper()
            if device not in ("DISK", "PRINTER"):
                continue
            name = fs.name.upper()
            opened = name if device == "PRINTER" else overrides.target(self.session, name)
            obj, err = objects.locate(self.store, who, opened, "*FILE", self.session.search_order())
            if err:
                raise RpgleError(err.text)
            if opened != name:
                self.session.joblog.append((datetime.now(), "message", f"File {name} overridden to {obj.library}/{obj.name}."))
            if device == "PRINTER":
                self._attach_printer(who, obj)
                continue
            if obj.data.get("attr", "PF") != "PF" or not obj.data.get("dds"):
                raise RpgleError(f"File {obj.name} in library {obj.library} is not a physical file with a record layout.")
            prev = self.objs.get(obj.name)
            if prev is not None and prev is not obj:
                raise RpgleError(f"File {obj.name} is in two libraries ({prev.library} and {obj.library}) and only one "
                                 "can be open in a job here.")
            pf = parse_pf(obj.name, obj.data["dds"])
            if prev is None:
                self.objs[obj.name] = obj
                self.db.load_rows(pf, obj.data.get("records", []))
            pfs[name] = pf
        return pfs

    def display(self, prog, stack: list[str], inline: str = ""):
        """The record formats of the display files a program declares. Each WORKSTN F-spec names a `*FILE`
        object with attribute DSPF, found through the library list and needing *USE. The program's own
        library is tried after the list, a simplification: a real job would fail to open a display file
        whose library is not on the list, and CALL APPLIB/ADVENTURE would be a poor first experience. A program written
        before display files were objects can still carry its DDS in its own `dspf`, used when no such
        file exists anywhere on the list."""
        from . import objects
        who = effective(self.store, self.actor, stack)
        home = stack[-1].partition("/")[0] if stack else ""
        search = self.session.search_order()
        search = search + [home] if home and home not in search else search    # see the docstring
        texts = []
        for fs in prog.files:
            if (fs.device or "").upper() != "WORKSTN":
                continue
            name = fs.name.upper()
            if inline and not any((lib, name, "*FILE") in self.store.objects for lib in search):
                continue
            obj, err = objects.locate(self.store, who, name, "*FILE", search)
            if err:
                raise RpgleError(err.text)
            if obj.data.get("attr") != "DSPF" or not obj.data.get("dds"):
                raise RpgleError(f"File {obj.name} in library {obj.library} is not a display file.")
            if USE not in self.store.authority_to_object(who, obj):
                raise RpgleError(messages.not_authorized_to_object(obj.name, obj.library, "*FILE").text)
            texts.append(obj.data["dds"])
        return parse_dds("\n".join(texts) if texts else inline)

    def _attach_printer(self, who, obj) -> None:
        """A printer file needs *USE, and so does the queue its output goes to. The queue and the file are
        checked now, as whoever the stack holds when the program is loaded. The spool file is the job's
        own, so it belongs to the user and not to an owner the program adopts."""
        if obj.data.get("attr") != "PRTF" or not obj.data.get("dds"):
            raise RpgleError(f"File {obj.name} in library {obj.library} is not a printer file.")
        if USE not in self.store.authority_to_object(who, obj):
            raise RpgleError(messages.not_authorized_to_object(obj.name, obj.library, "*FILE").text)
        q = self.queue_of(obj)
        if q is None:
            raise RpgleError(f"Output queue {obj.data.get('outq', DEFAULT_OUTQ)} for {obj.name} not found.")
        if Auth.READ not in self.store.authority_to_object(who, q):
            raise RpgleError(messages.not_authorized_to_object(q.name, q.library, "*OUTQ").text)
        self.printers[obj.name] = obj
        self.spool.defs[obj.name] = parse_prtf(obj.name, obj.data["dds"])

    def queue_of(self, obj):
        lib, _, name = obj.data.get("outq", DEFAULT_OUTQ).partition("/")
        return self.store.objects.get((lib.upper(), name.upper(), "*OUTQ"))

    def _spool_out(self) -> bool:
        """Put what the program has printed on its output queue as spooled files of the job."""
        changed = False
        for pf in self.spool.files:
            text = pf.text()
            if not text:
                continue
            lines = [ln.rstrip() for ln in text.replace("\f", "").split("\n")]
            sf = self._spooled.get(id(pf))
            if sf is None:
                obj = self.printers[pf.name.upper()]
                qlib, _, qname = obj.data.get("outq", DEFAULT_OUTQ).partition("/")
                sf = spoolmod.new_file(self.store, self.session, self.actor, obj.name, lines, obj.data.get("usrdta", ""),
                                       (qlib.upper(), qname.upper()))
                self._spooled[id(pf)] = sf
                changed = True
            elif sf.lines != lines:
                sf.lines = lines
                changed = True
        return changed

    def _authorize(self, name: str, op: str) -> None:
        obj = self.objs.get(name.upper())
        if obj is None:
            return
        stack = list(self.loader.active) if self.loader is not None else []
        who = effective(self.store, self.actor, stack)
        need = OPEN_NEEDS.get(op[5:], OPEN_NEEDS["I"]) if op.startswith("open:") else OP_NEEDS[op]
        if need not in self.store.authority_to_object(who, obj):
            self.session.joblog.append((datetime.now(), "message",
                                        f"{op.replace('open:', 'open ')} refused on {obj.library}/{obj.name}"))
            raise RpgleError(messages.not_authorized_to_object(obj.name, obj.library, "*FILE").text)

    def save(self) -> None:
        changed = False
        for name, obj in self.objs.items():
            rows = self.db.dump_rows(name)
            if rows != obj.data.get("records"):
                obj.data["records"] = rows
                changed = True
        if self._spool_out():
            changed = True
        if changed:
            self.store.on_change()


class StoreLoader(ProgramLoader if AVAILABLE else object):
    """Finds the programs a program CALLs among the session's objects instead of in folders, and only
    those the profile may use: a program you cannot call cannot be reached through one you can."""

    def __init__(self, store, actor, search: list[str], files: Files | None = None) -> None:
        super().__init__(dirs=[], main=None)
        self.store, self.actor, self.search = store, actor, search
        self.files = files
        self._loaded: dict[tuple, Any] = {}

    def _find(self, target: str):
        from . import objects                               # imported late: objects imports a lot
        name = target.strip().strip("'\"").strip().upper()
        if not all(p and p.replace("_", "").replace("$", "").replace("#", "").replace("@", "").isalnum()
                   for p in name.split("/")) or name.count("/") > 1:
            raise CallError(f"{target.strip()!r} is not a program name")
        who = effective(self.store, self.actor, self.active or ([self.main_name] if self.main_name else []))
        obj, err = objects.use_object(self.store, who, name, "*PGM", self.search)
        if err:
            raise CallError(err.text)
        return obj

    def name_for(self, target: str) -> str:
        """Resolve the target against the library list now, so the name is 'LIB/NAME' from here on."""
        obj = self._find(target)
        return f"{obj.library}/{obj.name}"

    def load(self, key: str, caller_dir=None):          # noqa: ARG002 (the folder means nothing here)
        obj = self._find(key)
        if not is_rpg(obj):
            raise CallError(f"Program {obj.name} in library {obj.library} is not an RPG program.")
        cached = self._loaded.get(obj.key)
        if cached is None:
            try:
                prog = parse_rpgle(obj.data["source"])
            except RpgleError as exc:
                raise RpgleError(f"{obj.name}: {exc}") from None
            stack = [*self.active, f"{obj.library}/{obj.name}"]
            pfs = self.files.attach(prog, stack) if self.files else {}
            dds = self.files.display(prog, stack, obj.data.get("dspf", "")) if self.files else parse_dds(obj.data.get("dspf", ""))
            cached = LoadedProgram(key=key, path=Path(f"/QSYS.LIB/{obj.library}.LIB/{obj.name}.PGM"), prog=prog,
                                   dds=dds, pfs=pfs)
            self._loaded[obj.key] = cached
        return cached


def adopted_owners(store, stack: list[str]) -> list[str]:
    """Whose authority the programs on the stack hold, outermost program first. A program that adopts
    (USRPRF *OWNER) adds its owner. USEADPAUT(*YES) lets it keep what the program that called it held,
    USEADPAUT(*NO) cuts that off (IBM, "Adopted Authority"). The user's own authority is never lost."""
    held: list[str] = []
    for key in stack:
        lib, _, name = key.partition("/")
        prog = store.objects.get((lib, name, "*PGM"))
        if prog is None:
            continue
        if prog.data.get("useadpaut", "*YES") != "*YES":
            held = []
        if prog.data.get("usrprf", "*USER") == "*OWNER":
            held = held + [prog.owner]
    return held


def make_qcmdexc(store, actor, session, loader):
    """What CALL 'QCMDEXC' does here: the CL string goes to Silverlake's own command dispatcher, in this
    process, as the profile the stack holds right now. It never reaches a shell. Parameters are the
    command string and its length, and only that many characters are read (a short length cuts the
    command, as on a real system)."""
    from ..cl import commands                                   # imported late: commands imports this module

    def hook(args: list) -> None:
        text = str(args[0]) if args else ""
        if len(args) > 1:
            try:
                text = text[:max(0, int(float(args[1])))]
            except (TypeError, ValueError):
                pass
        line = text.strip()
        owners = adopted_owners(store, loader.active)
        who = store.adopting(actor, owners)
        now = datetime.now()
        if who is not actor:
            session.joblog.append((now, "message", f"Program {loader.active[-1]} running with the authority of "
                                                   f"{', '.join(who.adopted)} (adopted)."))
        outcome = commands.execute(store, who, line, session)
        session.joblog.append((now, "command", f"QCMDEXC: {line}"))
        if outcome.message and outcome.message.text:
            session.joblog.append((now, "message", outcome.message.text))
        if outcome.view or outcome.go or outcome.cmdentry or outcome.signoff:
            raise CallError(f"Command {line.split('(')[0].split()[0] if line else ''} needs a screen and cannot run "
                            "from a program here.")
        if outcome.message and (outcome.message.id or any(w in outcome.message.text.lower() for w in _FAILED)):
            said = outcome.message.text
            if "parenthesis not found" in said:        # QCMDEXC's own wording, captured on PUB400
                said = "A matching parenthesis not found."
                session.joblog.append((now, "message", said))
            raise CallError(said)

    return hook


def start(store, actor, obj, session) -> tuple[Run | None, messages.Message | None]:
    """Begin a program. Returns the run (which may already be finished) or the reason it cannot start."""
    if not AVAILABLE:
        return None, not_installed()
    if not is_rpg(obj):
        return None, messages.syntax(f"Program {obj.name} cannot be run: it has no RPG source.")
    try:
        prog = parse_rpgle(obj.data["source"])
    except RpgleError as exc:
        return None, messages.info(f"Program {obj.name} did not load: {exc}")
    files = Files(store, actor, session)
    loader = StoreLoader(store, actor, session.search_order(), files)
    loader.main_name = f"{obj.library}/{obj.name}"
    files.loader = loader
    try:
        pfs = files.attach(prog, [loader.main_name])
        dds = files.display(prog, [loader.main_name], obj.data.get("dspf", ""))
    except RpgleError as exc:
        return None, messages.info(str(exc))
    gen = run_program(prog, dds, files.db, pfs, loader, files.spool, max_steps=MAX_STEPS,
                      system_programs={"QCMDEXC": make_qcmdexc(store, actor, session, loader)})
    return Run(obj, gen, files).start(), None


# -- the screen a program shows -----------------------------------------------------------------------

def to_screen(data, message: str = "") -> Screen:
    """A ScreenData as a terminal screen. The runtime has already turned DDS positions (which start at 1)
    into 0-based ones, the way this screen model counts. Text is clipped at the edge rather than refused. Only the first
    input on a row is named (the runtime keys input by row), so a second one on the same row is shown
    as plain text."""
    rows: list[Text | Input] = []
    named: set[int] = set()
    for f in data.fields:
        r, c = f.row, f.col                       # the runtime already counts from 0
        if not (0 <= r < ROWS and 0 <= c < COLS):
            continue
        if r == 0 and c == 0:
            c = 1                                  # the attribute cell needs a cell before the first one
        if f.input and f.row in data.input_map and f.row not in named:
            named.add(f.row)
            length = max(1, min(f.length or 1, ROWS * COLS - 2 - (r * COLS + c)))
            rows.append(Input(r, c, length, data.input_map[f.row], value=f.text.rstrip()))
        elif f.text.strip() or f.input:
            rows.append(Text(r, c, f.text[:COLS - c], ds.ATTR_GREEN))
    if message:
        rows.append(Text(23, 1, message[:77], ds.ATTR_WHITE))
    cursor = data.input_map.get(data.cursor.row) if data.input_map else None
    return Screen(rows, cursor=cursor if cursor in {x.name for x in rows if isinstance(x, Input)} else None)


def usable_key(data, aid: str) -> bool:
    """Enter always works. A function key works only if the display file names it (CFnn or CAnn)."""
    return aid == "ENTER" or aid in data.keys


def bad_numeric(data, values: dict[str, str]) -> str:
    """The first numeric field with something other than digits in it, if any. A real 5250 keyboard
    refuses the letter as it is typed, so the program never sees it. Ours checks on Enter."""
    for name in data.numeric_fields:
        text = values.get(name, "").strip()
        if text and not text.replace(".", "", 1).replace("-", "", 1).isdigit():
            return name
    return ""
