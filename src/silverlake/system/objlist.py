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

  RNMOBJ     *OBJMGT on the object (and *OBJOPR for a file), and *UPD and *EXECUTE on the library
             it sits in. IBM's system libraries cannot be renamed, nor can a library take a
             system library's name. The new name must be unique in the library for the type.
  CHGOBJD    *OBJMGT on the object (and *OBJOPR for a file) and *EXECUTE on the library.

  DLTF       *OBJEXIST and *OBJOPR on the file, *EXECUTE on the library.
  DLTMSGQ    *USE, *OBJEXIST and *DLT on the queue, *EXECUTE on the library.
  DLTMNU     *OBJEXIST and *OBJOPR on the menu, *EXECUTE on the library.
  DLTPGM     *OBJEXIST on the program, *EXECUTE on the library.
  DLTCMD     *OBJEXIST on the command (the page names no library authority).
  EDTOBJAUT  *OBJMGT on the object (and *OBJOPR for a file), or the owner, or *ALLOBJ.
  DSPOBJD    *EXECUTE on the library and some authority other than *EXCLUDE on the object.

Not on the pages, so ours: the options on the list displays (the pages do not list them, so
none are offered), and what the library gate means for a *USE check on a library you only
reach through *PUBLIC. *AUTL objects are not in the object table yet, so they never appear."""

import fnmatch

from . import messages
from .authority import ALL, USE, Auth, SecuredObject, SpecialAuthority
from .objects import NAME, SYSTEM_LIBRARIES, TYPES, Done, _no, _ok, authority_to_library, locate
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


def _need_for(typ: str) -> Auth:
    return Auth.OBJMGT | (Auth.OBJOPR if typ == "*FILE" else Auth.NONE)


def _protected(obj: SecuredObject) -> messages.Message | None:
    """Inferred from IBM's list of things RNMOBJ will not rename: its system libraries, and what
    is in them. User libraries live in QSYS as *LIB objects, so those stay renamable."""
    if obj.type == "*LIB":
        return messages.system_library_name(obj.name) if obj.name in SYSTEM_LIBRARIES else None
    if obj.library in ("QSYS", "QSYS2", "QHLPSYS"):
        return messages.protected_library(obj.library)
    return None


def rename_object(store: ProfileStore, actor: Profile, qualified: str, typ: str, new: str,
                  search: list[str]) -> Done:
    obj, err = locate(store, actor, qualified, typ, search)
    if err:
        return _no(err)
    new = new.upper()
    if not NAME.match(new):
        return _no(messages.syntax(f"New object name {new} not valid."))
    blocked = _protected(obj)
    if blocked:
        return _no(blocked)
    if typ == "*LIB" and new in SYSTEM_LIBRARIES:
        return _no(messages.system_library_name(new))
    if not _allobj(store, actor):
        if _need_for(typ) & ~store.authority_to_object(actor, obj):
            return _no(messages.not_authorized_to_object_2189(obj.name, obj.library, typ))
        lib = store.find_library(obj.library)
        if lib is None or (Auth.UPD | Auth.EXECUTE) & ~authority_to_library(store, actor, lib):
            return _no(messages.not_authorized_to_library(obj.library))
    if (obj.library, new, typ) in store.objects:
        return _no(messages.object_already_exists(new, obj.library))
    old = obj.name
    del store.objects[obj.key]
    if typ == "*LIB":                          # everything in the library moves with its name
        for inside in [o for o in store.objects.values() if o.library == old]:
            del store.objects[inside.key]
            inside.library = new
            store.objects[inside.key] = inside
        for p in store.profiles.values():
            if p.current_library == old:
                p.current_library = new
    obj.name = new
    store.objects[obj.key] = obj
    store.on_change()
    return _ok(f"Object {old} renamed to {new}.")


def change_description(store: ProfileStore, actor: Profile, qualified: str, typ: str, text: str,
                       search: list[str]) -> Done:
    obj, err = locate(store, actor, qualified, typ, search)
    if err:
        return _no(err)
    if not _allobj(store, actor) and _need_for(typ) & ~store.authority_to_object(actor, obj):
        return _no(messages.not_authorized_to_object_2189(obj.name, obj.library, typ))
    obj.text = text[:50]
    store.on_change()
    return _ok(f"Object {obj.name} in {obj.library} type {obj.type} description changed.")


def objects_secured_by(store: ProfileStore, actor: Profile, autl: str) -> list[SecuredObject]:
    return sorted((o for o in store.objects.values()
                   if o.autl == autl and (_allobj(store, actor) or store.authority_to_object(actor, o) != Auth.NONE)),
                  key=lambda o: (o.library, o.name, o.type))


DELETE_NEEDS = {"*FILE": Auth.OBJEXIST | Auth.OBJOPR, "*MENU": Auth.OBJEXIST | Auth.OBJOPR,
                "*PGM": Auth.OBJEXIST, "*CMD": Auth.OBJEXIST,
                "*MSGQ": Auth.OBJEXIST | Auth.OBJOPR | Auth.READ | Auth.DLT}


def delete_object(store: ProfileStore, actor: Profile, qualified: str, typ: str, search: list[str],
                  in_use: list[str] | None = None) -> Done:
    """DLTF, DLTMNU, DLTPGM, DLTCMD, and DLTLIB for a library. What is in IBM's system libraries is
    protected the way RNMOBJ protects it (inferred, the delete pages do not say)."""
    from .objects import delete_library
    if typ == "*LIB":
        return delete_library(store, actor, qualified.split("/")[-1], in_use or [])
    obj, err = locate(store, actor, qualified, typ, search)
    if err:
        return _no(err)
    blocked = _protected(obj)
    if blocked:
        return _no(blocked)
    if not _allobj(store, actor):
        if DELETE_NEEDS[typ] & ~store.authority_to_object(actor, obj):
            return _no(messages.not_authorized_to_object_2189(obj.name, obj.library, typ))
        lib = store.find_library(obj.library)
        needs_library = typ != "*CMD"          # the DLTCMD page names none
        if needs_library and (lib is None or Auth.EXECUTE not in authority_to_library(store, actor, lib)):
            return _no(messages.not_authorized_to_library(obj.library))
    del store.objects[obj.key]
    store.on_change()
    return _ok(f"Object {obj.name} in {obj.library} type {obj.type} deleted.")


def can_edit_authority(store: ProfileStore, actor: Profile, obj: SecuredObject) -> bool:
    if _allobj(store, actor) or actor.name == obj.owner:
        return True
    return _need_for(obj.type) & ~store.authority_to_object(actor, obj) == Auth.NONE


def edit_authority(store: ProfileStore, actor: Profile, qualified: str, typ: str, search: list[str]):
    obj, err = locate(store, actor, qualified, typ, search)
    if err:
        return None, err
    if not can_edit_authority(store, actor, obj):
        return None, messages.not_authorized_to_change_authorities()
    return obj, None


def describe_object(store: ProfileStore, actor: Profile, qualified: str, typ: str, search: list[str]):
    obj, err = locate(store, actor, qualified, typ, search)
    if err:
        return None, err
    if not _allobj(store, actor) and store.authority_to_object(actor, obj) == Auth.NONE:
        return None, messages.not_authorized_to_object_2189(obj.name, obj.library, typ)
    return obj, None
