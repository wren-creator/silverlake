"""Libraries and object authority: CRTLIB, DLTLIB, library list changes,
DSPOBJAUT, GRTOBJAUT, RVKOBJAUT.

Rules read from the IBM i 7.5 command reference:

  DLTLIB     *USE and *OBJEXIST on the library and *OBJEXIST on every object in
             it. Without *OBJEXIST on the library nothing is deleted. Not for
             IBM system libraries, nor a library on the job's library list.
  GRTOBJAUT  the owner, a user with *OBJMGT on the object, or *ALLOBJ. Only the
             owner or *ALLOBJ may give *OBJMGT. Setting an authorization list
             takes ownership or *ALL.
  RVKOBJAUT  the owner, *OBJMGT (only for authority the caller can see), or
             *ALLOBJ.
  DSPOBJAUT  shows the full list only to someone with *OBJMGT; others see their
             own entry, or *PUBLIC when they have none (seen on a real system).

Inferred, not read on a command page: that ADDLIBLE needs *USE to the library, that an object whose library you cannot
enter looks like "not authorized" and one that is not there looks like "not
found" (a real enumeration leak, kept on purpose), and what revoking from an
authorization list does to *PUBLIC."""

from datetime import datetime
import re
from dataclasses import dataclass

from . import messages
from .authority import ALL, CHANGE, EXCLUDE, USE, Auth, SecuredObject, SpecialAuthority, name_auth, parse_auth
from .profiles import Profile, ProfileStore

SA = SpecialAuthority

NAME = re.compile(r"^[A-Z@#$][A-Z0-9@#$_]{0,9}$")
SYSTEM_LIBRARIES = frozenset({"QSYS", "QGPL", "QUSRSYS", "QSYS2", "QHLPSYS", "QTEMP"})
LIBCRTAUT = CHANGE          # "same as the create authority for QSYS", from QCRTAUT; *CHANGE assumed
# CRTLIB has no authority check here. A real QSYS is *PUBLIC *USE (seen with DSPOBJAUT),
# which has no *ADD, so "needs *ADD to QSYS" cannot be what stops ordinary users. What
# stopped a basic profile on a real system was authority to the command itself ("Not
# authorized to command CRTLIB in library *LIBL."), and commands are not objects here yet.
TYPES = ("*LIB", "*FILE", "*CMD", "*MENU", "*PGM", "*OUTQ", "*MSGQ")   # the object types modeled so far


@dataclass(frozen=True)
class Done:
    ok: bool
    message: messages.Message
    extra: tuple[messages.Message, ...] = ()


def _ok(text: str) -> Done:
    return Done(True, messages.info(text))


def _no(m: messages.Message) -> Done:
    return Done(False, m)


def _allobj(store: ProfileStore, actor: Profile) -> bool:
    return SA.ALLOBJ in store.special_authorities(actor)


def authority_to_library(store: ProfileStore, actor: Profile, lib: SecuredObject) -> Auth:
    return ALL if _allobj(store, actor) else store.object_authority(actor, lib)


# -- finding objects ---------------------------------------------------------------------

def create_authority(store: ProfileStore, lib_name: str) -> Auth:
    """What a new object in a library gets for *PUBLIC: the library's CRTAUT when it has one (data `crtaut`),
    else its own public authority, which is what *SYSVAL and *LIBCRTAUT come to here."""
    lib = store.find_library(lib_name)
    if lib is None:
        return Auth.NONE
    if lib.data.get("crtaut"):
        return parse_auth(lib.data["crtaut"])
    return lib.public if lib.public is not None else Auth.NONE


def tag_temp(obj: SecuredObject, session) -> None:
    """Whatever is made in QTEMP belongs to the job that made it."""
    if obj.library == "QTEMP":
        obj.data["job"] = session.job.qualified if session.job is not None else None


def visible(obj: SecuredObject | None, search) -> bool:
    """An object in QTEMP is only there for its own job."""
    if obj is None or obj.library != "QTEMP":
        return obj is not None
    return obj.data.get("job") == getattr(search, "job", None)


