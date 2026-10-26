"""Creating, changing, displaying and deleting user profiles, with IBM i's rules.

The rules come from the IBM i 7.5 command reference for CRTUSRPRF, CHGUSRPRF,
DSPUSRPRF and DLTUSRPRF:

  create   *SECADM; *CHANGE and *OBJMGT to any group profile; the actor must hold
           every special authority being given, and giving *SECADM or *AUDIT also
           takes *ALLOBJ.
  change   *SECADM, plus *OBJMGT and *USE to the profile being changed; the same
           rules for what may be given.
  display  *READ to the profile.
  delete   *SECADM, plus *OBJEXIST and *USE to the profile. A profile that owns
           objects is not deleted unless OWNOBJOPT says what happens to them.

Not modeled: authority to the initial program, menu, job description, message
queue and output queue (there is no object model yet), and password rules.
"""

import re
from dataclasses import dataclass

from . import messages
from .authority import CHANGE, USE, Auth, SpecialAuthority, UserClass, can_grant, class_authorities
from .profiles import Profile, ProfileStore

SA = SpecialAuthority

# IBM lists these as not valid for DLTUSRPRF ("and others", which we do not know).
PROTECTED = frozenset({"QSYS", "QSECOFR", "QDFTOWN", "QPGMR", "QUSER"})
NAME = re.compile(r"^[A-Z@#$][A-Z0-9@#$_]{0,9}$")


@dataclass(frozen=True)
class Result:
    ok: bool
    message: messages.Message


def _ok(text: str) -> Result:
    return Result(True, messages.info(text))


def _no(message: messages.Message) -> Result:
    return Result(False, message)


def _effective_special(store: ProfileStore, user_class: UserClass,
                       special: frozenset[SA] | None) -> frozenset[SA]:
    return special if special is not None else class_authorities(user_class, store.system.qsecurity)


def _check_special_grant(store: ProfileStore, actor: Profile, wanted: frozenset[SA]) -> messages.Message | None:
    held = store.special_authorities(actor)
    if not wanted <= held:
        return messages.lacking_authorities()
    if not can_grant(held, wanted):
        return messages.allobj_required()
    return None


def _check_groups(store: ProfileStore, actor: Profile, groups: list[str]) -> messages.Message | None:
    for g in groups:
        target = store.get(g)
        if target is None:
            return messages.group_not_found(g)
        need = CHANGE | Auth.OBJMGT
        if need not in store.authority_to_profile(actor, target):
            return messages.not_authorized_to_profile(g)
    return None


def _all_groups(attrs: dict, fallback: Profile | None = None) -> list[str]:
    group = attrs.get("group_profile", fallback.group_profile if fallback else None)
    supp = attrs.get("supplemental_groups", fallback.supplemental_groups if fallback else [])
    return ([group] if group else []) + list(supp)


def create(store: ProfileStore, actor: Profile, name: str, attrs: dict) -> Result:
    """`attrs` holds every attribute with the command's defaults filled in."""
    name = name.upper()
    if SA.SECADM not in store.special_authorities(actor):
        return _no(messages.secadm_required())
    if not NAME.match(name):
        return _no(messages.syntax(f"{name} is not a valid profile name."))
    if store.get(name):
        return _no(messages.profile_exists(name))
    if (bad := _check_groups(store, actor, _all_groups(attrs))):
        return _no(bad)
    wanted = _effective_special(store, attrs["user_class"], attrs["special"])
    if (bad := _check_special_grant(store, actor, wanted)):
        return _no(bad)
    if attrs["password"] is None and attrs["password_expired"]:
        return _no(messages.expired_with_no_password())

    profile = Profile(
        name=name, user_class=attrs["user_class"], special_authorities=attrs["special"],
        password=attrs["password"], status=attrs["status"], password_expired=attrs["password_expired"],
        limited_capabilities=attrs["limited_capabilities"], group_profile=attrs["group_profile"],
        supplemental_groups=list(attrs["supplemental_groups"]), initial_program=attrs["initial_program"],
        initial_menu=attrs["initial_menu"], current_library=attrs["current_library"], text=attrs["text"],
        owner=actor.name, public_authority=attrs["public_authority"],
    )
    store.profiles[name] = profile
    store.on_change()
    return _ok(f"User profile {name} created.")


