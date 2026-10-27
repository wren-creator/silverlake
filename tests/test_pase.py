"""The simulated PASE shell and the QP2TERM display."""

import pytest

from silverlake.screens.model import Text
from silverlake.screens.signon import SignonController
from silverlake.system import ifs, pase, profiles


@pytest.fixture
def store():
    return profiles.load()


def shell(store, user="STUDENT"):
    return pase.Shell(store, store.profiles[user])


def test_the_shell_starts_in_the_home_directory_with_a_plain_environment(store):
    sh = shell(store)
    assert sh.run("pwd") == ["/home/STUDENT"] and sh.run("whoami") == ["STUDENT"]
    env = dict(line.split("=", 1) for line in sh.run("env"))
    assert env["HOME"] == "/home/STUDENT" and env["USER"] == "STUDENT" and "PATH" in env


def test_cd_and_ls_and_cat_work_on_the_virtual_ifs(store):
    sh = shell(store)
    assert sh.run("ls") == ["notes.txt"]
    assert sh.run("cat notes.txt") == ["Things to try: ls, cat, cd, id."]
    assert sh.run("cd /QOpenSys/etc") == [] and sh.run("pwd") == ["/QOpenSys/etc"]
    assert sh.run("ls") == ["motd", "profile"]
    assert sh.run("cd ..") == [] and sh.run("pwd") == ["/QOpenSys"]
    assert sh.run("cd") == [] and sh.run("pwd") == ["/home/STUDENT"]
    assert sh.run("cat ~/notes.txt") and sh.run("cat /QOpenSys/etc/motd")[0].startswith("Welcome")


def test_ls_long_and_hidden_and_several_paths(store):
    sh = shell(store, "OPERATOR")
    assert sh.run("ls") == [] and ".profile" in sh.run("ls -a")
    long = sh.run("ls -la")
    assert any(row.startswith("-rw-r--r--") and row.endswith(".profile") and "OPERATOR" in row for row in long)
    both = sh.run("ls /QOpenSys /tmp")
    assert both[0] == "/QOpenSys:" and "/tmp:" in both


def test_what_the_profile_may_not_touch_is_refused_in_the_shells_voice(store):
    sh = shell(store)
    assert sh.run("cat /home/OPERATOR/.profile") == ["cat: 0652-050 Cannot open /home/OPERATOR/.profile."]
    assert sh.run("ls /home/OPERATOR") == ["ls: 0653-345 /home/OPERATOR: Permission denied."]
    assert sh.run("cd /home/OPERATOR") == ["ksh: cd: /home/OPERATOR: [Permission denied]"]
    assert sh.run("ls /nowhere") == ["ls: 0653-341 The file /nowhere does not exist."]
    assert sh.run("cd /nowhere") == ["ksh: cd: /nowhere: [No such file or directory]"]
    assert sh.run("cd notes.txt") == ["ksh: cd: notes.txt: [Not a directory]"]
    assert sh.run("cat /home") == ["cat: 0652-050 /home is a directory."]
    assert sh.cwd == "/home/STUDENT"


def test_a_security_officer_reads_everything(store):
    sh = shell(store, "QSECOFR")
    assert sh.run("cat /home/STUDENT/notes.txt") and sh.run("ls /home/OPERATOR") == []
    assert "Chen, Priya" in " ".join(sh.run("cat /QSYS.LIB/APPLIB.LIB/PAYROLL.FILE"))


def test_the_shell_reaches_the_object_store_through_qsys_lib_with_the_same_authority(store):
    st = shell(store)
    assert "CUSTOMERS.FILE" in st.run("ls /QSYS.LIB/APPLIB.LIB")
    assert "PAYROLL.FILE" not in st.run("ls /QSYS.LIB/APPLIB.LIB")
    assert st.run("cat /QSYS.LIB/APPLIB.LIB/PAYROLL.FILE") == ["cat: 0652-050 Cannot open /QSYS.LIB/APPLIB.LIB/PAYROLL.FILE."]
    assert "Chen, Priya" in " ".join(shell(store, "OPERATOR").run("cat /QSYS.LIB/APPLIB.LIB/PAYROLL.FILE"))


