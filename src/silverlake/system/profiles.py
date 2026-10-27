"""User profiles, the store that holds them, and the sign-on check.

Profiles come from a TOML seed file, so assigning any access level to any user
is an edit to that file (see docs/access-model.md). The file is the range's
golden state; nothing here writes back to it.
"""

import hmac
import tomllib
from datetime import date, timedelta
from dataclasses import dataclass, field, replace
from pathlib import Path

from .jobs import JobTable
from . import menus, messages
from .commandobjs import ensure_commands
from .authority import (ALL, CHANGE, EXCLUDE, QSECURITY_LEVELS, Auth, AuthList, SecuredObject, SpecialAuthority,
                        UserClass, can_grant, class_authorities, name_auth, parse_auth,
                        resolve_object_authority)

DEFAULT_SEED = Path(__file__).resolve().parent.parent / "data" / "profiles.toml"

NO_PASSWORD = None  # PASSWORD(*NONE): the profile cannot sign on interactively


class SeedError(ValueError):
    pass


@dataclass
class Profile:
    name: str
    user_class: UserClass = UserClass.USER
    # None means SPCAUT(*USRCLS). An empty set means SPCAUT(*NONE).
    special_authorities: frozenset[SpecialAuthority] | None = None
    password: str | None = NO_PASSWORD
    status: str = "*ENABLED"          # or *DISABLED
    password_expired: bool = False    # PWDEXP(*YES)
    password_changed: str | None = None   # ISO date the password was last set; None = unknown
    password_history: list[str] = field(default_factory=list)   # earlier passwords, newest last (QPWDRQDDIF)
    pwd_expitv: int | None = None         # PWDEXPITV: days, 0 is *NOMAX, None is *SYSVAL
    limited_capabilities: str = "*NO"  # LMTCPB: *NO, *PARTIAL, *YES. Recorded, not enforced yet.
    group_profile: str | None = None
    supplemental_groups: list[str] = field(default_factory=list)
    initial_program: str = "*NONE"
    initial_menu: str = "MAIN"
    current_library: str = "*CRTDFT"
    text: str = ""
    # The profile is itself a secured object. AUT defaults to *EXCLUDE, and the
    # profile always holds *CHANGE and *OBJMGT to itself (CRTUSRPRF).
    owner: str = "QSECOFR"
    public_authority: Auth = EXCLUDE
    private_authority: dict[str, Auth] = field(default_factory=dict)
    # Profiles whose authority this one holds right now through programs that adopt it. Never stored: a
    # copy of the profile made for the duration of a call (see ProfileStore.adopting).
    adopted: tuple[str, ...] = ()


@dataclass
class System:
    qsecurity: int = 40
    qpwdlvl: int = 0
    mode: str = "vulnerable"
    default_profile_owner: str = "QSECOFR"  # who "created" the seeded accounts
    qmaxsign: int = 3        # QMAXSIGN: bad sign-on attempts allowed in a row, 0 is *NOMAX
    qmaxsgnacn: int = 3      # QMAXSGNACN: 1 disable device, 2 disable profile, 3 both (devices are not simulated)
    qpwdexpitv: int = 0      # QPWDEXPITV: days a password lasts, 0 is *NOMAX
    qpwdexpwrn: int = 7      # QPWDEXPWRN: days of warning before a password expires
    qpwdminlen: int = 1      # QPWDMINLEN / QPWDMAXLEN: the length range (IBM ships 6 and 8, the seed is looser)
    qpwdmaxlen: int = 10
    qpwdrqddgt: int = 0      # QPWDRQDDGT: 1 means at least one digit
    qpwdlmtajc: int = 0      # QPWDLMTAJC: 1 means no two adjacent digits
    qpwdlmtrep: int = 0      # QPWDLMTREP: 1 no repeated character at all, 2 not twice in a row
    qpwdrqddif: int = 0      # QPWDRQDDIF: 0 off, 1 to 8 are the IBM steps (32 down to 4 remembered passwords)


