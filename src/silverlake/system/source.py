"""Source files, their members, and the commands that compile them.

A source physical file is a `*FILE` with attribute `PF-SRC`. Its `members` are kept in the object:
{name: {"type": "RPGLE", "text": "...", "lines": [...], "changed": iso time}}. A line is the data part
of a source record, the way SEU shows it (columns 1 to 80 of an RPG or DDS line, the first five being the
sequence area the compiler ignores). The default record length is 92 (captured on PUB400: CRTSRCPF RCDLEN
92), which is 12 for the sequence number and date and 80 for the line.

CRTBNDRPG, CRTPF, CRTDSPF and CRTPRTF read a member, check it, and make the object: a `*PGM` that carries
the source for the runtime, or a `*FILE` that carries the DDS. They also print a compile listing to the
spool as QSYSPRT, the way a real compile does.

What came from a real system (PUB400, read-only captures `auth-pdm`):
  * the prompt layouts and defaults of the five commands (the prompts themselves are not built yet),
  * CRTBNDRPG with a source library that is not there says "Unable to open member NOPGM of file
    QRPGLESRC in library NOSUCH.", and the same wording is used here for any member that cannot be opened.
What is ours: every message that reports a finished or failed compile, the listing, and what happens
when a program that already exists is replaced (the new owner is the compiling user and the old
authorities are kept, from memory of IBM's REPLACE(*YES) behavior, not read on a page)."""

from __future__ import annotations

from datetime import datetime

from . import messages, spool as spoolmod
from .authority import USE, Auth, SecuredObject, SpecialAuthority
from .objects import NAME, Done, _no, _ok, authority_to_library, locate
from .profiles import Profile, ProfileStore

SA = SpecialAuthority
SRC_ATTR = "PF-SRC"
DEFAULT_RCDLEN = 92
SEQ_WIDTH = 12                      # sequence number and date, in front of the data of every source record


def is_source(obj: SecuredObject) -> bool:
    return obj.type == "*FILE" and obj.data.get("attr") == SRC_ATTR


def width(obj: SecuredObject) -> int:
    """How many characters of a line a member of this file can hold."""
    return int(obj.data.get("rcdlen", DEFAULT_RCDLEN)) - SEQ_WIDTH


def _doc(id_: str, text: str) -> messages.Message:
    return messages.Message(id_, text, "no message ID checked; the wording is ours")


def _allobj(store: ProfileStore, actor: Profile) -> bool:
    return SA.ALLOBJ in store.special_authorities(actor)


# -- finding source ----------------------------------------------------------------------------------

def find_file(store: ProfileStore, actor: Profile, session, spec: str, need: Auth = USE, seu: bool = False):
    """A source file by `LIB/FILE` or `FILE` through the library list, with what PDM and SEU say when it
    cannot be had (captured: "Library NOSUCH was not found." from PDM and "Library NOSUCH not found." from
    SEU, and "You do not have authority to file QCLSRC in QGPL."). Returns (file, None) or (None, message)."""
    name = spec.split("/")[-1].upper()
    lib = spec.split("/")[0].upper() if "/" in spec else "*LIBL"
    if lib in ("*LIBL", "*CURLIB"):
        search = session.search_order()
        if lib == "*CURLIB":
            search = [session.current_library or "QGPL"]
        found = next((lb for lb in search if (lb, name, "*FILE") in store.objects), None)
        if found is None:
            return None, messages.info(f"File {name} not found in library {lib}.")
        lib = found
    libobj = store.find_library(lib)
    if libobj is None:
        return None, messages.info(f"Library {lib} not found." if seu else f"Library {lib} was not found.")
    obj = store.objects.get((lib, name, "*FILE"))
    if obj is None:
        return None, messages.info(f"File {name} not found in library {lib}.")
    if Auth.EXECUTE not in authority_to_library(store, actor, libobj) or need & ~store.authority_to_object(actor, obj):
        return None, messages.info(f"You do not have authority to file {name} in {lib}.")
    if not is_source(obj):
        return None, messages.info(f"File {name} in library {lib} is not a source file.")
    return obj, None


WRITE = Auth.OBJOPR | Auth.READ | Auth.ADD | Auth.UPD | Auth.DLT


def can_write(store: ProfileStore, actor: Profile, obj: SecuredObject) -> bool:
    return _allobj(store, actor) or not (WRITE & ~store.authority_to_object(actor, obj))


