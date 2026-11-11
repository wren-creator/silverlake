"""CHGFTPA: Change FTP Attributes, from IBM i's command page (read, not captured). The command needs
*IOSYSCFG, and a changed attribute applies to new connections only, not ones already open.

AUTOSTART controls whether the FTP server starts when TCP/IP starts (STRTCP, or STRTCPSVR with
*AUTOSTART); Silverlake has no STRTCP to obey it, so the value is recorded and not enforced, the same
way LMTCPB was before the command line enforced it. CCSID is accepted and ignored: character
conversion between the job and the wire is not modeled."""

from . import messages
from .authority import SpecialAuthority
from .objects import Done, _no, _ok
from .profiles import Profile, ProfileStore

SA = SpecialAuthority


def change(store: ProfileStore, actor: Profile, autostart: str) -> Done:
    if SA.IOSYSCFG not in store.special_authorities(actor):
        return _no(messages.iosyscfg_required())
    if autostart != "*SAME":
        store.system.ftp_autostart = autostart
        store.on_change()
    return _ok("FTP attributes changed.")
