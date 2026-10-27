"""Running RPG IV programs inside a session, on the rpgle runtime.

A program object (`*PGM`, attribute RPGLE) keeps its source in `data["source"]` and the DDS of its
display file in `data["dspf"]`. CALL starts it as a generator, and every EXFMT becomes a screen on
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
from . import messages

try:
    from rpgle import (CallError, LoadedProgram, ProgramLoader, Resume, RpgleError, parse_dds, parse_rpgle,
                       run_program)
    AVAILABLE = True
except ImportError:                       # the RPG runtime is optional: Silverlake runs without it
    AVAILABLE = False

MAX_STEPS = 200_000      # instructions between screens before a program is stopped
_FAILED = ("not found", "not authorized", "not valid", "does not exist", "already exists", "not correct",
           "cannot", "not allowed", "parenthesis", "not available", "not modeled")


def not_installed() -> messages.Message:
    return messages.info("The RPG runtime (rpgle_library) is not installed, so RPG programs cannot run.")


def is_rpg(obj) -> bool:
    return obj.type == "*PGM" and obj.data.get("attr") in ("RPGLE", "RPG") and bool(obj.data.get("source"))


class Run:
    """One running program: its generator, the screen it is showing, and how it ended."""

    def __init__(self, obj, gen) -> None:
        self.obj = obj
        self.gen = gen
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

    def start(self) -> "Run":
        self._advance(None)
        return self

    def send(self, key: str, values: dict[str, str]) -> None:
        self._advance(Resume(key=key, values=values))

    def close(self) -> None:
        self.gen.close()
        self.done = True


class StoreLoader(ProgramLoader if AVAILABLE else object):
    """Finds the programs a program CALLs among the session's objects instead of in folders, and only
    those the profile may use: a program you cannot call cannot be reached through one you can."""

    def __init__(self, store, actor, search: list[str]) -> None:
        super().__init__(dirs=[], main=None)
        self.store, self.actor, self.search = store, actor, search
        self._loaded: dict[tuple, Any] = {}

    def _find(self, target: str):
        from . import objects                               # imported late: objects imports a lot
        name = target.strip().strip("'\"").strip().upper()
        if not all(p and p.replace("_", "").replace("$", "").replace("#", "").replace("@", "").isalnum()
                   for p in name.split("/")) or name.count("/") > 1:
            raise CallError(f"{target.strip()!r} is not a program name")
        obj, err = objects.use_object(self.store, self.actor, name, "*PGM", self.search)
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
            cached = LoadedProgram(key=key, path=Path(f"/QSYS.LIB/{obj.library}.LIB/{obj.name}.PGM"), prog=prog,
                                   dds=parse_dds(obj.data.get("dspf", "")), pfs={})
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
        dds = parse_dds(obj.data.get("dspf", ""))
    except RpgleError as exc:
        return None, messages.info(f"Program {obj.name} did not load: {exc}")
    loader = StoreLoader(store, actor, session.search_order())
    loader.main_name = f"{obj.library}/{obj.name}"
    gen = run_program(prog, dds, None, None, loader, None, max_steps=MAX_STEPS,
                      system_programs={"QCMDEXC": make_qcmdexc(store, actor, session, loader)})
    return Run(obj, gen).start(), None


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