def member(obj: SecuredObject, name: str) -> dict | None:
    return obj.data.get("members", {}).get(name.upper())


def put_member(store: ProfileStore, obj: SecuredObject, name: str, lines: list[str], type_: str | None = None,
               text: str | None = None) -> dict:
    """Create or replace a member. Lines are cut to the file's width, which is what a record of that
    length can hold."""
    name = name.upper()
    members = obj.data.setdefault("members", {})
    cur = members.get(name, {"type": type_ or "", "text": "", "lines": []})
    cur["lines"] = [ln.rstrip()[:width(obj)] for ln in lines]
    if type_ is not None:
        cur["type"] = type_
    if text is not None:
        cur["text"] = text
    cur["changed"] = datetime.now().isoformat(timespec="seconds")
    members[name] = cur
    store.on_change()
    return cur


def delete_member(store: ProfileStore, obj: SecuredObject, name: str) -> bool:
    gone = obj.data.get("members", {}).pop(name.upper(), None) is not None
    if gone:
        store.on_change()
    return gone


# -- CRTSRCPF ------------------------------------------------------------------------------------------

def _target(store: ProfileStore, actor: Profile, session, spec: str):
    """Library and name for something new. Returns (lib name, name, library object, message)."""
    lib_name, _, name = spec.upper().rpartition("/")
    if lib_name in ("", "*CURLIB"):
        lib_name = session.current_library or "QGPL"
    if lib_name == "*LIBL":
        return None, None, None, messages.syntax("*LIBL is not valid for a new object, name the library.")
    if not NAME.match(name):
        return None, None, None, messages.syntax(f"Object name {name} is not valid.")
    lib = store.find_library(lib_name)
    if lib is None:
        return None, None, None, _doc("CPF2110", f"Library {lib_name} not found.")
    if not _allobj(store, actor) and Auth.ADD not in authority_to_library(store, actor, lib):
        return None, None, None, messages.not_authorized_to_library(lib_name)
    return lib_name, name, lib, None


def _create_authority(store: ProfileStore, lib_name: str) -> Auth:
    lib = store.find_library(lib_name)
    return lib.public if lib is not None and lib.public is not None else Auth.NONE


def create_source_file(store: ProfileStore, actor: Profile, session, spec: str, rcdlen: int, mbr: str,
                       text: str) -> Done:
    lib_name, name, _, err = _target(store, actor, session, spec)
    if err:
        return _no(err)
    if (lib_name, name, "*FILE") in store.objects:
        return _no(_doc("CPF5813", f"File {name} in library {lib_name} already exists."))
    if not 28 <= rcdlen <= 32766:
        return _no(messages.syntax("Value for parameter RCDLEN not valid. Use 28 to 32766."))
    obj = SecuredObject(name, actor.name, public=_create_authority(store, lib_name), library=lib_name, type="*FILE",
                        text=text, data={"attr": SRC_ATTR, "rcdlen": rcdlen, "members": {},
                                         "created": datetime.now().isoformat(timespec="seconds")})
    store.objects[obj.key] = obj
    if mbr not in ("*NONE", ""):
        put_member(store, obj, mbr.upper(), [], text="")
    store.on_change()
    return _ok(f"File {name} created in library {lib_name}.")


# -- the compile listing --------------------------------------------------------------------------------

def _listing(store: ProfileStore, actor: Profile, session, title: str, command: str, lines: list[str],
             problems: list[tuple[str, str]], outcome: str, user_data: str) -> None:
    """Put the compile listing on the spool as QSYSPRT, in the job, on QGPL/QPRINT, as the user. The layout
    is the shape of a real listing (header, source, messages, end), the wording is ours."""
    now = datetime.now()
    out = [f" {title:<60}{now:%y-%m-%d}  {now:%H:%M:%S}", f" Command . . . . . : {command}", ""]
    out.append(" Line  Source")
    out += [f" {i:>4}  {ln}" for i, ln in enumerate(lines, 1)] or ["       (no source lines)"]
    out += ["", " Messages"]
    out += [f" {sev:<5} {text}" for sev, text in problems] or [" (none)"]
    out += ["", f" {outcome}", "      * * * * *   E N D   O F   L I S T I N G   * * * * *"]
    spoolmod.new_file(store, session, actor, "QSYSPRT", out, user_data)


# -- opening the member to compile ------------------------------------------------------------------------

