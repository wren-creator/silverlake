"""Data in physical files, from the command line: CPYF and what DSPPFM shows.

Not from a real system: none of this was captured. The authority each needs is from IBM's command pages as
remembered, not re-read, and the completion wording is ours (no message ID is checked). What the range
cares about:

  * CPYF needs `*USE` on the from-file and, on the to-file, `*OBJOPR` and `*ADD` (and `*DLT` to replace the
    records, `*UPD` to update them). It never needs anything on the program that normally guards the data.
  * A file CPYF creates (CRTFILE(*YES)) belongs to the person who copied, gets the library's create
    authority, and does not inherit the original's authorization list. A copy of a locked file is a file that
    is not locked, which is why `*USE` on payroll is not a small thing.
  * DSPPFM shows the records of a file to anyone with `*USE`, laid out as the raw characters of each record.

Simplifications: one member per file, so FROMMBR and TOMBR are accepted and ignored; source files are
refused (CPYSRCF is its own piece); FMTOPT *NONE needs the same field names, and *MAP and *NOCHK copy the
fields the two files share by name."""

from __future__ import annotations

from datetime import datetime

from . import messages, objects
from .authority import USE, Auth, SecuredObject, SpecialAuthority
from .objects import Done, _no, _ok, authority_to_library, locate
from .profiles import Profile, ProfileStore

try:
    from rpgle import parse_pf
except ImportError:                                           # the runtime is optional, as in rpg.py
    parse_pf = None

SA = SpecialAuthority
NEED_TO = {"*ADD": Auth.OBJOPR | Auth.ADD, "*REPLACE": Auth.OBJOPR | Auth.ADD | Auth.DLT,
           "*UPDADD": Auth.OBJOPR | Auth.ADD | Auth.UPD, "*NONE": Auth.OBJOPR | Auth.ADD}


def _allobj(store: ProfileStore, actor: Profile) -> bool:
    return SA.ALLOBJ in store.special_authorities(actor)


def is_data_file(obj: SecuredObject) -> bool:
    return obj.type == "*FILE" and obj.data.get("attr", "PF") == "PF" and bool(obj.data.get("dds"))


def find_data_file(store: ProfileStore, actor: Profile, session, spec: str, need: Auth = USE):
    """A physical file with a record layout, or the reason not. Returns (obj, None) or (None, message)."""
    obj, err = locate(store, actor, spec, "*FILE", session.search_order())
    if err:
        return None, err
    if need & ~store.authority_to_object(actor, obj) and not _allobj(store, actor):
        return None, messages.not_authorized_to_object(obj.name, obj.library, "*FILE")
    if not is_data_file(obj):
        return None, messages.info(f"File {obj.name} in library {obj.library} is not a physical file with a record "
                                   "layout.")
    return obj, None


def layout(obj: SecuredObject):
    return parse_pf(obj.name, obj.data["dds"])


def _blank(f) -> object:
    return " " * f.length if f.dtype == "A" else 0


def _map(src_pf, dst_pf, rec: dict, strict: bool):
    """The record as the to-file lays it out, or None when FMTOPT *NONE finds different fields."""
    names = [f.name for f in src_pf.fields]
    if strict and names != [f.name for f in dst_pf.fields]:
        return None
    return {f.name: rec.get(f.name, _blank(f)) for f in dst_pf.fields}


