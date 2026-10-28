"""The IBM i side of PASE: what the shell needs to read system values, data areas, data queues and spooled files, and
the small tables behind `sysval` and `getconf`.

Wording and layout come from the PUB400 captures of 2026-10-28 (ssh-pase-b3a, b3b, b3c, kept local). Values in the
tables are PUB400's where captured and made up where the simulator has no such setting; docs/pase.md says which.

A data area is a `*DTAARA` object, `data = {"value": "...", "length": N}` (character only), and a data queue a
`*DTAQ`, `data = {"entries": [...], "maxlen": N}`. Reading takes *USE and changing takes *CHANGE, as the CL commands
RTVDTAARA and CHGDTAARA do; the library still has to be reachable (`authority_to_object` checks it)."""

from __future__ import annotations

import re

from .authority import Auth, SecuredObject, SpecialAuthority
from .profiles import Profile, ProfileStore

MAX_DTAARA = 2000                              # characters one data area may hold
MAX_QUEUE = 100                                # entries one data queue keeps

# system values the simulator has no setting for, so they are fixed. QCCSID, QMODEL, QLANGID and QSRLNBR are PUB400's,
# except that a serial number is not ours to publish: it is made up.
STATIC_SYSVALS = {"QCCSID": "273", "QMODEL": " 22A", "QLANGID": "ENU", "QSRLNBR": " 7SLK001", "QCNTRYID": "US",
                  "QDATFMT": "MDY", "QTIMSEP": ":", "QDATSEP": "/", "QSYSLIBL": "QSYS QSYS2 QHLPSYS QUSRSYS"}
# (zero padding width) for the ones PUB400 printed padded; the rest print as the number
PADDED = {"QMAXSIGN": 6}
MODELED = {"QSECURITY": "qsecurity", "QPWDLVL": "qpwdlvl", "QMAXSIGN": "qmaxsign", "QMAXSGNACN": "qmaxsgnacn",
           "QPWDEXPITV": "qpwdexpitv", "QPWDEXPWRN": "qpwdexpwrn", "QPWDMINLEN": "qpwdminlen",
           "QPWDMAXLEN": "qpwdmaxlen", "QPWDRQDDGT": "qpwdrqddgt", "QPWDLMTAJC": "qpwdlmtajc",
           "QPWDLMTREP": "qpwdlmtrep", "QPWDRQDDIF": "qpwdrqddif"}
NETATTRS = {"SYSNAME": "SILVERLAKE", "LCLNETID": "APPN", "LCLCPNAME": "SILVERLAKE", "LCLLOCNAME": "SILVERLAKE",
            "DMNNAME": "silverlake.localdomain"}

# getconf: PUB400's answers. _NPROCESSORS_ONLN and anything unlisted was "not valid on this system".
GETCONF = {"PATH": "/QOpenSys/usr/bin", "PAGESIZE": "4096", "PAGE_SIZE": "4096", "CHILD_MAX": "128",
           "ARG_MAX": "4194304", "OPEN_MAX": "65534"}
GETCONF_PATH = {"NAME_MAX": "255", "PATH_MAX": "4095"}     # PATH_MAX was not captured: the PASE value, a guess


def sysval(store: ProfileStore, name: str) -> str | None:
    """A system value as `sysval` prints it, or None when the name is not one."""
    name = name.upper()
    if name in MODELED:
        raw = getattr(store.system, MODELED[name])
        return str(raw).zfill(PADDED.get(name, 0))
    return STATIC_SYSVALS.get(name)


def dspmsg(args: list[str]) -> tuple[str, int]:
    """The AIX catalog utility, not an IBM i message file. With no catalog behind it, it prints the default text with
    %s and %d filled from the arguments, and no newline at the end (PUB400 printed `hello world` that way)."""
    rest = list(args)
    if rest[:1] == ["-s"] and len(rest) >= 2:
        rest = rest[2:]
    if len(rest) < 2:
        return "Usage: dspmsg [-s setno] <catname> <msgno> ['default' arg ... ]", 1
    if len(rest) == 2:
        return "dspmsg: missing default message", 1
    text, values = rest[2], rest[3:]
    for v in values:
        text = re.sub(r"%(?:\d+\$)?[sd]", lambda m, v=v: v, text, count=1)
    return text, 0


# -- data areas ---------------------------------------------------------------------------------------------------

def parse_qsys_path(path: str) -> tuple[str, str, str] | None:
    """(library, name, type) for /QSYS.LIB/LIB.LIB/NAME.TYPE, else None."""
    m = re.fullmatch(r"/QSYS\.LIB/([^/]+)\.LIB/([^/]+)\.([A-Za-z]+)", path, re.IGNORECASE)
    return (m[1].upper(), m[2].upper(), "*" + m[3].upper()) if m else None


def find_object(store: ProfileStore, actor: Profile, path: str, want: str):
    """(object, None) or (None, error text), the error being what the QSH utility said."""
    key = parse_qsys_path(path)
    if key is None or key[2] != want:
        return None, "must specify an object in the QSYS.LIB file system."
    obj, lib = store.objects.get(key), store.find_library(key[0])
    if obj is None or lib is None or (SpecialAuthority.ALLOBJ not in store.special_authorities(actor)
                                      and Auth.EXECUTE not in store.object_authority(actor, lib)):
        return None, "missing"
    return obj, None


def may(store: ProfileStore, actor: Profile, obj: SecuredObject, need: Auth) -> bool:
    return need in store.authority_to_object(actor, obj)


def area_text(obj: SecuredObject, substring: str | None) -> str:
    value = obj.data.get("value", "")
    if substring:
        m = re.fullmatch(r"(\d+)(?:,(\d+))?", substring)
        if m:
            start = int(m[1]) - 1
            end = start + int(m[2]) if m[2] else len(value)
            value = value[max(start, 0):end]
    return value


def area_set(store: ProfileStore, obj: SecuredObject, text: str, substring: str | None) -> None:
    length = int(obj.data.get("length", len(obj.data.get("value", ""))))
    value = obj.data.get("value", "").ljust(length)
    if substring and (m := re.fullmatch(r"(\d+)(?:,(\d+))?", substring)):
        start = max(int(m[1]) - 1, 0)
        width = int(m[2]) if m[2] else len(text)
        value = value[:start] + text[:width].ljust(width) + value[start + width:]
    else:
        value = text
    obj.data["value"] = value[:length].ljust(length)
    store.on_change()
