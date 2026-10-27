"""The command line: binds a parsed command to its parameters and runs it.

The user profile commands and the library and object authority commands exist
so far. Keywords must be written in full
(no F4 prompting, no abbreviations yet). Parameters we accept but do not model
are named in IGNORED so a copied command from a real system still runs."""

import fnmatch
from dataclasses import dataclass

from ..system import admin, autls, jobctl, messages, msgq, objects, objlist, spool
from ..system.authority import EXCLUDE, SPECIAL_VALUES, USE, Auth, SpecialAuthority, UserClass, parse_auth
from ..system.profiles import Profile, ProfileStore
from . import parser
from .session import Session

SA = SpecialAuthority
SAME = "*SAME"


@dataclass
class Outcome:
    message: messages.Message | None = None
    # ("dspusrprf", Profile), ("wrkusrprf", [Profile]), ("dsplibl", Session),
    # ("wrklib", [SecuredObject]), ("dspobjaut", SecuredObject, [(user, authority)])
    view: tuple | None = None
    signoff: bool = False
    go: tuple | None = None          # (menu object, RTNPNT) for the controller to put on the stack
    cmdentry: bool = False           # CALL QCMD: open command entry


class BindError(ValueError):
    pass


@dataclass(frozen=True)
class Param:
    key: str
    kind: str                # one of the KINDS below
    default: str
    maxn: int = 1
    required: bool = False


# Parameter order is the positional order on the real commands.
CRT_PARAMS = [
    Param("USRPRF", "name", "", required=True), Param("PASSWORD", "password", "*NONE"),
    Param("PWDEXP", "yesno", "*NO"), Param("STATUS", "status", "*ENABLED"),
    Param("USRCLS", "class", "*USER"), Param("ASTLVL", "ignored", "*SYSVAL"),
    Param("CURLIB", "name*", "*CRTDFT"), Param("INLPGM", "qname*", "*NONE"),
    Param("INLMNU", "qname*", "MAIN"), Param("LMTCPB", "lmtcpb", "*NO"),
    Param("TEXT", "text", "*BLANK"), Param("SPCAUT", "spcaut", "*USRCLS", 8),
    Param("GRPPRF", "name*", "*NONE"), Param("SUPGRPPRF", "names", "*NONE", 15),
    Param("AUT", "aut", "*EXCLUDE"),
]
CHG_PARAMS = [Param(p.key, p.kind, SAME, p.maxn) for p in CRT_PARAMS]
CHG_PARAMS[0] = CRT_PARAMS[0]
DSP_PARAMS = [Param("USRPRF", "name", "", required=True), Param("TYPE", "dsptype", "*BASIC"), Param("OUTPUT", "output", "*")]
DLT_PARAMS = [Param("USRPRF", "name", "", required=True), Param("OWNOBJOPT", "ownobj", "*NODLT", 2)]
WRK_PARAMS = [Param("USRPRF", "wrkname", "*ALL"), Param("ASTLVL", "ignored", "*SYSVAL")]

CRTLIB_PARAMS = [
    Param("LIB", "name", "", required=True), Param("TYPE", "libtype", "*PROD"), Param("TEXT", "text", "*BLANK"),
    Param("AUT", "libaut", "*LIBCRTAUT"), Param("ASP", "ignored", "1"), Param("ASPDEV", "ignored", "*ASP"),
    Param("CRTAUT", "ignored", "*SYSVAL"), Param("CRTOBJAUD", "ignored", "*SYSVAL"),
]
DLTLIB_PARAMS = [Param("LIB", "name", "", required=True), Param("ASPDEV", "ignored", "*")]
DSPLIBL_PARAMS = [Param("OUTPUT", "output", "*")]
ADDLIBLE_PARAMS = [Param("LIB", "name", "", required=True), Param("POSITION", "position", "*FIRST", 2)]
RMVLIBLE_PARAMS = [Param("LIB", "name", "", required=True)]
WRKLIB_PARAMS = [Param("LIB", "libspec", "*LIBL"), Param("ASP", "ignored", "*ALL"), Param("ASPDEV", "ignored", "*")]
DSPOBJAUT_PARAMS = [
    Param("OBJ", "qname", "", required=True), Param("OBJTYPE", "objtype", "", required=True),
    Param("ASPDEV", "ignored", "*"), Param("OUTPUT", "output", "*"),
]
GRTOBJAUT_PARAMS = [
    Param("OBJ", "qname", "", required=True), Param("OBJTYPE", "objtype", "", required=True),
    Param("USER", "users", "", 50), Param("AUT", "autspec", "*CHANGE", 10),
    Param("ASPDEV", "ignored", "*"), Param("AUTL", "name*", "*NONE"), Param("REPLACE", "yesno", "*NO"),
]
RVKOBJAUT_PARAMS = [
    Param("OBJ", "qname", "", required=True), Param("OBJTYPE", "objtype", "", required=True),
    Param("USER", "users", "", 50), Param("AUT", "autspec", "*CHANGE", 10),
    Param("ASPDEV", "ignored", "*"), Param("AUTL", "name*", "*NONE"),
]

DSPMSG_PARAMS = [Param("MSGQ", "msgqname", "*WRKUSR"), Param("OUTPUT", "output", "*"), Param("MSGTYPE", "ignored", "*ALL"),
                 Param("START", "ignored", "*LAST"), Param("SEV", "ignored", "0"), Param("ASTLVL", "ignored", "*PRV")]
SNDMSG_PARAMS = [Param("MSG", "msgtext", "", required=True), Param("TOMSGQ", "msgqs", "", 50), Param("TOUSR", "touser", ""),
                 Param("MSGTYPE", "msgtype", "*INFO"), Param("RPYMSGQ", "ignored", "*WRKSTN"), Param("CCSID", "ignored", "*JOB")]
CRTMSGQ_PARAMS = [Param("MSGQ", "qname", "", required=True), Param("TEXT", "text", "*BLANK"),
                  Param("FORCE", "ignored", "*NO"), Param("SIZE", "ignored", "3", 3), Param("AUT", "libaut", "*LIBCRTAUT"),
                  Param("ALWALR", "ignored", "*NO"), Param("CCSID", "ignored", "*HEX"), Param("MSGQFULL", "ignored", "*SNDMSG")]