class ProfileStore:
    def __init__(self, system: System, profiles: list[Profile],
                 objects: list[SecuredObject] | None = None,
                 autls: list[AuthList] | None = None, spool: list | None = None) -> None:
        self.system = system
        self.profiles = {p.name: p for p in profiles}
        self.objects = {o.key: o for o in (objects or [])}
        self.autls = {a.name: a for a in (autls or [])}
        self.active: dict[str, int] = {}          # profile name -> sessions signed on
        self.spool: list = list(spool or [])      # SpoolFile rows, kept in the state file
        self.jobs = JobTable()                    # live jobs, in memory only
        self.on_change = lambda: None             # persistence hook, set by the state layer
        self.member_locks: dict[tuple, str] = {}  # (library, file, member) -> job, while an editor has it open; memory only
        self.bad_signons: dict[str, int] = {}     # consecutive bad passwords per profile, memory only
        self.today = lambda: date.today()         # a test swaps this to move the clock

    # -- lookups ---------------------------------------------------------------

    def get(self, name: str) -> Profile | None:
        return self.profiles.get(name.upper())

    def _own_special(self, profile: Profile) -> frozenset[SpecialAuthority]:
        if profile.special_authorities is not None:
            return profile.special_authorities
        return class_authorities(profile.user_class, self.system.qsecurity)

    def special_authorities(self, profile: Profile) -> frozenset[SpecialAuthority]:
        """Own special authorities plus those of any profile adopted. The adopted ones are inferred from
        IBM's how-to pages (QSECOFR's authority "flows down the stack"), not stated outright."""
        held = self._own_special(profile)
        for name in profile.adopted:
            owner = self.profiles.get(name)
            if owner is not None:
                held = held | self._own_special(owner)
        return held

    def adopting(self, profile: Profile, owners: list[str]) -> Profile:
        """The profile as it is while programs adopt `owners`: the same name (objects it creates are still
        its own, as on IBM i), with the owners' authority added to its own. A copy, so nothing sticks."""
        names = tuple(dict.fromkeys(o for o in owners if o and o != profile.name))
        return replace(profile, adopted=names) if names else profile

    def groups_of(self, profile: Profile) -> list[str]:
        groups = ([profile.group_profile] if profile.group_profile else []) + profile.supplemental_groups
        return [g for g in groups if g in self.profiles]

    def object_authority(self, profile: Profile, obj: SecuredObject) -> Auth:
        got = resolve_object_authority(
            profile.name, self.special_authorities(profile), self.groups_of(profile), obj, self.autls)
        for name in profile.adopted:          # the user keeps their own, the owner's is added (IBM)
            owner = self.profiles.get(name)
            if owner is not None:
                got = got | resolve_object_authority(
                    owner.name, self._own_special(owner), self.groups_of(owner), obj, self.autls)
        return got

    def find_library(self, name: str) -> SecuredObject | None:
        return self.objects.get(("QSYS", name.upper(), "*LIB"))

    def authority_to_object(self, profile: Profile, obj: SecuredObject) -> Auth:
        """Authority to an object including the library it sits in. Reaching an
        object means locating it in its library, which takes *EXECUTE on the
        library (IBM: "Execute authority provides the authority needed to ...
        locate an object in a library"). So a wide open object in a locked
        library is still out of reach. *ALLOBJ skips the gate; that part is
        inferred from IBM i behavior, not read on a command page. Libraries
        themselves sit in QSYS, whose gate is treated as always open."""
        if SpecialAuthority.ALLOBJ in self.special_authorities(profile):
            return ALL
        if obj.type != "*LIB" or obj.library != "QSYS":
            lib = self.find_library(obj.library)
            if lib is None or Auth.EXECUTE not in self.object_authority(profile, lib):
                return Auth.NONE
        return self.object_authority(profile, obj)

    def profile_object(self, profile: Profile) -> SecuredObject:
        """The profile as a secured object, so the usual authority rules apply."""
        private = dict(profile.private_authority)
        private[profile.name] = private.get(profile.name, Auth.NONE) | CHANGE | Auth.OBJMGT
        return SecuredObject(profile.name, profile.owner, public=profile.public_authority, private=private,
                             type="*USRPRF")

    def authority_to_profile(self, actor: Profile, target: Profile) -> Auth:
        return self.object_authority(actor, self.profile_object(target))

    def sign_on(self, profile: Profile) -> None:
        self.active[profile.name] = self.active.get(profile.name, 0) + 1

    def sign_off(self, profile: Profile) -> None:
        if self.active.get(profile.name, 0) <= 1:
            self.active.pop(profile.name, None)
        else:
            self.active[profile.name] -= 1

    def may_create_or_change(self, actor: Profile, wanted: frozenset[SpecialAuthority]) -> bool:
        """CRTUSRPRF and CHGUSRPRF need *SECADM, and the actor must hold what they give."""
        held = self.special_authorities(actor)
        return SpecialAuthority.SECADM in held and can_grant(held, wanted)

    # -- sign-on -----------------------------------------------------------------

    def _password_matches(self, profile: Profile, typed: str) -> bool:
        if profile.password is None:
            return False
        a, b = profile.password, typed
        if self.system.qpwdlvl < 2:  # levels 0 and 1 are not case sensitive
            a, b = a.upper(), b.upper()
        return hmac.compare_digest(a.encode(), b.encode())

    def password_is_expired(self, profile: Profile) -> bool:
        """PWDEXP(*YES), or older than QPWDEXPITV days (IBM: the interval is counted from the last change)."""
        if profile.password_expired:
            return True
        days = self.expiry_days(profile)
        if not days or not profile.password_changed:
            return False
        return self.today() > date.fromisoformat(profile.password_changed) + timedelta(days=days)

    def stamp_password(self, profile: Profile) -> None:
        profile.password_changed = self.today().isoformat()

    HISTORY = {0: 0, 1: 32, 2: 24, 3: 18, 4: 12, 5: 10, 6: 8, 7: 6, 8: 4}   # QPWDRQDDIF, from memory of IBM's table

    def expiry_days(self, profile: Profile) -> int:
        """Days a password lasts for this profile: its own PWDEXPITV, else QPWDEXPITV. 0 is *NOMAX."""
        return self.system.qpwdexpitv if profile.pwd_expitv is None else profile.pwd_expitv

    def days_left(self, profile: Profile) -> int | None:
        """Days until the password expires, or None when it never will (or no change date is kept)."""
        days = self.expiry_days(profile)
        if not days or not profile.password_changed:
            return None
        return (date.fromisoformat(profile.password_changed) + timedelta(days=days) - self.today()).days

    def expiry_warning(self, profile: Profile) -> str:
        left = self.days_left(profile)
        if left is None or left < 0 or left > self.system.qpwdexpwrn:
            return ""
        return "Password will expire today." if left == 0 else (
            f"Password will expire in {left} day{'s' if left != 1 else ''}.")

    def check_password_rules(self, profile: Profile, new: str) -> messages.Message | None:
        """The QPWD* rules. Same-length rules are checked against the typed text, case folded below
        QPWDLVL 2 as the match is. The wording is ours and the real message IDs are not used."""
        s = self.system
        if len(new) < s.qpwdminlen:
            return messages.info(f"Password must be at least {s.qpwdminlen} characters long.")
        if len(new) > s.qpwdmaxlen:
            return messages.info(f"Password must be no longer than {s.qpwdmaxlen} characters.")
        if s.qpwdrqddgt and not any(c.isdigit() for c in new):
            return messages.info("Password must contain at least one digit.")
        if s.qpwdlmtajc and any(a.isdigit() and b.isdigit() for a, b in zip(new, new[1:])):
            return messages.info("Password cannot have two digits next to each other.")
        folded = new if s.qpwdlvl >= 2 else new.upper()
        if s.qpwdlmtrep == 1 and len(set(folded)) != len(folded):
            return messages.info("Password cannot repeat a character.")
        if s.qpwdlmtrep == 2 and any(a == b for a, b in zip(folded, folded[1:])):
            return messages.info("Password cannot repeat a character twice in a row.")
        keep = self.HISTORY.get(s.qpwdrqddif, 0)
        if keep:
            used = ([profile.password] if profile.password else []) + profile.password_history[-keep:]
            if any((u if s.qpwdlvl >= 2 else u.upper()) == folded for u in used):
                return messages.info("Password was used before and is not allowed again.")
        return None

    def set_password(self, profile: Profile, new: str | None) -> None:
        """Replace a password: remember the old one, clear the expired flag, stamp the date."""
        if profile.password:
            profile.password_history = (profile.password_history + [profile.password])[-32:]
        profile.password = new
        profile.password_expired = False
        self.stamp_password(profile)

    def _bad_password(self, profile: Profile) -> None:
        """Count a wrong password. At QMAXSIGN in a row the profile is disabled (QMAXSGNACN 2 or 3).
        A device cannot be varied off here, so action 1 only counts. Not read off a real host."""
        limit = self.system.qmaxsign
        n = self.bad_signons[profile.name] = self.bad_signons.get(profile.name, 0) + 1
        if limit and n >= limit and self.system.qmaxsgnacn in (2, 3):
            profile.status = "*DISABLED"
            self.bad_signons.pop(profile.name, None)
            self.on_change()

    def check_signon(self, user: str, password: str) -> "SignonResult":
        user = user.strip().upper()
        profile = self.get(user)
        if profile is None:
            return SignonResult(None, messages.user_not_found(user))
        if profile.password is None:
            return SignonResult(None, messages.no_password(user))
        if not self._password_matches(profile, password):
            if profile.status == "*ENABLED":
                self._bad_password(profile)
            return SignonResult(None, messages.password_not_correct(user))
        if profile.status != "*ENABLED":
            return SignonResult(None, messages.cannot_sign_on(user))
        self.bad_signons.pop(profile.name, None)
        return SignonResult(profile, None, self.password_is_expired(profile))

    def change_password(self, profile: Profile, current: str, new: str, verify: str) -> messages.Message | None:
        """The Change Password display at sign-on. None means it worked. Rules are the minimum
        that mean anything here, then the QPWD* rules."""
        if not self._password_matches(profile, current):
            return messages.password_not_correct(profile.name)
        if not new:
            return messages.info("New password is required.")
        limit = 10 if self.system.qpwdlvl < 2 else 128
        if len(new) > limit:
            return messages.info(f"New password is longer than {limit} characters.")
        if new != verify:
            return messages.info("New password and verify password do not match.")
        if self._password_matches(profile, new):
            return messages.info("New password must be different from the current password.")
        if (bad := self.check_password_rules(profile, new)):
            return bad
        self.set_password(profile, new)
        self.on_change()
        return None

    def describe(self, profile: Profile) -> dict[str, str]:
        """What a security review of this profile would list."""
        held = self.special_authorities(profile)
        source = "*USRCLS" if profile.special_authorities is None else (
            "*NONE" if not profile.special_authorities else "explicit")
        return {
            "profile": profile.name,
            "class": profile.user_class.value,
            "special": " ".join(sorted(a.value for a in held)) or "(none)",
            "special_source": source,
            "status": profile.status,
            "password": "*NONE" if profile.password is None else "set",
            "group": profile.group_profile or "*NONE",
            "owner": profile.owner,
            "public": name_auth(profile.public_authority),
        }


