"""Turn the F4 prompt screens in `auth-prompts-*` captures into the table `screens/promptspecs.py`.

    python -m silverlake.oracle.promptspec captures/pub400/auth-prompts-*.json > src/silverlake/screens/promptspecs.py

Only layout comes out: title, rows, labels, keywords, columns, lengths, defaults, the bottom marker and the
key lines. The first screen after F4 for each command is the one read, so a second page (Roll Up) is not
part of this table. Rows are in the shape `screens/prompt.py` already uses:
(row, label as drawn, field name, field column, field length, default). A row with no field name is a label
only. The field name is the command's keyword, and "KW@" is the library part of a qualified name."""

from __future__ import annotations

import json
import re
import sys

_TITLE = re.compile(r"\((\w+)\)\s*$")
LABEL_COL, KEYWORD_COL = 1, 34


def _runs_by_row(snapshot: dict) -> dict[int, list[dict]]:
    rows: dict[int, list[dict]] = {}
    for run in snapshot["runs"]:
        rows.setdefault(run["row"], []).append(run)
    return rows


def extract(snapshot: dict, carry: tuple[str, int] = ("", 0)) -> tuple[str, dict] | None:
    """The command name and its layout, or None when the screen is not a prompt. `carry` is the keyword and how
    many of its fields were seen at the end of the page before, for a page that starts mid parameter."""
    runs = snapshot["runs"]
    if not runs or runs[0]["row"] != 0 or not (m := _TITLE.search(runs[0]["text"])):
        return None
    if not any("Type choices" in r["text"] for r in runs):
        # CHGPWD: the host draws the title and the keys and says there is nothing to prompt for.
        note = next((r["text"] for r in runs if r["row"] == 23 and "No parameters" in r["text"]), "")
        if not note:
            return None
        lead = len(runs[0]["text"]) - len(runs[0]["text"].lstrip())
        keys = tuple(r["text"] for r in runs if r["row"] in (21, 22))
        return m.group(1), {"title": (runs[0]["text"].strip(), runs[0]["col"] + lead), "rows": [], "bottom": "",
                            "keys": keys, "note": note, "odd": [], "end": ("", 0)}
    lead = len(runs[0]["text"]) - len(runs[0]["text"].lstrip())
    title = (runs[0]["text"].strip(), runs[0]["col"] + lead)
    fields = {(f["row"], f["col"]): f for f in snapshot["fields"]}
    rows: list[tuple] = []
    odd: list[str] = []
    current, count = carry                     # the keyword the next field belongs to, and fields seen under it
    for row, here in sorted(_runs_by_row(snapshot).items()):
        if row < 3 or row > 19:
            continue
        label = next((r for r in here if r["col"] == LABEL_COL), None)
        keyword = next((r for r in here if r["col"] == KEYWORD_COL), None)
        placed = [f for (fr, _), f in fields.items() if fr == row]
        if len(placed) > 1:
            odd.append(f"row {row} has {len(placed)} fields")
        field = placed[0] if placed else None
        if label is None:                      # a lone line like "+ for more values"
            for r in here:
                if field is None or r["col"] < field["col"]:
                    rows.append((row, " " * (r["col"] - LABEL_COL) + r["text"], "", 0, 0, ""))
            continue
        drawn = label["text"].rstrip()
        if keyword:
            drawn = drawn.ljust(KEYWORD_COL - LABEL_COL) + keyword["text"]
        if field is None:
            if keyword:
                current, count = keyword["text"], 0
            rows.append((row, drawn, "", 0, 0, ""))
            continue
        if keyword:
            name, current, count = keyword["text"], keyword["text"], 1
        else:                                  # the library of a qualified name is KW@, a later value KW@3, KW@4
            count += 1
            name = current if count == 1 else current + "@" + (str(count) if count > 2 else "")
        default = next((r["text"].strip() for r in here if r["col"] == field["col"]), "")
        rows.append((row, drawn, name, field["col"], field["length"], default))
        extra = [r["text"] for r in here if r is not label and r is not keyword
                 and not (r["col"] == field["col"] and r["text"].strip() == default)]
        if extra:
            odd.append(f"row {row} also has {extra}")
    tail = {r["row"]: r for r in runs if r["row"] >= 20}
    keys = []
    for row in (21, 22):
        if row in tail:
            text = tail[row]["text"]
            keys.append(text[1:] if tail[row]["col"] == 0 and text.startswith(" ") else text)
    bottom = tail[20]["text"].strip() if 20 in tail else ""
    return m.group(1), {"title": title, "rows": rows, "bottom": bottom, "keys": tuple(keys), "odd": odd, "end": (current, count)}


def extract_all(captures: list[dict]) -> dict[str, dict]:
    """The first prompt screen seen for each command, in the order the captures give them."""
    found: dict[str, dict] = {}
    for cap in captures:
        snaps = cap["snapshots"]
        for i, snap in enumerate(snaps):
            got = extract(snap)
            if not got:
                continue
            name, spec = got
            if name not in found:
                found[name] = {**spec, "pages": []}
            elif found[name]["pages"] or found[name]["bottom"] != "More...":
                continue
            # Roll Ups that paged: the same command, other rows, no complaint about a missing parameter.
            # The first prompt seen for a command is the one kept, so its pages are read once.
            if found[name]["pages"] or spec["bottom"] != "More...":
                continue
            cur, end, j = spec, spec["end"], i
            while cur["bottom"] == "More..." and j + 1 < len(snaps):
                nxt = extract(snaps[j + 1], end)
                if (not nxt or nxt[0] != name or nxt[1]["rows"] == cur["rows"]
                        or any(r["row"] == 23 for r in snaps[j + 1]["runs"])):
                    break
                found[name]["pages"].append((nxt[1]["rows"], nxt[1]["bottom"]))
                cur, end, j = nxt[1], nxt[1]["end"], j + 1
    return found


def render(found: dict[str, dict]) -> str:
    out = ['"""F4 prompt layouts captured from PUB400 (read only, `auth-prompts-*`). Generated by',
           '`python -m silverlake.oracle.promptspec`, so change that and run it again, not this file.',
           '',
           'Each entry: the title and its column, the rows as (row, label as drawn, field name, field column,',
           'field length, default), the marker on row 20 and the two key lines."""',
           '', 'from __future__ import annotations', '', 'SPECS: dict[str, dict] = {']
    for name in sorted(found):
        spec = found[name]
        out.append(f'    "{name}": {{"title": {spec["title"]!r}, "bottom": {spec["bottom"]!r},')
        out.append(f'        "keys": {spec["keys"]!r},')
        if spec.get("note"):
            out.append(f'        "note": {spec["note"]!r},')
        if spec["pages"]:
            out.append(f'        "pages": {spec["pages"]!r},')
        out.append('        "rows": [')
        out += [f"            {row!r}," for row in spec["rows"]]
        out.append("        ]},")
    out.append("}")
    return "\n".join(out) + "\n"


def main(paths: list[str]) -> int:
    found = extract_all([json.load(open(p)) for p in sorted(paths)])
    for name, spec in sorted(found.items()):
        for note in spec["odd"]:
            print(f"{name}: {note}", file=sys.stderr)
    sys.stdout.write(render(found))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