def copy_file(store: ProfileStore, actor: Profile, session, frm: str, to: str, mbropt: str, crtfile: bool,
              fmtopt: list[str], from_rcd: str, nbr: str) -> Done:
    if parse_pf is None:
        return _no(messages.info("The RPG runtime is not installed, so files cannot be read here."))
    src, err = find_data_file(store, actor, session, frm, USE)
    if err:
        return _no(err)
    to_obj, err = locate(store, actor, to, "*FILE", session.search_order())
    created = False
    if err:
        if not crtfile or "not found" not in err.text.lower():
            return _no(err)
        lib_name = to.split("/")[0].upper() if "/" in to else (session.current_library or "QGPL")
        if lib_name in ("*LIBL", "*CURLIB"):
            lib_name = session.current_library or "QGPL"
        lib = store.find_library(lib_name)
        if lib is None:
            return _no(messages.library_not_found(lib_name))
        if not _allobj(store, actor) and Auth.ADD not in authority_to_library(store, actor, lib):
            return _no(messages.not_authorized_to_library(lib_name))
        name = to.split("/")[-1].upper()
        to_obj = SecuredObject(name, actor.name, public=objects.create_authority(store, lib_name),
                               library=lib_name, type="*FILE", text=src.text,
                               data={"attr": "PF", "dds": src.data["dds"], "records": [],
                                     "created": datetime.now().isoformat(timespec="seconds")})
        objects.tag_temp(to_obj, session)
        created = True
    elif to_obj.key == src.key:
        return _no(messages.info("The from-file and the to-file are the same file."))
    elif need := NEED_TO.get(mbropt):
        if need & ~store.authority_to_object(actor, to_obj) and not _allobj(store, actor):
            return _no(messages.not_authorized_to_object(to_obj.name, to_obj.library, "*FILE"))
    if not created and not is_data_file(to_obj):
        return _no(messages.info(f"File {to_obj.name} in library {to_obj.library} is not a physical file with a "
                                 "record layout."))
    mode = fmtopt[0] if fmtopt else "*NONE"
    s_pf, d_pf = layout(src), layout(to_obj)
    records = src.data.get("records", [])
    first = 1 if from_rcd in ("*START", "") else int(from_rcd) if from_rcd.isdigit() else 0
    if first < 1:
        return _no(messages.syntax("Value for parameter FROMRCD not valid. Use *START or a record number."))
    chosen = records[first - 1:]
    if nbr != "*END":
        if not nbr.isdigit():
            return _no(messages.syntax("Value for parameter NBRRCDS not valid. Use *END or a number."))
        chosen = chosen[:int(nbr)]
    mapped = []
    for rec in chosen:
        out = _map(s_pf, d_pf, rec, mode == "*NONE")
        if out is None:
            return _no(messages.info("The record formats of the two files do not match. Use FMTOPT(*MAP) or "
                                     "FMTOPT(*NOCHK) to copy the fields they share."))
        mapped.append(out)
    existing = to_obj.data.setdefault("records", [])
    if existing and mbropt == "*NONE":
        return _no(messages.info(f"File {to_obj.name} in library {to_obj.library} already has records. Use "
                                 "MBROPT(*ADD), *REPLACE or *UPDADD."))
    keys = d_pf.keys
    if mbropt == "*UPDADD" and not keys:
        return _no(messages.info("MBROPT(*UPDADD) needs a keyed to-file."))
    new = [] if mbropt == "*REPLACE" else list(existing)
    for rec in mapped:
        if mbropt == "*UPDADD":
            at = next((i for i, r in enumerate(new) if all(r.get(k) == rec.get(k) for k in keys)), None)
            if at is not None:
                new[at] = rec
                continue
        elif keys and d_pf.unique and any(all(r.get(k) == rec.get(k) for k in keys) for r in new):
            return _no(messages.info("Copy ended: a record with the same key is already in the to-file."))
        new.append(rec)
    if created:
        store.objects[to_obj.key] = to_obj
    to_obj.data["records"] = new
    store.on_change()
    made = f"File {to_obj.name} created in library {to_obj.library}. " if created else ""
    return _ok(f"{made}{len(mapped)} records copied from file {src.name} to file {to_obj.name}.")


# -- CHGPF, RGZPFM, CLRPFM ----------------------------------------------------------------------------------

def change_physical_file(store: ProfileStore, actor: Profile, session, spec: str) -> Done:
    """CHGPF FILE(lib/name). Needs *OBJMGT or *OBJALTER on the file and *EXECUTE on its library (IBM's
    CHGPF page, from a web search, not read in full -- it also wants an exclusive lock with no one
    using the file, not modeled here). FILE is CHGPF's only required parameter; everything else it
    takes (SIZE, MAXMBRS, REUSEDLT, LVLCHK, ALLOCATE, CONTIG and the rest) changes an attribute this
    minimal PF model doesn't track, so the command exists for its authority check and completion
    message, not because anything it could change here has anywhere to go."""
    obj, err = locate(store, actor, spec, "*FILE", session.search_order())
    if err:
        return _no(err)
    if not _allobj(store, actor):
        if not store.authority_to_object(actor, obj) & (Auth.OBJMGT | Auth.OBJALTER):
            return _no(messages.not_authorized_to_object(obj.name, obj.library, "*FILE"))
        lib = store.find_library(obj.library)
        if lib is None or Auth.EXECUTE not in authority_to_library(store, actor, lib):
            return _no(messages.not_authorized_to_library(obj.library))
    if not is_data_file(obj):
        return _no(messages.info(f"File {obj.name} in library {obj.library} is not a physical file with a "
                                 "record layout."))
    store.on_change()
    return _ok(f"File {obj.name} in library {obj.library} changed.")


