"""An IBM i style FTP server: the QTCP server a real system runs on 21, here on 2121 (21 is privileged).

Sign-on is the profile store's, and bad attempts count against the profile. It is clear text on the plain
port, as a real server is until a client asks for AUTH TLS (or uses the implicit TLS port). After sign-on it is the same authority as everywhere else:
a file is read only if the profile may read it, through the same finder DSPPFM uses.

Read only by construction: there is no STOR, DELE, MKD, RMD or RNFR. RCMD runs a CL command as the profile.

FtpSession is a pure state machine (a command line in, a Step out) so the tests need no sockets."""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field

from ..cl import commands
from ..cl.session import Session
from ..system import dbfiles
from ..system.authority import Auth
from ..system.profiles import Profile, ProfileStore
from ..system.rpg import _FAILED          # the words QCMDEXC treats as a failed command
from . import textview

log = logging.getLogger("silverlake.ftp")

OS_LEVEL = "V7R4M0"
EXIT_KEY = ("QUSRSYS", "FTPEXIT", "*PGM")
MAX_LINE = 1024
IDLE = 60.0
DATA_WAIT = 5.0
Reply = tuple[int, str]


@dataclass
class Step:
    replies: list[Reply] = field(default_factory=list)
    before: list[Reply] = field(default_factory=list)    # sent when the data connection opens
    data: str | None = None                               # then this text, then `after`
    after: list[Reply] = field(default_factory=list)
    pasv: bool = False
    close: bool = False
    upgrade: bool = False                                  # switch the control connection to TLS after the reply


def exit_program_registered(store: ProfileStore) -> bool:
    obj = store.objects.get(EXIT_KEY)
    return bool(obj) and obj.data.get("registered", "no") == "yes"


def _name(path: str) -> str:
    """LIB/FILE, or /QSYS.LIB/LIB.LIB/FILE.FILE (a member after it is ignored), as LIB/FILE."""
    parts = [p for p in path.strip().split("/") if p]
    if parts and parts[0].upper() == "QSYS.LIB":
        parts = [re.sub(r"\.(LIB|FILE)$", "", p, flags=re.IGNORECASE) for p in parts[1:3]]
    return "/".join(p.upper() for p in parts[:2])


