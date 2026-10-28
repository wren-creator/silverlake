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
    assert sh.run("ls") == ["motd", "profile", "ssh"]
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
    assert sh.run("rm -rf /")[0].startswith("rm: 0653-345") and "/home" in store.ifs
    assert sh.run("python -c 'print(1)'") == ["ksh: python: not found."]
    for line in ("ls | cat", "cat < /tmp/x", "cat /tmp/x; id", "id &", "echo `id`", "echo $(id)"):
        assert "not available in the simulator" in sh.run(line)[0], line
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


# -- the writing set -------------------------------------------------------------------------------------------

def test_files_and_directories_can_be_made_changed_and_removed_where_the_profile_may(store):
    sh = shell(store)
    assert sh.run("mkdir work") == [] and sh.run("touch work/a") == []
    assert sh.run("echo hi > work/a") == [] and sh.run("echo there >> work/a") == []
    assert sh.run("cat work/a") == ["hi", "there"]
    assert sh.run("cp work/a work/b") == [] and sh.run("mv work/b /tmp/b") == []
    assert sh.run("ls work") == ["a"] and sh.run("cat /tmp/b") == ["hi", "there"]
    assert store.ifs["/tmp/b"].owner == "STUDENT"
    assert sh.run("rm work") == ["rm: 0653-603 work is a directory."]
    assert sh.run("rm -r work") == [] and "/home/STUDENT/work" not in store.ifs and "/home/STUDENT/work/a" not in store.ifs
    assert sh.run("rm /tmp/b") == [] and sh.run("rm /tmp/b") == ["rm: 0653-341 The file /tmp/b does not exist."]
    assert sh.run("rm -f /tmp/b") == []
    assert sh.run("mkdir -p a/b/c") == [] and "/home/STUDENT/a/b/c" in store.ifs


def test_writes_are_refused_without_write_on_the_directory(store):
    sh = shell(store)
    assert sh.run("touch /home/x") == ["touch: 0653-345 /home/x: Permission denied."]
    assert sh.run("echo hi > /QOpenSys/etc/motd") == ["ksh: 0653-345 /QOpenSys/etc/motd: Permission denied."]
    assert sh.run("rm /QOpenSys/etc/motd")[0].startswith("rm: 0653-345")
    assert sh.run("mkdir /QSYS.LIB/NEW.LIB")[0].startswith("mkdir: 0653-345")
    assert sh.run("rm -rf /")[0].startswith("rm: 0653-345") and "/" in store.ifs
    assert sh.run("echo x > /home/OPERATOR/.profile")[0].startswith("ksh: 0653-345")
    assert sh.run("mkdir w") == [] and sh.run("mkdir w") == ["mkdir: 0653-340 w already exists."]


def test_chmod_by_octal_and_symbol_and_only_for_the_owner(store):
    sh = shell(store)
    assert sh.run("touch f") == [] and sh.run("chmod 600 f") == []
    assert store.ifs["/home/STUDENT/f"].public == "---"
    assert sh.run("chmod o+w f") == [] and store.ifs["/home/STUDENT/f"].public == "-w-"
    assert sh.run("chmod a-w f") == [] and store.ifs["/home/STUDENT/f"].owner_mode == "r--"
    assert sh.run("chmod u+w f") == [] and sh.run("chmod 7z f") == ["chmod: 0653-350 7z: invalid mode."]
    assert sh.run("chmod 777 /QOpenSys/etc/motd")[0].startswith("chmod: 0653-349")
    assert shell(store, "QSECOFR").run("chmod 666 /QOpenSys/etc/motd") == []


def test_a_world_writable_file_can_be_changed_by_anyone(store):
    assert shell(store, "QSECOFR").run("chmod 666 /QOpenSys/etc/profile") == []
    assert shell(store).run("echo owned >> /QOpenSys/etc/profile") == []
    assert shell(store).run("cat /QOpenSys/etc/profile")[-1] == "owned"


def test_system_runs_cl_as_the_signed_on_profile_and_nothing_more(store):
    sh = shell(store)
    assert "STUDENT" in " ".join(sh.run("system 'DSPUSRPRF USRPRF(STUDENT)'"))
    assert sh.run("system 'NOSUCHCMD'")[0].startswith("CPD") or "not found" in sh.run("system 'NOSUCHCMD'")[0]
    assert sh.run("system") == ["system: 0653-401 usage: system 'CL command'"]
    assert sh.run("system 'CRTUSRPRF USRPRF(EVIL) PASSWORD(X) SPCAUT(*ALLOBJ)'") and "EVIL" not in store.profiles


def test_a_redirect_must_end_the_line(store):
    sh = shell(store)
    assert "last thing" in sh.run("echo a > x y z >")[0] or "last thing" in sh.run("echo > x extra")[0]
    assert sh.run("echo a > /nodir/x") == ["ksh: 0653-341 The file /nodir/x does not exist."]


def test_writes_are_saved_with_the_store(store):
    shell(store).run("echo kept > ~/k")
    again = ifs.from_rows(ifs.to_rows(store.ifs))
    assert again["/home/STUDENT/k"].content == "kept\n"


# -- scripts, PATH and login ----------------------------------------------------------------------------------

def test_a_script_needs_x_and_is_found_along_path_before_the_simulators_own_command(store):
    sh = shell(store)
    sh.run("mkdir bin")
    sh.run("echo 'echo hijacked' > bin/id")
    assert sh.run("export PATH=/home/STUDENT/bin:$PATH") == []
    assert sh.run("id")[0].startswith("uid=")                     # no x yet: only text, the shell skips it
    sh.run("chmod 755 bin/id")
    assert sh.run("id") == ["hijacked"]
    assert sh.run("./bin/id") == ["hijacked"] and sh.run("/home/STUDENT/bin/id") == ["hijacked"]
    assert sh.run("echo $PATH") != ["hijacked"]                   # echo is the shell's own, nothing can replace it


def test_a_script_runs_as_whoever_runs_it_and_nests_only_so_far(store):
    sh = shell(store)
    sh.run("echo whoami > who")
    sh.run("chmod 755 who")
    assert sh.run("./who") == ["STUDENT"] and shell(store, "QSECOFR").run("/home/STUDENT/who") == ["QSECOFR"]
    sh.run("echo ./loop > loop")
    sh.run("chmod 755 loop")
    assert "too many nested" in " ".join(sh.run("./loop"))
    assert sh.depth == 0


def test_login_reads_the_system_profile_then_the_home_profile(store):
    out = shell(store, "OPERATOR").login()
    assert out and out[0].startswith("uid=") and "(OPERATOR)" in out[0]       # the seeded .profile runs id
    sh = shell(store, "OPERATOR")
    sh.login()
    assert sh.env["PATH"].startswith("/tmp/opsbin:") and sh.env["EDITOR"] == "vi"
    assert shell(store).login() == []                                         # STUDENT has no .profile


def test_the_terminal_shows_what_the_login_printed():
    from silverlake.screens.pdm import Context
    from silverlake.screens.pase import PaseTerm
    store = profiles.load()
    store.profiles["OPERATOR"]
    term = PaseTerm(Context(store, store.profiles["OPERATOR"], None, lambda line: None))
    assert any("(OPERATOR)" in line for line in term.lines)
