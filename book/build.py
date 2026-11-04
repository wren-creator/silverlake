#!/usr/bin/env python3
"""Build Silverlake 101 as an EPUB 3 file: the free training syllabus that ships with this repo, not a Gumroad title.

Usage:  python3 build.py [output.epub]

It scans OEBPS/chapters/*.xhtml in name order, so a chapter is in the book the moment its file exists and nothing
points at a file that is missing. It writes OEBPS/content.opf and OEBPS/nav.xhtml, checks every chapter is well formed
XML, scans the text for a hyphen or em dash used as a spacing device, and zips the result with the mimetype file first
and uncompressed, as the EPUB spec requires.

Cover: put a JPEG at OEBPS/assets/cover.jpg and it is picked up. Without one the book builds with no cover.
Exit status is 1 if any check fails, and no epub is written.
"""

from __future__ import annotations

import re
import sys
import xml.dom.minidom
import zipfile
from datetime import datetime, timezone
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OEBPS = ROOT / "OEBPS"
TITLE = "Silverlake 101: A Hands-On Training Syllabus for the Silverlake IBM i Security Range"
AUTHOR = "Britley Hoff"
UID = "urn:uuid:7c1a9914-3656-469f-8845-379bcf705601"
DEFAULT_OUT = ROOT.parent / "silverlake-101.epub"

# A spacing dash is " - ", " -- " or an em or en dash. A hyphen inside a word is fine, and so is text inside <pre> or
# <code>, which quotes the range's own screens and messages word for word.
SPACING_DASH = re.compile(r"\s-{1,2}\s|[—–]")
PROTECTED = re.compile(r"<(pre|code)\b.*?</\1>", re.S | re.I)
TAGS = re.compile(r"<[^>]+>")


def chapters() -> list[Path]:
    return sorted((OEBPS / "chapters").glob("*.xhtml"))


def title_of(path: Path) -> str:
    m = re.search(r"<title>(.*?)</title>", path.read_text(encoding="utf-8"), re.S)
    return m.group(1).strip() if m else path.stem


def check(paths: list[Path]) -> list[str]:
    problems = []
    for p in paths:
        text = p.read_text(encoding="utf-8")
        try:
            xml.dom.minidom.parseString(text.encode("utf-8"))
        except Exception as exc:                                  # a parse error says where
            problems.append(f"{p.name}: not well formed: {exc}")
            continue
        prose = TAGS.sub(" ", PROTECTED.sub(" ", text))
        for m in SPACING_DASH.finditer(prose):
            around = " ".join(prose[max(0, m.start() - 30):m.end() + 30].split())
            problems.append(f"{p.name}: dash used as punctuation near '{around}'")
    return problems


def write_nav(paths: list[Path]) -> None:
    items = "\n".join(f'<li><a href="chapters/{p.name}">{title_of(p)}</a></li>' for p in paths)
    (OEBPS / "nav.xhtml").write_text(f"""<?xml version='1.0' encoding='utf-8'?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
<head><meta charset="utf-8"/><title>Table of Contents</title><link rel="stylesheet" type="text/css" href="styles.css"/></head>
<body>
<nav epub:type="toc" id="toc">
<h1>Table of Contents</h1>
<ol>
{items}
</ol>
</nav>
</body>
</html>
""", encoding="utf-8")


def write_opf(paths: list[Path]) -> None:
    cover = (OEBPS / "assets" / "cover.jpg").exists()
    manifest = [f'<item id="chap{i:02d}" href="chapters/{p.name}" media-type="application/xhtml+xml"/>'
                for i, p in enumerate(paths)]
    manifest += ['<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>',
                 '<item id="css" href="styles.css" media-type="text/css"/>']
    if cover:
        manifest.append('<item id="cover-img" href="assets/cover.jpg" media-type="image/jpeg" properties="cover-image"/>')
    spine = "\n".join(f'<itemref idref="chap{i:02d}"/>' for i in range(len(paths)))
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    (OEBPS / "content.opf").write_text(f"""<?xml version='1.0' encoding='utf-8'?>
<package xmlns="http://www.idpf.org/2007/opf" unique-identifier="uid" version="3.0">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title id="title">{escape(TITLE)}</dc:title>
    <dc:creator id="creator">{AUTHOR}</dc:creator>
    <dc:identifier id="uid">{UID}</dc:identifier>
    <dc:language>en</dc:language>
    <meta refines="#title" property="title-type">main</meta>
    <meta refines="#creator" property="role" scheme="marc:relators">aut</meta>
    <meta property="dcterms:modified">{now}</meta>
  </metadata>
  <manifest>
    {chr(10).join("    " + m for m in manifest).strip()}
  </manifest>
  <spine>
{spine}
  </spine>
  <guide>
    <reference type="toc" title="Table of Contents" href="nav.xhtml"/>
  </guide>
</package>
""", encoding="utf-8")


def zip_epub(out: Path) -> None:
    if out.exists():
        out.unlink()
    with zipfile.ZipFile(out, "w") as z:
        z.writestr(zipfile.ZipInfo("mimetype"), (ROOT / "mimetype").read_bytes(), compress_type=zipfile.ZIP_STORED)
        for folder in ("META-INF", "OEBPS"):
            for f in sorted((ROOT / folder).rglob("*")):
                if f.is_file() and f.name != ".DS_Store":
                    z.write(f, f.relative_to(ROOT).as_posix(), compress_type=zipfile.ZIP_DEFLATED)


def main() -> int:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUT
    paths = chapters()
    if not paths:
        print("no chapters in OEBPS/chapters/", file=sys.stderr)
        return 1
    problems = check(paths)
    if problems:
        print("\n".join(problems), file=sys.stderr)
        print(f"{len(problems)} problem(s), nothing built", file=sys.stderr)
        return 1
    write_nav(paths)
    write_opf(paths)
    zip_epub(out)
    words = sum(len(TAGS.sub(" ", p.read_text(encoding="utf-8")).split()) for p in paths)
    print(f"built {out} with {len(paths)} chapter(s), about {words} words"
          + ("" if (OEBPS / "assets" / "cover.jpg").exists() else ", no cover"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