def _open_for_compile(store, actor, session, srcfile: str, mbr: str):
    """The member or the one message the compiler gives for every way it cannot be opened (captured)."""
    file_name = srcfile.split("/")[-1].upper()
    lib = srcfile.split("/")[0].upper() if "/" in srcfile else "*LIBL"
    obj, err = find_file(store, actor, session, srcfile)
    cannot = messages.info(f"Unable to open member {mbr} of file {file_name} in library {lib}.")
    if err or member(obj, mbr) is None:
        return None, None, cannot
    return obj, member(obj, mbr), None


def _text_for(requested: str, mem: dict) -> str:
    return mem.get("text", "") if requested == "*SRCMBRTXT" else requested


def _place(store: ProfileStore, actor: Profile, session, lib_name: str, name: str, typ: str, text: str,
           data: dict, replace_ok: bool) -> tuple[SecuredObject | None, messages.Message | None]:
    """Put the new object in its library. An existing one is replaced when that is allowed (a program) and
    refused when it is not (a file). A replaced object belongs to the user from now on and keeps the
    authorities it had."""
    key = (lib_name, name, typ)
    old = store.objects.get(key)
    if old is not None:
        if not replace_ok:
            return None, _doc("CPF5813", f"File {name} in library {lib_name} already exists.")
        if not _allobj(store, actor) and Auth.OBJEXIST not in store.authority_to_object(actor, old):
            return None, messages.not_authorized_to_object_2189(name, lib_name, typ)
    obj = SecuredObject(name, actor.name, public=old.public if old else _create_authority(store, lib_name),
                        library=lib_name, type=typ, text=text, data=data,
                        private=dict(old.private) if old else {}, autl=old.autl if old else None)
    store.objects[obj.key] = obj
    store.on_change()
    return obj, None


# -- CRTBNDRPG --------------------------------------------------------------------------------------------

def compile_rpg(store: ProfileStore, actor: Profile, session, pgm: str, srcfile: str, srcmbr: str, text: str,
                usrprf: str, useadpaut: bool) -> Done:
    """CRTBNDRPG. The program is named by PGM, or by the member when PGM is *CTLSPEC (which would be the H-spec
    name on a real system, not read here), and the member by SRCMBR, or by the program when SRCMBR is *PGM."""
    from .rpg import AVAILABLE
    if not AVAILABLE:
        return _no(messages.info("The RPG runtime (rpgle_library) is not installed, so RPG programs cannot be compiled."))
    pgm_name = pgm.split("/")[-1].upper()
    if pgm_name == "*CTLSPEC":
        if srcmbr == "*PGM":
            return _no(messages.syntax("Parameter PGM required."))
        pgm_name = srcmbr.upper()
        pgm = pgm_name if "/" not in pgm else pgm.split("/")[0] + "/" + pgm_name
    if srcmbr == "*PGM":
        srcmbr = pgm_name
    srcmbr = srcmbr.upper()
    src, mem, cannot = _open_for_compile(store, actor, session, srcfile, srcmbr)
    if cannot:
        return _no(cannot)
    lib_arg = pgm.split("/")[0] if "/" in pgm else "*CURLIB"
    lib_name, name, _, err = _target(store, actor, session, f"{lib_arg}/{pgm_name}")
    if err:
        return _no(err)
    lines = list(mem["lines"])
    problems = _check_rpg(store, actor, session, "\n".join(lines) + "\n")
    cmd = (f"CRTBNDRPG PGM({lib_name}/{name}) SRCFILE({src.library}/{src.name}) SRCMBR({srcmbr})"
           f" USRPRF({usrprf}) USEADPAUT({'*YES' if useadpaut else '*NO'})")
    title = "Compile listing, RPG IV"
    errors = [p for p in problems if p[0] != "00"]
    if errors:
        _listing(store, actor, session, title, cmd, lines, problems,
                 f"Compilation failed. Program {name} not created in library {lib_name}.", name)
        return _no(_doc("RNS9308", f"Compilation failed. Program {name} not created in library {lib_name}."))
    data = {"attr": "RPGLE", "usrprf": usrprf, "useadpaut": "*YES" if useadpaut else "*NO",
            "source": "\n".join(lines) + "\n", "srcfile": f"{src.library}/{src.name}", "srcmbr": srcmbr,
            "created": datetime.now().isoformat(timespec="seconds")}
    obj, err = _place(store, actor, session, lib_name, name, "*PGM", _text_for(text, mem), data, replace_ok=True)
    if err:
        return _no(err)
    now = datetime.now()
    done = f"Program {name} placed in library {lib_name}. 00 highest severity. Created on {now:%m/%d/%y} at {now:%H:%M:%S}."
    _listing(store, actor, session, title, cmd, lines, problems, done, name)
    return Done(True, _doc("RNS9310", done))