CHGMSGQ_PARAMS = [Param("MSGQ", "msgqname", "", required=True), Param("DLVRY", "dlvry", SAME), Param("PGM", "ignored", SAME, 2),
                  Param("SEV", "sevcode", SAME), Param("TEXT", "text", SAME), Param("RESET", "ignored", "*NO"),
                  Param("FORCE", "ignored", SAME), Param("ALWALR", "ignored", SAME), Param("CCSID", "ignored", SAME),
                  Param("MSGQFULL", "ignored", SAME)]
DLTMSGQ_PARAMS = [Param("MSGQ", "qname", "", required=True)]
CLRMSGQ_PARAMS = [Param("MSGQ", "msgqname", "", required=True), Param("CLEAR", "clearopt", "*ALL")]
WRKSPLF_PARAMS = [Param("SELECT", "splsel", "*CURRENT", 6), Param("JOB", "jobq", "*ALL", 3),
                  Param("PERIOD", "ignored", "*AVAIL"), Param("ASPDEV", "ignored", "*"),
                  Param("OUTPUT", "output", "*"), Param("DSPFMT", "ignored", "*INLENV"), Param("ASTLVL", "ignored", "*PRV")]
CRTOUTQ_PARAMS = [Param("OUTQ", "qname", "", required=True), Param("MAXPAGES", "ignored", "*NONE", 5),
                  Param("SEQ", "ignored", "*FIFO"), Param("RMTSYS", "ignored", "*NONE"), Param("RMTPRTQ", "ignored", "*USER"),
                  Param("AUTOSTRWTR", "ignored", "*NONE"), Param("MSGQ", "ignored", "QSYSOPR", 2),
                  Param("SEPPAGE", "ignored", "*YES"), Param("TEXT", "text", "*BLANK"), Param("DSPDTA", "dspdta", "*NO"),
                  Param("JOBSEP", "ignored", "0"), Param("OPRCTL", "oprctl", "*YES"), Param("DTAQ", "ignored", "*NONE", 2),
                  Param("AUTCHK", "autchk", "*OWNER"), Param("AUT", "libaut", "*USE")]
DLTOUTQ_PARAMS = [Param("OUTQ", "qname", "", required=True)]
WRKOUTQ_PARAMS = [Param("OUTQ", "outqname", "*ALL"), Param("OUTPUT", "output", "*")]
DSPSPLF_PARAMS = [Param("FILE", "name", "", required=True), Param("JOB", "jobq", "*", 3),
                  Param("SPLNBR", "splnbr", "*ONLY"), Param("JOBSYSNAME", "ignored", "*ONLY"),
                  Param("CRTDATE", "ignored", "*ONLY"), Param("FOLD", "ignored", "*NO")]
HLDJOB_PARAMS = [Param("JOB", "jobq", "", 3, required=True), Param("SPLFILE", "ignored", "*NO"),
                 Param("DUPJOBOPT", "ignored", "*SELECT")]
RLSJOB_PARAMS = [Param("JOB", "jobq", "", 3, required=True), Param("DUPJOBOPT", "ignored", "*SELECT")]
ENDJOB_PARAMS = [Param("JOB", "jobq", "", 3, required=True), Param("OPTION", "ignored", "*CNTRLD"),
                 Param("DELAY", "ignored", "30"), Param("SPLFILE", "ignored", "*NO"), Param("LOGLMT", "ignored", "*SAME"),
                 Param("ADLINTJOBS", "ignored", "*NONE"), Param("DUPJOBOPT", "ignored", "*SELECT")]
CHGJOB_PARAMS = [Param("JOB", "jobq", "*", 3)] + [
    Param(k, "jobattr", "*SAME") for k in ("JOBPTY", "OUTPTY", "RUNPTY", "TIMESLICE", "PURGE", "DFTWAIT", "CPUTIME", "MAXTMPSTG")]
DSPJOBLOG_PARAMS = [Param("JOB", "jobq", "*", 3), Param("OUTPUT", "output", "*"), Param("OUTFILE", "ignored", "*NONE"),
                    Param("OUTMBR", "ignored", "*FIRST"), Param("MSGF", "ignored", "*MSG"), Param("DUPJOBOPT", "ignored", "*SELECT")]
WRKJOB_PARAMS = [Param("JOB", "jobq", "*", 3), Param("OUTPUT", "output", "*"), Param("OPTION", "ignored", "*SELECT"),
                 Param("SLTTHD", "ignored", "*INITIAL"), Param("DUPJOBOPT", "ignored", "*SELECT")]
DSPJOB_PARAMS = [Param("JOB", "jobq", "*", 3), Param("OUTPUT", "output", "*"), Param("OPTION", "ignored", "*SELECT"),
                 Param("SLTTHD", "ignored", "*INITIAL"), Param("DUPJOBOPT", "ignored", "*SELECT")]
HLDSPLF_PARAMS = [Param("FILE", "name", "", required=True), Param("JOB", "jobq", "*", 3),
                  Param("SPLNBR", "splnbr", "*ONLY"), Param("JOBSYSNAME", "ignored", "*ONLY"),
                  Param("CRTDATE", "ignored", "*ONLY"), Param("OPTION", "ignored", "*IMMED")]
RLSSPLF_PARAMS = [Param("FILE", "name", "", required=True), Param("JOB", "jobq", "*", 3),
                  Param("SPLNBR", "splnbr", "*ONLY"), Param("JOBSYSNAME", "ignored", "*ONLY"),
                  Param("CRTDATE", "ignored", "*ONLY")]
DLTSPLF_PARAMS = [Param("FILE", "name", "", required=True), Param("JOB", "jobq", "*", 3),
                  Param("SPLNBR", "splnbr", "*ONLY"), Param("JOBSYSNAME", "ignored", "*ONLY"),
                  Param("CRTDATE", "ignored", "*ONLY"), Param("SELECT", "ignored", "*"), Param("ASPDEV", "ignored", "*")]
