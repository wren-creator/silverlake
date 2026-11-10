"""Authorization lists: CRTAUTL, DLTAUTL, ADDAUTLE, CHGAUTLE, RMVAUTLE, DSPAUTL, WRKAUTL."""

import pytest

from silverlake.cl.commands import execute
from silverlake.screens.model import Text
from silverlake.screens.render import render
from silverlake.screens.signon import SignonController
from silverlake.system import profiles, state
from silverlake.system.authority import ALL, CHANGE, USE, Auth


@pytest.fixture
def store():
    return profiles.load()


def run(store, user, line):
    out = execute(store, store.get(user), line)
    return out.message.line() if out.message else ""


def texts(screen):
    return " | ".join(f.text for f in screen.fields if isinstance(f, Text))


def test_create_makes_the_caller_the_owner_and_defaults_public_to_change(store):
    assert "created" in run(store, "DEVELOPER", "CRTAUTL AUTL(MYLIST) TEXT('mine')")
    a = store.autls["MYLIST"]
    assert (a.owner, a.public, a.text) == ("DEVELOPER", CHANGE, "mine")
    run(store, "DEVELOPER", "CRTAUTL OTHER AUT(*EXCLUDE)")        # positional name and AUT
    assert store.autls["OTHER"].public == Auth.NONE
    assert "CPF2278" in run(store, "DEVELOPER", "CRTAUTL MYLIST")


def test_bad_names_are_refused(store):
    assert "not valid" in run(store, "DEVELOPER", "CRTAUTL AUTL(1BAD)")
    assert "not valid" in run(store, "DEVELOPER", "CRTAUTL AUTL(PAY*)")


def test_owner_or_allobj_can_delete_and_a_list_in_use_cannot_be_deleted(store):
    assert "CPF2279" in run(store, "QSECOFR", "DLTAUTL PAYAUTL")             # secures APPLIB/PAYROLL
    run(store, "DEVELOPER", "CRTAUTL MYLIST")
    assert "CPF2189" in run(store, "STUDENT", "DLTAUTL MYLIST")
    assert "deleted" in run(store, "DEVELOPER", "DLTAUTL MYLIST")
    assert "MYLIST" not in store.autls
    assert "CPF2105" in run(store, "DEVELOPER", "DLTAUTL MYLIST")


def test_add_change_and_remove_entries(store):
    run(store, "DEVELOPER", "CRTAUTL MYLIST AUT(*EXCLUDE)")
    assert "added" in run(store, "DEVELOPER", "ADDAUTLE AUTL(MYLIST) USER(STUDENT) AUT(*USE)")
    assert store.autls["MYLIST"].entries["STUDENT"] == USE
    assert "CPF2282" in run(store, "DEVELOPER", "ADDAUTLE MYLIST STUDENT *USE")     # already there
    assert "changed" in run(store, "DEVELOPER", "CHGAUTLE MYLIST STUDENT AUT(*OBJOPR *READ)")
    assert store.autls["MYLIST"].entries["STUDENT"] == Auth.OBJOPR | Auth.READ
    assert "changed" in run(store, "DEVELOPER", "CHGAUTLE MYLIST *PUBLIC *USE")
    assert store.autls["MYLIST"].public == USE
    assert "removed" in run(store, "DEVELOPER", "RMVAUTLE MYLIST STUDENT")
    assert "STUDENT" not in store.autls["MYLIST"].entries
    assert "CPF2285" in run(store, "DEVELOPER", "RMVAUTLE MYLIST STUDENT")          # no longer there


def test_public_rules_and_unknown_users(store):
    run(store, "DEVELOPER", "CRTAUTL MYLIST")
    assert "CPF2280" in run(store, "DEVELOPER", "ADDAUTLE MYLIST *PUBLIC *USE")
    assert "CPF2288" in run(store, "DEVELOPER", "RMVAUTLE MYLIST *PUBLIC")
    assert "CPF2286" in run(store, "DEVELOPER", "CHGAUTLE MYLIST *PUBLIC *AUTLMGT")
    assert "CPF2281" in run(store, "DEVELOPER", "ADDAUTLE MYLIST NOBODY *USE")
    assert "CPF2283" in run(store, "DEVELOPER", "ADDAUTLE NOSUCH STUDENT *USE")


