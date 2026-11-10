"""CRTDTAARA, CHGDTAARA, DLTDTAARA, CRTUSRSPC, DLTUSRSPC.

Rules read from the IBM i 7.5 command reference:
  CRTDTAARA   *ADD authority to the library (inferred, same general rule as CRTMSGQ and CRTOUTQ; the
              page's Restrictions section only covers *ALLOBJ or *SECADM for a *SECURITY data area
              type, which is not modeled). TYPE(*CHAR) is the only type modeled: pasei.py already
              keeps a data area's value as plain text for the PASE `datarea` utility and RTVDTAARA/
              CHGDTAARA's wording, so *DEC and *LGL stay unmodeled rather than add a second shape.
              LEN is required unless VALUE is given, in which case it defaults to VALUE's length, as
              the page describes.
  CHGDTAARA   *CHANGE authority to the data area (docs/pase.md: "writing *CHANGE", matching what
              pasei.py already enforces for the PASE side). Only replacing the whole value is modeled;
              the DTAARA parameter's (starting-position length) qualifier is not, so CHGDTAARA here
              always takes DTAARA(lib/name) with no substring.
  DLTDTAARA   *OBJEXIST authority to the data area and *EXECUTE to the library, the same general rule
              objlist.delete_object already applies to *PGM and *CMD.
  CRTUSRSPC   *ADD authority to the library (inferred, same rule as above). A user space here is a
              plain character buffer like a data area (data = {"value": ..., "size": N}); EXTATR and
              DOMAIN are accepted and ignored, there being nothing in Silverlake that reads either.
              INZVAL defaulting to blanks rather than IBM's hex zeros is ours, not IBM's: Silverlake
              has no binary object content anywhere else, and a user space is not read back through
              any command here, so the distinction has nothing to show against.
  DLTUSRSPC   *OBJEXIST authority to the space and *EXECUTE to the library, same as any delete. There
              is no native CHGUSRSPC command on a real system (a user space changes through the
              QUSCUSAT/QUSPTRUS APIs, not CL), so none is modeled here either."""

from datetime import datetime

from . import messages
from .authority import CHANGE, Auth, SecuredObject, SpecialAuthority as SA
from .objects import NAME, Done, _no, _ok, authority_to_library, create_authority, locate, tag_temp
from . import pasei
from .profiles import Profile, ProfileStore


def _resolve_new(store: ProfileStore, session, spec: str):
    """(library object, name, None) or (None, None, error) for a CRTDTAARA/CRTUSRSPC target."""
    lib_name, _, name = spec.upper().rpartition("/")
    if lib_name in ("", "*CURLIB"):
        lib_name = session.current_library or "QGPL"
    if lib_name == "*LIBL":
        return None, None, messages.syntax("*LIBL is not valid for a new object, name the library.")
    if not NAME.match(name):
        return None, None, messages.syntax(f"Object name {name} is not valid.")
    lib = store.find_library(lib_name)
    if lib is None:
        return None, None, messages.Message("CPF2402", f"Library {lib_name} not found.", messages.DOCUMENTED)
    return lib, name, None


def create_data_area(store: ProfileStore, actor: Profile, session, spec: str, length: int | None,
                     value: str, text: str, aut: Auth | None) -> Done:
    lib, name, err = _resolve_new(store, session, spec)
    if err:
        return _no(err)
    lib_name = lib.name
    if SA.ALLOBJ not in store.special_authorities(actor) and Auth.ADD not in authority_to_library(store, actor, lib):
        return _no(messages.not_authorized_to_library(lib_name))
    if (lib_name, name, "*DTAARA") in store.objects:
        return _no(messages.object_already_exists(name, lib_name))
    length = length if length is not None else len(value)
    if length <= 0:
        return _no(messages.syntax("Give LEN, VALUE, or both."))
    if length > pasei.MAX_DTAARA:
        return _no(messages.syntax(f"LEN cannot be more than {pasei.MAX_DTAARA} for a character data area."))
    public = aut if aut is not None else create_authority(store, lib_name)
    obj = SecuredObject(name, actor.name, public=public, library=lib_name, type="*DTAARA", text=text,
                        data={"value": value[:length].ljust(length), "length": length,
                              "created": datetime.now().isoformat(timespec="seconds")})
    tag_temp(obj, session)
    store.objects[obj.key] = obj
    store.on_change()
    return _ok(f"Data area {name} created in library {lib_name}.")


def change_data_area(store: ProfileStore, actor: Profile, session, spec: str, value: str) -> Done:
    obj, err = locate(store, actor, spec, "*DTAARA", session.search_order())
    if err:
        return _no(err)
    if CHANGE & ~store.authority_to_object(actor, obj):
        return _no(messages.not_authorized_to_object_2189(obj.name, obj.library, "*DTAARA"))
    pasei.area_set(store, obj, value, None)
    return _ok(f"Data area {obj.name} in {obj.library} changed.")


def create_user_space(store: ProfileStore, actor: Profile, session, spec: str, size: int,
                      value: str, text: str, aut: Auth | None) -> Done:
    lib, name, err = _resolve_new(store, session, spec)
    if err:
        return _no(err)
    lib_name = lib.name
    if SA.ALLOBJ not in store.special_authorities(actor) and Auth.ADD not in authority_to_library(store, actor, lib):
        return _no(messages.not_authorized_to_library(lib_name))
    if (lib_name, name, "*USRSPC") in store.objects:
        return _no(messages.object_already_exists(name, lib_name))
    public = aut if aut is not None else create_authority(store, lib_name)
    obj = SecuredObject(name, actor.name, public=public, library=lib_name, type="*USRSPC", text=text,
                        data={"value": value[:size].ljust(size), "size": size,
                              "created": datetime.now().isoformat(timespec="seconds")})
    tag_temp(obj, session)
    store.objects[obj.key] = obj
    store.on_change()
    return _ok(f"User space {name} created in library {lib_name}.")