def drop_temp(store: ProfileStore, job: str | None) -> None:
    """QTEMP goes away with the job."""
    for key in [k for k, o in store.objects.items() if o.library == "QTEMP" and o.data.get("job") == job]:
        del store.objects[key]



def locate(store: ProfileStore, actor: Profile, qualified: str, typ: str,
           search: list[str]) -> tuple[SecuredObject | None, messages.Message | None]:
    """Resolve `LIB/NAME` or an unqualified name against the library list, then
    apply what a real system shows: library not found, library not usable,
    object not found, object not usable. In that order, which is what lets a
    low authority user tell what exists."""
    name = qualified.split("/")[-1].upper()
    lib_name = qualified.split("/")[0].upper() if "/" in qualified else None
    if typ == "*LIB":
        lib_name = "QSYS"
    if lib_name in ("*LIBL", None):
        found = next((lib for lib in search if visible(store.objects.get((lib, name, typ)), search)), None)
        if found is None:
            return None, messages.object_not_found(name, "*LIBL", typ)
        lib_name = found
    elif lib_name == "*CURLIB":
        return None, messages.syntax("*CURLIB is not supported yet.")
    if typ != "*LIB" or lib_name != "QSYS":
        lib = store.find_library(lib_name)
        if lib is None:
            return None, messages.library_not_found_for_object(lib_name)
        if Auth.EXECUTE not in authority_to_library(store, actor, lib):
            return None, messages.not_authorized_to_use_library(lib_name)
    obj = store.objects.get((lib_name, name, typ))
    if not visible(obj, search):
        return None, messages.object_not_found(name, lib_name, typ)
    return obj, None


def use_object(store: ProfileStore, actor: Profile, qualified: str, typ: str, search: list[str]):
    """Find an object and require *USE to it, which running a program or going to a
    menu takes (GO: "*USE authority for the menu", "*USE authority for the library")."""
    obj, err = locate(store, actor, qualified, typ, search)
    if err:
        return None, err
    if USE not in store.authority_to_object(actor, obj):
        return None, messages.not_authorized_to_object(obj.name, obj.library, typ)
    return obj, None


# -- libraries ---------------------------------------------------------------------------------

def create_library(store: ProfileStore, actor: Profile, name: str, text: str, aut: Auth | None) -> Done:
    name = name.upper()
    if not NAME.match(name):
        return _no(messages.library_name_not_valid(name))
    if store.find_library(name):
        return _no(messages.library_exists(name))
    lib = SecuredObject(name, actor.name, public=LIBCRTAUT if aut is None else aut,
                        library="QSYS", type="*LIB", text=text,
                        data={"created": datetime.now().isoformat(timespec="seconds")})
    store.objects[lib.key] = lib
    store.on_change()
    return _ok(f"Library {name} created.")


def delete_library(store: ProfileStore, actor: Profile, name: str, in_use: list[str]) -> Done:
    name = name.upper()
    lib = store.find_library(name)
    if lib is None:
        return _no(messages.library_not_found(name))
    if name in SYSTEM_LIBRARIES:
        return _no(messages.system_library(name))
    have = authority_to_library(store, actor, lib)
    if (USE | Auth.OBJEXIST) not in have:
        return _no(messages.not_authorized_to_library(name))
    if name in in_use:
        return _no(messages.library_on_list(name))
    inside = [o for o in store.objects.values() if o.library == name]
    stuck = [o for o in inside if Auth.OBJEXIST not in store.authority_to_object(actor, o)]
    for o in inside:
        if o not in stuck:
            del store.objects[o.key]
    if stuck:
        store.on_change()
        return Done(False, messages.some_objects_not_deleted(name), (messages.library_not_deleted(name),))
    del store.objects[lib.key]
    store.on_change()
    return _ok(f"Library {name} deleted.")