WRKACTJOB_PARAMS = [Param("SBS", "name*", "*ALL"), Param("CPUPCTLMT", "ignored", "*NONE"), Param("JOB", "ignored", "*ALL")]
GO_PARAMS = [Param("MENU", "qname", "", required=True), Param("RTNPNT", "yesno", "*YES")]
CALL_PARAMS = [Param("PGM", "qname", "", required=True)]
CHGPRF_PARAMS = [Param("INLPGM", "qname*", SAME), Param("INLMNU", "qname*", SAME), Param("CURLIB", "name*", SAME)]

CRTAUTL_PARAMS = [Param("AUTL", "autl", "", required=True), Param("AUT", "aut", "*CHANGE"),
                  Param("TEXT", "text", "*BLANK")]
DLTAUTL_PARAMS = [Param("AUTL", "autl", "", required=True)]
ADDAUTLE_PARAMS = [Param("AUTL", "autl", "", required=True), Param("USER", "users", "", 50, True),
                   Param("AUT", "autlaut", "*CHANGE", 11)]
CHGAUTLE_PARAMS = [Param("AUTL", "autl", "", required=True), Param("USER", "users", "", 50, True),
                   Param("AUT", "autlaut", "*CHANGE", 11)]
RMVAUTLE_PARAMS = [Param("AUTL", "autl", "", required=True), Param("USER", "users", "", 50, True)]
DSPAUTL_PARAMS = [Param("AUTL", "autl", "", required=True), Param("OUTPUT", "output", "*")]
WRKAUTL_PARAMS = [Param("AUTL", "wrkname", "*ALL")]

WRKOBJ_PARAMS = [Param("OBJ", "wrkobj", "", required=True), Param("OBJTYPE", "objtypes", "*ALL", 100)]
WRKOBJOWN_PARAMS = [Param("USRPRF", "wrkowner", "*CURRENT"), Param("OBJTYPE", "objtypes", "*ALL", 100)]
CHGOBJOWN_PARAMS = [
    Param("OBJ", "qname", "", required=True), Param("OBJTYPE", "objtype", "", required=True),
    Param("NEWOWN", "name", "", required=True), Param("CUROWNAUT", "curownaut", "*REVOKE"),
]

RNMOBJ_PARAMS = [Param("OBJ", "qname", "", required=True), Param("OBJTYPE", "objtype", "", required=True),
                 Param("NEWOBJ", "name", "", required=True), Param("ASPDEV", "ignored", "*"),
                 Param("SYSTEM", "ignored", "*LCL")]
CHGOBJD_PARAMS = [Param("OBJ", "qname", "", required=True), Param("OBJTYPE", "objtype", "", required=True),
                  Param("TEXT", "text", SAME), Param("USECOUNT", "ignored", "*NORESET")]

DLTF_PARAMS = [Param("FILE", "qname", "", required=True), Param("SYSTEM", "ignored", "*LCL"),
               Param("RMVCST", "ignored", "*RESTRICT")]
DLTCMD_PARAMS = [Param("CMD", "qname", "", required=True)]
DLTMNU_PARAMS = [Param("MENU", "qname", "", required=True), Param("DLTREFOBJ", "ignored", "*NONE", 3)]
DLTPGM_PARAMS = [Param("PGM", "qname", "", required=True)]
EDTOBJAUT_PARAMS = [Param("OBJ", "qname", "", required=True), Param("OBJTYPE", "objtype", "", required=True),
                    Param("ASPDEV", "ignored", "*")]
DSPOBJD_PARAMS = [Param("OBJ", "qname", "", required=True), Param("OBJTYPE", "objtype", "", required=True),
                  Param("DETAIL", "detail", "*BASIC"), Param("ASPDEV", "ignored", "*"),
                  Param("OUTPUT", "output", "*")]
DELETE_COMMANDS = {"DLTF": ("FILE", "*FILE"), "DLTCMD": ("CMD", "*CMD"), "DLTMNU": ("MENU", "*MENU"),
                   "DLTPGM": ("PGM", "*PGM"), "DLTMSGQ": ("MSGQ", "*MSGQ")}

COMMANDS = {
    "CRTUSRPRF": CRT_PARAMS, "CHGUSRPRF": CHG_PARAMS, "DSPUSRPRF": DSP_PARAMS,
    "DLTUSRPRF": DLT_PARAMS, "WRKUSRPRF": WRK_PARAMS, "SIGNOFF": [],
    "CRTLIB": CRTLIB_PARAMS, "DLTLIB": DLTLIB_PARAMS, "DSPLIBL": DSPLIBL_PARAMS,
    "ADDLIBLE": ADDLIBLE_PARAMS, "RMVLIBLE": RMVLIBLE_PARAMS, "WRKLIB": WRKLIB_PARAMS,
    "DSPOBJAUT": DSPOBJAUT_PARAMS, "GRTOBJAUT": GRTOBJAUT_PARAMS, "RVKOBJAUT": RVKOBJAUT_PARAMS,
    "GO": GO_PARAMS, "CALL": CALL_PARAMS, "CHGPRF": CHGPRF_PARAMS,
    "CRTAUTL": CRTAUTL_PARAMS, "DLTAUTL": DLTAUTL_PARAMS, "ADDAUTLE": ADDAUTLE_PARAMS,
    "CHGAUTLE": CHGAUTLE_PARAMS, "RMVAUTLE": RMVAUTLE_PARAMS, "DSPAUTL": DSPAUTL_PARAMS,
    "WRKAUTL": WRKAUTL_PARAMS, "WRKOBJ": WRKOBJ_PARAMS, "WRKOBJOWN": WRKOBJOWN_PARAMS,
    "WRKACTJOB": WRKACTJOB_PARAMS, "DSPMSG": DSPMSG_PARAMS, "SNDMSG": SNDMSG_PARAMS, "CLRMSGQ": CLRMSGQ_PARAMS, "CRTMSGQ": CRTMSGQ_PARAMS, "CHGMSGQ": CHGMSGQ_PARAMS,
    "DLTMSGQ": DLTMSGQ_PARAMS, "WRKSPLF": WRKSPLF_PARAMS, "WRKOUTQ": WRKOUTQ_PARAMS, "CRTOUTQ": CRTOUTQ_PARAMS, "DLTOUTQ": DLTOUTQ_PARAMS, "DSPSPLF": DSPSPLF_PARAMS,
    "DLTSPLF": DLTSPLF_PARAMS, "HLDSPLF": HLDSPLF_PARAMS, "HLDJOB": HLDJOB_PARAMS, "DSPJOBLOG": DSPJOBLOG_PARAMS, "WRKJOB": WRKJOB_PARAMS, "DSPJOB": DSPJOB_PARAMS, "RLSJOB": RLSJOB_PARAMS,
    "ENDJOB": ENDJOB_PARAMS, "CHGJOB": CHGJOB_PARAMS, "RLSSPLF": RLSSPLF_PARAMS, "CHGOBJOWN": CHGOBJOWN_PARAMS, "RNMOBJ": RNMOBJ_PARAMS, "CHGOBJD": CHGOBJD_PARAMS,
    "DLTF": DLTF_PARAMS, "DLTCMD": DLTCMD_PARAMS, "DLTMNU": DLTMNU_PARAMS, "DLTPGM": DLTPGM_PARAMS,
    "EDTOBJAUT": EDTOBJAUT_PARAMS, "DSPOBJD": DSPOBJD_PARAMS,
}


