"""Message queues: DSPMSG, SNDMSG, CLRMSGQ, CRTMSGQ, CHGMSGQ, DLTMSGQ.

A queue is a `*MSGQ` object, so its authority is the ordinary object authority and GRTOBJAUT,
RVKOBJAUT and DSPOBJAUT work on it. Its messages live in the object's `data`. `QSYS/QSYSOPR` is
the system operator's queue. Every profile has a queue named after it in `QUSRSYS`, made the first
time anyone reaches for it (and removed with the profile).

What PUB400 showed (captured, read only): a basic profile displayed `QSYSOPR` and read system
events about other people's jobs, with their names, and its own user queue was in `QUSRSYS`
with delivery *BREAK. Delivery and severity are shown, not acted on: nothing interrupts a
session, and inquiry messages and replies are not modeled.

Rules, from IBM's 7.5 command pages:
  SNDMSG    *OBJOPR and *ADD to the queue, *USE to the queue and its library.
  CLRMSGQ   *CHANGE to the queue, *USE to the library. RMVMSG says the same for removing a message.
  CRTMSGQ   a queue gets AUT(*LIBCRTAUT): the library's create authority. The page has no
            restrictions section; it only says users of the queue need *USE to its library.
            *ADD to the library for the creator is inferred (IBM's general rule for adding an object).
            A new queue is delivery *HOLD, severity 00, as the page says.
  CHGMSGQ   *USE and *DLT to the queue. No library rule on the page. DLVRY, SEV, TEXT are modeled.
  DLTMSGQ   *USE, *OBJEXIST and *DLT to the queue, *EXECUTE to the library. QSYSOPR cannot be
            deleted. The delete itself is objlist.delete_object, shared with DLTF and the others.
The DSPMSG page has no authority section at all and lists CPF2408, "Not authorized to message
queue". Reading needing *USE is inferred, and fits the capture. That a user's own queue is created
with the library's create authority, so that on a stock QUSRSYS (public *CHANGE here) anyone can
read and write anyone's queue, is also inferred."""

from datetime import datetime

from . import messages
from .authority import Auth, SecuredObject, SpecialAuthority as SA, USE
from .objects import NAME, Done, _no, _ok, authority_to_library, locate
from .profiles import Profile, ProfileStore

USER_LIB = "QUSRSYS"
SYSOPR = ("QSYS", "QSYSOPR", "*MSGQ")
SEND_NEEDS = Auth.OBJOPR | Auth.ADD | USE
CHGMSGQ_NEEDS = USE | Auth.DLT
CHANGE_NEEDS = Auth.OBJOPR | Auth.READ | Auth.ADD | Auth.UPD | Auth.DLT | Auth.EXECUTE


def _doc(id_: str, text: str) -> messages.Message:
    return messages.Message(id_, text, messages.DOCUMENTED)


def not_authorized(q: SecuredObject) -> messages.Message:
    return _doc("CPF2408", f"Not authorized to message queue {q.name}.")


def _create_authority(store: ProfileStore, lib_name: str) -> Auth:
    """What AUT(*LIBCRTAUT) gives a new queue. The library's own public authority stands in for its
    create authority (inferred)."""
    lib = store.find_library(lib_name)
    return lib.public if lib is not None and lib.public is not None else Auth.NONE


def user_queue(store: ProfileStore, name: str) -> SecuredObject | None:
    """A profile's own queue, made on first use. None if there is no such profile."""
    name = name.upper()
    if name not in store.profiles:
        return None
    key = (USER_LIB, name, "*MSGQ")
    if key not in store.objects:
        lib = store.find_library(USER_LIB)
        public = _create_authority(store, USER_LIB)
        store.objects[key] = SecuredObject(
            name, name, public=public, library=USER_LIB, type="*MSGQ", text="User message queue",
            data={"dlvry": "*BREAK", "sev": "00", "userq": True, "messages": []})
        store.on_change()
    return store.objects[key]


def resolve(store: ProfileStore, actor: Profile, session, spec: str):
    """DSPMSG, SNDMSG and CLRMSGQ queue names: a special value, or LIB/NAME or NAME."""
    spec = spec.upper()
    if spec == "*SYSOPR":
        return store.objects.get(SYSOPR), None
    if spec in ("*WRKUSR", "*USRPRF"):
        return user_queue(store, actor.name), None
    if spec == "*WRKSTN":
        return None, messages.syntax("Work station message queues are not modeled.")
    return locate(store, actor, spec, "*MSGQ", session.search_order())


