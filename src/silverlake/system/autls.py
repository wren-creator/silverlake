"""Authorization lists: CRTAUTL, DLTAUTL, ADDAUTLE, CHGAUTLE, RMVAUTLE, DSPAUTL, WRKAUTL.

Rules read from the IBM i 7.5 command reference pages:

  CRTAUTL    AUT is the authority for users with no entry of their own, not on a list, and
             whose groups have none (default *CHANGE). The creator owns the list.
  DLTAUTL    the owner or *ALLOBJ. A list that still secures an object cannot be deleted
             (CPF2279).
  ADDAUTLE   the owner, *ALLOBJ, or a user holding *AUTLMGT on the list. Only the owner or
             *ALLOBJ may give *AUTLMGT. *PUBLIC is always on the list and cannot be added.
  CHGAUTLE   same, and *PUBLIC may be changed but never given *AUTLMGT.
  RMVAUTLE   the owner, *ALLOBJ, or *AUTLMGT, and a *AUTLMGT user may only remove someone
             whose authorities they hold too. *PUBLIC cannot be removed.
  WRKAUTL    shows lists you have some authority to.

Inferred, not read on a page: that a *AUTLMGT user may only hand out authorities they hold
themselves (the page says "only to the *AUTLMGT level"), that DSPAUTL needs the owner, *ALLOBJ
or an entry on the list, that an entry already on the list counts as an error when added,
and that QIBM_DB_SECADM (which the pages also name) does not exist here."""

import fnmatch

from . import messages
from .authority import EXCLUDE, SPECIAL_VALUES, Auth, AuthList, SpecialAuthority
from .objects import NAME, Done, _no, _ok
from .profiles import Profile, ProfileStore

SA = SpecialAuthority
PUBLIC = "*PUBLIC"


def _full(store: ProfileStore, actor: Profile, autl: AuthList) -> bool:
    return actor.name == autl.owner or SA.ALLOBJ in store.special_authorities(actor)


def _manager(store: ProfileStore, actor: Profile, autl: AuthList) -> bool:
    return Auth.AUTLMGT in autl.entries.get(actor.name, EXCLUDE)


def can_change(store: ProfileStore, actor: Profile, autl: AuthList) -> bool:
    return _full(store, actor, autl) or _manager(store, actor, autl)


def can_see(store: ProfileStore, actor: Profile, autl: AuthList) -> bool:
    return _full(store, actor, autl) or actor.name in autl.entries


def visible(store: ProfileStore, actor: Profile, pattern: str = "*ALL") -> list[AuthList]:
    return sorted((a for a in store.autls.values()
                   if can_see(store, actor, a) and (pattern == "*ALL" or fnmatch.fnmatchcase(a.name, pattern))),
                  key=lambda a: a.name)


def resolve_aut(values: list[str]) -> Auth | messages.Message:
    """AUT for the entry commands: *EXCLUDE alone, or up to eleven values where a special
    value (*ALL, *CHANGE, *USE) can only be joined by *AUTLMGT."""
    if values == ["*EXCLUDE"]:
        return EXCLUDE
    if "*EXCLUDE" in values:
        return messages.exclude_with_another()
    specials = [v for v in values if v in SPECIAL_VALUES]
    others = [v for v in values if v not in SPECIAL_VALUES and v != "*AUTLMGT"]
    if specials:
        if len(specials) > 1 or others:
            return messages.autlmgt_only_with(specials[0])
        auth = SPECIAL_VALUES[specials[0]]
        return auth | Auth.AUTLMGT if "*AUTLMGT" in values else auth
    auth = EXCLUDE
    for v in values:
        auth |= Auth[v.lstrip("*")]
    return auth


def create(store: ProfileStore, actor: Profile, name: str, aut: Auth, text: str) -> Done:
    name = name.upper()
    if not NAME.match(name):
        return _no(messages.syntax(f"Authorization list name {name} not valid."))
    if name in store.autls:
        return _no(messages.autl_exists(name))
    store.autls[name] = AuthList(name, {}, aut, actor.name, text)
    store.on_change()
    return _ok(f"Authorization list {name} created.")


