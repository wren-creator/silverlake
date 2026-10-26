"""Structural diff of two captures. By default only structure is compared:
where fields are, how long, their attributes, where text runs start and in what
attribute, the cursor, and which message IDs appear. Wording is ours to write,
so it is only compared when asked, and that comparison is for local use."""

FIELD_KEYS = ("row", "col", "length", "attr", "hidden", "monocase", "shift")
RUN_KEYS = ("row", "col", "attr")


def _fields(a: dict, b: dict, out: list[str]) -> None:
    fa, fb = a["fields"], b["fields"]
    if len(fa) != len(fb):
        out.append(f"input fields: {len(fa)} != {len(fb)}")
    for i, (x, y) in enumerate(zip(fa, fb)):
        for k in FIELD_KEYS:
            if x.get(k) != y.get(k):
                out.append(f"field[{i}].{k}: {x.get(k)} != {y.get(k)}")


def _runs(a: dict, b: dict, text: bool, out: list[str]) -> None:
    ra, rb = a["runs"], b["runs"]
    ka = [tuple(r[k] for k in RUN_KEYS) for r in ra]
    kb = [tuple(r[k] for k in RUN_KEYS) for r in rb]
    only_a = [k for k in ka if k not in kb]
    only_b = [k for k in kb if k not in ka]
    for k in only_a:
        out.append(f"run only in A: row={k[0]} col={k[1]} attr={k[2]}")
    for k in only_b:
        out.append(f"run only in B: row={k[0]} col={k[1]} attr={k[2]}")
    if text:
        by_pos_b = {tuple(r[k] for k in RUN_KEYS): r for r in rb}
        for r in ra:
            other = by_pos_b.get(tuple(r[k] for k in RUN_KEYS))
            if other and other["text"] != r["text"]:
                out.append(f"text at row={r['row']} col={r['col']}: {r['text']!r} != {other['text']!r}")


def diff_snapshots(a: dict, b: dict, text: bool = False, fields_only: bool = False) -> list[str]:
    out: list[str] = []
    if a["geometry"] != b["geometry"]:
        out.append(f"geometry: {a['geometry']} != {b['geometry']}")
    if a["cursor"] != b["cursor"]:
        out.append(f"cursor: {a['cursor']} != {b['cursor']}")
    _fields(a, b, out)
    if not fields_only:
        _runs(a, b, text, out)
    if a["message_ids"] != b["message_ids"]:
        out.append(f"message ids: {a['message_ids']} != {b['message_ids']}")
    return out


def diff_captures(a: dict, b: dict, text: bool = False, fields_only: bool = False) -> list[str]:
    """Differences between two capture files, prefixed with the screen index."""
    out: list[str] = []
    sa, sb = a["snapshots"], b["snapshots"]
    if len(sa) != len(sb):
        out.append(f"screens: {len(sa)} != {len(sb)}")
    for i, (x, y) in enumerate(zip(sa, sb)):
        out += [f"screen {i}: {d}" for d in diff_snapshots(x, y, text, fields_only)]
    return out
