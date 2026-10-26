"""Message IDs and our own wording for them. Each carries where its ID came from,
so a message we only believe in is never presented as one we confirmed."""

from dataclasses import dataclass

VERIFIED = "seen on a real IBM i"
RECALLED = "from the earlier web3270 mock, not yet confirmed on a real system"


@dataclass(frozen=True)
class Message:
    id: str
    text: str
    source: str

    def line(self) -> str:
        return f"{self.id} - {self.text}"


def user_not_found(user: str) -> Message:
    return Message("CPF1120", f"User {user} does not exist.", VERIFIED)


def password_not_correct(user: str) -> Message:
    return Message("CPF1107", "Password not correct for user profile.", RECALLED)


def no_password(user: str) -> Message:
    return Message("CPF1118", f"No password associated with user {user}.", RECALLED)


def cannot_sign_on(user: str) -> Message:
    return Message("CPF1394", f"User profile {user} cannot sign on.", RECALLED)
