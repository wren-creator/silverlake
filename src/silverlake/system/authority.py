"""Who may do what: user classes, special authorities, and object authority.

Sources: IBM i 7.5 CRTUSRPRF (USRCLS, SPCAUT) for classes and special authorities,
and IBM's authority collection reference for the object authority values. What is
a deliberate simplification is marked where it happens.
"""

from dataclasses import dataclass, field
from enum import Enum, Flag, auto


class SpecialAuthority(str, Enum):
    ALLOBJ = "*ALLOBJ"        # all object authority, with or without private authorizations
    AUDIT = "*AUDIT"          # auditing functions
    IOSYSCFG = "*IOSYSCFG"    # change system I/O configuration
    JOBCTL = "*JOBCTL"        # change, hold, release, cancel all jobs
    SAVSYS = "*SAVSYS"        # save and restore all objects
    SECADM = "*SECADM"        # create, change, delete user profiles
    SERVICE = "*SERVICE"      # service functions
    SPLCTL = "*SPLCTL"        # all spool functions


class UserClass(str, Enum):
    USER = "*USER"
    SYSOPR = "*SYSOPR"
    PGMR = "*PGMR"
    SECADM = "*SECADM"
    SECOFR = "*SECOFR"


SA = SpecialAuthority
QSECURITY_LEVELS = (10, 20, 30, 40, 50)


def class_authorities(user_class: UserClass, qsecurity: int) -> frozenset[SpecialAuthority]:
    """What SPCAUT(*USRCLS) grants. At QSECURITY 10 or 20 the lower classes get
    *ALLOBJ, which is why a level 20 system has no real access control."""
    if qsecurity not in QSECURITY_LEVELS:
        raise ValueError(f"QSECURITY must be one of {QSECURITY_LEVELS}, not {qsecurity}")
    low = qsecurity <= 20
    table = {
        UserClass.SECOFR: set(SA),
        UserClass.SECADM: {SA.ALLOBJ, SA.SAVSYS, SA.SECADM, SA.JOBCTL} if low else {SA.SECADM},
        UserClass.PGMR: {SA.ALLOBJ, SA.SAVSYS, SA.JOBCTL} if low else set(),
        UserClass.SYSOPR: {SA.ALLOBJ, SA.SAVSYS, SA.JOBCTL} if low else {SA.SAVSYS, SA.JOBCTL},
        UserClass.USER: {SA.ALLOBJ, SA.SAVSYS} if low else set(),
    }
    return frozenset(table[user_class])


def can_grant(grantor: frozenset[SpecialAuthority], wanted: frozenset[SpecialAuthority]) -> bool:
    """May a user holding `grantor` give `wanted` to someone else? The granting
    user must hold every authority being given. Giving *SECADM also takes *ALLOBJ
    and *SECADM, and giving *AUDIT takes *ALLOBJ, *SECADM and *AUDIT (CHGUSRPRF)."""
    if not wanted <= grantor:
        return False
    if SA.SECADM in wanted and not {SA.ALLOBJ, SA.SECADM} <= grantor:
        return False
    if SA.AUDIT in wanted and not {SA.ALLOBJ, SA.SECADM, SA.AUDIT} <= grantor:
        return False
    return True


class Auth(Flag):
    """Detailed object authorities."""
    NONE = 0
    OBJOPR = auto()
    OBJMGT = auto()
    OBJEXIST = auto()
    OBJALTER = auto()
    OBJREF = auto()
    READ = auto()
    ADD = auto()
    UPD = auto()
    DLT = auto()
    EXECUTE = auto()


ALL = (Auth.OBJOPR | Auth.OBJMGT | Auth.OBJEXIST | Auth.OBJALTER | Auth.OBJREF
       | Auth.READ | Auth.ADD | Auth.UPD | Auth.DLT | Auth.EXECUTE)
CHANGE = Auth.OBJOPR | Auth.READ | Auth.ADD | Auth.UPD | Auth.DLT | Auth.EXECUTE
USE = Auth.OBJOPR | Auth.READ | Auth.EXECUTE
EXCLUDE = Auth.NONE

SPECIAL_VALUES = {"*ALL": ALL, "*CHANGE": CHANGE, "*USE": USE, "*EXCLUDE": EXCLUDE}


def parse_auth(value: str | Auth) -> Auth:
    """`*ALL`, `*CHANGE`, `*USE`, `*EXCLUDE`, or a list such as `*OBJOPR *READ`."""
    if isinstance(value, Auth):
        return value
    text = value.strip().upper()
    if text in SPECIAL_VALUES:
        return SPECIAL_VALUES[text]
    result = Auth.NONE
    for part in text.split():
        name = part.lstrip("*")
        if name not in Auth.__members__ or name == "NONE":
            raise ValueError(f"unknown authority {part!r}")
        result |= Auth[name]
    return result


def name_auth(auth: Auth) -> str:
    """The shortest way IBM i would name this set."""
    for name, value in SPECIAL_VALUES.items():
        if auth == value:
            return name
    return " ".join(f"*{m.name}" for m in Auth if m is not Auth.NONE and m in auth)


@dataclass
class AuthList:
    name: str
    entries: dict[str, Auth] = field(default_factory=dict)  # profile name -> authority
    public: Auth = EXCLUDE


@dataclass
class SecuredObject:
    name: str
    owner: str
    owner_auth: Auth = ALL
    private: dict[str, Auth] = field(default_factory=dict)
    public: Auth | None = EXCLUDE   # None means *AUTL: ask the authorization list
    autl: str | None = None


def resolve_object_authority(
    user: str,
    special: frozenset[SpecialAuthority],
    groups: list[str],
    obj: SecuredObject,
    autls: dict[str, AuthList] | None = None,
) -> Auth:
    """What `user` may do to `obj`. Order: *ALLOBJ, the owner, the user's own
    entry (on the object, then on its authorization list), the user's groups,
    then *PUBLIC.

    Simplified, on purpose: group authorities from the primary and supplemental
    groups are simply combined, and adopted authority and the ownership
    exceptions to *ALLOBJ are not modeled yet."""
    autls = autls or {}
    autl = autls.get(obj.autl) if obj.autl else None

    if SA.ALLOBJ in special:
        return ALL
    if user == obj.owner:
        return obj.owner_auth
    if user in obj.private:
        return obj.private[user]
    if autl and user in autl.entries:
        return autl.entries[user]

    found: Auth | None = None
    for g in groups:
        for entries in (obj.private, autl.entries if autl else {}):
            if g in entries:
                found = (found or Auth.NONE) | entries[g]
    if found is not None:
        return found

    if obj.public is None:
        return autl.public if autl else EXCLUDE
    return obj.public
