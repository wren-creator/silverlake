"""A virtual IFS: the directories and stream files PASE sees, kept in the store and saved with it.

Nothing here touches the host. A node is data (kind, owner, permissions, text), `/QSYS.LIB` is not stored but
mapped onto the library and object store the rest of Silverlake already has, and reading a file never reads a
file.

Permissions are the IBM i model reduced to what teaching needs: *ALLOBJ gets everything, the owner gets the
owner's bits, a profile with a private entry gets that entry, and everyone else gets the public bits (`r`, `w`,
`x`; on a directory `r` lists, `w` adds and removes, `x` searches). Every directory on the way to a node needs
`x` for the profile, which is IBM's own rule for paths. Not modeled: the group bits (the long listing shows the
public bits there), authorization lists, and adopted authority, which the IFS is documented not to honor.

What is unconfirmed on a real system is listed in docs/pase.md. That includes the default permissions of the
seeded directories, which were chosen to be plausible, not read off a machine."""

from __future__ import annotations

import posixpath
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from .authority import Auth, SpecialAuthority
from .profiles import Profile, ProfileStore

SEED = Path(__file__).resolve().parent.parent / "data" / "ifs.toml"
QSYS = "/QSYS.LIB"
STAMP = "Oct 26 09:00"
MODES = frozenset("rwx")


@dataclass
class Node:
    path: str
    kind: str                                   # "dir" or "file"
    owner: str = "QSYS"
    owner_mode: str = "rwx"
    public: str = "r-x"
    private: dict[str, str] = field(default_factory=dict)      # profile -> mode
    content: str = ""                           # files only

    @property
    def is_dir(self) -> bool:
        return self.kind == "dir"


@dataclass
class Entry:
    """What a lookup finds, whether it is a stored node or a mapped library object."""
    path: str
    kind: str
    owner: str
    mode: str                                   # what the asking profile may do: a subset of "rwx"
    owner_mode: str
    public: str
    size: int
    text: str = ""

    @property
    def is_dir(self) -> bool:
        return self.kind == "dir"


class IfsError(Exception):
    """kind is one of ENOENT, EACCES, ENOTDIR, EISDIR."""

    def __init__(self, kind: str, path: str) -> None:
        super().__init__(f"{kind}: {path}")
        self.kind, self.path = kind, path


# -- the seed and the saved form -------------------------------------------------------------------------------

def _bits(value: str) -> str:
    return "".join(c if c in value else "-" for c in "rwx")


def load_seed(path: Path | None = None) -> dict[str, Node]:
    from .. import flags                          # imported late: flags reaches back into the system layer
    raw = tomllib.loads(flags.fill((path or SEED).read_text()))
    nodes = {}
    for row in raw.get("node", []):
        n = Node(row["path"], row.get("kind", "dir"), row.get("owner", "QSYS"), _bits(row.get("owner_mode", "rwx")),
                 _bits(row.get("public", "r-x")), {k.upper(): _bits(v) for k, v in row.get("private", {}).items()},
                 row.get("content", ""))
        nodes[n.path] = n
    return nodes


def to_rows(nodes: dict[str, Node]) -> list[dict]:
    return [{"path": n.path, "kind": n.kind, "owner": n.owner, "owner_mode": n.owner_mode, "public": n.public,
             "private": dict(n.private), "content": n.content} for n in sorted(nodes.values(), key=lambda n: n.path)]


def from_rows(rows: list[dict]) -> dict[str, Node]:
    return {r["path"]: Node(r["path"], r["kind"], r["owner"], r["owner_mode"], r["public"], dict(r["private"]),
                            r["content"]) for r in rows}


# -- paths -----------------------------------------------------------------------------------------------------

def normalize(path: str, cwd: str = "/", home: str = "/") -> str:
    """An absolute path with `.`, `..`, `//` and a leading `~` dealt with."""
    if path == "~" or path.startswith("~/"):
        path = home + path[1:]
    if not path.startswith("/"):
        path = cwd.rstrip("/") + "/" + path
    out = posixpath.normpath(path)
    return "/" + out.lstrip("/") if out.startswith("//") else out