def _check_rpg(store: ProfileStore, actor: Profile, session, source: str) -> list[tuple[str, str]]:
    """What the compiler found, as (severity, text). Syntax and structure come from the runtime's parser, and
    every file the program declares has to exist on the library list and be usable, because a compile
    cannot describe fields of a file it cannot find."""
    from rpgle import RpgleError, compile_program, parse_rpgle
    try:
        prog = parse_rpgle(source)
        compile_program(prog.statements)
    except RpgleError as exc:
        return [("40", str(exc))]
    problems: list[tuple[str, str]] = []
    wanted = {"DISK": {"PF"}, "PRINTER": {"PRTF"}, "WORKSTN": {"DSPF"}}
    for fs in prog.files:
        device = (fs.device or "").upper()
        if device not in wanted:
            continue
        found, err = locate(store, actor, fs.name.upper(), "*FILE", session.search_order())
        if err:
            problems.append(("40", f"File {fs.name.upper()} was not found, so its fields cannot be described."))
        elif found.data.get("attr") not in wanted[device]:
            problems.append(("40", f"File {found.name} is not the kind of file the F-spec says ({device})."))
        elif USE & ~store.authority_to_object(actor, found):
            problems.append(("40", f"You do not have authority to file {found.name} in {found.library}."))
    return problems or [("00", "No errors.")]


# -- CRTPF, CRTDSPF, CRTPRTF ------------------------------------------------------------------------------

KINDS = {"PF": "Physical file", "DSPF": "Display file", "PRTF": "Printer file"}


def compile_dds(store: ProfileStore, actor: Profile, session, kind: str, file: str, srcfile: str, srcmbr: str,
                text: str) -> Done:
    """CRTPF, CRTDSPF and CRTPRTF, all from a DDS member. A file with no source (SRCFILE(*NONE) and a record
    length) is not built."""
    from rpgle import RpgleError, parse_dds, parse_pf, parse_prtf
    name = file.split("/")[-1].upper()
    if srcfile == "*NONE":
        return _no(messages.info("A file without DDS source is not built. Name a SRCFILE."))
    mbr = (name if srcmbr == "*FILE" else srcmbr).upper()
    src, mem, cannot = _open_for_compile(store, actor, session, srcfile, mbr)
    if cannot:
        return _no(cannot)
    lib_arg = file.split("/")[0] if "/" in file else "*CURLIB"
    lib_name, name, _, err = _target(store, actor, session, f"{lib_arg}/{name}")
    if err:
        return _no(err)
    lines = list(mem["lines"])
    dds = "\n".join(lines) + "\n"
    problems: list[tuple[str, str]] = []
    try:
        if kind == "PF":
            pf = parse_pf(name, dds)
            if not pf.fields:
                problems.append(("30", "The source describes no fields."))
        elif kind == "PRTF":
            parse_prtf(name, dds)
        else:
            parse_dds(dds)
    except RpgleError as exc:
        problems.append(("40", str(exc)))
    cmd = f"CRT{kind} FILE({lib_name}/{name}) SRCFILE({src.library}/{src.name}) SRCMBR({mbr})"
    title = f"Compile listing, DDS ({kind})"
    if problems:
        done = f"File {name} not created in library {lib_name}."
        _listing(store, actor, session, title, cmd, lines, problems, done, name)
        return _no(_doc("CPF7302", done))
    data = {"attr": kind, "dds": dds, "created": datetime.now().isoformat(timespec="seconds")}
    if kind == "PF":
        data["records"] = []
    if kind == "PRTF":
        data["outq"] = "QGPL/QPRINT"
    obj, err = _place(store, actor, session, lib_name, name, "*FILE", _text_for(text, mem), data, replace_ok=False)
    if err:
        return _no(err)
    _listing(store, actor, session, title, cmd, lines, [("00", "No errors.")], f"File {name} created.", name)
    return Done(True, _doc("CPC7301", f"File {name} created in library {lib_name}."))
