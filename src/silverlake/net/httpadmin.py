"""The IBM i HTTP Server Administration console, the ADMIN instance a real system serves on 2001.

Signing in is checked against the profile store, so a password that works at the 5250 sign-on works here, and
failed attempts count against the profile the same way. Any enabled profile gets in, which is what the
published vector for the bug in this class assumes (a low privilege account).

The deliberate flaw is a class of bug, not a copy of one: IBM has not published the vulnerable parameter of
CVE-2026-96119, so this does not reproduce it. The server's description field is put into a page that evaluates
SSI style directives, <!--#exec cmd="..." -->, without neutralising them, and the command runs as QTMHHTTP,
not as the person signed in. Nothing real runs: the command goes to Silverlake's own dispatcher, in this
process, and answers from the simulator's objects. Once the fix (a PTF recorded on QHTTPSVR/QZHBADMIN) is
installed the field is escaped and never evaluated, and /HTTPAdmin/about lists the fix.

`handle` is a pure function of a request and the store, so tests need no sockets."""

from __future__ import annotations

import base64
import binascii
import html
import re
from dataclasses import dataclass, field
from urllib.parse import parse_qsl

from ..system.profiles import ProfileStore
from . import textview

SERVER_HEADER = "IBM HTTP Server for i"
REALM = "IBM i HTTP Server Administration"
MAX_BODY = 8 * 1024
RUN_AS = "QTMHHTTP"
PTF_KEY = ("QHTTPSVR", "QZHBADMIN", "*PGM")
OS_LEVEL = "V7R4M0"
PTFS = {"V7R3M0": "SJ11641", "V7R4M0": "SJ11643", "V7R5M0": "SJ11644", "V7R6M0": "SJ11645"}
DIRECTIVE = re.compile(r'<!--#exec\s+cmd="([^"]*)"\s*-->', re.IGNORECASE)


@dataclass
class Request:
    method: str = "GET"
    url: str = "/"
    headers: dict[str, str] = field(default_factory=dict)      # names lower case
    body: str = ""


@dataclass
class Response:
    status: int
    headers: dict[str, str]
    body: str


@dataclass
class State:
    """What the console keeps in memory: the server instances. A restart puts the three seeded ones back."""
    servers: list[dict] = field(default_factory=lambda: [
        {"name": "ADMIN", "status": "Running", "description": "HTTP Server Administration instance"},
        {"name": "APACHEDFT", "status": "Stopped", "description": "Default HTTP server instance"},
        {"name": "MYAPP", "status": "Running", "description": "Payroll web front end"},
    ])


def fix_installed(store: ProfileStore) -> str | None:
    """The PTF on the console, or None when the fix is not installed."""
    obj = store.objects.get(PTF_KEY)
    ptf = obj.data.get("ptf", "*NONE") if obj else "*NONE"
    return None if ptf == "*NONE" else ptf


def _esc(s: object) -> str:
    return html.escape(str(s), quote=True)


def _reply(status: int, body: str = "", **extra: str) -> Response:
    return Response(status, {"Server": SERVER_HEADER, "Content-Type": "text/html; charset=utf-8", **extra}, body)


