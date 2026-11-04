"""SLSCENARIO: the instructor flips a lesson on the running range, no restart."""

import pytest

from silverlake import scenarios
from silverlake.cl.commands import execute
from silverlake.net import ftpd
from silverlake.system import commandobjs, msgq, profiles

REG = scenarios.registry()
LESSON = "ftp-console-cleartext"


@pytest.fixture
def store():
    return profiles.load()


def run(store, user, line):
    out = execute(store, store.get(user), line)
    return out.message.line() if out.message else (out.view[0] if out.view else "")


def test_qsecofr_flips_a_lesson_and_the_running_services_see_it_at_once(store):
    saved = []
    store.on_change = lambda: saved.append(1)
    ftp = ftpd.FtpSession(store)
    assert ftp.handle("USER STUDENT").replies[0][0] == 331          # clear text works before
    assert run(store, "QSECOFR", f"SLSCENARIO ID({LESSON}) STATE(*SECURE)") == f"{LESSON}: now secure."
    assert scenarios.current(store, LESSON) == "secure" and store.system.require_tls == "yes" and saved
    assert ftpd.FtpSession(store).handle("USER STUDENT").replies[0][0] == 534
    assert run(store, "QSECOFR", f"SLSCENARIO ID({LESSON}) STATE(*VULNERABLE)") == f"{LESSON}: now vulnerable."
    assert store.system.require_tls == "no"
    assert run(store, "QSECOFR", f"slscenario {LESSON.upper()} *secure").endswith("now secure.")


def test_only_qsecofr_may_even_with_all_object_and_use_authority_to_the_command(store):
    assert run(store, "QSECOFR", "CRTUSRPRF USRPRF(ZZBOSS) PASSWORD(ZZBOSS) USRCLS(*SECOFR) SPCAUT(*ALLOBJ)").startswith("User")
    run(store, "QSECOFR", "GRTOBJAUT OBJ(QSYS/SLSCENARIO) OBJTYPE(*CMD) USER(*PUBLIC) AUT(*USE)")
    for user in ("STUDENT", "ZZBOSS"):
        got = run(store, user, f"SLSCENARIO ID({LESSON}) STATE(*SECURE)")
        assert got == "Not authorized to command SLSCENARIO in library *LIBL.", user
    assert scenarios.current(store, LESSON) == "vulnerable"


def test_the_command_is_closed_to_the_public_from_the_start_and_the_others_stay_open(store):
    assert commandobjs.CLOSED == {"SLSCENARIO"}
    assert run(store, "STUDENT", f"SLSCENARIO ID({LESSON}) STATE(*SECURE)").startswith("Not authorized to command")
    assert run(store, "STUDENT", "DSPLIBL") == "dsplibl"


def test_the_whole_range_and_back(store):
    assert run(store, "QSECOFR", "SLSCENARIO ID(*ALL) STATE(*SECURE)") == "all lessons: now secure."
    assert store.system.mode == "secure" and all(scenarios.current(store, s) == "secure" for s in REG)
    assert run(store, "QSECOFR", "SLSCENARIO *ALL *VULNERABLE") == "all lessons: now vulnerable."
    assert store.system.mode == "vulnerable" and all(scenarios.current(store, s) == "vulnerable" for s in REG)


def test_reset_puts_a_lesson_back_and_clears_what_the_exploit_left(store):
    run(store, "QSECOFR", "SLSCENARIO ID(runcmd-qcmdexc) STATE(*SECURE)")
    run(store, "QSECOFR", "CRTUSRPRF USRPRF(ZZLOOT) PASSWORD(ZZLOOT)")
    assert "ZZLOOT" in store.profiles
    assert run(store, "QSECOFR", "SLSCENARIO ID(runcmd-qcmdexc) STATE(*RESET)") == "runcmd-qcmdexc: reset to vulnerable."
    assert scenarios.current(store, "runcmd-qcmdexc") == "vulnerable" and "ZZLOOT" not in store.profiles
    assert "ZZBOSS" not in store.profiles


