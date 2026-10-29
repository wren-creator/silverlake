"""Turn the F4 prompt screens in `auth-prompts-*` captures into the table `screens/promptspecs.py`.

    python -m silverlake.oracle.promptspec captures/pub400/auth-pdm.json captures/pub400/auth-prompts-*.json captures/pub400/auth-f10-*.json captures/pub400/auth-f13-helpall.json > src/silverlake/screens/promptspecs.py

Only layout comes out: title, rows, labels, keywords, columns, lengths, defaults, the bottom marker and the
key lines. The first screen after F4 for each command is the one read, and a Roll Up that paged adds the
next page. Rows are in the shape `screens/prompt.py` already uses:
(row, label as drawn, field name, field column, field length, default). A row with no field name is a label
only. The field name is the command's keyword, and "KW@" is the library part of a qualified name."""

from __future__ import annotations

import json
import re
import sys

_TITLE = re.compile(r"\((\w+)\)\s*$")
LABEL_COL, KEYWORD_COL = 1, 34
REQUIRED_ATTR = "0x26"      # the host draws a required parameter brighter than the rest


# A change command (CHGPRF, CHGJOB) shows the current values of the profile it was captured with, and those are
# the host's own, not a default: the profile name, its current library, its text, its printer, the customized
# print text. They never go into the table. The ones that stand for the signed-on user become tokens that
# screens/prompt.py fills in; the rest become the usual IBM default.
SCRUB = {"WREN01": "{USER}", "WREN011": "{CURLIB}", "'Hoff,Britley'": "{TEXT}", "PRT01": "*WRKSTN",
         "PUB400SYS": "*LIBL"}
_BANNER = re.compile(r"^'-=\* .*pub400.*", re.I)


def scrub(default: str) -> str:
    return "*SAME" if _BANNER.match(default) else SCRUB.get(default, default)


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
                            "keys": keys, "note": note, "required": [], "odd": [], "end": ("", 0)}
    lead = len(runs[0]["text"]) - len(runs[0]["text"].lstrip())
    title = (runs[0]["text"].strip(), runs[0]["col"] + lead)
    fields = {(f["row"], f["col"]): f for f in snapshot["fields"]}
    rows: list[tuple] = []
    required: list[str] = []
    odd: list[str] = []
    current, count = carry                     # the keyword the next field belongs to, and fields seen under it
    by_row = _runs_by_row(snapshot)
    for f in snapshot["fields"]:                   # a field that is empty and has no label draws no run at all
        by_row.setdefault(f["row"], [])
    for row, here in sorted(by_row.items()):
        if row < 3 or row > 19:
            continue
        label = next((r for r in here if r["col"] == LABEL_COL), None)
        keyword = next((r for r in here if r["col"] == KEYWORD_COL), None)
        placed = [f for (fr, _), f in fields.items() if fr == row]
        if len(placed) > 1:
            odd.append(f"row {row} has {len(placed)} fields")
        field = placed[0] if placed else None
        if label is None and not here and field is not None:     # a later value of the keyword above: KW@, KW@3
            count += 1
            name = current + "@" + (str(count) if count > 2 else "")
            rows.append((row, "", name, field["col"], field["length"], ""))
            continue
        if label is None and all(r["col"] == 0 and r["text"] == "'" for r in here) and field is None:
            continue                           # the tail of a value that ran off the end of the row above
        if label is None:                      # a lone line like "+ for more values", which may carry a field
            before = len(rows)
            for r in here:
                if field is None or r["col"] < field["col"]:
                    rows.append((row, " " * (r["col"] - LABEL_COL) + r["text"], "", 0, 0, ""))
            if field is not None and len(rows) == before:     # a bare field, like the library under KW+: KW+@
                default = scrub(next((r["text"].strip() for r in here if r["col"] == field["col"]), ""))
                rows.append((row, "", current + "+@", field["col"], field["length"], default))
            elif field is not None and len(rows) > before:    # more values of the keyword above: KW+
                default = scrub(next((r["text"].strip() for r in here if r["col"] == field["col"]), ""))
                rows[-1] = (*rows[-1][:2], current + "+", field["col"], field["length"], default)
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
        shown = default
        default = scrub(default)
        rows.append((row, drawn, name, field["col"], field["length"], default))
        if field["attr"] == REQUIRED_ATTR:
            required.append(name)
        extra = [r["text"] for r in here if r is not label and r is not keyword
                 and not (r["col"] == field["col"] and r["text"].strip() == shown)]
        if extra:
            odd.append(f"row {row} also has {extra}")
    tail = {r["row"]: r for r in runs if r["row"] >= 20}
    keys = []
    for row in (21, 22):
        if row in tail:
            text = tail[row]["text"]
            keys.append(text[1:] if tail[row]["col"] == 0 and text.startswith(" ") else text)
    bottom = tail[20]["text"].strip() if 20 in tail else ""
    return m.group(1), {"title": title, "rows": rows, "bottom": bottom, "keys": tuple(keys), "required": required, "odd": odd,
                        "end": (current, count)}


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
                found[name]["required"] += nxt[1]["required"]
                cur, end, j = nxt[1], nxt[1]["end"], j + 1
    return found