def test_id_whoami_echo_export_and_variables(store):
    sh = shell(store)
    assert sh.run("id")[0].startswith("uid=") and "(STUDENT)" in sh.run("id")[0]
    assert shell(store, "QSECOFR").run("id")[0].startswith("uid=0(QSECOFR)")
    assert sh.run("echo hello $USER ${HOME}") == ["hello STUDENT /home/STUDENT"]
    assert sh.run("export WHO=me") == [] and sh.run("echo $WHO") == ["me"]
    assert sh.run("export 9bad=1") == ["ksh: export: 9bad=1: not a valid identifier."]
    assert sh.run("echo $NOPE.") == ["."]


def test_everything_else_is_refused_and_nothing_reaches_the_host(store):
    sh = shell(store)
    assert sh.run("rm -rf /") == ["ksh: rm: not found."]
    assert sh.run("python -c 'print(1)'") == ["ksh: python: not found."]
    for line in ("ls | cat", "echo hi > /tmp/x", "cat /tmp/x; id", "id &", "echo `id`", "echo $(id)"):
        assert "not available in the simulator" in sh.run(line)[0], line
    assert "/tmp/x" not in store.ifs
    assert sh.run("echo 'unclosed") == ["ksh: a quote was not closed."]
    assert sh.run("") == [] and sh.run("# comment") == []
    assert sh.run("../etc") == ["ksh: ../etc: not found."]
    assert sh.run("cmd_pwd") == ["ksh: cmd_pwd: not found."]


def test_exit_ends_the_shell(store):
    sh = shell(store)
    assert not sh.done
    sh.run("exit")
    assert sh.done


# -- the display ----------------------------------------------------------------------------------------------

def text(s):
    return "\n".join(f.text for f in s.fields if isinstance(f, Text))


def signed(store, user="STUDENT"):
    c = SignonController("QPADEV0301", store)
    c.handle("ENTER", {"user": user, "password": user})
    return c


def test_call_qp2term_opens_the_terminal_and_commands_scroll_up_the_screen(store):
    c = signed(store)
    s = c.handle("ENTER", {"command": "CALL PGM(QP2TERM)"})
    assert "Simulated PASE terminal" in text(s) and any(i.name == "cmd" for i in s.inputs())
    s = c.handle("ENTER", {"cmd": "pwd"})
    assert "$ pwd" in text(s) and "/home/STUDENT" in text(s)
    s = c.handle("ENTER", {"cmd": "cat notes.txt"})
    assert "Things to try" in text(s) and "$ pwd" in text(s)


def test_f3_and_exit_leave_the_terminal(store):
    c = signed(store)
    c.handle("ENTER", {"command": "CALL PGM(QP2TERM)"})
    s = c.handle("F3", {})
    assert "Simulated PASE terminal" not in text(s)
    c.handle("ENTER", {"command": "CALL PGM(QP2TERM)"})
    s = c.handle("ENTER", {"cmd": "exit"})
    assert "Simulated PASE terminal" not in text(s)


def test_a_fresh_terminal_does_not_keep_the_last_one(store):
    c = signed(store)
    c.handle("ENTER", {"command": "CALL PGM(QP2TERM)"})
    c.handle("ENTER", {"cmd": "cd /tmp"})
    c.handle("F3", {})
    s = c.handle("ENTER", {"command": "CALL PGM(QP2TERM)"})
    assert "/tmp" not in text(s)
    assert "/home/STUDENT" in text(c.handle("ENTER", {"cmd": "pwd"}))


def test_a_long_line_wraps_and_the_scrollback_is_capped(store):
    c = signed(store)
    c.handle("ENTER", {"command": "CALL PGM(QP2TERM)"})
    s = c.handle("ENTER", {"cmd": "echo " + "x" * 200})
    rows = [f.text for f in s.fields if isinstance(f, Text)]
    assert all(len(r) <= 78 for r in rows) and rows.count("x" * 78) == 2 and "x" * 44 in rows      # 200 = 78 + 78 + 44
    for _ in range(30):
        s = c.handle("ENTER", {"cmd": "pwd"})
    assert len([f for f in s.fields if isinstance(f, Text)]) <= 26


def test_a_profile_without_use_authority_to_the_program_cannot_open_it(store):
    from silverlake.system.authority import EXCLUDE
    store.objects[("QSYS", "QP2TERM", "*PGM")].public = EXCLUDE
    c = signed(store)
    s = c.handle("ENTER", {"command": "CALL PGM(QP2TERM)"})
    assert "Simulated PASE terminal" not in text(s) and "uthorized" in text(s)