def test_bad_input_is_refused_and_changes_nothing(store):
    assert run(store, "QSECOFR", "SLSCENARIO ID(no-such-lesson) STATE(*SECURE)") == "Lesson no-such-lesson not found."
    for line in ("SLSCENARIO ID(x y) STATE(*SECURE)", f"SLSCENARIO ID({LESSON}) STATE(*PARANOID)",
                 f"SLSCENARIO ID({LESSON})", "SLSCENARIO ID(../x) STATE(*SECURE)"):
        assert run(store, "QSECOFR", line) != "", line
    assert all(scenarios.current(store, s) == "vulnerable" for s in REG)


def test_a_state_saved_before_the_command_existed_gets_it_closed(store):
    del store.objects[("QSYS", "SLSCENARIO", "*CMD")]
    commandobjs.ensure_commands(store)
    assert run(store, "STUDENT", f"SLSCENARIO ID({LESSON}) STATE(*SECURE)").startswith("Not authorized")


def test_list_shows_every_lesson_and_its_state_and_changes_nothing(store):
    run(store, "QSECOFR", f"SLSCENARIO ID({LESSON}) STATE(*SECURE)")
    out = execute(store, store.get("QSECOFR"), "SLSCENARIO STATE(*LIST)")
    kind, rows, mode = out.view
    assert kind == "slslist" and mode == store.system.mode
    assert {r[2] for r in rows} == set(REG)
    assert next(r for r in rows if r[2] == LESSON)[0] == "secure"
    assert [r[2] for r in execute(store, store.get("QSECOFR"), f"SLSCENARIO ID({LESSON}) STATE(*LIST)").view[1]] == [LESSON]
    assert run(store, "QSECOFR", "SLSCENARIO ID(no-such-lesson) STATE(*LIST)") == "Lesson no-such-lesson not found."


def test_list_is_still_the_instructors_alone(store):
    assert run(store, "STUDENT", "SLSCENARIO STATE(*LIST)").startswith("Not authorized to command")


def test_a_flip_leaves_a_line_on_qsysopr_that_students_can_read(store):
    before = len(msgq.messages_of(store.objects[msgq.SYSOPR]))
    run(store, "QSECOFR", f"SLSCENARIO ID({LESSON}) STATE(*SECURE)")
    run(store, "QSECOFR", "SLSCENARIO ID(*ALL) STATE(*RESET)")
    log = [m["text"] for m in msgq.messages_of(store.objects[msgq.SYSOPR])][before:]
    assert log == [f"SLSCENARIO: QSECOFR set {LESSON} to *SECURE.", "SLSCENARIO: QSECOFR set all lessons to *RESET."]
    assert run(store, "STUDENT", "SLSCENARIO ID(*ALL) STATE(*SECURE)").startswith("Not authorized")
    assert len(msgq.messages_of(store.objects[msgq.SYSOPR])) == before + 2       # a refusal logs nothing


def test_list_runs_in_the_text_services_too(store):
    from silverlake.net import textview
    text = textview.run(store, store.get("QSECOFR"), "SLSCENARIO STATE(*LIST)")
    assert text.startswith("range mode:") and LESSON in text


def test_the_lesson_control_menu_is_reached_from_main_and_every_option_is_the_instructors(store):
    from silverlake.system import menus
    main = menus.parse(store.objects[("QSYS", "MAIN", "*MENU")].data)
    assert main.find("6").cmd == "GO MENU(QSYS/SLADMIN)"
    admin = menus.parse(store.objects[("QSYS", "SLADMIN", "*MENU")].data)
    cmds = [i.cmd for i in admin.items if i.cmd != "SIGNOFF"]
    assert len(cmds) == 4 and all(c.startswith("SLSCENARIO ") for c in cmds)
    for c in cmds:
        assert run(store, "STUDENT", c).startswith("Not authorized to command SLSCENARIO")
    assert execute(store, store.get("QSECOFR"), cmds[0]).view[0] == "slslist"
    assert run(store, "QSECOFR", cmds[1]) == "all lessons: now secure."