def home_of(profile: Profile) -> str:
    return f"/home/{profile.name}"


def uid_of(store: ProfileStore, profile: Profile) -> int:
    """QSECOFR is 0. Everyone else is numbered from 500 in the order the profiles were made. A real system
    assigns the UID when the profile is created (UID(*GEN)); how it numbers them is not confirmed here."""
    if profile.name == "QSECOFR":
        return 0
    return 500 + list(store.profiles).index(profile.name)


# -- who may do what -------------------------------------------------------------------------------------------

def _all_object(store: ProfileStore, actor: Profile) -> bool:
    return SpecialAuthority.ALLOBJ in store.special_authorities(actor)


def mode_for(store: ProfileStore, actor: Profile, node: Node) -> str:
    if _all_object(store, actor):
        return "rwx"
    if actor.name == node.owner:
        return node.owner_mode.replace("-", "")
    if actor.name in node.private:
        return node.private[actor.name].replace("-", "")
    return node.public.replace("-", "")


def _auth_mode(auth: Auth) -> str:
    return ("r" if Auth.READ in auth else "") + ("w" if (Auth.ADD in auth or Auth.UPD in auth) else "") + \
           ("x" if Auth.EXECUTE in auth else "")


# -- /QSYS.LIB, mapped onto the object store -------------------------------------------------------------------

def _qsys_parts(path: str) -> list[str]:
    return [p for p in path[len(QSYS):].split("/") if p]


def _split_object(name: str) -> tuple[str, str]:
    base, _, typ = name.rpartition(".")
    return (base.upper(), "*" + typ.upper()) if base else (name.upper(), "")


def _qsys_entry(store: ProfileStore, actor: Profile, path: str) -> Entry:
    from . import dbfiles, objects
    parts = _qsys_parts(path)
    if not parts:
        return Entry(QSYS, "dir", "QSYS", "rx", "rwx", "r-x", 4096)
    lib_name, typ = _split_object(parts[0])
    lib = store.find_library(lib_name) if typ == "*LIB" else None
    if lib is None:
        raise IfsError("ENOENT", path)
    lib_mode = "rwx" if _all_object(store, actor) else _auth_mode(objects.authority_to_library(store, actor, lib))
    if len(parts) == 1:
        return Entry(path, "dir", lib.owner, lib_mode, "rwx", "r-x", 4096)
    if len(parts) > 2:
        raise IfsError("ENOTDIR", path)             # an object is a file, nothing sits below it
    if "x" not in lib_mode:
        raise IfsError("EACCES", path)
    name, otype = _split_object(parts[1])
    obj = store.objects.get((lib.name, name, otype))
    if obj is None:
        raise IfsError("ENOENT", path)
    got = "rwx" if _all_object(store, actor) else _auth_mode(store.authority_to_object(actor, obj))
    text = ""
    if dbfiles.is_data_file(obj):
        pf = dbfiles.layout(obj)
        text = "".join(dbfiles.record_text(pf, r) + "\n" for r in obj.data.get("records", []))
    return Entry(path, "file", obj.owner, got, "rwx", "---", len(text), text)


def _qsys_children(store: ProfileStore, actor: Profile, path: str) -> list[str]:
    parts = _qsys_parts(path)
    allobj = _all_object(store, actor)
    if not parts:
        return sorted(f"{o.name}.LIB" for o in store.objects.values()
                      if o.type == "*LIB" and o.library == "QSYS"
                      and (allobj or _try(lambda: _qsys_entry(store, actor, f"{QSYS}/{o.name}.LIB"))))
    lib_name, _ = _split_object(parts[0])
    return sorted(f"{o.name}.{o.type[1:]}" for o in store.objects.values()
                  if o.library == lib_name and o.type != "*LIB"
                  and (allobj or store.authority_to_object(actor, o) != Auth.NONE))


def _try(fn) -> bool:
    try:
        fn()
        return True
    except IfsError:
        return False