def _one(key: str, values: list[str], allowed: tuple[str, ...]) -> str:
    if len(values) != 1 or values[0] not in allowed:
        raise BindError(f"Value for parameter {key} not valid. Use one of {' '.join(allowed)}.")
    return values[0]


def _word_ok(key: str, v: str, special_ok: bool = False) -> str:
    base = v.split("/")[-1]
    if not base or len(base) > 10 or (v.startswith("*") and not special_ok):
        raise BindError(f"Value {v} for parameter {key} not valid.")
    return base


def convert(store: ProfileStore, p: Param, values: list[str]):
    """Turn the typed values for one parameter into what the admin layer wants."""
    k = p.kind
    if len(values) > p.maxn:
        raise BindError(f"Too many values for parameter {p.key}.")
    if not values:
        raise BindError(f"No value given for parameter {p.key}.")
    if values == [SAME] and k != "name":
        return SAME
    if k == "name":
        return _name(p.key, values)
    if k == "password":
        if len(values) != 1:
            raise BindError("Only one value is allowed for PASSWORD.")
        v = values[0]
        if v == "*NONE":
            return None
        limit = 10 if store.system.qpwdlvl < 2 else 128
        if len(v) > limit:
            raise BindError(f"Password longer than {limit} characters.")
        return v
    if k == "yesno":
        return _one(p.key, values, ("*NO", "*YES")) == "*YES"
    if k == "status":
        return _one(p.key, values, ("*ENABLED", "*DISABLED"))
    if k == "class":
        return UserClass(_one(p.key, values, tuple(c.value for c in UserClass)))
    if k == "lmtcpb":
        return _one(p.key, values, ("*NO", "*PARTIAL", "*YES"))
    if k == "ignored":
        return SAME
    if k == "text":
        return "" if values == ["*BLANK"] else values[0][:50]
    if k == "name*":
        v = values[0]
        if v.startswith("*"):
            return v
        return _word_ok(p.key, v)
    if k == "qname*":                      # a special value, or a name qualified by library
        return values[0] if values[0].startswith("*") else _qualified(p.key, values)
    if k == "names":
        return [] if values == ["*NONE"] else [_word_ok(p.key, v) for v in values]
    if k == "spcaut":
        if values == ["*USRCLS"]:
            return None
        if values == ["*NONE"]:
            return frozenset()
        try:
            return frozenset(SA(v) for v in values)
        except ValueError:
            raise BindError(f"Value for parameter SPCAUT not valid. Use *USRCLS, *NONE or any of "
                            f"{' '.join(a.value for a in SA)}.") from None
    if k == "aut":
        v = _one(p.key, values, ("*EXCLUDE", "*USE", "*CHANGE", "*ALL"))
        return parse_auth(v)
    if k == "wrkobj":                       # (name or generic or *ALL, library spec)
        v = values[0]
        lib, _, obj = v.rpartition("/")
        lib = lib.upper() or "*LIBL"
        obj = obj.upper()
        if not obj or len(obj) > 10 or (obj.startswith("*") and obj != "*ALL") or obj.count("*") > 1 \
                or ("*" in obj and obj != "*ALL" and not obj.endswith("*")):
            raise BindError(f"Object name {obj or v} in OBJ not valid.")
        if lib.startswith("*") and lib not in ("*LIBL", "*CURLIB", "*USRLIBL", "*ALLUSR", "*ALL"):
            raise BindError(f"Library {lib} in OBJ not valid.")
        return (obj, lib)
    if k == "objtypes":
        if values == ["*ALL"]:
            return "*ALL"
        for v in values:
            if v not in objects.TYPES:
                raise BindError(f"Object type {v} is not modeled yet. Modeled: {' '.join(objects.TYPES)}.")
        return list(values)
    if k == "wrkowner":
        return values[0].upper()
    if k == "curownaut":
        return _one(p.key, values, ("*REVOKE", "*SAME")) == "*SAME"
    if k == "autl":
        v = values[0]
        if "*" in v or not objects.NAME.match(v.upper()):
            raise BindError(f"Authorization list name {v} not valid. Generic names are not supported yet.")
        return v.upper()
    if k == "autlaut":
        for v in values:
            if v not in SPECIAL_VALUES and v not in _DETAILED and v != "*AUTLMGT":
                raise BindError(f"Value {v} for parameter AUT not valid.")
        return list(values)
    if k == "jobattr":
        return values[0].upper()
    if k == "msgqname":
        v = values[0].upper()
        if v.startswith("*"):
            if v not in ("*WRKUSR", "*SYSOPR", "*USRPRF", "*WRKSTN"):
                raise BindError(f"Value {v} for parameter {p.key} not valid.")
            return v
        return _qualified(p.key, values)
    if k in ("dspdta", "oprctl", "autchk"):
        allowed = {"dspdta": ("*NO", "*YES", "*OWNER"), "oprctl": ("*YES", "*NO"), "autchk": ("*OWNER", "*DTAAUT")}[k]
        return _one(p.key, values, allowed)
    if k == "outqname":
        v = values[0].upper()
        return v if v == "*ALL" else _qualified(p.key, values)
    if k == "msgqs":
        return [v.upper() if v.upper() == "*SYSOPR" else _qualified(p.key, [v]) for v in values]
    if k == "touser":
        v = values[0].upper()
        if v.startswith("*") and v not in ("*SYSOPR", "*ALLACT", "*REQUESTER"):
            raise BindError(f"Value {v} for parameter TOUSR not valid.")
        return v
    if k == "msgtext":
        return values[0][:512]
    if k == "msgtype":
        return _one(p.key, values, ("*INFO", "*INQ"))
    if k == "dlvry":
        return _one(p.key, values, (SAME, "*HOLD", "*BREAK", "*NOTIFY", "*DFT"))
    if k == "sevcode":
        if values == [SAME]:
            return SAME
        if len(values) != 1 or not values[0].isdigit() or int(values[0]) > 99:
            raise BindError(f"Value for parameter {p.key} not valid. Use {SAME} or 0 to 99.")
        return f"{int(values[0]):02d}"
    if k == "clearopt":
        return _one(p.key, values, ("*ALL", "*KEEPUNANS"))
    if k == "splsel":                       # SELECT(user device form userdata asp splfile): user and file only
        user = values[0].upper()
        if user.startswith("*") and user not in ("*CURRENT", "*ALL"):
            raise BindError(f"Value {user} for parameter SELECT not valid.")
        name = values[5].upper() if len(values) > 5 else "*ALL"
        return (user, name)
    if k == "jobq":                         # * , or number/user/name (number and user may be *)
        if values == ["*"]:
            return "*"
        parts = [v.upper() for v in values[0].split("/")] if len(values) == 1 else [v.upper() for v in values]
        if len(parts) == 1:
            return (parts[0], "*", "*")
        if len(parts) == 3:
            return (parts[2], parts[1], parts[0])
        raise BindError("Value for parameter JOB not valid. Use name or number/user/name.")
    if k == "splnbr":
        v = values[0].upper()
        if v in ("*ONLY", "*LAST", "*ANY") or (v.isdigit() and 1 <= int(v) <= 999999):
            return v
        raise BindError("Value for parameter SPLNBR not valid. Use *ONLY, *LAST, *ANY or 1 to 999999.")
    if k == "detail":
        return _one(p.key, values, ("*BASIC", "*FULL"))
    if k == "dsptype":
        return _one(p.key, values, ("*BASIC",))
    if k == "output":
        return _one(p.key, values, ("*",))
    if k == "ownobj":
        mode = values[0]
        if mode not in ("*NODLT", "*DLT", "*CHGOWN"):
            raise BindError("Value for parameter OWNOBJOPT not valid. Use *NODLT, *DLT or *CHGOWN name.")
        if mode == "*CHGOWN" and len(values) != 2:
            raise BindError("OWNOBJOPT(*CHGOWN) needs the name of the new owner.")
        if mode != "*CHGOWN" and len(values) != 1:
            raise BindError(f"OWNOBJOPT({mode}) takes no second value.")
        return tuple(values)
    if k == "wrkname":
        return values[0]
    if k == "libtype":
        return _one(p.key, values, ("*PROD", "*TEST"))
    if k == "libaut":
        v = _one(p.key, values, ("*LIBCRTAUT", "*EXCLUDE", "*USE", "*CHANGE", "*ALL"))
        return None if v == "*LIBCRTAUT" else parse_auth(v)
    if k == "libspec":
        v = values[0]
        return v if v.startswith("*") and v in ("*LIBL", "*ALL", "*ALLUSR", "*USRLIBL", "*CURLIB") else \
            _generic(p.key, v)
    if k == "position":
        if values[0] in ("*FIRST", "*LAST") and len(values) == 1:
            return tuple(values)
        if values[0] in ("*AFTER", "*BEFORE", "*REPLACE") and len(values) == 2:
            return (values[0], _word_ok(p.key, values[1]))
        raise BindError("Value for parameter POSITION not valid. Use *FIRST, *LAST, "
                        "or *AFTER, *BEFORE, *REPLACE followed by a library.")
    if k == "qname":
        return _qualified(p.key, values)
    if k == "objtype":
        v = _one(p.key, values, objects.TYPES) if len(values) == 1 and values[0] in objects.TYPES else None
        if v is None:
            raise BindError(f"Object type {' '.join(values)} is not modeled yet. Modeled: {' '.join(objects.TYPES)}.")
        return v
    if k == "users":
        out = []
        for v in values:
            out.append(v if v in ("*PUBLIC", "*ALL") else _word_ok(p.key, v))
        return out
    if k == "autspec":
        return _autspec(values)
    raise AssertionError(k)