@dataclass(frozen=True)
class SignonResult:
    profile: Profile | None
    message: messages.Message | None
    must_change_password: bool = False


# -- loading ---------------------------------------------------------------------

RPG_DIR = Path(__file__).resolve().parent.parent / "data" / "rpg"


def _with_source_files(o: dict) -> dict:
    """A seeded program names its source and display file by file name (`source_file`, `dspf_file`), and a
    seeded file its record layout (`dds_file`), in data/rpg. The text goes into the object, where a student
    can read and change it."""
    d = o.get("data")
    if d and isinstance(d.get("members"), dict):
        d = dict(d)
        members = {}
        for mname, m in d["members"].items():
            m = dict(m)
            if "file" in m:
                try:
                    text = (RPG_DIR / m.pop("file")).read_text()
                except OSError as exc:
                    raise SeedError(f"object {o['name']}: member {mname}: {exc}") from exc
                m["lines"] = text.rstrip("\n").split("\n")
            m.setdefault("lines", [])
            m.setdefault("type", "")
            m.setdefault("text", "")
            members[mname.upper()] = m
        d["members"] = members
        o = {**o, "data": d}
    if not d or not ({"source_file", "dspf_file", "dds_file"} & d.keys()):
        return o
    d = dict(d)
    for key, out in (("source_file", "source"), ("dspf_file", "dspf"), ("dds_file", "dds")):
        if key in d:
            name = d.pop(key)
            try:
                d[out] = (RPG_DIR / name).read_text()
            except OSError as exc:
                raise SeedError(f"object {o['name']}: cannot read {name}: {exc}") from exc
    return {**o, "data": d}

