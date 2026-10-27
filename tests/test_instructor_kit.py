"""The instructor kit names every lesson and only lessons that exist."""

import re
from pathlib import Path

from silverlake import scenarios

KIT = Path(__file__).resolve().parents[1] / "instructor"


def test_the_kit_has_its_files():
    names = {p.name for p in KIT.iterdir()} | {"slides/" + p.name for p in (KIT / "slides").iterdir()}
    assert {"agenda.md", "answer-key.md", "rubric.md", "setup-runbook.md"} <= names
    assert len([n for n in names if n.startswith("slides/session-")]) == 6


def test_the_answer_key_covers_every_lesson_and_invents_none():
    key = (KIT / "answer-key.md").read_text()
    rows = set(re.findall(r"^\| ([a-z]+(?:-[a-z]+)+) \|", key, re.M))
    assert rows == set(scenarios.registry())
