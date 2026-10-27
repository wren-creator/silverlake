"""WRKOBJ, WRKOBJOWN and CHGOBJOWN.

Rules read from the IBM i 7.5 command pages:

  WRKOBJ     OBJ(lib/name) with a generic name or *ALL, and a library of a name, *LIBL, *CURLIB,
             *USRLIBL, *ALLUSR or *ALL. "Only the libraries to which you have use (*USE)
             authority will be searched" and "only the objects to which you have some authority
             will be shown". A named library that does not exist is CPF9810, one you cannot use
             CPF9820.
  WRKOBJOWN  USRPRF(name or *CURRENT) and OBJTYPE. Needs *READ to the profile (CPF2217).
  CHGOBJOWN  needs *OBJEXIST on the object (and *OBJOPR too for a library or file), *ADD to the
             new owner's profile and *DLT to the present owner's, or *ALLOBJ. CUROWNAUT(*REVOKE)
             takes the old owner's authority away, *SAME keeps it as a private entry.

Not on the pages, so ours: the options on the list displays (the pages do not list them, so
none are offered), and what the library gate means for a *USE check on a library you only
reach through *PUBLIC. *AUTL objects are not in the object table yet, so they never appear."""

import fnmatch

from . import messages
from .authority import ALL, USE, Auth, SecuredObject, SpecialAuthority
from .objects import TYPES, Done, _no, _ok, locate
from .profiles import Profile, ProfileStore

SA = SpecialAuthority
NOT_USER_LIBS = frozenset({"QSYS", "QSYS2", "QHLPSYS", "QTEMP"})   # what *ALLUSR leaves out


def _allobj(store: ProfileStore, actor: Profile) -> bool:
    return SA.ALLOBJ in store.special_authorities(actor)


def _can_use_library(store: ProfileStore, actor: Profile, lib: SecuredObject) -> bool:
    return _allobj(store, actor) or USE & ~store.object_authority(actor, lib) == Auth.NONE


def _libraries(store: ProfileStore, actor: Profile, spec: str, session) -> tuple[list[str], messages.Message | None]:
    all_libs = sorted(o.name for o in store.objects.values() if o.type == "*LIB")
    if spec == "*LIBL":
        names = session.search_order()
    elif spec == "*CURLIB":
        names = [session.current_library] if session.current_library else []
    elif spec == "*USRLIBL":
        names = ([session.current_library] if session.current_library else []) + list(session.user_libs)
    elif spec == "*ALLUSR":
        names = [n for n in all_libs if n not in NOT_USER_LIBS]
    elif spec == "*ALL":
        names = all_libs
    else:
        lib = store.find_library(spec)
        if lib is None:
            return [], messages.object_list_library_not_found(spec)
        if not _can_use_library(store, actor, lib):
            return [], messages.object_list_not_authorized_to_library(spec)
        return [spec], None
    usable = [n for n in names if (lib := store.find_library(n)) is not None and _can_use_library(store, actor, lib)]
    return list(dict.fromkeys(usable)), None


def _types(typ: str | list[str]) -> set[str]:
    return set(TYPES) if typ == "*ALL" else set(typ)


def work_with_objects(store: ProfileStore, actor: Profile, name: str, lib_spec: str, typ: str, session):
    libs, err = _libraries(store, actor, lib_spec, session)
    if err:
        return [], err
    wanted = _types(typ)
    rows = [o for o in store.objects.values()
            if o.library in libs and o.type in wanted
            and (name == "*ALL" or fnmatch.fnmatchcase(o.name, name))
            and (_allobj(store, actor) or store.authority_to_object(actor, o) != Auth.NONE)]
    return sorted(rows, key=lambda o: (o.library, o.name, o.type)), None


def work_with_objects_by_owner(store: ProfileStore, actor: Profile, user: str, typ: str | list[str]):
    owner = actor if user == "*CURRENT" else store.profiles.get(user.upper())
    if owner is None:
        return [], messages.profile_not_found(user.upper())
    if Auth.READ not in store.authority_to_profile(actor, owner):
        return [], messages.not_authorized_to_profile(owner.name)
    wanted = _types(typ)
    rows = [o for o in store.objects.values()
            if o.owner == owner.name and o.type in wanted
            and (_allobj(store, actor) or store.authority_to_object(actor, o) != Auth.NONE)]
    return sorted(rows, key=lambda o: (o.library, o.name, o.type)), None


def change_owner(store: ProfileStore, actor: Profile, qualified: str, typ: str, new_owner: str,
                 keep_authority: bool, search: list[str]) -> Done:
    obj, err = locate(store, actor, qualified, typ, search)
    if err:
        return _no(err)
    new = store.profiles.get(new_owner.upper())
    if new is None:
        return _no(messages.profile_not_found(new_owner.upper()))
    old = store.profiles.get(obj.owner)
    if not _allobj(store, actor):
        have = store.authority_to_object(actor, obj)
        need = Auth.OBJEXIST | (Auth.OBJOPR if typ in ("*LIB", "*FILE") else Auth.NONE)
        if need & ~have:
            return _no(messages.not_authorized_to_object_in_library(obj.name, obj.library))
        if Auth.ADD not in store.authority_to_profile(actor, new):
            return _no(messages.not_authorized_to_new_owner(new.name))
        if old is not None and Auth.DLT not in store.authority_to_profile(actor, old):
            return _no(messages.no_delete_authority_to_owner(old.name))
    previous = obj.owner
    kept = obj.owner_auth
    obj.owner = new.name
    obj.private.pop(new.name, None)             # the owner needs no private entry
    if keep_authority and previous != new.name:
        obj.private[previous] = kept
    store.on_change()
    return _ok(f"Ownership of object {obj.name} in {obj.library} type {obj.type} changed.")