# -- lookups ---------------------------------------------------------------------------------------------------

def _entry_of(store: ProfileStore, actor: Profile, node: Node) -> Entry:
    return Entry(node.path, node.kind, node.owner, mode_for(store, actor, node), node.owner_mode, node.public,
                 4096 if node.is_dir else len(node.content), node.content)


def lookup(store: ProfileStore, actor: Profile, path: str) -> Entry:
    """The entry at an absolute path, or an IfsError. Every directory above it needs `x`."""
    if path == "/":
        return _entry_of(store, actor, store.ifs["/"])
    walked = ""
    for part in [p for p in path.split("/") if p][:-1]:
        walked += "/" + part
        if walked == QSYS or walked.startswith(QSYS + "/"):
            break
        node = store.ifs.get(walked)
        if node is None:
            raise IfsError("ENOENT", path)
        if not node.is_dir:
            raise IfsError("ENOTDIR", path)
        if "x" not in mode_for(store, actor, node):
            raise IfsError("EACCES", path)
    root = store.ifs.get("/")
    if root is not None and "x" not in mode_for(store, actor, root):
        raise IfsError("EACCES", path)
    if path == QSYS or path.startswith(QSYS + "/"):
        return _qsys_entry(store, actor, path)
    node = store.ifs.get(path)
    if node is None:
        raise IfsError("ENOENT", path)
    return _entry_of(store, actor, node)


def listdir(store: ProfileStore, actor: Profile, path: str) -> list[Entry]:
    entry = lookup(store, actor, path)
    if not entry.is_dir:
        raise IfsError("ENOTDIR", path)
    if "r" not in entry.mode:
        raise IfsError("EACCES", path)
    out = []
    if path == QSYS or path.startswith(QSYS + "/"):
        for name in _qsys_children(store, actor, path):
            child = f"{path.rstrip('/')}/{name}"
            try:
                out.append(_qsys_entry(store, actor, child))
            except IfsError:
                out.append(Entry(child, "file", "QSYS", "", "rwx", "---", 0))
        return out
    prefix = path.rstrip("/") + "/"
    for p, node in sorted(store.ifs.items()):
        if p != path and p.startswith(prefix) and "/" not in p[len(prefix):]:
            out.append(_entry_of(store, actor, node))
    if path == "/":
        out.append(Entry(QSYS, "dir", "QSYS", "rx", "rwx", "r-x", 4096))
    return sorted(out, key=lambda e: e.path)


def read(store: ProfileStore, actor: Profile, path: str) -> str:
    entry = lookup(store, actor, path)
    if entry.is_dir:
        raise IfsError("EISDIR", path)
    if "r" not in entry.mode:
        raise IfsError("EACCES", path)
    return entry.text


def perms(entry: Entry) -> str:
    """The ten character permission string of a long listing. The group bits repeat the public ones."""
    def bits(m: str) -> str:
        return "".join(c if c in m else "-" for c in "rwx")
    return ("d" if entry.is_dir else "-") + bits(entry.owner_mode) + bits(entry.public) + bits(entry.public)


# -- writing ---------------------------------------------------------------------------------------------------
# Every change goes through the same walk as a read (`x` on each directory above), then asks the parent for `w`.
# /QSYS.LIB is never written from here: its objects are made and changed by CL, with CL's own rules.

def _parent(store: ProfileStore, actor: Profile, path: str) -> tuple[str, Entry]:
    if path == "/" or path == QSYS or path.startswith(QSYS + "/"):
        raise IfsError("EACCES", path)
    parent = posixpath.dirname(path) or "/"
    entry = lookup(store, actor, parent)
    if not entry.is_dir:
        raise IfsError("ENOTDIR", path)
    if "w" not in entry.mode or "x" not in entry.mode:
        raise IfsError("EACCES", path)
    return parent, entry