def test_aut_combinations_follow_the_documented_errors(store):
    run(store, "DEVELOPER", "CRTAUTL MYLIST")
    assert "CPF22AA" in run(store, "DEVELOPER", "ADDAUTLE MYLIST STUDENT AUT(*ALL *READ)")
    assert "CPF22AB" in run(store, "DEVELOPER", "ADDAUTLE MYLIST STUDENT AUT(*CHANGE *READ)")
    assert "CPF22AC" in run(store, "DEVELOPER", "ADDAUTLE MYLIST STUDENT AUT(*USE *READ)")
    assert "CPF2290" in run(store, "DEVELOPER", "ADDAUTLE MYLIST STUDENT AUT(*EXCLUDE *READ)")
    assert "added" in run(store, "DEVELOPER", "ADDAUTLE MYLIST STUDENT AUT(*USE *AUTLMGT)")
    assert store.autls["MYLIST"].entries["STUDENT"] == USE | Auth.AUTLMGT


def test_autlmgt_is_not_part_of_all():
    assert Auth.AUTLMGT not in ALL


def test_only_the_owner_or_allobj_may_give_autlmgt_and_strangers_may_change_nothing(store):
    run(store, "DEVELOPER", "CRTAUTL MYLIST")
    assert "CPF2284" in run(store, "STUDENT", "ADDAUTLE MYLIST OPERATOR *USE")
    run(store, "DEVELOPER", "ADDAUTLE MYLIST STUDENT AUT(*USE *AUTLMGT)")
    assert "CPF2284" in run(store, "STUDENT", "ADDAUTLE MYLIST OPERATOR AUT(*USE *AUTLMGT)")
    assert "added" in run(store, "STUDENT", "ADDAUTLE MYLIST OPERATOR *USE")         # a manager, at their own level
    assert "CPF2282" in run(store, "STUDENT", "ADDAUTLE MYLIST BACKUP AUT(*ALL)")    # beyond what they hold
    assert "BACKUP" not in store.autls["MYLIST"].entries
    assert "added" in run(store, "QSECOFR", "ADDAUTLE MYLIST BACKUP AUT(*ALL *AUTLMGT)")


def test_a_manager_cannot_remove_someone_who_holds_more(store):
    run(store, "DEVELOPER", "CRTAUTL MYLIST")
    run(store, "DEVELOPER", "ADDAUTLE MYLIST STUDENT AUT(*USE *AUTLMGT)")
    run(store, "DEVELOPER", "ADDAUTLE MYLIST BACKUP AUT(*ALL)")
    run(store, "DEVELOPER", "ADDAUTLE MYLIST OPERATOR AUT(*USE)")
    assert "CPF2285" in run(store, "STUDENT", "RMVAUTLE MYLIST BACKUP")
    assert "BACKUP" in store.autls["MYLIST"].entries
    assert "removed" in run(store, "STUDENT", "RMVAUTLE MYLIST OPERATOR")


def test_removing_an_entry_changes_what_the_list_secures(store):
    """OPERATOR reads PAYROLL through PAYAUTL; taking them off sends them to public *EXCLUDE."""
    payroll = store.objects[("APPLIB", "PAYROLL", "*FILE")]
    assert Auth.READ in store.authority_to_object(store.get("OPERATOR"), payroll)
    run(store, "QSECOFR", "RMVAUTLE PAYAUTL OPERATOR")
    assert store.authority_to_object(store.get("OPERATOR"), payroll) == Auth.NONE


def test_dspautl_and_wrkautl_show_only_what_you_may_see(store):
    assert "CPF2207" in run(store, "STUDENT", "DSPAUTL PAYAUTL")
    assert "CPF2283" in run(store, "STUDENT", "DSPAUTL NOSUCH")
    out = execute(store, store.get("OPERATOR"), "DSPAUTL PAYAUTL")        # has an entry
    assert out.view[0] == "dspautl" and ("OPERATOR", "*USE") in out.view[2] and out.view[2][-1][0] == "*PUBLIC"
    assert "No authorization lists" in run(store, "STUDENT", "WRKAUTL")
    assert [a.name for a in execute(store, store.get("QSECOFR"), "WRKAUTL").view[1]] == ["PAYAUTL"]
    assert execute(store, store.get("QSECOFR"), "WRKAUTL PAY*").view[0] == "wrkautl"
    assert "No authorization lists" in run(store, "QSECOFR", "WRKAUTL ZZ*")


def test_screens_render_over_the_controller(store):
    c = SignonController("QPADEV0001", store)
    c.handle("ENTER", {"user": "QSECOFR", "password": "QSECOFR"})
    s = c.handle("ENTER", {"command": "wrkautl"})
    assert "PAYAUTL" in texts(s)
    render(s)
    c.handle("ENTER", {})
    s = c.handle("ENTER", {"command": "dspautl payautl"})
    assert "SECADMIN" in texts(s) and "*PUBLIC" in texts(s)
    render(s)


