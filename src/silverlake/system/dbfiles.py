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
        to_obj = SecuredObject(name, actor.name, public=lib.public if lib.public is not None else Auth.NONE,
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
