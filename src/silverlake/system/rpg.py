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
from .authority import USE, Auth, SpecialAuthority

try:
    from rpgle import (CallError, Database, LoadedProgram, ProgramLoader, Resume, RpgleError, parse_dds,
                       parse_lf, parse_pf, parse_prtf, parse_rpgle, run_program, Spool)
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


_USE_CODE = {"I": "Input", "O": "Output", "U": "Update", "C": "Combined"}


def program_references(store, actor, name: str, search: list[str]):
    """DSPPGMREF: the objects an RPG program's F-specs record, from IBM's page (read in full, not a
    capture, 2026-11): *OBJOPR to the program, and for RPGLE "*FILE, *PGM, *DTAARA, *SRVPGM" are what
    the page says the command can report. Only *FILE is built: nothing here scans RPG source for the
    programs, data areas or service programs it calls, so those three are left out rather than guessed
    at. Returns (program, rows, None) or (None, None, a refusal)."""
    from . import objects
    obj, err = objects.locate(store, actor, name, "*PGM", search)
    if err:
        return None, None, err
    if Auth.OBJOPR not in store.authority_to_object(actor, obj):
        return None, None, messages.not_authorized_to_object(obj.name, obj.library, "*PGM")
    if not AVAILABLE or not is_rpg(obj):
        return obj, [], None
    try:
        prog = parse_rpgle(obj.data["source"])
    except RpgleError:
        return obj, [], None
    rows = []
    for fs in prog.files:
        device = (fs.device or "").upper()
        if device in ("DISK", "PRINTER", "WORKSTN") and fs.name:
            rows.append((fs.name.upper(), "*FILE", _USE_CODE.get((fs.type or "").upper(), "Unspecified")))
    return obj, rows, None


def change_program(store, actor, name: str, search: list[str], usrprf: str, useadpaut: str, text: str):
    """CHGPGM, from IBM's page (read in full, not a capture, 2026-11): *OBJMGT and *USE to the program
    always; USRPRF and USEADPAUT also need the program's owner, or *ALLOBJ together with *SECADM (the
    page: "either be the owner of the program or have all object ... and security administrator ...
    special authorities"), so granting yourself someone else's adopted authority takes more than owning
    the program you call them through. A program in QSYS or QGDDM is refused (CPF0544, the one escape ID
    the page actually ties to a condition). Not modeled: the page's own "the program must be re-created"
    rule for USRPRF and USEADPAUT; here the change takes effect at once, which this project's verification
    list flags as simpler than the real thing. Returns a Done."""
    from . import objects
    from .objects import Done, _no, _ok
    obj, err = objects.locate(store, actor, name, "*PGM", search)
    if err:
        return _no(err)
    if obj.library in ("QSYS", "QGDDM"):
        return _no(messages.program_in_restricted_library(obj.name, obj.library))
    need = Auth.OBJMGT | USE
    if need & ~store.authority_to_object(actor, obj):
        return _no(messages.not_authorized_to_object(obj.name, obj.library, "*PGM"))
    if (usrprf != "*SAME" or useadpaut != "*SAME") and actor.name != obj.owner:
        sa = store.special_authorities(actor)
        if not (SpecialAuthority.ALLOBJ in sa and SpecialAuthority.SECADM in sa):
            return _no(messages.not_authorized_to_object(obj.name, obj.library, "*PGM"))
    if usrprf != "*SAME":
        obj.data["usrprf"] = usrprf
    if useadpaut != "*SAME":
        obj.data["useadpaut"] = useadpaut
    if text != "*SAME":          # convert() has already turned *BLANK into "" by the time this runs
        obj.text = text
    store.on_change()
    return _ok(f"Program {obj.name} in library {obj.library} changed.")