class FtpSession:
    def __init__(self, store: ProfileStore) -> None:
        self.store = store
        self.user: str | None = None
        self.actor: Profile | None = None
        self.namefmt = 0
        self.cwd = "QGPL"
        self.job = Session()
        self.tls_available = False       # the listener has a certificate, so AUTH TLS can work
        self.secure = False              # the control connection is TLS now
        self.prot_private = False        # PROT P: data connections are TLS too

    def greeting(self) -> Step:
        return Step([(220, "QTCP at SILVERLAKE.\nConnection will close if idle more than 5 minutes.")])

    def handle(self, line: str) -> Step:
        m = re.fullmatch(r"(\S+)(?:\s+(.*))?", line.strip())
        if not m:
            return Step([(500, "Command not understood.")])
        cmd, arg = m.group(1).upper(), (m.group(2) or "").strip()
        fn = getattr(self, "_" + cmd.lower(), None) if cmd.isalpha() else None
        if fn is None:
            return Step([(500, "Command not understood.")])
        if self.actor is None and cmd not in ("USER", "PASS", "QUIT", "NOOP", "FEAT", "AUTH", "PBSZ", "PROT"):
            return Step([(530, "Log in with USER and PASS first.")])
        return fn(arg)

    # -- sign on ---------------------------------------------------------------------------------------------

    def _user(self, arg: str) -> Step:
        self.user, self.actor = arg, None
        return Step([(331, "Enter password.")])

    def _pass(self, arg: str) -> Step:
        if not self.user:
            return Step([(503, "Send USER first.")])
        result = self.store.check_signon(self.user, arg)
        if result.profile is None or result.must_change_password:
            return Step([(530, f"Log on attempt by user {self.user.upper()} rejected.")])
        self.actor = result.profile
        lib = self.actor.current_library
        self.cwd = lib if lib and not lib.startswith("*") else "QGPL"
        self.job = Session.for_profile(self.actor.current_library)
        return Step([(230, f"{self.actor.name} logged on.")])

    def _quit(self, arg: str) -> Step:
        return Step([(221, "Goodbye.")], close=True)

    def _noop(self, arg: str) -> Step:
        return Step([(200, "OK.")])

    def _auth(self, arg: str) -> Step:
        if not self.tls_available:
            return Step([(502, "AUTH is not supported, there is no certificate (run ./setup.sh).")])
        if arg.upper() not in ("TLS", "TLS-C", "TLS-P", "SSL"):
            return Step([(504, "Security mechanism not supported.")])
        if self.secure:
            return Step([(503, "Already secure.")])
        return Step([(234, "Security environment established - ready for negotiation.")], upgrade=True)

    def _pbsz(self, arg: str) -> Step:
        if not self.secure:
            return Step([(503, "Send AUTH TLS first.")])
        return Step([(200, "PBSZ=0")])

    def _prot(self, arg: str) -> Step:
        if not self.secure:
            return Step([(503, "Send AUTH TLS first.")])
        level = arg.upper()
        if level not in ("C", "P"):
            return Step([(504, "PROT C or P.")])
        self.prot_private = level == "P"
        return Step([(200, "Data channel protection level set to " + ("private." if self.prot_private else "clear."))])

    def _feat(self, arg: str) -> Step:
        tls = [" AUTH TLS", " PBSZ", " PROT"] if self.tls_available else []
        return Step([(211, "\n".join(["Extensions supported:", *tls, " NAMEFMT", "END"]))])

    # -- information -----------------------------------------------------------------------------------------

    def _syst(self, arg: str) -> Step:
        return Step([(215, f'OS/400 is the remote operating system. The TCP/IP version is "{OS_LEVEL}".')])

    def _type(self, arg: str) -> Step:
        return Step([(200, f"Representation type is {arg or 'A'}.")])

    def _help(self, arg: str) -> Step:
        return Step([(214, "The following commands are recognized:\nUSER PASS SYST FEAT PWD CWD NAMEFMT TYPE "
                           "PASV LIST NLST RETR RCMD HELP NOOP QUIT\nEnd of help.")])

    def _namefmt(self, arg: str) -> Step:
        if arg not in ("0", "1"):
            return Step([(501, "NAMEFMT 0 or 1.")])
        self.namefmt = int(arg)
        self.cwd = "QGPL" if self.namefmt == 0 else "/"
        return Step([(250, f'Now using naming format "{arg}".')])

    def _pwd(self, arg: str) -> Step:
        what = "current library" if self.namefmt == 0 else "current directory"
        return Step([(257, f'"{self.cwd}" is {what}.')])

    def _cwd(self, arg: str) -> Step:
        if self.namefmt == 1:
            if arg == "/":
                self.cwd = "/"
                return Step([(250, "Current directory changed to /.")])
            lib = _name(arg)
            if not lib or "/" in lib or not self.store.find_library(lib):
                return Step([(550, f"{arg} not found.")])
            self.cwd = f"/QSYS.LIB/{lib}.LIB"
            return Step([(250, f"Current directory changed to {self.cwd}.")])
        lib = arg.upper()
        if not self.store.find_library(lib):
            return Step([(550, f"Library {arg} not found.")])
        self.cwd = lib
        return Step([(250, f"Library {lib} is current library.")])

    def _pasv(self, arg: str) -> Step:
        return Step(pasv=True)

    # -- listing and getting files -----------------------------------------------------------------------------

    def _current_library(self) -> str | None:
        if self.namefmt == 0:
            return self.cwd
        return _name(self.cwd) if self.cwd.startswith("/QSYS.LIB/") else None

    def _turned_away(self) -> Step | None:
        """The request exit program, once registered, refuses profiles whose capabilities are limited. Without
        it FTP does not know what limited capability is: that is a rule of the 5250 menu, not of the server."""
        if exit_program_registered(self.store) and self.actor.limited_capabilities != "*NO":
            return Step([(550, "Request rejected by the FTP server exit program.")])
        return None

    def _list(self, arg: str) -> Step:
        if (no := self._turned_away()):
            return no
        if self.namefmt == 1 and self.cwd == "/":
            return self._data("QSYS.LIB\r\n")
        if self.namefmt == 1 and self.cwd == "/QSYS.LIB" or (self.namefmt == 1 and not self._current_library()):
            return self._data("".join(f"{k[1]}.LIB\r\n" for k in self.store.objects if k[0] == "QSYS" and k[2] == "*LIB"))
        lib = self._current_library()
        lib_obj = self.store.find_library(lib or "")
        if lib_obj is None:
            return Step([(550, f"Library {lib} not found.")])
        if Auth.READ & ~self.store.authority_to_object(self.actor, lib_obj) and not self._allobj():
            return Step([(550, f"Not authorized to library {lib}.")])
        rows = [f"{k[1]:<10} *FILE" for k, o in self.store.objects.items()
                if k[0] == lib and k[2] == "*FILE" and self._visible(o)]
        return self._data("".join(r + "\r\n" for r in rows))

    _nlst = _list

    def _visible(self, obj) -> bool:
        return self._allobj() or self.store.authority_to_object(self.actor, obj) != Auth.NONE

    def _allobj(self) -> bool:
        return dbfiles._allobj(self.store, self.actor)

    def _retr(self, arg: str) -> Step:
        if (no := self._turned_away()):
            return no
        spec = _name(arg) if self.namefmt == 1 else arg.upper().split(".")[0]
        if "/" not in spec and self._current_library():
            spec = f"{self._current_library()}/{spec}"
        obj, err = dbfiles.find_data_file(self.store, self.actor, self.job, spec)
        if err:
            return Step([(550, err.text)])
        pf = dbfiles.layout(obj)
        text = "".join(dbfiles.record_text(pf, r) + "\r\n" for r in obj.data.get("records", []))
        return self._data(text)

    def _rcmd(self, arg: str) -> Step:
        """`quote rcmd <CL command>`: run a CL command as the signed on profile, through Silverlake's own
        dispatcher in this process (never a shell). It is the profile's own authority and nothing more, and
        like the file commands it ignores limited capability until the exit program is registered."""
        if (no := self._turned_away()):
            return no
        if not arg:
            return Step([(501, "RCMD needs a CL command.")])
        outcome = commands.execute(self.store, self.actor, arg, self.job)
        text = textview.outcome_text(self.store, outcome, arg)
        said = outcome.message
        failed = bool(said and ((said.id and not said.id.startswith("CPC")) or any(w in said.text.lower() for w in _FAILED)))
        if failed:
            return Step([(550, text or "Command failed.")])
        return Step([(250, text or "Command successful.")])

    def _data(self, text: str) -> Step:
        return Step(before=[(150, "Opening data connection.")], data=text, after=[(226, "Transfer complete.")])