def _generic(key: str, v: str) -> str:
    base = v.rstrip("*")
    if not base or len(base) > 10 or "*" in base:
        raise BindError(f"Value {v} for parameter {key} not valid.")
    return v


def _qualified(key: str, values: list[str]) -> str:
    if len(values) != 1:
        raise BindError(f"Only one value is allowed for {key}.")
    v = values[0]
    lib, _, name = v.rpartition("/")
    if (lib and lib not in ("*LIBL", "*CURLIB") and not lib.isidentifier() and not lib.replace("@", "A")
            .replace("#", "A").replace("$", "A").replace("_", "A").isalnum()):
        raise BindError(f"Library {lib} in {key} not valid.")
    if not name or len(name) > 10 or name.startswith("*") or "*" in name:
        raise BindError(f"Object name {name or v} in {key} not valid. Generic names and *ALL are not supported yet.")
    return v


_DETAILED = ("*OBJALTER", "*OBJEXIST", "*OBJMGT", "*OBJOPR", "*OBJREF", "*ADD", "*DLT", "*READ", "*UPD", "*EXECUTE")


def _autspec(values: list[str]) -> list[str]:
    for v in values:
        if v not in SPECIAL_VALUES and v != "*AUTL" and v not in _DETAILED:
            raise BindError(f"Value {v} for parameter AUT not valid.")
    return list(values)