def add_library_entry(store: ProfileStore, actor: Profile, session, name: str, position: tuple[str, ...]) -> Done:
    name = name.upper()
    lib = store.find_library(name)
    if lib is None:
        return _no(messages.library_not_found(name))
    if USE not in authority_to_library(store, actor, lib):
        return _no(messages.not_authorized_to_library(name))
    if name in session.search_order() and position[0] != "*REPLACE":
        return _no(messages.already_on_list(name))
    mode = position[0]
    ref = position[1] if len(position) > 1 else None
    libs = session.user_libs
    if mode in ("*FIRST", "*LAST"):
        libs.insert(0, name) if mode == "*FIRST" else libs.append(name)
    else:
        if ref not in libs:
            return _no(messages.not_on_user_list(ref or "(none)"))
        i = libs.index(ref)
        if mode == "*REPLACE":
            libs[i] = name
        else:
            libs.insert(i + 1 if mode == "*AFTER" else i, name)
    return _ok(f"Library {name} added to library list.")


def remove_library_entry(session, name: str) -> Done:
    name = name.upper()
    if name not in session.user_libs:
        return _no(messages.not_on_user_list(name))
    session.user_libs.remove(name)
    return _ok(f"Library {name} removed from library list.")


def visible_libraries(store: ProfileStore, actor: Profile, pattern: str, session) -> list[SecuredObject]:
    """WRKLIB: only libraries you have some authority to."""
    import fnmatch
    libs = [o for o in store.objects.values() if o.type == "*LIB"]
    user_names = set(session.user_libs)
    if pattern == "*ALL":
        chosen = libs
    elif pattern == "*ALLUSR":
        chosen = [o for o in libs if o.name not in SYSTEM_LIBRARIES]
    elif pattern == "*USRLIBL":
        chosen = [o for o in libs if o.name in user_names]
    elif pattern == "*CURLIB":
        chosen = [o for o in libs if o.name == session.current_library]
    elif pattern == "*LIBL":
        chosen = [o for o in libs if o.name in session.search_order()]
    else:
        chosen = [o for o in libs if fnmatch.fnmatchcase(o.name, pattern)]
    return sorted((o for o in chosen if authority_to_library(store, actor, o) != Auth.NONE),
                  key=lambda o: o.name)


# -- object authority ----------------------------------------------------------------------------------

def _can_manage(store: ProfileStore, actor: Profile, obj: SecuredObject) -> bool:
    return (_allobj(store, actor) or actor.name == obj.owner
            or Auth.OBJMGT in store.authority_to_object(actor, obj))


def authority_rows(store: ProfileStore, actor: Profile, obj: SecuredObject) -> list[tuple[str, str]]:
    """DSPOBJAUT: (user, authority). Everyone with *OBJMGT sees the whole list,
    anyone else sees only themselves."""
    if not _can_manage(store, actor, obj):
        # Seen on a real system: a basic user asking about QSYS gets one row, *PUBLIC.
        # Someone with an entry of their own sees that entry instead.
        if actor.name == obj.owner:
            return [(actor.name, name_auth(obj.owner_auth))]
        if actor.name in obj.private:
            return [(actor.name, name_auth(obj.private[actor.name]) or "*EXCLUDE")]
        if obj.public is None:
            return [("*PUBLIC", "*AUTL")]
        return [("*PUBLIC", name_auth(obj.public) or "*EXCLUDE")]
    rows = [(obj.owner, name_auth(obj.owner_auth))]
    rows += [(who, name_auth(a) or "*EXCLUDE") for who, a in sorted(obj.private.items())]
    if obj.public is None:
        rows.append(("*PUBLIC", "*AUTL"))
    else:
        rows.append(("*PUBLIC", name_auth(obj.public) or "*EXCLUDE"))
    return rows


def display_authority(store: ProfileStore, actor: Profile, qualified: str, typ: str, session) -> tuple:
    obj, err = locate(store, actor, qualified, typ, session.search_order())
    if err:
        return None, err
    if store.authority_to_object(actor, obj) == Auth.NONE:
        return None, messages.not_authorized_to_object(obj.name, obj.library, typ)
    return obj, None


def _check_user(store: ProfileStore, who: str) -> messages.Message | None:
    if who not in ("*PUBLIC", "*ALL") and store.get(who) is None:
        return messages.syntax(f"User profile {who} not found.")
    return None