def make(store: ProfileStore, actor: Profile, path: str, kind: str, content: str = "") -> Node:
    """A new directory or file owned by the actor. A new directory is rwx for the owner and r-x for everyone;
    a file is rw- for the owner and r-- for everyone (a umask of 022)."""
    _parent(store, actor, path)
    if path in store.ifs:
        raise IfsError("EEXIST", path)
    node = Node(path, kind, actor.name, "rwx" if kind == "dir" else "rw-", "r-x" if kind == "dir" else "r--",
                {}, content)
    store.ifs[path] = node
    store.on_change()
    return node


def write(store: ProfileStore, actor: Profile, path: str, text: str, append: bool = False) -> None:
    """Replace or extend a stream file, making it if it is not there (what `>` and `>>` do)."""
    if path not in store.ifs:
        make(store, actor, path, "file", text)
        return
    entry = lookup(store, actor, path)
    if entry.is_dir:
        raise IfsError("EISDIR", path)
    if "w" not in entry.mode:
        raise IfsError("EACCES", path)
    node = store.ifs[path]
    node.content = node.content + text if append else text
    store.on_change()


def remove(store: ProfileStore, actor: Profile, path: str, recursive: bool = False) -> None:
    _parent(store, actor, path)
    entry = lookup(store, actor, path)
    node = store.ifs[path]
    below = [p for p in store.ifs if p.startswith(path.rstrip("/") + "/")]
    if node.is_dir and below and not recursive:
        raise IfsError("ENOTEMPTY", path)
    for p in below:
        del store.ifs[p]
    del store.ifs[path]
    store.on_change()


def copy(store: ProfileStore, actor: Profile, src: str, dst: str) -> None:
    text = read(store, actor, src)
    if dst in store.ifs and store.ifs[dst].is_dir:
        dst = dst.rstrip("/") + "/" + posixpath.basename(src)
    write(store, actor, dst, text)


def move(store: ProfileStore, actor: Profile, src: str, dst: str) -> None:
    _parent(store, actor, src)
    entry = lookup(store, actor, src)
    if dst in store.ifs and store.ifs[dst].is_dir:
        dst = dst.rstrip("/") + "/" + posixpath.basename(src)
    _parent(store, actor, dst)
    if dst in store.ifs:
        raise IfsError("EEXIST", dst)
    node = store.ifs[src]
    moved = {p: n for p, n in store.ifs.items() if p == src or p.startswith(src.rstrip("/") + "/")}
    for p, n in moved.items():
        del store.ifs[p]
        n.path = dst + p[len(src):]
        store.ifs[n.path] = n
    store.on_change()


def chmod(store: ProfileStore, actor: Profile, path: str, spec: str) -> None:
    """Octal (`644`, owner then group then public; the group digit is accepted and not kept) or `[ugoa][+-][rwx]`.
    Only the owner or *ALLOBJ may change a mode."""
    entry = lookup(store, actor, path)
    node = store.ifs.get(path)
    if node is None:
        raise IfsError("EACCES", path)                       # a library object is changed with CL
    if not (actor.name == node.owner or _all_object(store, actor)):
        raise IfsError("EPERM", path)
    if spec.isdigit() and len(spec) in (3, 4) and set(spec) <= set("01234567"):
        d = spec[-3:]
        node.owner_mode, node.public = _from_octal(int(d[0])), _from_octal(int(d[2]))
    else:
        m = re.fullmatch(r"([ugoa]*)([+-])([rwx]+)", spec)
        if not m:
            raise IfsError("EINVAL", spec)
        who, op, bits = m.group(1) or "a", m.group(2), m.group(3)
        for target, hit in (("owner_mode", "u"), ("public", "o")):
            if "a" in who or hit in who or (hit == "o" and "g" in who):
                cur = {c for c in getattr(node, target) if c in MODES}
                cur = cur | set(bits) if op == "+" else cur - set(bits)
                setattr(node, target, "".join(c if c in cur else "-" for c in "rwx"))
    store.on_change()


def _from_octal(n: int) -> str:
    return ("r" if n & 4 else "-") + ("w" if n & 2 else "-") + ("x" if n & 1 else "-")