def dump_program(store, actor, session, obj, detail: str) -> None:
    """A stand-in for QPPGMDMP, the spooled file a real formatted dump goes to when an RPG program ends
    in error (confirmed by a web search of an IBM manual excerpt, not a page read in full). A real dump
    also shows the statement in error, the call stack and every variable's value; by the time an
    exception here reaches this far the interpreter's own call stack has already unwound past them
    (each CALL restores `active` in a `finally` as the error passes through it), so none of that is
    shown, and this says so rather than guessing at it."""
    now = datetime.now()
    out = [f" {'Program dump':<60}{now:%y-%m-%d}  {now:%H:%M:%S}",
           f" Program . . . . . : {obj.name}      Library . . . . . : {obj.library}      "
           f"Owner . . . . . . : {obj.owner}", "", " Error:", f"   {detail}", "",
           " Not shown: the statement in error, the call stack and variable values. A real QPPGMDMP has",
           " all three; this is a simplified stand-in, not a capture.",
           "      * * * * *   E N D   O F   D U M P   * * * * *"]
    spoolmod.new_file(store, session, actor, "QPPGMDMP", out)


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
            if self.done:
                self.files.release_locks()     # the program ended (or abended): its record locks go with it
        if self.done and self.error and self.files:
            dump_program(self.files.store, self.files.actor, self.files.session, self.obj, self.error)

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
            self.files.release_locks()


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
        self.db = Database(authorize=self._authorize, lock=self._lock_record, unlock=self._unlock_record)
        self._held_locks: set[tuple] = set()            # (library, name, rrn) this run's db has locked
        self.objs: dict[str, Any] = {}
        self._lf_objs: dict[str, Any] = {}              # logical files opened: own name -> own object, for
                                                         # authority only (their records live on self.objs)
        self.spool = Spool()
        self.printers: dict[str, Any] = {}               # PRTF name -> its *FILE object
        self._spooled: dict[int, Any] = {}               # id of an open printer file -> the SpoolFile it fills

    def attach(self, prog, stack: list[str]) -> dict:
        """The record layouts for the DISK files a program declares, loading each file's records. A
        logical file has no records of its own: its physical file loads (once, under the physical
        file's own name, same as if a program opened it directly), and the logical file's own object
        is tracked only for authority checks against it."""
        from . import objects
        who = effective(self.store, self.actor, stack)
        pfs = {}
        for fs in prog.files:
            device = (fs.device or "").upper()
            if device not in ("DISK", "PRINTER"):
                continue
            name = fs.name.upper()
            # USROPN: the field layout binds to the name as declared, not whatever is overridden right
            # now (a real compiler binds the layout once, before any override can exist); the override
            # that matters for a USROPN file is read again, live, by open_user_file() when OPEN runs.
            user_open = device == "DISK" and getattr(fs, "user_open", False)
            opened = name if user_open else overrides.target(self.session, name)
            obj, err = objects.locate(self.store, who, opened, "*FILE", self.session.search_order())
            if err:
                raise RpgleError(err.text)
            if opened != name:
                self.session.joblog.append((datetime.now(), "message", f"File {name} overridden to {obj.library}/{obj.name}."))
            if device == "PRINTER":
                self._attach_printer(who, obj, name)
                continue
            attr = obj.data.get("attr", "PF")
            if attr == "LF":
                based_on = self._lf_base(obj)
                if based_on is None:
                    raise RpgleError(f"Physical file for logical file {obj.name} in library {obj.library} was "
                                     "not found.")
                pf = parse_pf(based_on.name, based_on.data["dds"])
                self._load_pf(based_on, pf)
                secondaries = {}
                for sobj in self._lf_joined(obj):
                    spf = parse_pf(sobj.name, sobj.data["dds"])
                    self._load_pf(sobj, spf)
                    secondaries[sobj.name] = spf
                    pfs.setdefault(sobj.name, spf)
                lf = parse_lf(obj.name, obj.data["dds"], pf, secondaries or None)
                self._lf_objs[obj.name] = obj
                pfs[name] = lf
                pfs.setdefault(based_on.name, pf)
                continue
            if attr != "PF" or not obj.data.get("dds"):
                raise RpgleError(f"File {obj.name} in library {obj.library} is not a physical file with a record layout.")
            pf = parse_pf(obj.name, obj.data["dds"])
            self._load_pf(obj, pf)
            pfs[name] = pf
        return pfs

    def open_user_file(self, name: str, mode: str):
        """The host side of OPEN on a USROPN file, called by the interpreter when the statement runs,
        not at program start. Unlike attach(), this re-applies whatever override is active right now
        (an OVRDBF the program itself issued after it started, through QCMDEXC, and before OPEN, is
        the whole reason USROPN exists) and re-checks authority against the stack running at that
        moment, through the same _authorize the rest of the file does."""
        from . import objects
        stack = list(self.loader.active) if self.loader is not None else []
        who = effective(self.store, self.actor, stack)
        up = name.upper()
        target = overrides.target(self.session, up)
        obj, err = objects.locate(self.store, who, target, "*FILE", self.session.search_order())
        if err:
            raise RpgleError(err.text)
        if target != up:
            self.session.joblog.append((datetime.now(), "message", f"File {up} overridden to {obj.library}/{obj.name}."))
        attr = obj.data.get("attr", "PF")
        if attr == "LF":
            raise RpgleError(f"File {obj.name} in library {obj.library}: OPEN on a logical file is not supported yet.")
        if attr != "PF" or not obj.data.get("dds"):
            raise RpgleError(f"File {obj.name} in library {obj.library} is not a physical file with a record layout.")
        pf = parse_pf(obj.name, obj.data["dds"])
        self._load_pf(obj, pf)
        return pf

    def _load_pf(self, obj, pf) -> None:
        """Loads a physical file's records into the run's database the first time anything (its own
        F-spec, or a logical file over it) opens it. A second F-spec on the same file, direct or
        through a different logical file, reuses what is already loaded."""
        prev = self.objs.get(obj.name)
        if prev is not None and prev is not obj:
            raise RpgleError(f"File {obj.name} is in two libraries ({prev.library} and {obj.library}) and only one "
                             "can be open in a job here.")
        if prev is None:
            self.objs[obj.name] = obj
            self.db.load_rows(pf, obj.data.get("records", []))

    def _lf_base(self, obj):
        """The physical file a logical file *FILE object was created over, by the fully qualified name
        CRTLF recorded in data["based_on"] (LIB/NAME). Fixed when the logical file is created, not
        re-resolved against the library list on every open, the same as a real system."""
        lib, _, name = obj.data.get("based_on", "").partition("/")
        return self.store.objects.get((lib.upper(), name.upper(), "*FILE"))

    def _lf_joined(self, obj) -> list:
        """The secondary physical files a join logical file was created over, by the fully qualified
        names CRTLF recorded in data["joined"] (JFILE order, after the primary). [] for a plain,
        single-file logical file."""
        out = []
        for qualified in obj.data.get("joined", []):
            lib, _, name = qualified.partition("/")
            pf_obj = self.store.objects.get((lib.upper(), name.upper(), "*FILE"))
            if pf_obj is None:
                raise RpgleError(f"Physical file {qualified} for logical file {obj.name} in library "
                                 f"{obj.library} was not found.")
            out.append(pf_obj)
        return out

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

    def _attach_printer(self, who, obj, name: str) -> None:
        """A printer file needs *USE, and so does the queue its output goes to. The queue and the file are
        checked now, as whoever the stack holds when the program is loaded. The spool file is the job's
        own, so it belongs to the user and not to an owner the program adopts. Kept under the F-spec's own
        declared `name`, not `obj.name`: an OVRPRTF resolves to a different object, but the program still
        WRITEs to the name it declared, and that is what rpgle_library's spool looks up by."""
        if obj.data.get("attr") != "PRTF" or not obj.data.get("dds"):
            raise RpgleError(f"File {obj.name} in library {obj.library} is not a printer file.")
        if USE not in self.store.authority_to_object(who, obj):
            raise RpgleError(messages.not_authorized_to_object(obj.name, obj.library, "*FILE").text)
        q = self.queue_of(obj)
        if q is None:
            raise RpgleError(f"Output queue {obj.data.get('outq', DEFAULT_OUTQ)} for {obj.name} not found.")
        if Auth.READ not in self.store.authority_to_object(who, q):
            raise RpgleError(messages.not_authorized_to_object(q.name, q.library, "*OUTQ").text)
        self.printers[name] = obj
        self.spool.defs[name] = parse_prtf(obj.name, obj.data["dds"])

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
        up = name.upper()
        obj = self.objs.get(up) or self._lf_objs.get(up)
        if obj is None:
            return
        stack = list(self.loader.active) if self.loader is not None else []
        who = effective(self.store, self.actor, stack)
        need = OPEN_NEEDS.get(op[5:], OPEN_NEEDS["I"]) if op.startswith("open:") else OP_NEEDS[op]
        if need not in self.store.authority_to_object(who, obj):
            self.session.joblog.append((datetime.now(), "message",
                                        f"{op.replace('open:', 'open ')} refused on {obj.library}/{obj.name}"))
            raise RpgleError(messages.not_authorized_to_object(obj.name, obj.library, "*FILE").text)

    def _job_id(self):
        """Who this run's record locks belong to: the real job when there is one, else this run's own
        session, so two runs in two unconnected test sessions still contend like two real jobs would."""
        return self.session.job.qualified if self.session.job is not None else id(self.session)

    def _lock_key(self, name: str, rrn: int) -> tuple:
        obj = self.objs.get(name.upper())
        lib = obj.library if obj is not None else "*"
        return (lib, name.upper(), rrn)

    def _lock_record(self, name: str, rrn: int) -> bool:
        key = self._lock_key(name, rrn)
        who = self._job_id()
        held = self.store.record_locks.get(key)
        if held is not None and held != who:
            return False
        self.store.record_locks[key] = who
        self._held_locks.add(key)
        return True

    def _unlock_record(self, name: str, rrn: int) -> None:
        key = self._lock_key(name, rrn)
        self.store.record_locks.pop(key, None)
        self._held_locks.discard(key)

    def release_locks(self) -> None:
        """Every record lock this run still holds, let go: what a job ending releases on a real
        system. Not scoped to one file, since any DISK file this run opened for update may hold one."""
        for key in list(self._held_locks):
            self.store.record_locks.pop(key, None)
        self._held_locks.clear()

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
                      system_programs={"QCMDEXC": make_qcmdexc(store, actor, session, loader)},
                      open_hook=files.open_user_file)
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