def resolve_aut(values: list[str]) -> Auth | str | messages.Message:
    """One of *CHANGE *ALL *USE *EXCLUDE *AUTL, or up to ten detailed values."""
    if values == ["*AUTL"]:
        return "*AUTL"
    if len(values) == 1 and values[0] in SPECIAL_VALUES:
        return SPECIAL_VALUES[values[0]]
    if any(v in SPECIAL_VALUES or v == "*AUTL" for v in values):
        return messages.exclude_with_another() if "*EXCLUDE" in values else messages.syntax(
            "Special authority values cannot be mixed with a list of detailed authorities.")
    return parse_auth(" ".join(values))


def _name(key: str, values: list[str]) -> str:
    if len(values) != 1:
        raise BindError(f"Only one value is allowed for {key}.")
    return _word_ok(key, values[0])


def bind(store: ProfileStore, name: str, parsed: parser.Parsed) -> dict[str, object]:
    params = COMMANDS[name]
    given: dict[str, list[str]] = {}
    if len(parsed.positional) > len(params):
        raise BindError("Too many positional values for command.")
    for p, v in zip(params, parsed.positional):
        given[p.key] = [v]
    known = {p.key for p in params}
    for key, values in parsed.keywords.items():
        if key not in known:
            raise BindError(f"Keyword {key} not valid for this command.")
        if key in given:
            raise BindError(f"Parameter {key} specified more than once.")
        given[key] = values
    for p in params:
        if p.required and p.key not in given:
            raise BindError(f"Required parameter {p.key} not specified.")
    bound = {}
    for p in params:
        if p.key in given:
            bound[p.key] = convert(store, p, given[p.key])
        elif name != "CHGUSRPRF" and p.default != "":
            bound[p.key] = convert(store, p, [p.default])
    return bound


def _crt_attrs(b: dict) -> dict:
    password = b["PASSWORD"]
    if password == "*USRPRF":
        password = b["USRPRF"]
    return {
        "user_class": b["USRCLS"], "special": b["SPCAUT"], "password": password,
        "status": b["STATUS"], "password_expired": b["PWDEXP"],
        "limited_capabilities": b["LMTCPB"],
        "group_profile": None if b["GRPPRF"] == "*NONE" else b["GRPPRF"],
        "supplemental_groups": b["SUPGRPPRF"], "initial_program": b["INLPGM"],
        "initial_menu": b["INLMNU"], "current_library": b["CURLIB"], "text": b["TEXT"],
        "public_authority": b["AUT"],
    }


_CHG_FIELDS = {
    "PASSWORD": "password", "PWDEXP": "password_expired", "STATUS": "status", "USRCLS": "user_class",
    "CURLIB": "current_library", "INLPGM": "initial_program", "INLMNU": "initial_menu",
    "LMTCPB": "limited_capabilities", "TEXT": "text", "SPCAUT": "special", "GRPPRF": "group_profile",
    "SUPGRPPRF": "supplemental_groups", "AUT": "public_authority",
}


def _chg_attrs(b: dict) -> dict:
    out = {}
    for key, field in _CHG_FIELDS.items():
        v = b.get(key, SAME)
        if v == SAME:
            continue
        if key == "PASSWORD" and v == "*USRPRF":
            v = b["USRPRF"]
        if key == "GRPPRF" and v == "*NONE":
            v = None
        out[field] = v
    return out


