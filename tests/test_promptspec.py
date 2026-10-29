from silverlake.oracle import promptspec, scenario
from silverlake.screens.promptspecs import SPECS


def _run(row, col, text, attr="0x20"):
    return {"row": row, "col": col, "attr": attr, "length": len(text), "text": text}


def _field(row, col, length):
    return {"row": row, "col": col, "length": length, "attr": "0x24", "hidden": False}


def _screen(runs, fields):
    return {"runs": runs, "fields": fields, "message_ids": [], "cursor": None}


def _prompt():
    return _screen([
        _run(0, 19, "      Delete Thing (DLTTHG)"), _run(2, 1, "Type choices, press Enter."),
        _run(4, 1, "Thing  . . . . . . . . . . . . ."), _run(4, 34, "THING"),
        _run(5, 1, "  Library  . . . . . . . . . . ."), _run(5, 51, "*LIBL", "0x24"),
        _run(6, 1, "Device:", "0x20"), _run(6, 34, "DEV"),
        _run(7, 1, "  Printer  . . . . . . . . . . ."), _run(7, 49, "*JOB", "0x24"),
        _run(20, 66, "       Bottom"), _run(21, 1, "F3=Exit   F4=Prompt"), _run(22, 0, " F24=More keys"),
    ], [_field(4, 49, 10), _field(5, 51, 10), _field(7, 49, 10)])


def test_a_prompt_screen_becomes_a_command_and_its_rows():
    name, spec = promptspec.extract(_prompt())
    assert name == "DLTTHG"
    assert spec["title"] == ("Delete Thing (DLTTHG)", 25)               # column is where the words start
    assert spec["bottom"] == "Bottom" and spec["keys"] == ("F3=Exit   F4=Prompt", "F24=More keys")
    assert spec["rows"] == [
        (4, "Thing  . . . . . . . . . . . . .".ljust(33) + "THING", "THING", 49, 10, ""),
        (5, "  Library  . . . . . . . . . . .", "THING@", 51, 10, "*LIBL"),       # the library of a qualified name
        (6, "Device:".ljust(33) + "DEV", "", 0, 0, ""),
        (7, "  Printer  . . . . . . . . . . .", "DEV", 49, 10, "*JOB"),          # a field under a label only row
    ]


def test_a_screen_that_is_not_a_prompt_is_ignored():
    assert promptspec.extract(_screen([_run(0, 1, "MAIN"), _run(0, 32, "IBM i Main Menu")], [])) is None


def test_a_command_with_nothing_to_prompt_for_keeps_the_hosts_words():
    snap = _screen([_run(0, 19, "         Change Password (CHGPWD)"), _run(21, 1, "F3=Exit"),
                    _run(23, 1, "No parameters to show; press Enter to run, F3 to exit.")], [])
    name, spec = promptspec.extract(snap)
    assert name == "CHGPWD" and spec["rows"] == [] and spec["note"].startswith("No parameters to show")


def test_a_second_page_continues_the_keyword_it_started_in_the_middle_of():
    page1 = _prompt()
    page1["runs"][-3] = _run(20, 66, "      More...")
    page2 = _screen([
        _run(0, 19, "      Delete Thing (DLTTHG)"), _run(2, 1, "Type choices, press Enter."),
        _run(4, 1, "  Number . . . . . . . . . . . ."), _run(4, 49, "*ALL", "0x24"),
        _run(20, 66, "       Bottom"),
    ], [_field(4, 49, 6)])
    cap = {"snapshots": [page1, page2]}
    spec = promptspec.extract_all([cap])["DLTTHG"]
    assert spec["bottom"] == "More..." and spec["pages"] == [([(4, "  Number . . . . . . . . . . . .", "DEV@", 49, 6, "*ALL")], "Bottom")]


def test_a_roll_up_that_was_refused_is_not_a_second_page():
    page1 = _prompt()
    page1["runs"][-3] = _run(20, 66, "      More...")
    refused = _prompt()
    refused["runs"][-3] = _run(20, 66, "      More...")
    refused["runs"].append(_run(23, 1, "Parameter THING required."))
    assert promptspec.extract_all([{"snapshots": [page1, refused]}])["DLTTHG"]["pages"] == []


def test_the_table_has_every_command_the_scenarios_prompted_except_the_refused_one():
    asked = {c for batch in scenario.PROMPT_BATCHES.values() for c in batch}
    assert asked - set(SPECS) == {"CRTLIB"}              # the host refused it before the prompt


