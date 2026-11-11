"""DSPPTF: Display PTF Status. A real one lists every PTF known for a licensed program, each with
an apply status (temporarily applied, permanently applied, superseded, damaged...). Silverlake tracks
exactly one PTF, for IBM HTTP Server for i (5770DG1), recorded on QHTTPSVR/QZHBADMIN by the
httpadmin-ssi-injection lesson (the console in net/httpadmin.py reads the same record through
`fix_installed`). This models that one row, not a real product's PTF list, and says so for anything
else. Ours, not captured; no screen is built, only the message line a command without one already
uses elsewhere (CHGDTAARA, DLTUSRSPC)."""

from . import messages
from .profiles import ProfileStore

LICPGM = "5770DG1"
PTF_KEY = ("QHTTPSVR", "QZHBADMIN", "*PGM")
OS_LEVEL = "V7R4M0"
PTFS = {"V7R3M0": "SJ11641", "V7R4M0": "SJ11643", "V7R5M0": "SJ11644", "V7R6M0": "SJ11645"}


def fix_installed(store: ProfileStore) -> str | None:
    """The PTF recorded on the console's object, or None when the fix is not installed."""
    obj = store.objects.get(PTF_KEY)
    applied = obj.data.get("ptf", "*NONE") if obj else "*NONE"
    return None if applied == "*NONE" else applied


def status_message(store: ProfileStore, licpgm: str) -> messages.Message:
    licpgm = licpgm.upper()
    if licpgm != LICPGM:
        return messages.syntax(f"No PTF information is modeled for {licpgm}.")
    want = PTFS[OS_LEVEL]
    state = "Applied" if fix_installed(store) == want else "Not applied"
    return messages.info(f"PTF {want} for {licpgm}: {state}.")