def delete(store: ProfileStore, actor: Profile, name: str) -> Done:
    autl = store.autls.get(name.upper())
    if autl is None:
        return _no(messages.autl_object_not_found(name.upper()))
    if not _full(store, actor, autl):
        return _no(messages.not_authorized_to_autl_object(autl.name))
    if any(o.autl == autl.name for o in store.objects.values()):
        return _no(messages.autl_in_use(autl.name))
    del store.autls[autl.name]
    store.on_change()
    return _ok(f"Authorization list {autl.name} deleted.")


def _entry_command(store: ProfileStore, actor: Profile, name: str, users: list[str], aut: Auth | None,
                   mode: str) -> Done:
    """ADDAUTLE (mode "adding"), CHGAUTLE ("changing") and RMVAUTLE ("removing") share their checks."""
    autl = store.autls.get(name.upper())
    if autl is None:
        return _no(messages.autl_not_found(name.upper()))
    if not can_change(store, actor, autl):
        return _no(messages.not_authorized_to_change_autl(autl.name))
    full = _full(store, actor, autl)
    mine = autl.entries.get(actor.name, EXCLUDE)
    if aut is not None and Auth.AUTLMGT in aut and not full:
        return _no(messages.not_authorized_to_change_autl(autl.name))
    users = [u.upper() for u in users]
    if mode == "adding" and PUBLIC in users:
        return _no(messages.public_always_on_autl())
    if mode == "removing" and PUBLIC in users:
        return _no(messages.public_not_removable())
    if mode == "changing" and PUBLIC in users and aut is not None and Auth.AUTLMGT in aut:
        return _no(messages.public_no_autlmgt())
    missing = [u for u in users if u != PUBLIC and u not in store.profiles]
    if missing:
        return _no(messages.autl_users_not_found())

    errors = 0
    for user in users:
        old = autl.public if user == PUBLIC else autl.entries.get(user)
        if mode == "adding" and old is not None:
            errors += 1
        elif mode != "adding" and old is None:
            errors += 1
        elif not full and not _may_touch(mine, old, aut, mode):
            errors += 1
        elif mode == "removing":
            del autl.entries[user]
        elif user == PUBLIC:
            autl.public = aut
        else:
            autl.entries[user] = aut
    store.on_change()
    if errors:
        return Done(False, messages.autl_entry_errors(mode, errors))
    verb = {"adding": "added to", "changing": "changed on", "removing": "removed from"}[mode]
    return _ok(f"User entries {verb} authorization list {autl.name}.")


def _within(wanted: Auth, held: Auth) -> bool:
    return not (wanted & ~Auth.AUTLMGT & ~held)


def _may_touch(mine: Auth, old: Auth | None, new: Auth | None, mode: str) -> bool:
    """A *AUTLMGT user can only deal in authorities they hold themselves."""
    held = mine & ~Auth.AUTLMGT
    if mode == "removing":
        return _within(old, held)
    changed = (old or EXCLUDE) ^ new
    return _within(changed, held)


def add_entry(store, actor, name, users, aut) -> Done:
    return _entry_command(store, actor, name, users, aut, "adding")


def change_entry(store, actor, name, users, aut) -> Done:
    return _entry_command(store, actor, name, users, aut, "changing")


def remove_entry(store, actor, name, users) -> Done:
    return _entry_command(store, actor, name, users, None, "removing")


def display(store: ProfileStore, actor: Profile, name: str):
    autl = store.autls.get(name.upper())
    if autl is None:
        return None, messages.autl_not_found(name.upper())
    if not can_see(store, actor, autl):
        return None, messages.not_authorized_to_use_autl(autl.name)
    return autl, None


def entry_rows(autl: AuthList) -> list[tuple[str, str]]:
    from .authority import name_auth
    rows = [(u, name_auth(a) or "*EXCLUDE") for u, a in sorted(autl.entries.items())]
    return rows + [(PUBLIC, name_auth(autl.public) or "*EXCLUDE")]