def change(store: ProfileStore, actor: Profile, name: str, attrs: dict) -> Result:
    """`attrs` holds only what the command specified; everything else is *SAME."""
    name = name.upper()
    if SA.SECADM not in store.special_authorities(actor):
        return _no(messages.secadm_required())
    target = store.get(name)
    if target is None:
        return _no(messages.profile_not_found(name))
    if (Auth.OBJMGT | USE) not in store.authority_to_profile(actor, target):
        return _no(messages.not_authorized_to_change(name))
    if ("group_profile" in attrs or "supplemental_groups" in attrs) and (
            bad := _check_groups(store, actor, _all_groups(attrs, target))):
        return _no(bad)

    new_class = attrs.get("user_class", target.user_class)
    new_special = attrs["special"] if "special" in attrs else target.special_authorities
    added = _effective_special(store, new_class, new_special) - store.special_authorities(target)
    if added and (bad := _check_special_grant(store, actor, frozenset(added))):
        return _no(bad)
    new_password = attrs["password"] if "password" in attrs else target.password
    if new_password is None and attrs.get("password_expired", target.password_expired):
        return _no(messages.expired_with_no_password())

    for key, value in attrs.items():
        if key == "special":
            target.special_authorities = value
        elif key == "supplemental_groups":
            target.supplemental_groups = list(value)
        else:
            setattr(target, key, value)
    store.on_change()
    return _ok(f"User profile {name} changed.")


def display(store: ProfileStore, actor: Profile, name: str) -> tuple[Profile | None, messages.Message | None]:
    name = name.upper()
    target = store.get(name)
    if target is None:
        return None, messages.profile_not_found(name)
    if Auth.READ not in store.authority_to_profile(actor, target):
        return None, messages.not_authorized_to_profile(name)
    return target, None


def visible_profiles(store: ProfileStore, actor: Profile) -> list[Profile]:
    """WRKUSRPRF: only profiles you have some authority to."""
    return [p for p in sorted(store.profiles.values(), key=lambda p: p.name)
            if store.authority_to_profile(actor, p) != Auth.NONE]


def delete(store: ProfileStore, actor: Profile, name: str, ownobjopt: tuple[str, ...] = ("*NODLT",)) -> Result:
    name = name.upper()
    target = store.get(name)
    if target is None:
        return _no(messages.profile_not_found(name))
    if name in PROTECTED:
        return _no(messages.profile_not_correct(name))
    held = store.special_authorities(actor)
    if SA.SECADM not in held or (Auth.OBJEXIST | USE) not in store.authority_to_profile(actor, target):
        return _no(messages.not_authorized_to_delete(name))
    if store.active.get(name):
        return _no(messages.not_deleted(name, "A user is signed on under the profile."))

    owned = [o for o in store.objects.values() if o.owner == name]
    mode = ownobjopt[0]
    if owned and mode == "*NODLT":
        return _no(messages.not_deleted(name, "It owns objects and OWNOBJOPT(*NODLT) is in effect."))
    if owned and mode == "*DLT":
        for obj in owned:
            if Auth.OBJEXIST not in store.authority_to_object(actor, obj):
                return _no(messages.not_deleted(name, f"No *OBJEXIST authority to {obj.name}."))
    if owned and mode == "*CHGOWN":
        new_owner = ownobjopt[1].upper() if len(ownobjopt) > 1 else ""
        if new_owner == name:
            return _no(messages.syntax("The new owner cannot be the profile being deleted."))
        if new_owner not in store.profiles:
            return _no(messages.profile_not_found(new_owner or "(none)"))

    # Past every check. Now change things.
    notes = []
    if owned:
        for obj in owned:
            if mode == "*DLT":
                if obj.type == "*LIB" and obj.library == "QSYS":      # a library takes its contents with it
                    for inner in [o for o in store.objects.values() if o.library == obj.name]:
                        del store.objects[inner.key]
                store.objects.pop(obj.key, None)
            else:
                obj.owner = ownobjopt[1].upper()
        notes.append(f"{len(owned)} owned object(s) {'deleted' if mode == '*DLT' else 'moved to ' + ownobjopt[1].upper()}.")

    # Owned profiles are never deleted with their owner: they go to QDFTOWN.
    heir = next((n for n in ("QDFTOWN", "QSECOFR") if n in store.profiles and n != name), None)
    for p in store.profiles.values():
        if p.owner == name and p.name != name and heir:
            p.owner = heir

    members = 0
    for p in store.profiles.values():
        if p.group_profile == name:
            p.group_profile, members = None, members + 1
        if name in p.supplemental_groups:
            p.supplemental_groups.remove(name)
            members += 1
        p.private_authority.pop(name, None)
    if members:
        notes.append(f"Group information removed from {members} profile(s).")
    for obj in store.objects.values():
        obj.private.pop(name, None)
    for autl in store.autls.values():
        autl.entries.pop(name, None)

    del store.profiles[name]
    store.on_change()
    return _ok(" ".join([f"User profile {name} deleted."] + notes))