def test_every_row_in_the_table_is_well_formed():
    for name, spec in SPECS.items():
        assert spec["title"][0].endswith(f"({name})"), name
        pages = [(spec["rows"], spec["bottom"])] + list(spec.get("pages", []))
        for rows, bottom in pages:
            assert bottom in ("Bottom", "More...", ""), (name, bottom)
            for row, label, field, col, length, default in rows:
                assert 3 < row < 20 and label.strip(), (name, row)
                assert (length > 0) == bool(field) and (col > 0) == bool(field), (name, row)
                assert len(default) <= max(length, 1) or length == 0 or len(default) <= length + 40, (name, row)
        names = [r[2] for rows, _ in pages for r in rows if r[2]]
        assert len(names) == len(set(names)), name        # a field name is never used twice
        assert (spec["bottom"] == "") == ("note" in spec), name        # only a no-parameter prompt has no marker


def test_a_brighter_field_is_required_and_a_more_values_line_with_a_field_is_the_keywords_plus():
    snap = _screen([
        _run(0, 19, "      Add Thing (ADDTHG)"), _run(2, 1, "Type choices, press Enter."),
        _run(4, 1, "Thing  . . . . . . . . . . . . ."), _run(4, 34, "THING"),
        _run(5, 1, "User . . . . . . . . . . . . . ."), _run(5, 34, "USER"),
        _run(6, 17, "          + for more values"),
        _run(7, 1, "Authority  . . . . . . . . . . ."), _run(7, 34, "AUT"), _run(7, 49, "*CHANGE", "0x24"),
        _run(20, 66, "       Bottom"),
    ], [{**_field(4, 49, 10), "attr": "0x26"}, {**_field(5, 49, 10), "attr": "0x26"}, _field(6, 49, 10),
        _field(7, 49, 10)])
    name, spec = promptspec.extract(snap)
    assert spec["required"] == ["THING", "USER"]                                  # not AUT, and not USER+
    assert [r[2] for r in spec["rows"]] == ["THING", "USER", "USER+", "AUT"]
    assert spec["rows"][2] == (6, " " * 16 + "          + for more values", "USER+", 49, 10, "")


def test_every_required_name_in_the_table_is_a_field_of_the_prompt():
    for name, spec in SPECS.items():
        fields = {r[2] for rows in [spec["rows"]] + [p[0] for p in spec.get("pages", [])] for r in rows}
        assert set(spec["required"]) <= fields, name


def _f10_pair():
    keys = [_run(21, 1, "F3=Exit   F4=Prompt   F10=Additional parameters"), _run(22, 0, " F24=More keys")]
    plain = _screen([_run(0, 19, "      Delete Thing (DLTTHG)"), _run(2, 1, "Type choices, press Enter."),
                     _run(4, 1, "Thing  . . . . . . . . . . . . ."), _run(4, 34, "THING"),
                     _run(20, 66, "       Bottom"), *keys], [_field(4, 49, 10)])
    more = _screen([_run(0, 19, "      Delete Thing (DLTTHG)"), _run(2, 1, "Type choices, press Enter."),
                    _run(4, 1, "Thing  . . . . . . . . . . . . ."), _run(4, 34, "THING"),
                    _run(14, 18, "          Additional Parameters"),
                    _run(16, 1, "Colour . . . . . . . . . . . . ."), _run(16, 34, "COLOUR"), _run(16, 49, "*RED", "0x24"),
                    _run(20, 66, "       Bottom"), _run(21, 1, "F3=Exit   F4=Prompt"), _run(22, 0, " F24=More keys")],
                   [_field(4, 49, 10), _field(16, 49, 10)])
    return plain, more


def test_the_f10_view_is_read_whole_and_a_roll_up_that_complained_does_not_page():
    plain, more = _f10_pair()
    refused = {**more, "runs": [*more["runs"], _run(23, 1, "Parameter THING required.")]}
    found = promptspec.extract_f10([{"snapshots": [plain, more, refused, plain]}])
    assert list(found) == ["DLTTHG"]
    assert [b for _, b in found["DLTTHG"]["pages"]] == ["Bottom"] and len(found["DLTTHG"]["pages"]) == 1
    assert "F10=Additional" not in " ".join(found["DLTTHG"]["keys"])
    assert any(r[2] == "COLOUR" for r in found["DLTTHG"]["pages"][0][0])


def test_a_field_with_no_label_and_no_text_is_still_a_field_of_the_keyword_above():
    plain, _ = _f10_pair()
    snap = {**plain, "fields": [*plain["fields"], _field(5, 49, 10)]}                  # an empty second value
    _, spec = promptspec.extract(snap)
    assert (5, "", "THING@", 49, 10, "") in spec["rows"]


def test_values_of_the_profile_the_host_was_captured_with_never_reach_the_table():
    assert promptspec.scrub("WREN01") == "{USER}" and promptspec.scrub("'Hoff,Britley'") == "{TEXT}"
    assert promptspec.scrub("'-=* https://pub400.com *=-") == "*SAME" and promptspec.scrub("*YES") == "*YES"


def test_the_table_has_an_f10_view_for_every_prompt_that_offers_the_key():
    offered = [c for c, s in SPECS.items() if any("F10=Additional" in k for k in s["keys"])]
    assert len(offered) == 29 and all("more" in SPECS[c] for c in offered)