def execute(store: ProfileStore, actor: Profile, line: str, session: Session | None = None) -> Outcome:
    session = session or Session.for_profile(actor.current_library)
    try:
        parsed = parser.parse(line)
    except parser.ParseError as exc:
        return Outcome(messages.syntax(str(exc)))
    if parsed is None:
        return Outcome()
    name = parsed.command
    if name not in COMMANDS:
        return Outcome(messages.syntax(f"Command {name} in library *LIBL not found."))
    cmd = store.objects.get(("QSYS", name, "*CMD"))
    if cmd is None or USE not in store.authority_to_object(actor, cmd):
        # Checked before the parameters, as a real system does. Seen on PUB400.
        return Outcome(messages.not_authorized_to_command(name))
    try:
        b = bind(store, name, parsed)
    except BindError as exc:
        return Outcome(messages.syntax(str(exc)))

    if name == "SIGNOFF":
        return Outcome(signoff=True)
    if name == "CRTUSRPRF":
        return Outcome(admin.create(store, actor, b["USRPRF"], _crt_attrs(b)).message)
    if name == "CHGUSRPRF":
        return Outcome(admin.change(store, actor, b["USRPRF"], _chg_attrs(b)).message)
    if name == "DLTUSRPRF":
        return Outcome(admin.delete(store, actor, b["USRPRF"], b["OWNOBJOPT"]).message)
    if name == "DSPUSRPRF":
        target, err = admin.display(store, actor, b["USRPRF"])
        return Outcome(err) if err else Outcome(view=("dspusrprf", target))
    if name == "WRKUSRPRF":
        pattern = b["USRPRF"]
        rows = [p for p in admin.visible_profiles(store, actor)
                if pattern == "*ALL" or fnmatch.fnmatchcase(p.name, pattern)]
        if not rows:
            return Outcome(messages.syntax("No user profiles found, or you are not authorized to any."))
        return Outcome(view=("wrkusrprf", rows))
    if name == "DSPMSG":
        q, err = msgq.display(store, actor, session, b["MSGQ"])
        return Outcome(err) if err else Outcome(view=("dspmsg", q))
    if name == "SNDMSG":
        if b["MSGTYPE"] == "*INQ":
            return Outcome(messages.syntax("Inquiry messages are not modeled."))
        if b.get("TOMSGQ") and b.get("TOUSR"):
            return Outcome(messages.syntax("TOMSGQ and TOUSR cannot both be given."))
        if b.get("TOUSR") in ("*ALLACT", "*REQUESTER"):
            return Outcome(messages.syntax(f"TOUSR({b['TOUSR']}) is not modeled."))
        targets = b.get("TOMSGQ") or ([b.get("TOUSR")] if b.get("TOUSR") else [])
        if not targets:
            return Outcome(messages.syntax("Give TOUSR or TOMSGQ."))
        if b.get("TOUSR") and b.get("TOUSR") != "*SYSOPR":
            q = msgq.user_queue(store, b.get("TOUSR"))
            if q is None:
                return Outcome(messages.Message("CPF2204", f"User profile {b['TOUSR']} not found.", messages.DOCUMENTED))
            targets = [f"{q.library}/{q.name}"]
        return Outcome(msgq.send(store, actor, session, b["MSG"], targets).message)
    if name == "CLRMSGQ":
        return Outcome(msgq.clear(store, actor, session, b["MSGQ"]).message)
    if name == "CRTOUTQ":
        return Outcome(spool.create_queue(store, actor, session, b["OUTQ"], b["TEXT"], b["DSPDTA"], b["OPRCTL"],
                                          b["AUTCHK"], b["AUT"]).message)
    if name == "DLTOUTQ":
        return Outcome(spool.delete_queue(store, actor, session, b["OUTQ"]).message)
    if name == "CRTMSGQ":
        return Outcome(msgq.create(store, actor, session, b["MSGQ"], b["TEXT"], b["AUT"]).message)
    if name == "CHGMSGQ":
        changes = {k: b[k] for k in ("DLVRY", "SEV", "TEXT") if b[k] != SAME}
        if not changes:
            return Outcome(messages.syntax("Give at least one attribute to change."))
        return Outcome(msgq.change(store, actor, session, b["MSGQ"], changes).message)
    if name == "DSPJOBLOG":
        job, err = jobctl.display_log(store, actor, b["JOB"], session.job)
        return Outcome(err) if err else Outcome(view=("dspjoblog", job))
    if name == "DSPJOB":
        job, err = jobctl.work_with(store, actor, b["JOB"], session.job)
        return Outcome(err) if err else Outcome(view=("dspjob", job))
    if name == "WRKJOB":
        job, err = jobctl.work_with(store, actor, b["JOB"], session.job)
        return Outcome(err) if err else Outcome(view=("wrkjob", job))
    if name in ("HLDJOB", "RLSJOB", "ENDJOB", "CHGJOB"):
        job, err = jobctl.find(store, b["JOB"], session.job, name in ("ENDJOB", "CHGJOB"))
        if err:
            return Outcome(err)
        own = job is session.job
        if name == "ENDJOB":
            done = jobctl.end(store, actor, job)
            return Outcome(done.message, signoff=own and done.ok)
        if name == "CHGJOB":
            changes = {k: v for k, v in b.items() if k != "JOB" and v != SAME}
            if not changes:
                return Outcome(messages.syntax("Give at least one attribute to change."))
            return Outcome(jobctl.change(store, actor, job, changes, own).message)
        run = jobctl.hold if name == "HLDJOB" else jobctl.release
        return Outcome(run(store, actor, job).message)
    if name == "WRKSPLF":
        user, fname = b["SELECT"]
        if user not in ("*CURRENT", "*ALL") and "*" not in user and user not in store.profiles:
            return Outcome(messages.Message("CPF33D1", f"User {user} does not exist.", messages.DOCUMENTED))
        job = b["JOB"]
        if job not in ("*", ("*ALL", "*", "*")) and user != "*ALL":
            return Outcome(messages.syntax("JOB can only be given when SELECT names *ALL users."))
        job = None if job in ("*", ("*ALL", "*", "*")) else job
        rows = spool.select(store, actor, user, fname, job)
        if not rows:
            return Outcome(messages.syntax("No spooled files found."))
        return Outcome(view=("wrksplf", rows, lambda: spool.select(store, actor, user, fname, job)))
    if name == "WRKOUTQ":
        if b["OUTQ"] == "*ALL":
            return Outcome(messages.syntax("Work with All Output Queues is not available in Silverlake yet. Name a queue."))
        q, err = spool.queue(store, actor, b["OUTQ"], session.search_order())
        if err:
            return Outcome(err)
        return Outcome(view=("wrkoutq", q, spool.in_queue(store, q), lambda: spool.in_queue(store, q)))
    if name in ("DSPSPLF", "DLTSPLF", "HLDSPLF", "RLSSPLF"):
        job = b["JOB"]
        if job == "*":
            j = session.job
            job = (j.name, j.user, j.number) if j else ("*", "*", "*")
        f, err = spool.find(store, actor, b["FILE"].upper(), job, b["SPLNBR"])
        if err:
            return Outcome(err)
        if name == "DLTSPLF":
            return Outcome(spool.delete(store, actor, f).message)
        if name in ("HLDSPLF", "RLSSPLF"):
            return Outcome(spool.hold(store, actor, f, name == "HLDSPLF").message)
        return Outcome(view=("dspsplf", f))
    if name == "WRKACTJOB":
        sbs = b["SBS"].upper()
        if sbs != "*ALL" and not any(j.name == sbs for j in store.jobs.active() if j.type == "SBS"):
            return Outcome(messages.syntax(f"Subsystem {sbs} not found."))
        return Outcome(view=("wrkactjob", sbs))
    return _run_library_command(store, actor, session, name, b)


