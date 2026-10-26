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


# Command line problems. No ID checked for these yet.

def syntax(text: str) -> Message:
    return Message("", text, NO_ID)