# -- the socket side ---------------------------------------------------------------------------------------------

def _wire(replies: list[Reply]) -> bytes:
    out = []
    for code, text in replies:
        lines = text.split("\n")
        out += [f"{code}{' ' if i == len(lines) - 1 else '-'}{l}" for i, l in enumerate(lines)]
    return ("\r\n".join(out) + "\r\n").encode("latin-1", "replace")


async def serve(host: str, port: int, store_of: Callable[[], ProfileStore], ssl_context=None,
                implicit: bool = False) -> asyncio.Server:
    """On the plain port, `ssl_context` lets AUTH TLS upgrade the connection in place. With `implicit` the
    connection is TLS from the first byte, as on the real TLS port (990)."""
    async def on_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        session = FtpSession(store_of())
        session.tls_available = ssl_context is not None
        session.secure = implicit
        data_server: asyncio.Server | None = None
        data_conn: asyncio.Future | None = None

        async def close_data() -> None:
            nonlocal data_server, data_conn
            if data_server is not None:
                data_server.close()
            data_server = data_conn = None

        def send(replies: list[Reply]) -> None:
            if replies:
                writer.write(_wire(replies))

        try:
            send(session.greeting().replies)
            await writer.drain()
            while True:
                raw = await asyncio.wait_for(reader.readline(), IDLE)
                if not raw:
                    break
                if len(raw) > MAX_LINE:
                    send([(500, "Line too long.")])
                    await writer.drain()
                    continue
                step = session.handle(raw.decode("latin-1"))
                if step.pasv:
                    await close_data()
                    loop = asyncio.get_running_loop()
                    data_conn = loop.create_future()

                    def accepted(r, w, fut=data_conn):
                        if not fut.done():
                            fut.set_result(w)
                        else:
                            w.close()
                    data_server = await asyncio.start_server(accepted, host, 0,
                                                             ssl=ssl_context if session.prot_private else None)
                    p = data_server.sockets[0].getsockname()[1]
                    send([(227, f"Entering Passive Mode (127,0,0,1,{p >> 8},{p & 255}).")])
                elif step.data is not None:
                    if data_conn is None:
                        send([(425, "Use PASV first.")])
                    else:
                        send(step.before)
                        await writer.drain()
                        try:
                            dw = await asyncio.wait_for(data_conn, DATA_WAIT)
                            dw.write(step.data.encode("latin-1", "replace"))
                            await dw.drain()
                            dw.close()
                            send(step.after)
                        except asyncio.TimeoutError:
                            send([(425, "Can't open data connection.")])
                        await close_data()
                else:
                    send(step.replies)
                await writer.drain()
                if step.upgrade:
                    await writer.start_tls(ssl_context)
                    session.secure = True
                if step.close:
                    break
        except (asyncio.TimeoutError, ConnectionError, asyncio.IncompleteReadError, asyncio.LimitOverrunError):
            pass
        except Exception:
            log.exception("ftp session failed")
        finally:
            await close_data()
            writer.close()

    return await asyncio.start_server(on_client, host, port, ssl=ssl_context if implicit else None)
