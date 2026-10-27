"""Message IDs and our own wording for them. Each carries where its ID came from,
so a message we only believe in is never presented as one we confirmed."""

from dataclasses import dataclass

VERIFIED = "seen on a real IBM i"
RECALLED = "from the earlier web3270 mock, not yet confirmed on a real system"
DOCUMENTED = "listed in IBM's command reference; which condition raises it is inferred"
NO_ID = "no message ID checked; the wording is ours"


@dataclass(frozen=True)
class Message:
    id: str
    text: str
    source: str

    def line(self) -> str:
        return f"{self.id} - {self.text}" if self.id else self.text


def user_not_found(user: str) -> Message:
    return Message("CPF1120", f"User {user} does not exist.", VERIFIED)


def password_not_correct(user: str) -> Message:
    return Message("CPF1107", "Password not correct for user profile.", RECALLED)


def no_password(user: str) -> Message:
    return Message("CPF1118", f"No password associated with user {user}.", RECALLED)


def cannot_sign_on(user: str) -> Message:
    return Message("CPF1394", f"User profile {user} cannot sign on.", RECALLED)


# -- user profile administration. IDs come from the IBM i 7.5 command reference
# error lists for CRTUSRPRF, CHGUSRPRF, DSPUSRPRF and DLTUSRPRF. None of those
# pages lists a completion message, so completions carry no ID.

def info(text: str) -> Message:
    return Message("", text, NO_ID)


def _doc(id: str, text: str) -> Message:
    return Message(id, text, DOCUMENTED)


def profile_not_found(name: str) -> Message:
    return _doc("CPF2204", f"User profile {name} not found.")


def not_authorized_to_profile(name: str) -> Message:
    return _doc("CPF2217", f"Not authorized to user profile {name}.")


def secadm_required() -> Message:
    return _doc("CPF2292", "*SECADM special authority is required to create or change user profiles.")


def profile_exists(name: str) -> Message:
    return _doc("CPF2214", f"User profile {name} already exists.")


def not_authorized_to_change(name: str) -> Message:
    return _doc("CPF2228", f"Not authorized to change user profile {name}.")


def not_authorized_to_delete(name: str) -> Message:
    return _doc("CPF2229", f"Not authorized to delete user profile {name}.")


def group_not_found(name: str) -> Message:
    return _doc("CPF2259", f"Group profile {name} not found.")


def lacking_authorities() -> Message:
    return _doc("CPF2291", "User profile does not have all special authorities being granted.")


def allobj_required() -> Message:
    return _doc("CPF2269", "Special authority *ALLOBJ required when granting *SECADM or *AUDIT.")


def expired_with_no_password() -> Message:
    return _doc("CPF223F", "Cannot set password to expired when password is *NONE.")


def profile_not_correct(name: str) -> Message:
    return _doc("CPF2203", f"User profile {name} not correct.")


def not_deleted(name: str, why: str) -> Message:
    return _doc("CPF2215", f"User profile {name} not deleted. {why}")


# -- libraries and object authority. IDs and text come from the IBM i 7.5 error
# lists for CRTLIB, DLTLIB, ADDLIBLE, RMVLIBLE, DSPOBJAUT, GRTOBJAUT, RVKOBJAUT.
# Which condition raises each is still inferred.

def library_exists(lib: str) -> Message:
    return _doc("CPF2111", f"Library {lib} already exists.")


def library_not_found(lib: str) -> Message:
    return _doc("CPF2110", f"Library {lib} not found.")


def library_not_found_for_object(lib: str) -> Message:
    return _doc("CPF2209", f"Library {lib} not found.")


def library_name_not_valid(lib: str) -> Message:
    return _doc("CPF2166", f"Library name {lib} not valid.")


def not_authorized_to_library(lib: str) -> Message:
    return _doc("CPF2182", f"Not authorized to library {lib}.")


def not_authorized_to_use_library(lib: str) -> Message:
    return _doc("CPF2216", f"Not authorized to use library {lib}.")


def system_library(lib: str) -> Message:
    return _doc("CPF2129", f"Clear or delete of system library {lib} canceled.")


def library_on_list(lib: str) -> Message:
    return _doc("CPF2167", f"Library {lib} on library list and cannot be deleted.")


def some_objects_not_deleted(lib: str) -> Message:
    return _doc("CPF2161", f"Cannot delete some objects in library {lib}.")


def library_not_deleted(lib: str) -> Message:
    return _doc("CPF2168", f"Library {lib} not deleted.")


def already_on_list(lib: str) -> Message:
    return _doc("CPF2103", f"Library {lib} already exists in library list.")


def not_on_user_list(lib: str) -> Message:
    return _doc("CPF2149", f"Library {lib} was not found in the user library list.")


def object_not_found(obj: str, lib: str, typ: str) -> Message:
    return _doc("CPF2208", f"Object {obj} in library {lib} type {typ} not found.")


def not_authorized_to_object(obj: str, lib: str, typ: str) -> Message:
    return _doc("CPF2207", f"Not authorized to use object {obj} in library {lib} type {typ}.")


def not_authorized_to_give(obj: str, lib: str, typ: str) -> Message:
    return _doc("CPF2223", f"Not authorized to give authority to object {obj} in {lib} type {typ}.")


def not_authorized_to_revoke(obj: str, lib: str, typ: str) -> Message:
    return _doc("CPF2224", f"Not authorized to revoke authority for object {obj} in {lib} type {typ}.")


def exclude_with_another() -> Message:
    return _doc("CPF2290", "*EXCLUDE cannot be specified with another authority.")


def autl_only_for_public() -> Message:
    return _doc("CPF22A0", "Authority of *AUTL is allowed only with USER(*PUBLIC).")


def exclude_not_revocable_from_public() -> Message:
    return _doc("CPF22A4", "*EXCLUDE cannot be revoked from *PUBLIC.")


def not_secured_by_autl(obj: str, lib: str, typ: str, autl: str) -> Message:
    return _doc("CPF22A5", f"Object {obj} in {lib} type {typ} not secured by authorization list {autl}.")


def autl_not_found(name: str) -> Message:
    return _doc("CPF2283", f"Authorization list {name} does not exist.")


def authority_not_changed(obj: str, lib: str, typ: str, user: str) -> Message:
    return _doc("CPF2273", f"Authority may not have been changed for object {obj} in {lib} type {typ} for user {user}.")


# Command line problems. No ID checked for these yet.

def syntax(text: str) -> Message:
    return Message("", text, NO_ID)
