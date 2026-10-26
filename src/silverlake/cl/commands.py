"""The command line: binds a parsed command to its parameters and runs it.

Only the user profile commands exist so far. Keywords must be written in full
(no F4 prompting, no abbreviations yet). Parameters we accept but do not model
are named in IGNORED so a copied command from a real system still runs."""

import fnmatch
from dataclasses import dataclass

from ..system import admin, messages
from ..system.authority import Auth, SpecialAuthority, UserClass, parse_auth
from ..system.profiles import Profile, ProfileStore
from . import parser

SA = SpecialAuthority
SAME = "*SAME"


@dataclass
class Outcome:
    message: messages.Message | None = None
    view: tuple | None = None        # ("dspusrprf", Profile) or ("wrkusrprf", [Profile])
    signoff: bool = False


class BindError(ValueError):
    pass


@dataclass(frozen=True)
class Param:
    key: str
    kind: str                # one of the KINDS below
    default: str
    maxn: int = 1


# Parameter order is the positional order on the real commands.
CRT_PARAMS = [
    Param("USRPRF", "name", ""), Param("PASSWORD", "password", "*NONE"),
    Param("PWDEXP", "yesno", "*NO"), Param("STATUS", "status", "*ENABLED"),
    Param("USRCLS", "class", "*USER"), Param("ASTLVL", "ignored", "*SYSVAL"),
    Param("CURLIB", "name*", "*CRTDFT"), Param("INLPGM", "name*", "*NONE"),
    Param("INLMNU", "name*", "MAIN"), Param("LMTCPB", "lmtcpb", "*NO"),
    Param("TEXT", "text", "*BLANK"), Param("SPCAUT", "spcaut", "*USRCLS", 8),
    Param("GRPPRF", "name*", "*NONE"), Param("SUPGRPPRF", "names", "*NONE", 15),
    Param("AUT", "aut", "*EXCLUDE"),
]
CHG_PARAMS = [Param(p.key, p.kind, SAME, p.maxn) for p in CRT_PARAMS]
CHG_PARAMS[0] = CRT_PARAMS[0]
DSP_PARAMS = [Param("USRPRF", "name", ""), Param("TYPE", "dsptype", "*BASIC"), Param("OUTPUT", "output", "*")]
DLT_PARAMS = [Param("USRPRF", "name", ""), Param("OWNOBJOPT", "ownobj", "*NODLT", 2)]
WRK_PARAMS = [Param("USRPRF", "wrkname", "*ALL"), Param("ASTLVL", "ignored", "*SYSVAL")]

COMMANDS = {
    "CRTUSRPRF": CRT_PARAMS, "CHGUSRPRF": CHG_PARAMS, "DSPUSRPRF": DSP_PARAMS,
    "DLTUSRPRF": DLT_PARAMS, "WRKUSRPRF": WRK_PARAMS, "SIGNOFF": [],
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
    raise AssertionError(k)


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
    if params and params[0].key == "USRPRF" and "USRPRF" not in given and name != "WRKUSRPRF":
        raise BindError("Required parameter USRPRF not specified.")
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


def execute(store: ProfileStore, actor: Profile, line: str) -> Outcome:
    try:
        parsed = parser.parse(line)
    except parser.ParseError as exc:
        return Outcome(messages.syntax(str(exc)))
    if parsed is None:
        return Outcome()
    name = parsed.command
    if name not in COMMANDS:
        return Outcome(messages.syntax(f"Command {name} in library *LIBL not found."))
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
    raise AssertionError(name)
