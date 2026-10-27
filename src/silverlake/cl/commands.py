"""The command line: binds a parsed command to its parameters and runs it.

The user profile commands and the library and object authority commands exist
so far. Keywords must be written in full
(no F4 prompting, no abbreviations yet). Parameters we accept but do not model
are named in IGNORED so a copied command from a real system still runs."""

import fnmatch
from dataclasses import dataclass

from ..system import admin, autls, messages, objects
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

COMMANDS = {
    "CRTUSRPRF": CRT_PARAMS, "CHGUSRPRF": CHG_PARAMS, "DSPUSRPRF": DSP_PARAMS,
    "DLTUSRPRF": DLT_PARAMS, "WRKUSRPRF": WRK_PARAMS, "SIGNOFF": [],
    "CRTLIB": CRTLIB_PARAMS, "DLTLIB": DLTLIB_PARAMS, "DSPLIBL": DSPLIBL_PARAMS,
    "ADDLIBLE": ADDLIBLE_PARAMS, "RMVLIBLE": RMVLIBLE_PARAMS, "WRKLIB": WRKLIB_PARAMS,
    "DSPOBJAUT": DSPOBJAUT_PARAMS, "GRTOBJAUT": GRTOBJAUT_PARAMS, "RVKOBJAUT": RVKOBJAUT_PARAMS,
    "GO": GO_PARAMS, "CALL": CALL_PARAMS, "CHGPRF": CHGPRF_PARAMS,
    "CRTAUTL": CRTAUTL_PARAMS, "DLTAUTL": DLTAUTL_PARAMS, "ADDAUTLE": ADDAUTLE_PARAMS,
    "CHGAUTLE": CHGAUTLE_PARAMS, "RMVAUTLE": RMVAUTLE_PARAMS, "DSPAUTL": DSPAUTL_PARAMS,
    "WRKAUTL": WRKAUTL_PARAMS,
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
    return Outcome(view=("wrkautl", rows))


def _done(d: objects.Done) -> messages.Message:
    """A refusal can carry a second message (CPF2161 then CPF2168). Show both."""
    if not d.extra:
        return d.message
    return messages.Message(d.message.id, " ".join([d.message.text] + [m.line() for m in d.extra]), d.message.source)