def _page(store: ProfileStore, title: str, body: str) -> str:
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>{_esc(title)}</title></head><body>
<header><b>IBM Web Administration for i</b> &nbsp; {_esc(OS_LEVEL)}</header>
<nav><a href="/HTTPAdmin">Home</a> <a href="/HTTPAdmin/servers">Manage</a> <a href="/HTTPAdmin/create">Create HTTP Server</a> <a href="/HTTPAdmin/about">About</a></nav>
<h2>{_esc(title)}</h2>
{body}
<footer>IBM i {_esc(OS_LEVEL)} &middot; {_esc(SERVER_HEADER)}</footer>
</body></html>"""


def _basic(header: str | None) -> tuple[str, str] | None:
    m = re.fullmatch(r"Basic\s+([A-Za-z0-9+/=]+)", header or "")
    if not m:
        return None
    try:
        decoded = base64.b64decode(m.group(1), validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError):
        return None
    user, sep, password = decoded.partition(":")
    return (user.upper(), password) if sep else None


def _description(store: ProfileStore, raw: str) -> str:
    if fix_installed(store):
        return _esc(raw)
    runner = store.get(RUN_AS)

    def run(m: re.Match) -> str:
        if runner is None:
            return "CPF2204 User profile QTMHHTTP not found."
        return textview.run(store, runner, m.group(1))

    # Unfixed: evaluate first, then send the result on as markup, escaped on neither side.
    return DIRECTIVE.sub(run, raw)


def handle(req: Request, store: ProfileStore, state: State) -> Response:
    url = req.url.split("?", 1)[0]
    method = req.method.upper()
    if url in ("", "/"):
        return _reply(302, "", Location="/HTTPAdmin")
    if not url.startswith("/HTTPAdmin"):
        return _reply(404, _page(store, "Not found", "<p>The requested page was not found.</p>"))

    cred = _basic(req.headers.get("authorization"))
    result = store.check_signon(*cred) if cred else None
    if result is None or result.profile is None:
        return _reply(401, _page(store, "Authorization required", "<p>Sign in with an IBM i user profile.</p>"),
                      **{"WWW-Authenticate": f'Basic realm="{REALM}"'})
    user = result.profile.name

    if url.rstrip("/") == "/HTTPAdmin":
        return _reply(200, _page(store, "Welcome", f"<p>Signed in as <b>{_esc(user)}</b>.</p>"))
    if url == "/HTTPAdmin/about":
        ptf = fix_installed(store)
        return _reply(200, _page(store, "About", "<table>"
                                 "<tr><th>Product</th><td>5770-DG1 IBM HTTP Server for i</td></tr>"
                                 f"<tr><th>OS release</th><td>{_esc(OS_LEVEL)}</td></tr>"
                                 f"<tr><th>HTTP Server Admin fix</th><td>{_esc(ptf) if ptf else 'not installed'}</td></tr>"
                                 "</table>"))
    if url == "/HTTPAdmin/servers":
        if method == "POST":
            return _create(req, store, state)
        rows = "\n".join(f"<tr><td>{_esc(s['name'])}</td><td>{_esc(s['status'])}</td>"
                         f"<td>{_description(store, s['description'])}</td></tr>" for s in state.servers)
        return _reply(200, _page(store, "HTTP servers",
                                 f"<table><tr><th>Name</th><th>Status</th><th>Description</th></tr>\n{rows}</table>"))
    if url == "/HTTPAdmin/create":
        return _reply(200, _page(store, "Create HTTP Server",
                                 '<form method="POST" action="/HTTPAdmin/servers">'
                                 '<p>Server name <input name="name" maxlength="10"></p>'
                                 '<p>Description <input name="description" size="60"></p>'
                                 '<p><button type="submit">Finish</button></p></form>'))
    return _reply(404, _page(store, "Not found", "<p>The requested page was not found.</p>"))


def _create(req: Request, store: ProfileStore, state: State) -> Response:
    form = dict(parse_qsl(req.body, keep_blank_values=True))
    name = form.get("name", "").upper()
    if not re.fullmatch(r"[A-Z][A-Z0-9_]{0,9}", name):
        return _reply(400, _page(store, "Create HTTP Server", "<p>Server name must be 1 to 10 characters, "
                                 "letters, digits or underscore, starting with a letter.</p>"))
    if any(s["name"] == name for s in state.servers):
        return _reply(409, _page(store, "Create HTTP Server", f"<p>HTTP server {_esc(name)} already exists.</p>"))
    state.servers.append({"name": name, "status": "Stopped", "description": form.get("description", "")})
    return _reply(302, "", Location="/HTTPAdmin/servers")