def can_read(store: ProfileStore, actor: Profile, q: SecuredObject) -> bool:
    return USE & ~store.authority_to_object(actor, q) == Auth.NONE


def can_change(store: ProfileStore, actor: Profile, q: SecuredObject) -> bool:
    return CHANGE_NEEDS & ~store.authority_to_object(actor, q) == Auth.NONE


def messages_of(q: SecuredObject) -> list[dict]:
    return q.data.setdefault("messages", [])


def display(store: ProfileStore, actor: Profile, session, spec: str):
    q, err = resolve(store, actor, session, spec)
    if err:
        return None, err
    if q is None:
        return None, messages.object_not_found("QSYSOPR", "QSYS", "*MSGQ")
    if not can_read(store, actor, q):
        return None, not_authorized(q)
    return q, None


def send(store: ProfileStore, actor: Profile, session, text: str, queues: list[str]) -> Done:
    targets = []
    for spec in queues:
        q, err = resolve(store, actor, session, spec)
        if err:
            return _no(err)
        if q is None:
            return _no(_doc("CPF2204", f"User profile {spec} not found."))
        if SEND_NEEDS & ~store.authority_to_object(actor, q):
            return _no(not_authorized(q))
        targets.append(q)
    now = datetime.now().isoformat(timespec="seconds")
    for q in targets:
        messages_of(q).append({"from": actor.name, "when": now, "text": text})
    store.on_change()
    return _ok("Message sent.")


def clear(store: ProfileStore, actor: Profile, session, spec: str) -> Done:
    q, err = resolve(store, actor, session, spec)
    if err:
        return _no(err)
    if q is None or not can_change(store, actor, q):
        return _no(not_authorized(q) if q else messages.syntax("Message queue not found."))
    messages_of(q).clear()
    store.on_change()
    return _ok(f"Message queue {q.name} in {q.library} cleared.")


def create(store: ProfileStore, actor: Profile, session, spec: str, text: str, aut: Auth | None) -> Done:
    lib_name, _, name = spec.upper().rpartition("/")
    if lib_name in ("", "*CURLIB"):
        lib_name = session.current_library or "QGPL"
    if lib_name == "*LIBL":
        return _no(messages.syntax("*LIBL is not valid for a new object, name the library."))
    if not NAME.match(name):
        return _no(messages.syntax(f"Object name {name} is not valid."))
    lib = store.find_library(lib_name)
    if lib is None:
        return _no(_doc("CPF2402", f"Library {lib_name} not found."))
    if SA.ALLOBJ not in store.special_authorities(actor) and Auth.ADD not in authority_to_library(store, actor, lib):
        return _no(messages.not_authorized_to_library(lib_name))
    if (lib_name, name, "*MSGQ") in store.objects:
        return _no(_doc("CPF2112", f"Object {name} in {lib_name} type *MSGQ already exists."))
    q = SecuredObject(
        name, actor.name, public=_create_authority(store, lib_name) if aut is None else aut,
        library=lib_name, type="*MSGQ", text=text,
        data={"dlvry": "*HOLD", "sev": "00", "messages": [],
              "created": datetime.now().isoformat(timespec="seconds")})
    store.objects[q.key] = q
    store.on_change()
    return _ok(f"Message queue {name} created in library {lib_name}.")


def change(store: ProfileStore, actor: Profile, session, spec: str, changes: dict) -> Done:
    """CHGMSGQ: DLVRY, SEV and TEXT. `changes` holds only what was given."""
    if spec.upper() in ("*SYSOPR", "*WRKUSR"):
        return _no(messages.syntax(f"Value {spec} for parameter MSGQ not valid."))
    q, err = resolve(store, actor, session, spec)
    if err:
        return _no(err)
    if q is None:
        return _no(messages.object_not_found("QSYSOPR", "QSYS", "*MSGQ"))
    if CHGMSGQ_NEEDS & ~store.authority_to_object(actor, q):
        return _no(not_authorized(q))
    if changes.get("DLVRY") == "*DFT":
        return _no(messages.syntax("DLVRY(*DFT) is not modeled."))
    if "DLVRY" in changes:
        q.data["dlvry"] = changes["DLVRY"]
    if "SEV" in changes:
        q.data["sev"] = changes["SEV"]
    if "TEXT" in changes:
        q.text = changes["TEXT"]
    store.on_change()
    return _ok(f"Message queue {q.name} in {q.library} changed.")