def grant(store: ProfileStore, actor: Profile, qualified: str, typ: str, session, users: list[str],
          aut: str | Auth, autl: str, replace: bool) -> Done:
    """`aut` is a detailed Auth, or the string "*AUTL"."""
    obj, err = locate(store, actor, qualified, typ, session.search_order())
    if err:
        return _no(err)
    key = (obj.name, obj.library, typ)
    if not _can_manage(store, actor, obj):
        return _no(messages.not_authorized_to_give(*key))
    if autl not in ("*NONE", ""):
        if store.autls.get(autl) is None:
            return _no(messages.autl_not_found(autl))
        if not (_allobj(store, actor) or actor.name == obj.owner
                or store.authority_to_object(actor, obj) == ALL):
            return _no(messages.not_authorized_to_give(*key))
    if aut == "*AUTL":
        if users != ["*PUBLIC"]:
            return _no(messages.autl_only_for_public())
        if not (obj.autl or autl not in ("*NONE", "")):
            return _no(messages.syntax("*AUTL needs an authorization list: name one with AUTL()."))
    for who in users:
        if who == "*ALL":
            return _no(messages.syntax("USER(*ALL) is only valid on RVKOBJAUT."))
        if (bad := _check_user(store, who)):
            return _no(bad)
    if isinstance(aut, Auth) and Auth.OBJMGT in aut and not (_allobj(store, actor) or actor.name == obj.owner):
        return _no(messages.not_authorized_to_give(*key))

    if autl not in ("*NONE", ""):
        obj.autl = autl
    for who in users:
        if aut == "*AUTL":
            obj.public = None
        elif who == "*PUBLIC":
            obj.public = _merge(obj.public, aut, replace)
        elif who == obj.owner:
            obj.owner_auth = _merge(obj.owner_auth, aut, replace)
        else:
            obj.private[who] = _merge(obj.private.get(who), aut, replace)
    store.on_change()
    return _ok("Authority granted.") if users else _ok("Authorization list set.")


def _merge(current: Auth | None, aut: Auth, replace: bool) -> Auth:
    """REPLACE(*NO) adds to what is there. *EXCLUDE is nothing to add, so it
    always replaces. REPLACE(*YES) sets exactly this."""
    if replace or aut == EXCLUDE or current is None:
        return aut
    return current | aut


def revoke(store: ProfileStore, actor: Profile, qualified: str, typ: str, session, users: list[str],
           aut: str | Auth, autl: str) -> Done:
    obj, err = locate(store, actor, qualified, typ, session.search_order())
    if err:
        return _no(err)
    key = (obj.name, obj.library, typ)
    if not _can_manage(store, actor, obj):
        return _no(messages.not_authorized_to_revoke(*key))
    if autl not in ("*NONE", ""):
        if obj.autl != autl:
            return _no(messages.not_secured_by_autl(*key, autl))
        obj.autl = None
        if obj.public is None:
            obj.public = EXCLUDE
        store.on_change()
        return _ok("Authorization list removed from object.")
    if aut == "*AUTL":
        if users != ["*PUBLIC"]:
            return _no(messages.autl_only_for_public())
        if obj.public is not None:
            return _no(messages.syntax("The public authority is not set to *AUTL."))
        obj.public = EXCLUDE
        store.on_change()
        return _ok("Authority revoked.")
    for who in users:
        if who == "*PUBLIC" and aut == EXCLUDE:
            return _no(messages.exclude_not_revocable_from_public())
    targets = list(obj.private) if users == ["*ALL"] else users
    for who in targets:
        if who in ("*ALL",) or (who != "*PUBLIC" and who != obj.owner and store.get(who) is None):
            return _no(messages.syntax(f"User profile {who} not found."))
    for who in targets:
        if who == "*PUBLIC":
            obj.public = (obj.public if obj.public is not None else EXCLUDE) & ~aut
        elif who == obj.owner:
            obj.owner_auth = obj.owner_auth & ~aut
        elif who in obj.private:
            left = obj.private[who] & ~aut if aut != EXCLUDE else obj.private[who]
            if left == EXCLUDE:
                del obj.private[who]       # nothing left, so no entry: the user falls through to groups and public
            else:
                obj.private[who] = left
    store.on_change()
    return _ok("Authority revoked.")
