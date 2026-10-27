"""Commands are objects. Every CL command is a *CMD object in QSYS with an owner and
a public authority, and running it takes *USE to that object. That is how a site
decides who may run CRTLIB or CRTUSRPRF: it changes one object, and the command
line itself never has to know. A real basic profile on PUB400 was refused CRTLIB
with "Not authorized to command CRTLIB in library *LIBL." for exactly this reason.

The rule (*USE to the command object) is IBM i behavior but was not read on a
command page; the refusal wording was seen on a real system. The seed policy is
permissive: every command is public *USE. Take one away with RVKOBJAUT."""

from .authority import USE, SecuredObject

# Kept in step with the dispatcher in cl/commands.py; a test checks they match.
COMMAND_NAMES = (
    "CRTUSRPRF", "CHGUSRPRF", "DSPUSRPRF", "DLTUSRPRF", "WRKUSRPRF", "SIGNOFF",
    "CRTLIB", "DLTLIB", "DSPLIBL", "ADDLIBLE", "RMVLIBLE", "WRKLIB",
    "DSPOBJAUT", "GRTOBJAUT", "RVKOBJAUT",
    "GO", "CALL", "CHGPRF", "CHGPWD",
    "CRTAUTL", "DLTAUTL", "ADDAUTLE", "CHGAUTLE", "RMVAUTLE", "DSPAUTL", "WRKAUTL",
    "WRKOBJ", "WRKOBJOWN", "CHGOBJOWN", "RNMOBJ", "CHGOBJD",
    "WRKACTJOB", "DSPMSG", "SNDMSG", "CLRMSGQ", "CRTMSGQ", "CHGMSGQ", "DLTMSGQ", "WRKSPLF", "WRKOUTQ", "CRTOUTQ", "DLTOUTQ", "DSPSPLF", "DLTSPLF", "HLDSPLF", "RLSSPLF", "CHGSPLFA", "DSPJOBLOG", "WRKJOB", "DSPJOB", "HLDJOB", "RLSJOB", "ENDJOB", "CHGJOB", "DLTF", "DLTCMD", "DLTMNU", "DLTPGM", "EDTOBJAUT", "DSPOBJD", "DSPPGM",
    "CRTSRCPF", "CRTBNDRPG", "CRTPF", "CRTDSPF", "CRTPRTF", "STRPDM", "WRKMBRPDM", "WRKOBJPDM", "STRSEU", "OVRDBF", "DLTOVR",
)


def ensure_commands(store, names=COMMAND_NAMES) -> None:
    """Make sure every command has its object. Existing ones, with whatever
    authority someone gave them, are left alone."""
    for name in names:
        key = ("QSYS", name, "*CMD")
        if key not in store.objects:
            store.objects[key] = SecuredObject(name, "QSYS", public=USE, library="QSYS", type="*CMD",
                                               text="Command")
