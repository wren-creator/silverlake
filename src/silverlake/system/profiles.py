"""User profiles, the store that holds them, and the sign-on check.

Profiles come from a TOML seed file, so assigning any access level to any user
is an edit to that file (see docs/access-model.md). The file is the range's
golden state; nothing here writes back to it.
"""

import hmac
import tomllib
from datetime import date, timedelta
from dataclasses import dataclass, field
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


@dataclass
class System:
    qsecurity: int = 40
    qpwdlvl: int = 0
    mode: str = "vulnerable"
    default_profile_owner: str = "QSECOFR"  # who "created" the seeded accounts
    qmaxsign: int = 3        # QMAXSIGN: bad sign-on attempts allowed in a row, 0 is *NOMAX
    qmaxsgnacn: int = 3      # QMAXSGNACN: 1 disable device, 2 disable profile, 3 both (devices are not simulated)
    qpwdexpitv: int = 0      # QPWDEXPITV: days a password lasts, 0 is *NOMAX


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
        self.bad_signons: dict[str, int] = {}     # consecutive bad passwords per profile, memory only
        self.today = lambda: date.today()         # a test swaps this to move the clock

    # -- lookups ---------------------------------------------------------------

    def get(self, name: str) -> Profile | None:
        return self.profiles.get(name.upper())

    def special_authorities(self, profile: Profile) -> frozenset[SpecialAuthority]:
        if profile.special_authorities is not None:
            return profile.special_authorities
        return class_authorities(profile.user_class, self.system.qsecurity)

    def groups_of(self, profile: Profile) -> list[str]:
        groups = ([profile.group_profile] if profile.group_profile else []) + profile.supplemental_groups
        return [g for g in groups if g in self.profiles]

    def object_authority(self, profile: Profile, obj: SecuredObject) -> Auth:
        return resolve_object_authority(
            profile.name, self.special_authorities(profile), self.groups_of(profile), obj, self.autls)

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
        days = self.system.qpwdexpitv
        if not days or not profile.password_changed:
            return False
        return self.today() > date.fromisoformat(profile.password_changed) + timedelta(days=days)

    def stamp_password(self, profile: Profile) -> None:
        profile.password_changed = self.today().isoformat()

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
        that mean anything here; QPWDMINLEN, QPWDRQDDIF and the rest of the rules are not built."""
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
        profile.password = new
        profile.password_expired = False
        self.stamp_password(profile)
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
    )
    if system.qsecurity not in QSECURITY_LEVELS:
        raise SeedError(f"qsecurity must be one of {QSECURITY_LEVELS}, not {system.qsecurity}")
    if system.qpwdlvl not in (0, 1, 2, 3):
        raise SeedError(f"qpwdlvl must be 0 to 3, not {system.qpwdlvl}")

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
