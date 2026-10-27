"""Adopted authority and QCMDEXC: a program that adopts its owner, what the stack passes along, and the
classic hole (a QSECOFR-owned helper that hands a typed string to QCMDEXC) with its fix."""

import pytest

from silverlake.screens.model import Text
from silverlake.screens.signon import SignonController
from silverlake.system import profiles, rpg
from silverlake.system.authority import USE, SecuredObject


@pytest.fixture
def store():
    return profiles.load()


def signed(store, user="STUDENT"):
    c = SignonController("QPADEV0051", store)
    c.handle("ENTER", {"user": user, "password": user})
    return c


def text(s):
    return " | ".join(f.text for f in s.fields if isinstance(f, Text))


def joblog(c):
    return " | ".join(t for _, _, t in c.session.joblog)


def run_helper(c, prog, command):
    c.handle("ENTER", {"command": "ADDLIBLE APPLIB"})
    c.handle("ENTER", {"command": f"CALL PGM({prog})"})
    return c.handle("ENTER", {"cmd": command})


def test_a_normal_user_cannot_create_a_profile(store):
    c = signed(store)
    c.handle("ENTER", {"command": "CRTUSRPRF USRPRF(EVIL) PASSWORD(X) USRCLS(*SECOFR)"})
    assert store.get("EVIL") is None
    assert "special authority is required" in joblog(c)


def test_the_vulnerable_helper_hands_student_a_new_security_officer(store):
    c = signed(store)
    run_helper(c, "APPLIB/RUNCMD", "CRTUSRPRF USRPRF(EVIL) PASSWORD(EVIL) USRCLS(*SECOFR)")
    evil = store.get("EVIL")
    assert evil is not None and evil.user_class.value == "*SECOFR"
    assert evil.owner == "STUDENT"                        # the creator is still the user, as on IBM i
    log = joblog(c)
    assert "adopted" in log and "QSECOFR" in log and "QCMDEXC: CRTUSRPRF" in log


def test_the_user_keeps_no_new_power_once_the_program_ends(store):
    c = signed(store)
    run_helper(c, "APPLIB/RUNCMD", "CRTUSRPRF USRPRF(EVIL) PASSWORD(EVIL)")
    c.handle("ENTER", {"command": "CRTUSRPRF USRPRF(EVIL2) PASSWORD(EVIL2)"})
    assert store.get("EVIL2") is None                     # back to STUDENT's own authority


def test_the_fixed_helper_refuses_anything_off_its_list(store):
    c = signed(store)
    run_helper(c, "APPLIB/RUNCMDX", "CRTUSRPRF USRPRF(EVIL) PASSWORD(EVIL)")
    assert store.get("EVIL") is None
    assert "QCMDEXC" not in joblog(c)


def test_the_fixed_helper_runs_its_list_with_an_owner_who_holds_nothing(store):
    c = signed(store)
    run_helper(c, "APPLIB/RUNCMDX", "CHGJOB JOBPTY(5)")
    assert "QCMDEXC: CHGJOB JOBPTY(5)" in joblog(c)
    assert store.adopting(store.get("STUDENT"), rpg.adopted_owners(store, ["APPLIB/RUNCMDX"])).adopted == ("QDFTOWN",)


def test_an_unknown_command_uses_the_captured_wording(store):
    c = signed(store)
    run_helper(c, "APPLIB/RUNCMD", "NOSUCHCMD")
    assert "Command NOSUCHCMD in library *LIBL not found." in joblog(c)


def test_adoption_does_not_supply_the_group_profile_authority(store):
    # IBM: a group assignment needs the user's own *CHANGE and *OBJMGT to the group.
    c = signed(store)
    run_helper(c, "APPLIB/RUNCMD", "CRTUSRPRF USRPRF(EVIL) PASSWORD(EVIL) GRPPRF(QSECOFR)")
    assert store.get("EVIL") is None
    assert "Not authorized to user profile QSECOFR" in joblog(c)


def prog(store, name, usrprf, useadpaut, owner):
    obj = SecuredObject(name, owner, public=USE, library="APPLIB", type="*PGM",
                        data={"attr": "RPGLE", "usrprf": usrprf, "useadpaut": useadpaut, "source": "x"})
    store.objects[obj.key] = obj


def test_the_stack_passes_adoption_down_only_when_use_adopted_authority_says_so(store):
    prog(store, "A", "*OWNER", "*YES", "QSECOFR")
    prog(store, "B", "*USER", "*YES", "STUDENT")
    prog(store, "C", "*USER", "*NO", "STUDENT")
    assert rpg.adopted_owners(store, ["APPLIB/A", "APPLIB/B"]) == ["QSECOFR"]
    assert rpg.adopted_owners(store, ["APPLIB/A", "APPLIB/C"]) == []
    assert rpg.adopted_owners(store, ["APPLIB/B"]) == []


def test_two_adopting_programs_hold_both_owners(store):
    prog(store, "A", "*OWNER", "*YES", "QSECOFR")
    prog(store, "B", "*OWNER", "*YES", "SECADMIN")
    assert rpg.adopted_owners(store, ["APPLIB/A", "APPLIB/B"]) == ["QSECOFR", "SECADMIN"]


def test_adoption_adds_to_the_users_own_authority_and_is_never_stored(store):
    student = store.get("STUDENT")
    who = store.adopting(student, ["QSECOFR"])
    assert who.name == "STUDENT" and who.adopted == ("QSECOFR",)
    assert student.adopted == ()
    assert store.special_authorities(who) >= store.special_authorities(student)
    assert len(store.special_authorities(who)) > len(store.special_authorities(student))


def test_a_short_length_cuts_the_command_as_a_real_system_does(store):
    obj = store.objects[("APPLIB", "RUNCMD", "*PGM")]
    obj.data["source"] = obj.data["source"].replace("INZ(70)", "INZ(14)")
    c = signed(store)
    run_helper(c, "APPLIB/RUNCMD", "CHGJOB JOBPTY(5)")
    assert "A matching parenthesis not found." in joblog(c)