def reorganize_member(store: ProfileStore, actor: Profile, session, spec: str) -> Done:
    """RGZPFM FILE(lib/name). Needs *OBJOPR, *OBJMGT or *OBJALTER, and all the data authorities (*READ
    *ADD *UPD *DLT) on the file, and *EXECUTE on its library (a forum's quote of RGZPFM's own help
    text, not an IBM reference page read in full). A real RGZPFM compacts the gap a deleted record
    leaves; this PF model deletes a record outright (a SQLite DELETE, by way of rpgle_library's
    Database), so there is no gap here to compact. The command exists for its authority check and
    completion message."""
    obj, err = locate(store, actor, spec, "*FILE", session.search_order())
    if err:
        return _no(err)
    if not _allobj(store, actor):
        have = store.authority_to_object(actor, obj)
        needed = Auth.OBJOPR | Auth.READ | Auth.ADD | Auth.UPD | Auth.DLT
        if (needed & ~have) or not (have & (Auth.OBJMGT | Auth.OBJALTER)):
            return _no(messages.not_authorized_to_object(obj.name, obj.library, "*FILE"))
        lib = store.find_library(obj.library)
        if lib is None or Auth.EXECUTE not in authority_to_library(store, actor, lib):
            return _no(messages.not_authorized_to_library(obj.library))
    if not is_data_file(obj):
        return _no(messages.info(f"File {obj.name} in library {obj.library} is not a physical file with a "
                                 "record layout."))
    store.on_change()
    return _ok(f"Member {obj.name} in file {obj.name} in library {obj.library} reorganized.")


def clear_member(store: ProfileStore, actor: Profile, session, spec: str) -> Done:
    """CLRPFM FILE(lib/name). Needs *OBJOPR, *OBJMGT or *OBJALTER, and *DLT on the file, and *EXECUTE on
    its library (IBM's CL reference, which a web search quoted rather than the page itself; CPF3137 on
    refusal). Deletes every record in the member; the file object itself, and its authority, stay."""
    obj, err = locate(store, actor, spec, "*FILE", session.search_order())
    if err:
        return _no(err)
    if not _allobj(store, actor):
        have = store.authority_to_object(actor, obj)
        needed = Auth.OBJOPR | Auth.DLT
        if (needed & ~have) or not (have & (Auth.OBJMGT | Auth.OBJALTER)):
            return _no(messages.not_authorized_to_clear(obj.name, obj.library))
        lib = store.find_library(obj.library)
        if lib is None or Auth.EXECUTE not in authority_to_library(store, actor, lib):
            return _no(messages.not_authorized_to_library(obj.library))
    if not is_data_file(obj):
        return _no(messages.info(f"File {obj.name} in library {obj.library} is not a physical file with a "
                                 "record layout."))
    n = len(obj.data.get("records", []))
    obj.data["records"] = []
    store.on_change()
    return _ok(f"{n} records cleared from file {obj.name} in library {obj.library}.")


# -- CPYTOIMPF ------------------------------------------------------------------------------------------

RCDDLM = {"*CRLF": "\r\n", "*LF": "\n", "*CR": "\r", "*LFCR": "\n\r", "*EOR": "\n"}


def copy_to_import_file(store: ProfileStore, actor: Profile, session, frm: str, to: str, rcddlm: str,
                        strdlm: str) -> Done:
    """CPYTOIMPF FROMFILE(lib/file) TOFILE('/ifs/path') RCDDLM(*CRLF|*LF|*CR|*LFCR|*EOR) STRDLM(*DBLQUOTE|*NONE).
    RCDDLM's and STRDLM's choices are IBM's own (from a web search of the command page, not read in full);
    the delimited line itself -- character fields quoted unless STRDLM(*NONE), numbers written plain,
    fields comma-separated -- is ours, since the page's own grammar for that was not found. Needs *USE on
    the from-file; what writing the IFS path needs is `ifs.write`'s own rules, not a separate authority
    of CPYTOIMPF's."""
    from . import ifs
    src, err = find_data_file(store, actor, session, frm, USE)
    if err:
        return _no(err)
    delim = RCDDLM.get(rcddlm, "\r\n")
    quote = strdlm != "*NONE"
    pf = layout(src)
    lines = []
    for rec in src.data.get("records", []):
        fields = []
        for f in pf.fields:
            v = rec.get(f.name, _blank(f))
            fields.append(f'"{v}"' if quote and f.dtype == "A" else str(v))
        lines.append(",".join(fields))
    text = "".join(line + delim for line in lines)
    try:
        ifs.write(store, actor, to, text)
    except ifs.IfsError as exc:
        return _no(messages.info(str(exc)))
    return _ok(f"{len(lines)} records copied from file {src.name} to member {to}.")


# -- DSPPFM -------------------------------------------------------------------------------------------------

def record_text(pf, rec: dict) -> str:
    """The raw characters of a record: character fields as they are, numbers as digits without the decimal
    point, zero filled (a real display shows the sign in the last digit's zone, which is not shown here)."""
    out = []
    for f in pf.fields:
        v = rec.get(f.name, _blank(f))
        if f.dtype == "A":
            out.append(str(v).ljust(f.length)[:f.length])
        else:
            scaled = int(round(abs(float(v)) * (10 ** f.dec)))
            out.append(str(scaled).zfill(f.length)[-f.length:])
    return "".join(out)
