"""Message queues: DSPMSG, SNDMSG, CLRMSGQ. Layout positions are from the PUB400 captures."""

import pytest

from silverlake.cl import commands
from silverlake.screens.model import Text
from silverlake.screens.signon import SignonController
from silverlake.system import state


@pytest.fixture
def store(tmp_path):
    s, db = state.open_store(state_dir=tmp_path)
    yield s
    db.close()


def _signed(store, user="QSECOFR", device="QPADEV0001"):
    c = SignonController(device, store)
    c.handle("ENTER", {"user": user, "password": user})
    return c


def _text(s):
    return " | ".join(f.text for f in s.fields if isinstance(f, Text))


def _run(store, user, line):
    out = commands.execute(store, store.get(user), line)
    return out.message.text if out.message else ""


def test_qsysopr_is_seeded_and_world_readable(store):
    q = store.objects[("QSYS", "QSYSOPR", "*MSGQ")]
    assert q.data["dlvry"] == "*HOLD" and q.data["sev"] == "99" and len(q.data["messages"]) == 6
    c = _signed(store, "STUDENT")                                   # no special authority at all
    t = _text(c.handle("ENTER", {"command": "dspmsg msgq(*sysopr)"}))
    assert "004502/OPERATOR/QPADEV0003" in t                         # other people's jobs, by name


def test_display_messages_layout_follows_the_capture(store):
    c = _signed(store, "STUDENT")
    s = c.handle("ENTER", {"command": "dspmsg msgq(qsys/qsysopr)"})
    f = {(x.row, x.col): x for x in s.fields}
    assert f[(0, 32)].text == "Display Messages" and f[(2, 21)].text == "QSYSOPR" and f[(3, 23)].text == "QSYS"
    assert (f[(4, 21)].text, f[(4, 65)].text, f[(2, 65)].text) == ("99", "*HOLD", "*DSPMSG")
    assert f[(21, 1)].text.startswith("F3=Exit              F11=Remove a message")
    assert f[(22, 1)].text.startswith("F13=Remove all       F16=Remove all except unanswered")
    assert f[(20, 73)].text == "Bottom" and not s.inputs()
    assert any(x.text.startswith("From  . . . :   QSECOFR") for x in s.fields if isinstance(x, Text))


def test_own_queue_is_in_qusrsys_and_empty_says_so(store):
    c = _signed(store, "STUDENT")
    s = c.handle("ENTER", {"command": "dspmsg"})
    f = {(x.row, x.col): x for x in s.fields}
    assert (f[(2, 21)].text, f[(3, 23)].text, f[(4, 65)].text) == ("STUDENT", "QUSRSYS", "*BREAK")
    assert f[(7, 3)].text == "(No messages available)"


def test_sndmsg_needs_obj_opr_and_add_and_lands_with_the_sender(store):
    assert _run(store, "STUDENT", "SNDMSG MSG('lunch?') TOUSR(DEVELOPER)") == "Message sent."
    q = store.objects[("QUSRSYS", "DEVELOPER", "*MSGQ")]
    assert q.data["messages"][-1]["from"] == "STUDENT" and q.data["messages"][-1]["text"] == "lunch?"
    _run(store, "QSECOFR", "RVKOBJAUT OBJ(QUSRSYS/DEVELOPER) OBJTYPE(*MSGQ) USER(*PUBLIC) AUT(*ALL)")
    assert _run(store, "STUDENT", "SNDMSG MSG('again') TOUSR(DEVELOPER)") == "Not authorized to message queue DEVELOPER."


def test_stock_user_queues_are_readable_by_anyone_the_inferred_default(store):
    _run(store, "STUDENT", "SNDMSG MSG('private note') TOUSR(DEVELOPER)")
    out = commands.execute(store, store.get("GUEST"), "DSPMSG MSGQ(QUSRSYS/DEVELOPER)")
    assert out.view and out.view[0] == "dspmsg"                      # public *CHANGE on QUSRSYS: the weakness


def test_revoking_public_authority_closes_a_queue(store):
    _run(store, "QSECOFR", "RVKOBJAUT OBJ(QSYS/QSYSOPR) OBJTYPE(*MSGQ) USER(*PUBLIC) AUT(*ALL)")
    out = commands.execute(store, store.get("STUDENT"), "DSPMSG MSGQ(*SYSOPR)")
    assert out.message.id == "CPF2408" and out.message.text == "Not authorized to message queue QSYSOPR."
    assert commands.execute(store, store.get("QSECOFR"), "DSPMSG MSGQ(*SYSOPR)").view      # *ALLOBJ