def test_commands_are_objects_so_a_site_can_lock_them(store):
    run(store, "QSECOFR", "RVKOBJAUT OBJ(QSYS/CRTAUTL) OBJTYPE(*CMD) USER(*PUBLIC) AUT(*USE)")
    assert "Not authorized to command CRTAUTL" in run(store, "STUDENT", "CRTAUTL X")


def test_lists_persist_with_owner_text_and_autlmgt(store):
    run(store, "DEVELOPER", "CRTAUTL MYLIST AUT(*USE) TEXT('kept')")
    run(store, "DEVELOPER", "ADDAUTLE MYLIST STUDENT AUT(*CHANGE *AUTLMGT)")
    again = state.from_dict(state.to_dict(store))
    a = again.autls["MYLIST"]
    assert (a.owner, a.text, a.public) == ("DEVELOPER", "kept", USE)
    assert a.entries["STUDENT"] == CHANGE | Auth.AUTLMGT


def test_deleting_a_profile_removes_its_list_entries(store):
    run(store, "DEVELOPER", "CRTAUTL MYLIST")
    run(store, "QSECOFR", "CRTUSRPRF USRPRF(TEMPUSR) PASSWORD(TEMPUSR)")
    run(store, "DEVELOPER", "ADDAUTLE MYLIST TEMPUSR *USE")
    assert "deleted" in run(store, "QSECOFR", "DLTUSRPRF TEMPUSR")
    assert "TEMPUSR" not in store.autls["MYLIST"].entries


def test_public_authority_counts_as_some_authority_for_seeing_a_list(store):
    """Seen on PUB400: a basic profile lists many lists it neither owns nor has an entry on,
    and can display one with only a *PUBLIC *USE row."""
    run(store, "DEVELOPER", "CRTAUTL OPENLIST")                     # AUT defaults to *CHANGE
    run(store, "DEVELOPER", "CRTAUTL SHUTLIST AUT(*EXCLUDE)")
    seen = [a.name for a in execute(store, store.get("STUDENT"), "WRKAUTL").view[1]]
    assert seen == ["OPENLIST"]
    assert execute(store, store.get("STUDENT"), "DSPAUTL OPENLIST").view[2] == [("*PUBLIC", "*CHANGE")]
    assert "CPF2207" in run(store, "STUDENT", "DSPAUTL SHUTLIST")


def test_dspautl_screen_follows_the_real_layout(store):
    run(store, "DEVELOPER", "CRTAUTL MYLIST AUT(*USE)")
    run(store, "DEVELOPER", "ADDAUTLE MYLIST STUDENT AUT(*CHANGE *AUTLMGT)")
    c = SignonController("QPADEV0001", store)
    c.handle("ENTER", {"user": "DEVELOPER", "password": "DEVELOPER"})
    s = c.handle("ENTER", {"command": "dspautl mylist"})
    runs = {(f.row, f.col): f.text for f in s.fields if isinstance(f, Text)}
    assert runs[(5, 14)] == "Object" and runs[(6, 13)] == "Authority" and runs[(6, 24)] == "Mgt"
    assert runs[(7, 1)] == "STUDENT" and runs[(7, 13)] == "*CHANGE" and runs[(7, 24)] == "X"
    assert runs[(8, 1)] == "*PUBLIC" and (8, 24) not in runs
    assert runs[(3, 67)] == "*NONE"


def test_messages_after_sign_on_show_text_without_the_id(store):
    c = SignonController("QPADEV0001", store)
    c.handle("ENTER", {"user": "STUDENT", "password": "STUDENT"})
    s = c.handle("ENTER", {"command": "dspautl nosuch"})
    assert "Authorization list NOSUCH does not exist." in texts(s) and "CPF" not in texts(s)


def test_an_authorization_list_is_also_an_object_in_qsys(store):
    run(store, "DEVELOPER", "CRTAUTL AUTL(MYLIST) TEXT('mine')")
    obj = store.objects[("QSYS", "MYLIST", "*AUTL")]
    assert (obj.owner, obj.public, obj.library, obj.text) == ("DEVELOPER", USE, "QSYS", "mine")
    assert "MYLIST" in [n for lib, n, t in store.objects if t == "*AUTL"]
    run(store, "DEVELOPER", "DLTAUTL MYLIST")
    assert ("QSYS", "MYLIST", "*AUTL") not in store.objects