def _run_library_command(store: ProfileStore, actor: Profile, session: Session, name: str, b: dict) -> Outcome:
    if name == "CRTLIB":
        return Outcome(objects.create_library(store, actor, b["LIB"], b["TEXT"], b["AUT"]).message)
    if name == "DLTLIB":
        return Outcome(_done(objects.delete_library(store, actor, b["LIB"], session.search_order())))
    if name == "ADDLIBLE":
        return Outcome(objects.add_library_entry(store, actor, session, b["LIB"], b["POSITION"]).message)
    if name == "RMVLIBLE":
        return Outcome(objects.remove_library_entry(session, b["LIB"]).message)
    if name == "DSPLIBL":
        return Outcome(view=("dsplibl", session))
    if name == "WRKLIB":
        libs = objects.visible_libraries(store, actor, b["LIB"], session)
        if not libs:
            return Outcome(messages.syntax("No libraries found, or you are not authorized to any."))
        return Outcome(view=("wrklib", libs))
    if name == "DSPOBJAUT":
        obj, err = objects.display_authority(store, actor, b["OBJ"], b["OBJTYPE"], session)
        if err:
            return Outcome(err)
        return Outcome(view=("dspobjaut", obj, objects.authority_rows(store, actor, obj)))
    if name == "GO":
        menu, err = objects.use_object(store, actor, b["MENU"], "*MENU", session.search_order())
        return Outcome(err) if err else Outcome(go=(menu, b["RTNPNT"]))
    if name == "CALL":
        prog, err = objects.use_object(store, actor, b["PGM"], "*PGM", session.search_order())
        if err:
            return Outcome(err)
        if (prog.library, prog.name) == ("QSYS", "QCMD"):
            return Outcome(cmdentry=True)
        return Outcome(messages.syntax(f"Program {prog.name} cannot be run: programs are not modeled yet."))
    if name == "CHGPRF":
        attrs = {k: v for k, v in (("initial_program", b.get("INLPGM", SAME)), ("initial_menu", b.get("INLMNU", SAME)),
                                   ("current_library", b.get("CURLIB", SAME))) if v != SAME}
        if not attrs:
            return Outcome(messages.syntax("Nothing to change: give INLPGM, INLMNU or CURLIB."))
        return Outcome(admin.change_own_profile(store, actor, session.search_order(), attrs).message)
    if name == "WRKOBJ":
        def again():
            return objlist.work_with_objects(store, actor, *b["OBJ"], b["OBJTYPE"], session)[0]
        rows, err = objlist.work_with_objects(store, actor, *b["OBJ"], b["OBJTYPE"], session)
        return _object_view(rows, err, ("objects", None, again))
    if name == "WRKOBJOWN":
        owner = actor.name if b["USRPRF"] == "*CURRENT" else b["USRPRF"]

        def again():
            return objlist.work_with_objects_by_owner(store, actor, b["USRPRF"], b["OBJTYPE"])[0]
        rows, err = objlist.work_with_objects_by_owner(store, actor, b["USRPRF"], b["OBJTYPE"])
        return _object_view(rows, err, ("owner", owner, again))
    if name in DELETE_COMMANDS:
        key, typ = DELETE_COMMANDS[name]
        return Outcome(objlist.delete_object(store, actor, b[key], typ, session.search_order()).message)
    if name == "EDTOBJAUT":
        obj, err = objlist.edit_authority(store, actor, b["OBJ"], b["OBJTYPE"], session.search_order())
        return Outcome(err) if err else Outcome(view=("edtobjaut", obj))
    if name == "DSPOBJD":
        obj, err = objlist.describe_object(store, actor, b["OBJ"], b["OBJTYPE"], session.search_order())
        return Outcome(err) if err else Outcome(view=("dspobjd", obj, b["DETAIL"]))
    if name == "RNMOBJ":
        return Outcome(objlist.rename_object(store, actor, b["OBJ"], b["OBJTYPE"], b["NEWOBJ"],
                                             session.search_order()).message)
    if name == "CHGOBJD":
        if b["TEXT"] == SAME:
            return Outcome(messages.info("Object not changed."))
        return Outcome(objlist.change_description(store, actor, b["OBJ"], b["OBJTYPE"], b["TEXT"],
                                                  session.search_order()).message)
    if name == "CHGOBJOWN":
        return Outcome(objlist.change_owner(store, actor, b["OBJ"], b["OBJTYPE"], b["NEWOWN"],
                                            b["CUROWNAUT"], session.search_order()).message)
    if name in AUTL_COMMANDS:
        return _run_autl_command(store, actor, name, b)
    users = b.get("USER", [])
    if not users and b["AUTL"] == "*NONE":
        return Outcome(messages.syntax("Either USER or AUTL must be specified."))
    aut = resolve_aut(b["AUT"])
    if isinstance(aut, messages.Message):
        return Outcome(aut)
    if name == "GRTOBJAUT":
        return Outcome(objects.grant(store, actor, b["OBJ"], b["OBJTYPE"], session, users, aut,
                                     b["AUTL"], b["REPLACE"]).message)
    if name == "RVKOBJAUT":
        return Outcome(objects.revoke(store, actor, b["OBJ"], b["OBJTYPE"], session, users, aut, b["AUTL"]).message)
    raise AssertionError(name)


AUTL_COMMANDS = ("CRTAUTL", "DLTAUTL", "ADDAUTLE", "CHGAUTLE", "RMVAUTLE", "DSPAUTL", "WRKAUTL")


def _run_autl_command(store: ProfileStore, actor: Profile, name: str, b: dict) -> Outcome:
    if name == "CRTAUTL":
        return Outcome(autls.create(store, actor, b["AUTL"], b["AUT"], b["TEXT"]).message)
    if name == "DLTAUTL":
        return Outcome(autls.delete(store, actor, b["AUTL"]).message)
    if name == "RMVAUTLE":
        return Outcome(autls.remove_entry(store, actor, b["AUTL"], b["USER"]).message)
    if name in ("ADDAUTLE", "CHGAUTLE"):
        aut = autls.resolve_aut(b["AUT"])
        if isinstance(aut, messages.Message):
            return Outcome(aut)
        run = autls.add_entry if name == "ADDAUTLE" else autls.change_entry
        return Outcome(run(store, actor, b["AUTL"], b["USER"], aut).message)
    if name == "DSPAUTL":
        autl, err = autls.display(store, actor, b["AUTL"])
        return Outcome(err) if err else Outcome(view=("dspautl", autl, autls.entry_rows(autl)))
    pattern = b["AUTL"]
    rows = autls.visible(store, actor, pattern)
    if not rows:
        return Outcome(messages.syntax("No authorization lists found, or you are not authorized to any."))
    return Outcome(view=("wrkautl", rows, lambda: autls.visible(store, actor, pattern)))


def _object_view(rows: list, err, how: tuple) -> Outcome:
    if err:
        return Outcome(err)
    if not rows:
        return Outcome(messages.syntax("No objects found, or you are not authorized to any."))
    return Outcome(view=("wrkobj", rows, *how))


def _done(d: objects.Done) -> messages.Message:
    """A refusal can carry a second message (CPF2161 then CPF2168). Show both."""
    if not d.extra:
        return d.message
    return messages.Message(d.message.id, " ".join([d.message.text] + [m.line() for m in d.extra]), d.message.source)
