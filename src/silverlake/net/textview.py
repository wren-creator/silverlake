"""Plain text for what a command says, for the services that have no screen (the HTTP console, FTP).

A command can come back with a message, or with a view meant for a 5250 display. The views a network
service can show are the three that read well as lines; anything else says it needs a screen."""

from __future__ import annotations

from ..cl import commands
from ..cl.session import Session
from ..system.profiles import Profile, ProfileStore


def run(store: ProfileStore, actor: Profile, line: str) -> str:
    """Run one CL command as `actor`, in this process, through the same dispatcher as the 5250 side. It never
    reaches a shell. Returns the text the command produced."""
    outcome = commands.execute(store, actor, line, Session.for_profile(actor.current_library))
    return outcome_text(store, outcome, line)


def outcome_text(store: ProfileStore, outcome, line: str = "") -> str:
    if outcome.view:
        kind = outcome.view[0]
        if kind == "dspmsg":
            return "\n".join(f"{m.get('from') or '*SYSTEM':<10} {m.get('when', '')}  {m.get('text', '')}"
                             for m in outcome.view[1].data.get("messages", [])) or "No messages."
        if kind == "wrkusrprf":
            return "\n".join(f"{p.name:<10} {p.status:<10} {p.text}" for p in outcome.view[1])
        if kind == "dspusrprf":
            return "\n".join(f"{k} . . . : {v}" for k, v in store.describe(outcome.view[1]).items())
        name = (line.split() or ["command"])[0].upper()
        return f"CPD0030 {name} needs a screen and cannot run here."
    if outcome.signoff or outcome.go or outcome.cmdentry:
        return "CPD0030 That command needs a screen and cannot run here."
    if outcome.message is not None:
        text = outcome.message.text
        return f"{outcome.message.id} {text}".strip() if outcome.message.id else text
    return ""