def test_the_seeded_list_is_already_an_object(store):
    assert ("QSYS", "PAYAUTL", "*AUTL") in store.objects
    assert store.objects[("QSYS", "PAYAUTL", "*AUTL")].owner == "QSECOFR"


def test_wrkobj_and_dspobjaut_see_an_authorization_list(store):
    run(store, "DEVELOPER", "CRTAUTL AUTL(MYLIST)")
    c = SignonController("QPADEV0001", store)
    c.handle("ENTER", {"user": "DEVELOPER", "password": "DEVELOPER"})
    s = c.handle("ENTER", {"command": "wrkobj obj(mylist) objtype(*autl)"})
    assert "MYLIST" in texts(s)
    out = execute(store, store.get("DEVELOPER"), "DSPOBJAUT OBJ(MYLIST) OBJTYPE(*AUTL)")
    assert out.view is not None


def test_grtobjaut_and_rvkobjaut_work_on_an_authorization_list_as_an_object(store):
    run(store, "DEVELOPER", "CRTAUTL AUTL(MYLIST)")
    assert "granted" in run(store, "DEVELOPER", "GRTOBJAUT OBJ(MYLIST) OBJTYPE(*AUTL) USER(STUDENT) AUT(*USE)")
    obj = store.objects[("QSYS", "MYLIST", "*AUTL")]
    assert obj.private["STUDENT"] == USE
    assert "revoked" in run(store, "DEVELOPER", "RVKOBJAUT OBJ(MYLIST) OBJTYPE(*AUTL) USER(STUDENT) AUT(*USE)")
    assert "STUDENT" not in obj.private


def test_rnmobj_and_crtdupobj_refuse_an_authorization_list(store):
    run(store, "DEVELOPER", "CRTAUTL AUTL(MYLIST)")
    assert "not" in run(store, "DEVELOPER", "RNMOBJ OBJ(MYLIST) OBJTYPE(*AUTL) NEWOBJ(OTHERLIST)").lower()
    assert ("QSYS", "MYLIST", "*AUTL") in store.objects
    assert "not" in run(store, "DEVELOPER", "CRTDUPOBJ OBJ(MYLIST) OBJTYPE(*AUTL) NEWOBJ(COPY)").lower()


def test_chgobjd_and_wrkautl_option_13_write_the_same_text(store):
    run(store, "DEVELOPER", "CRTAUTL AUTL(MYLIST)")
    assert "changed" in run(store, "DEVELOPER", "CHGOBJD OBJ(MYLIST) OBJTYPE(*AUTL) TEXT('from chgobjd')")
    assert store.autls["MYLIST"].text == "from chgobjd"
    c = SignonController("QPADEV0001", store)
    c.handle("ENTER", {"user": "DEVELOPER", "password": "DEVELOPER"})
    c.handle("ENTER", {"command": "wrkautl"})
    s = c.handle("ENTER", {"opt0": "13", "command": "from option 13"})
    assert store.objects[("QSYS", "MYLIST", "*AUTL")].text == "from option 13"


def test_wrkobj_option_4_deletes_an_authorization_list_through_dltautl(store):
    run(store, "DEVELOPER", "CRTAUTL AUTL(MYLIST)")
    c = SignonController("QPADEV0002", store)
    c.handle("ENTER", {"user": "DEVELOPER", "password": "DEVELOPER"})
    s = c.handle("ENTER", {"command": "wrkobj obj(mylist) objtype(*autl)"})
    assert "MYLIST" in texts(s)
    s = c.handle("ENTER", {"opt0": "4"})
    assert "Confirm Delete" in texts(s)
    c.handle("ENTER", {})
    assert "MYLIST" not in store.autls
    assert ("QSYS", "MYLIST", "*AUTL") not in store.objects


def test_a_state_saved_before_autl_was_an_object_gets_one_backfilled(store):
    run(store, "DEVELOPER", "CRTAUTL AUTL(MYLIST)")
    saved = state.to_dict(store)
    saved["objects"] = [o for o in saved["objects"] if o["type"] != "*AUTL"]     # simulate an older save
    again = state.from_dict(saved)
    assert ("QSYS", "MYLIST", "*AUTL") in again.objects
    assert ("QSYS", "PAYAUTL", "*AUTL") in again.objects
    assert again.objects[("QSYS", "MYLIST", "*AUTL")].owner == "DEVELOPER"