def test_sndmsg_to_a_missing_user_or_queue_and_unmodeled_targets(store):
    assert _run(store, "STUDENT", "SNDMSG MSG('x') TOUSR(NOSUCH)") == "User profile NOSUCH not found."
    assert "not found" in _run(store, "STUDENT", "SNDMSG MSG('x') TOMSGQ(QGPL/NOSUCH)")
    assert "not modeled" in _run(store, "STUDENT", "SNDMSG MSG('x') TOUSR(*ALLACT)")
    assert "Inquiry" in _run(store, "STUDENT", "SNDMSG MSG('x') TOUSR(DEVELOPER) MSGTYPE(*INQ)")
    assert "Give TOUSR or TOMSGQ" in _run(store, "STUDENT", "SNDMSG MSG('x')")


def test_sndmsg_to_sysopr_by_either_spelling(store):
    assert _run(store, "STUDENT", "SNDMSG MSG('disk low') TOUSR(*SYSOPR)") == "Message sent."
    assert _run(store, "STUDENT", "SNDMSG MSG('disk lower') TOMSGQ(*SYSOPR)") == "Message sent."
    assert [m["text"] for m in store.objects[("QSYS", "QSYSOPR", "*MSGQ")].data["messages"]][-2:] == ["disk low", "disk lower"]


def test_clrmsgq_needs_change_authority(store):
    _run(store, "STUDENT", "SNDMSG MSG('hi') TOUSR(DEVELOPER)")
    _run(store, "QSECOFR", "RVKOBJAUT OBJ(QUSRSYS/DEVELOPER) OBJTYPE(*MSGQ) USER(*PUBLIC) AUT(*CHANGE)")
    _run(store, "QSECOFR", "GRTOBJAUT OBJ(QUSRSYS/DEVELOPER) OBJTYPE(*MSGQ) USER(*PUBLIC) AUT(*USE)")
    assert _run(store, "STUDENT", "CLRMSGQ MSGQ(QUSRSYS/DEVELOPER)") == "Not authorized to message queue DEVELOPER."
    assert "cleared" in _run(store, "DEVELOPER", "CLRMSGQ MSGQ(QUSRSYS/DEVELOPER)")
    assert store.objects[("QUSRSYS", "DEVELOPER", "*MSGQ")].data["messages"] == []


def test_f13_removes_all_for_someone_who_may_and_refuses_otherwise(store):
    _run(store, "STUDENT", "SNDMSG MSG('hi') TOUSR(STUDENT)")
    c = _signed(store, "STUDENT")
    c.handle("ENTER", {"command": "dspmsg"})
    assert "All messages removed." in _text(c.handle("F13", {}))
    assert store.objects[("QUSRSYS", "STUDENT", "*MSGQ")].data["messages"] == []
    _run(store, "QSECOFR", "RVKOBJAUT OBJ(QSYS/QSYSOPR) OBJTYPE(*MSGQ) USER(*PUBLIC) AUT(*CHANGE)")
    _run(store, "QSECOFR", "GRTOBJAUT OBJ(QSYS/QSYSOPR) OBJTYPE(*MSGQ) USER(*PUBLIC) AUT(*USE)")
    c.handle("F12", {})
    c.handle("ENTER", {"command": "dspmsg msgq(*sysopr)"})
    assert "Not authorized to message queue QSYSOPR." in _text(c.handle("F13", {}))
    assert len(store.objects[("QSYS", "QSYSOPR", "*MSGQ")].data["messages"]) == 6


def test_queue_messages_survive_a_restart(tmp_path):
    s, db = state.open_store(state_dir=tmp_path)
    _run(s, "STUDENT", "SNDMSG MSG('persist me') TOUSR(DEVELOPER)")
    db.close()
    s2, db2 = state.open_store(state_dir=tmp_path)
    assert s2.objects[("QUSRSYS", "DEVELOPER", "*MSGQ")].data["messages"][-1]["text"] == "persist me"
    db2.close()


def test_a_profiles_queue_goes_when_the_profile_does(store):
    _run(store, "QSECOFR", "CRTUSRPRF USRPRF(TMPUSER) PASSWORD(abc12345)")
    _run(store, "STUDENT", "SNDMSG MSG('x') TOUSR(TMPUSER)")
    assert ("QUSRSYS", "TMPUSER", "*MSGQ") in store.objects
    assert "deleted" in _run(store, "QSECOFR", "DLTUSRPRF USRPRF(TMPUSER)")
    assert ("QUSRSYS", "TMPUSER", "*MSGQ") not in store.objects


def test_new_commands_are_objects_and_msgq_is_a_known_object_type(store):
    assert all(("QSYS", n, "*CMD") in store.objects for n in ("DSPMSG", "SNDMSG", "CLRMSGQ"))
    assert commands.execute(store, store.get("QSECOFR"), "DSPOBJAUT OBJ(QSYS/QSYSOPR) OBJTYPE(*MSGQ)").view