#

def _enum(cls, value, what):
    try:
        return cls(value)
    except ValueError as exc:
        raise SeedError(f"{what}: {value!r} is not one of {[m.value for m in cls]}") from exc


def _special(value, who: str) -> frozenset[SpecialAuthority] | None:
    if value == "*USRCLS" or value is None:
        return None
    if value == "*NONE":
        return frozenset()
    if isinstance(value, str):
        value = [value]
    return frozenset(_enum(SpecialAuthority, v, f"profile {who} special_authorities") for v in value)


def load(path: Path | str | None = None) -> ProfileStore:
    path = Path(path or DEFAULT_SEED)
    try:
        data = tomllib.loads(path.read_text())
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise SeedError(f"cannot read profiles from {path}: {exc}") from exc

    sysdata = data.get("system", {})
    system = System(
        qsecurity=int(sysdata.get("qsecurity", 40)),
        qpwdlvl=int(sysdata.get("qpwdlvl", 0)),
        mode=sysdata.get("mode", "vulnerable"),
        default_profile_owner=str(sysdata.get("default_profile_owner", "QSECOFR")).upper(),
        qmaxsign=int(sysdata.get("qmaxsign", 3)),
        qmaxsgnacn=int(sysdata.get("qmaxsgnacn", 3)),
        qpwdexpitv=int(sysdata.get("qpwdexpitv", 0)),
        qpwdexpwrn=int(sysdata.get("qpwdexpwrn", 7)),
        qpwdminlen=int(sysdata.get("qpwdminlen", 1)),
        qpwdmaxlen=int(sysdata.get("qpwdmaxlen", 10)),
        qpwdrqddgt=int(sysdata.get("qpwdrqddgt", 0)),
        qpwdlmtajc=int(sysdata.get("qpwdlmtajc", 0)),
        qpwdlmtrep=int(sysdata.get("qpwdlmtrep", 0)),
        qpwdrqddif=int(sysdata.get("qpwdrqddif", 0)),
    )
    if system.qsecurity not in QSECURITY_LEVELS:
        raise SeedError(f"qsecurity must be one of {QSECURITY_LEVELS}, not {system.qsecurity}")
    if system.qpwdlvl not in (0, 1, 2, 3):
        raise SeedError(f"qpwdlvl must be 0 to 3, not {system.qpwdlvl}")
    if system.qpwdrqddif not in ProfileStore.HISTORY:
        raise SeedError(f"qpwdrqddif must be 0 to 8, not {system.qpwdrqddif}")
    if system.qpwdminlen > system.qpwdmaxlen:
        raise SeedError("qpwdminlen cannot be more than qpwdmaxlen")

    profiles: list[Profile] = []
    for raw in data.get("profile", []):
        name = str(raw.get("name", "")).upper()
        if not name or len(name) > 10:
            raise SeedError(f"profile name {name!r} must be 1 to 10 characters")
        if any(p.name == name for p in profiles):
            raise SeedError(f"duplicate profile {name}")
        pw = raw.get("password", "*NONE")
        profiles.append(Profile(
            name=name,
            user_class=_enum(UserClass, raw.get("user_class", "*USER"), f"profile {name} user_class"),
            special_authorities=_special(raw.get("special_authorities"), name),
            password=None if pw == "*NONE" else str(pw),
            status=_enum_status(raw.get("status", "*ENABLED"), name),
            password_expired=bool(raw.get("password_expired", False)),
            pwd_expitv=raw.get("pwdexpitv"),
            password_changed=raw.get("password_changed"),
            limited_capabilities=raw.get("limited_capabilities", "*NO"),
            group_profile=(raw.get("group_profile") or None) and str(raw["group_profile"]).upper(),
            supplemental_groups=[str(g).upper() for g in raw.get("supplemental_groups", [])],
            initial_program=raw.get("initial_program", "*NONE"),
            initial_menu=raw.get("initial_menu", "MAIN"),
            current_library=raw.get("current_library", "*CRTDFT"),
            text=raw.get("text", ""),
            owner=str(raw.get("owner", "")).upper(),   # blank is resolved below
            public_authority=parse_auth(raw.get("public_authority", "*EXCLUDE")),
            private_authority={k.upper(): parse_auth(v) for k, v in raw.get("private_authority", {}).items()},
        ))
    names = {p.name for p in profiles}
    for p in profiles:
        if not p.owner:
            # Not named: the default creator if there is one, else the profile owns itself.
            default = "QSECOFR" if p.name == "QSECOFR" else system.default_profile_owner
            p.owner = default if default in names else p.name
        elif p.owner not in names:
            raise SeedError(f"profile {p.name}: owner {p.owner} does not exist")
    for p in profiles:
        for g in ([p.group_profile] if p.group_profile else []) + p.supplemental_groups:
            if g not in names:
                raise SeedError(f"profile {p.name}: group {g} does not exist")

    autls = [AuthList(a["name"].upper(),
                      {k.upper(): parse_auth(v) for k, v in a.get("entries", {}).items()},
                      parse_auth(a.get("public", "*EXCLUDE")),
                      a.get("owner", "QSECOFR").upper(), a.get("text", ""))
             for a in data.get("authorization_list", [])]
    objects = []
    for o in data.get("object", []):
        o = _with_source_files(o)
        public = o.get("public", "*EXCLUDE")
        objects.append(SecuredObject(
            name=o["name"].upper(), owner=o["owner"].upper(),
            library=o.get("library", "QSYS").upper(), type=o.get("type", "*LIB").upper(),
            text=o.get("text", ""), data=dict(o.get("data", {})),
            owner_auth=parse_auth(o.get("owner_auth", "*ALL")),
            private={k.upper(): parse_auth(v) for k, v in o.get("private", {}).items()},
            public=None if public == "*AUTL" else parse_auth(public),
            autl=o.get("autl", None) and o["autl"].upper(),
        ))
    seen: set[tuple] = set()
    autl_names = {a.name for a in autls}
    libs = {o.name for o in objects if o.library == "QSYS" and o.type == "*LIB"}
    for o in objects:
        if o.key in seen:
            raise SeedError(f"duplicate object {o.library}/{o.name} {o.type}")
        seen.add(o.key)
        if o.owner not in names:
            raise SeedError(f"object {o.library}/{o.name}: owner {o.owner} does not exist")
        if o.type == "*LIB":
            if o.library != "QSYS":
                raise SeedError(f"library {o.name} must live in QSYS, not {o.library}")
        elif o.library not in libs:
            raise SeedError(f"object {o.library}/{o.name}: library {o.library} does not exist")
        if o.autl and o.autl not in autl_names:
            raise SeedError(f"object {o.library}/{o.name}: authorization list {o.autl} does not exist")
        if o.public is None and not o.autl:
            raise SeedError(f"object {o.library}/{o.name}: public *AUTL needs an authorization list")
        if o.type == "*MENU":
            try:
                menus.parse(o.data, f"menu {o.library}/{o.name}")
            except menus.MenuError as exc:
                raise SeedError(str(exc)) from exc
    from .spool import from_row
    spool = [from_row({**{"lines": []}, **{k: v for k, v in s.items()}}) for s in _spool_seed(data.get("spool_file", []))]
    for f in spool:
        if f.user not in names:
            raise SeedError(f"spool file {f.name}: owner {f.user} does not exist")
        if (f.outq_lib, f.outq, "*OUTQ") not in seen:
            raise SeedError(f"spool file {f.name}: output queue {f.outq_lib}/{f.outq} does not exist")
    store = ProfileStore(system, profiles, objects, autls, spool)
    ensure_commands(store)
    return store


def _spool_seed(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        r = dict(r)
        r["lines"] = str(r.get("lines", "")).rstrip("\n").split("\n") if r.get("lines") else []
        for k in ("user", "outq", "outq_lib", "job_name"):
            if k in r:
                r[k] = str(r[k]).upper()
        r["job_number"] = str(r["job_number"]).zfill(6)
        out.append(r)
    return out


def _enum_status(value: str, who: str) -> str:
    if value not in ("*ENABLED", "*DISABLED"):
        raise SeedError(f"profile {who} status: {value!r} is not *ENABLED or *DISABLED")
    return value
