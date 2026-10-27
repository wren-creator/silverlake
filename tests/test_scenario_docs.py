"""The scenario docs are generated from the registry, so they have to be complete and current."""

import pytest

from silverlake import scenario_docs, scenarios


def test_every_scenario_has_all_its_doc_text():
    for sid, scn in scenarios.registry().items():
        assert scenario_docs.missing(scn) == [], sid


def test_the_committed_docs_match_the_registry():
    assert scenario_docs.main(["--check"]) == 0


def test_the_trainee_copy_has_no_fixes_and_the_instructor_copy_has_all_of_them():
    instructor, trainee = scenario_docs.render(True), scenario_docs.render(False)
    reg = scenarios.registry()
    assert instructor.count("**Fix:**") == len(reg)
    assert "**Fix:**" not in trainee and "scenario.sh set" not in trainee
    for scn in reg.values():
        assert scn.title in instructor and scn.title in trainee
        assert scn.doc["fix"] in instructor and scn.doc["fix"] not in trainee


def test_a_scenario_without_doc_text_stops_the_build():
    reg = scenarios.registry()
    reg["clerk-menu-escape"].doc = {}
    with pytest.raises(scenarios.ScenarioError, match="clerk-menu-escape"):
        scenario_docs.render(True, reg)