def extract_f10(captures: list[dict]) -> dict[str, dict]:
    """What F10=Additional parameters shows, from the `auth-f10-*` captures: for each command a prompt screen that
    offers F10, then the screen F10 gave, then the pages Roll Up gave. The F10 view repeats the first page's rows
    and goes on to the rest, so it is kept whole as its own pages. A Roll Up that complained (a message on row 23)
    or showed the same rows did not page and ends the chain. Where several captures reach different depths for the
    same command, the longest chain wins."""
    found: dict[str, dict] = {}
    for cap in captures:
        snaps = cap["snapshots"]
        for i, snap in enumerate(snaps[:-1]):
            got = extract(snap)
            if not got or not any("F10=Additional" in k for k in got[1]["keys"]):
                continue
            name = got[0]
            first = extract(snaps[i + 1])
            if not first or first[0] != name or first[1]["keys"] == got[1]["keys"]:
                continue
            pages = [(first[1]["rows"], first[1]["bottom"])]
            required = list(first[1]["required"])
            cur, end, j = first[1], first[1]["end"], i + 1
            while cur["bottom"] == "More..." and j + 1 < len(snaps):
                nxt = extract(snaps[j + 1], end)
                if (not nxt or nxt[0] != name or nxt[1]["rows"] == cur["rows"]
                        or any(r["row"] == 23 for r in snaps[j + 1]["runs"])):
                    break
                pages.append((nxt[1]["rows"], nxt[1]["bottom"]))
                required += nxt[1]["required"]
                cur, end, j = nxt[1], nxt[1]["end"], j + 1
            if name not in found or len(pages) > len(found[name]["pages"]):
                found[name] = {"keys": first[1]["keys"], "pages": pages, "required": required}
    return found


def extract_help(captures: list[dict]) -> dict | None:
    """The F13 help ("How to use this display"), from an `auth-f13-helpall` capture. It is one text for every prompt,
    so one is kept: the screens that open with `Help` on row 0, in order, with the run of the same page that Roll Up
    past the end repeats dropped. Each page is its runs as (row, col, attribute, text), the message row left out, and
    the cursor is where the host put it (the hidden one character field on row 1)."""
    pages: list[tuple] = []
    cursor = None
    for cap in captures:
        for snap in cap["snapshots"]:
            runs = snap["runs"]
            if not runs or (runs[0]["row"], runs[0]["col"], runs[0]["text"]) != (0, 1, "Help"):
                continue
            page = tuple((r["row"], r["col"], int(r["attr"], 16), r["text"]) for r in runs if r["row"] < 23)
            if not pages or page != pages[-1]:
                pages.append(page)
            cursor = tuple(snap["cursor"])
    return {"cursor": cursor, "pages": pages} if pages else None


def render(found: dict[str, dict], more: dict[str, dict] | None = None, help_: dict | None = None) -> str:
    out = ['"""F4 prompt layouts captured from PUB400 (read only, `auth-prompts-*`). Generated by',
           '`python -m silverlake.oracle.promptspec`, so change that and run it again, not this file.',
           '',
           'Each entry: the title and its column, the rows as (row, label as drawn, field name, field column,',
           'field length, default), the marker on row 20 and the two key lines. "required" names the parameters',
           'the host draws brighter and will not run without. "pages" has the rows and marker of each page after',
           'the first, where Roll Up was captured. "note" is what the host says when there is nothing to prompt',
           'for.',
           '"more" is what F10=Additional parameters shows (`auth-f10-*`): its key lines and its pages,',
           'each (rows, marker), the first page repeating the prompt\'s rows. HELP, at the end, is the F13 help."""',
           '', 'from __future__ import annotations', '', 'SPECS: dict[str, dict] = {']
    for name in sorted(found):
        spec = found[name]
        out.append(f'    "{name}": {{"title": {spec["title"]!r}, "bottom": {spec["bottom"]!r},')
        out.append(f'        "keys": {spec["keys"]!r},')
        out.append(f'        "required": {tuple(spec["required"])!r},')
        if spec.get("note"):
            out.append(f'        "note": {spec["note"]!r},')
        if spec["pages"]:
            out.append(f'        "pages": {spec["pages"]!r},')
        if more and name in more:
            m = more[name]
            out.append(f'        "more": {{"keys": {m["keys"]!r}, "pages": {m["pages"]!r}}},')
        out.append('        "rows": [')
        out += [f"            {row!r}," for row in spec["rows"]]
        out.append("        ]},")
    out.append("}")
    if help_:
        out += ["", "# The F13 help, one text for every prompt (`auth-f13-helpall`): the cursor and each page as runs of",
                "# (row, col, attribute, text).", "HELP: dict = {", f'    "cursor": {help_["cursor"]!r},', '    "pages": [']
        for page in help_["pages"]:
            out.append("        (")
            out += [f"            {run!r}," for run in page]
            out.append("        ),")
        out += ["    ],", "}"]
    return "\n".join(out) + "\n"


def main(paths: list[str]) -> int:
    f10 = [p for p in paths if "auth-f10-" in p]
    helps = [p for p in paths if "auth-f13-helpall" in p]
    found = extract_all([json.load(open(p)) for p in sorted(set(paths) - set(f10) - set(helps))])
    more = extract_f10([json.load(open(p)) for p in sorted(f10)])
    for name, spec in sorted(found.items()):
        for note in spec["odd"]:
            print(f"{name}: {note}", file=sys.stderr)
    sys.stdout.write(render(found, more, extract_help([json.load(open(p)) for p in helps])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
