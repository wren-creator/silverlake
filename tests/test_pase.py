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
    assert sh.run("pwd") == ["/home/STUDENT"] and sh.run("echo $USER") == ["STUDENT"]
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
    assert sh.run("cat $HOME/notes.txt") == ["Things to try: ls, cat, cd, id."] and sh.run("cat /QOpenSys/etc/motd")[0].startswith("Welcome")


def test_ls_long_and_hidden_and_several_paths(store):
    sh = shell(store, "OPERATOR")
    assert sh.run("ls") == [] and ".profile" in sh.run("ls -a")
    long = sh.run("ls -la")
    assert any(row.startswith("-rw-r--r--") and row.endswith(".profile") and "OPERATOR" in row for row in long)
    both = sh.run("ls /QOpenSys /tmp")
    assert both[0] == "/QOpenSys:" and "/tmp:" in both


def test_what_the_profile_may_not_touch_is_refused_in_the_shells_voice(store):
    sh = shell(store)
    assert sh.run("cat /home/OPERATOR/.profile") == ["cat: cannot open /home/OPERATOR/.profile"]
    assert sh.run("ls /home/OPERATOR") == ["ls: 0653-345 /home/OPERATOR: Permission denied."]
    assert sh.run("cd /home/OPERATOR") == ["/home/OPERATOR: Permission denied"]
    assert sh.run("ls /nowhere") == ["/nowhere not found"]
    assert sh.run("cd /nowhere") == ["/nowhere: No such file or directory"]
    assert sh.run("cd notes.txt") == ["notes.txt: Not a directory"]
    assert sh.run("cat /home") == ["cat: cannot open /home"]
    assert sh.cwd == "/home/STUDENT"


def test_a_security_officer_reads_everything(store):
    sh = shell(store, "QSECOFR")
    assert sh.run("cat /home/STUDENT/notes.txt") and sh.run("ls /home/OPERATOR") == []
    assert "Chen, Priya" in " ".join(sh.run("cat /QSYS.LIB/APPLIB.LIB/PAYROLL.FILE"))


def test_the_shell_reaches_the_object_store_through_qsys_lib_with_the_same_authority(store):
    st = shell(store)
    assert "CUSTOMERS.FILE" in st.run("ls /QSYS.LIB/APPLIB.LIB")
    assert "PAYROLL.FILE" not in st.run("ls /QSYS.LIB/APPLIB.LIB")
    assert st.run("cat /QSYS.LIB/APPLIB.LIB/PAYROLL.FILE") == ["cat: cannot open /QSYS.LIB/APPLIB.LIB/PAYROLL.FILE"]
    assert "Chen, Priya" in " ".join(shell(store, "OPERATOR").run("cat /QSYS.LIB/APPLIB.LIB/PAYROLL.FILE"))


def test_id_echo_export_and_variables(store):
    sh = shell(store)
    assert sh.run("id")[0].startswith("uid=") and "(student)" in sh.run("id")[0]
    assert shell(store, "QSECOFR").run("id")[0].startswith("uid=0(qsecofr)")
    assert sh.run("echo hello $USER ${HOME}") == ["hello STUDENT /home/STUDENT"]
    assert sh.run("export WHO=me") == [] and sh.run("echo $WHO") == ["me"]
    assert sh.run("export 9bad=1") == ["bsh: 9bad=1: is not an identifier"]       # PUB400's wording
    assert sh.run("echo $NOPE.") == ["."]


def test_everything_else_is_refused_and_nothing_reaches_the_host(store):
    sh = shell(store)
    assert sh.run("rm -rf /")[0].startswith("rm: 0653-345") and "/home" in store.ifs
    assert sh.run("python -c 'print(1)'") == ["bsh: python: not found"]
    for line in ("id &", "cat <<EOF", "(id)", "echo a & echo b", "echo )"):
        assert "not available in the simulator" in sh.run(line)[0], line
    assert sh.run("echo 'unclosed") == ["bsh: a quote was not closed."]
    assert sh.run("") == [] and sh.run("# comment") == []
    assert sh.run("../etc") == ["bsh: ../etc: not found"]
    assert sh.run("cmd_pwd") == ["bsh: cmd_pwd: not found"]


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
    assert sh.run("echo hi > /QOpenSys/etc/motd") == ["bsh: 0653-345 /QOpenSys/etc/motd: Permission denied."]
    assert sh.run("rm /QOpenSys/etc/motd")[0].startswith("rm: 0653-345")
    assert sh.run("mkdir /QSYS.LIB/NEW.LIB")[0].startswith("mkdir: 0653-345")
    assert sh.run("rm -rf /")[0].startswith("rm: 0653-345") and "/" in store.ifs
    assert sh.run("echo x > /home/OPERATOR/.profile")[0].startswith("bsh: 0653-345")
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
    assert sh.run("echo a > /nodir/x") == ["bsh: 0653-341 The file /nodir/x does not exist."]


def test_writes_are_saved_with_the_store(store):
    shell(store).run("echo kept > $HOME/k")
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
    sh.run("echo 'echo $USER' > who")
    sh.run("chmod 755 who")
    assert sh.run("./who") == ["STUDENT"] and shell(store, "QSECOFR").run("/home/STUDENT/who") == ["QSECOFR"]
    sh.run("echo ./loop > loop")
    sh.run("chmod 755 loop")
    assert "too many nested" in " ".join(sh.run("./loop"))
    assert sh.depth == 0


def test_login_reads_the_system_profile_then_the_home_profile(store):
    out = shell(store, "OPERATOR").login()
    assert out and out[0].startswith("uid=") and "(operator)" in out[0]       # the seeded .profile runs id
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
    assert any("(operator)" in line for line in term.lines)


def test_single_quotes_keep_a_dollar_sign_as_it_is(store):
    sh = shell(store)
    assert sh.run("echo '$USER' \"$USER\" $USER") == ["$USER STUDENT STUDENT"]
    assert sh.run("echo 'a b' c") == ["a b c"]


# -- the small read-only batch, wording from PUB400 --------------------------------------------------------------

def test_uname_hostname_date_logname_printenv_and_ps_say_what_pub400_said(store):
    from datetime import datetime, timezone
    sh = shell(store)
    sh.clock = lambda: datetime(2026, 10, 28, 1, 14, 40, tzinfo=timezone.utc)
    assert sh.run("uname") == ["OS400"] and sh.run("uname -s") == ["OS400"]
    assert sh.run("uname -a") == [f"OS400 SILVERLAKE 4 7 {pase.MACHINE_ID}"]       # nodename, release, version, machine
    assert sh.run("uname -r") == ["4"] and sh.run("hostname") == [pase.HOST_NAME]
    assert sh.run("date") == ["Wed Oct 28 01:14:40 UTC 2026"]
    sh.clock = lambda: datetime(2026, 10, 5, 9, 0, 0, tzinfo=timezone.utc)
    assert sh.run("date") == ["Mon Oct  5 09:00:00 UTC 2026"]                       # the day is padded with a space
    assert sh.run("logname") == ["logname: getlogin failed"]
    assert sh.run("printenv HOME") == ["/home/STUDENT"] and sh.run("printenv NOSUCHVAR") == []
    assert any(l.startswith("HOME=") for l in sh.run("printenv"))
    assert sh.run("ps") == ["    PID    TTY  TIME CMD"]


def test_head_tail_wc_and_grep_read_files_and_fail_the_way_pub400_did(store):
    sh = shell(store, "QSECOFR")
    sh.run("echo one > f")
    sh.run("echo two >> f")
    sh.run("echo three >> f")
    assert sh.run("head -n 2 f") == ["one", "two"] and sh.run("tail -n 2 f") == ["two", "three"]
    assert sh.run("head -1 f") == ["one"] and sh.run("tail f") == ["one", "two", "three"]
    assert sh.run("wc f") == ["       3       3      14 f"]
    assert sh.run("wc -l f") == ["       3 f"]
    assert sh.run("grep t f") == ["two", "three"] and sh.run("grep -c t f") == ["2"]
    assert sh.run("grep -n -v t f") == ["1:one"] and sh.run("grep -i ONE f") == ["one"]
    assert sh.run("grep nomatch f") == []
    assert sh.run("head /nosuchfile") == ["/nosuchfile: No such file or directory"]
    assert sh.run("tail /nosuchfile") == ["/nosuchfile: No such file or directory"]
    assert sh.run("wc /nosuchfile") == ["wc: cannot open /nosuchfile"]
    assert sh.run("grep x /nosuchfile") == ["grep: can't open /nosuchfile"]
    assert sh.run("head f f")[0] == "==> f <==" and sh.run("grep o f f")[0] == "f:one"
    assert sh.run("head") == [] and sh.run("grep")[0].startswith("Usage")
    assert shell(store).run("head /home/OPERATOR/.profile") == ["/home/OPERATOR/.profile: Permission denied"]


def test_grep_options_end_at_the_pattern_or_at_double_dash(store):
    sh = shell(store)
    sh.run("echo '-x marks it' > f")
    assert sh.run("grep -- -x f") == ["-x marks it"]
    assert sh.run("grep -i X -x") == ["grep: can't open -x"]                       # the second -x is a file name


# -- P1: exit statuses, ; && ||, globbing, ~ ----------------------------------------------------------------------

def status_of(sh, line):
    sh.run(line)
    return sh.status


def test_exit_statuses_follow_what_pub400_returned(store):
    sh = shell(store)
    assert status_of(sh, "pwd") == 0
    assert status_of(sh, "ls /nowhere") == 2 and status_of(sh, "cat /nowhere") == 2
    assert status_of(sh, "cd /nowhere") == 1 and status_of(sh, "head /nowhere") == 1
    assert status_of(sh, "wc /nowhere") == 2 and status_of(sh, "grep x /nowhere") == 2
    assert status_of(sh, "grep zzzz notes.txt") == 1 and status_of(sh, "grep Things notes.txt") == 0
    assert status_of(sh, "printenv NOSUCH") == 1 and status_of(sh, "printenv HOME") == 0
    assert status_of(sh, "logname") == 1 and status_of(sh, "ps") == 1
    assert status_of(sh, "nosuchcmd") == 1 and status_of(sh, "/nosuchdir/x") == 1, "bsh gives 1, not 127"
    assert status_of(sh, "mkdir /QOpenSys/x") == 1
    assert sh.run("ls /nowhere; echo $?") == ["/nowhere not found", "2"]
    assert sh.run("echo $?") == ["0"], "$? is the status of the line before"


def test_joints_read_left_to_right(store):
    sh = shell(store)
    assert sh.run("echo a; echo b") == ["a", "b"]
    assert sh.run("cd /nowhere && echo no") == ["/nowhere: No such file or directory"]
    assert sh.run("cd /tmp && echo yes") == ["yes"]
    assert sh.run("cd /nowhere || echo recovered") == ["/nowhere: No such file or directory", "recovered"]
    assert sh.run("pwd || echo never") == ["/tmp"]
    assert sh.run("cd /nowhere && echo a || echo b") == ["/nowhere: No such file or directory", "b"]
    assert sh.run("pwd && cd /nowhere || echo c; echo d")[-2:] == ["c", "d"]
    assert sh.run("echo a;") == ["a"] and sh.run("echo a ;echo b") == ["a", "b"]
    assert sh.run("cd /nowhere; pwd") [-1] == "/tmp"
    sh.run("cd; X=1; echo $X")
    assert sh.env["X"] == "1"


def test_joints_inside_quotes_are_text_and_bad_lines_are_refused(store):
    sh = shell(store)
    assert sh.run("echo 'a; b && c || d'") == ["a; b && c || d"]
    assert sh.run('echo "a;b" ; echo x#y') == ["a;b", "x#y"]
    assert sh.run("echo a # a comment; echo b") == ["a"]
    assert sh.run("echo 'a|b' '$(id)' \\| ") == ["a|b $(id) |"]
    for line in ("; echo a", "echo a ;; echo b", "echo a && && echo b", "echo a &&"):
        out = sh.run(line)
        assert out and "syntax error" in out[0] and sh.status == 2, line
    many = sh.run("; ".join(["echo x"] * 101))
    assert len(many) == 1 and "too many commands" in many[0]
    assert len(sh.run("; ".join(["echo x"] * 100))) == 100


def test_globbing_matches_what_the_profile_can_list(store):
    sh = shell(store)
    sh.run("cd /tmp")
    sh.run("touch a1.txt a2.txt b1.txt .hid")
    sh.run("mkdir sub")
    sh.run("touch sub/z.txt")
    assert sh.run("echo a*") == ["a1.txt a2.txt"]
    assert sh.run("echo *.txt") == ["a1.txt a2.txt b1.txt"]
    assert sh.run("echo ?1.txt") == ["a1.txt b1.txt"]
    assert sh.run("echo [ab]1.txt") == ["a1.txt b1.txt"] and sh.run("echo [!a]1.txt") == ["b1.txt"]
    assert sh.run("echo *") == [" ".join(sh.run("ls"))]
    assert ".hid" not in sh.run("echo *")[0] and sh.run("echo .h*") == [".hid"]
    assert sh.run("echo */z.txt") == ["sub/z.txt"] and sh.run("echo /tmp/a*") == ["/tmp/a1.txt /tmp/a2.txt"]
    assert sh.run("echo nomatch*") == ["nomatch*"]
    assert sh.run("echo 'a*' \"a*\" a\\*") == ["a* a* a*"], "quoted stars are text"
    assert sh.run("cat a*.txt") == []
    assert sh.run("rm a*.txt; ls") .count("a1.txt") == 0


def test_a_glob_only_sees_directories_the_profile_may_list(store):
    sh = shell(store)
    assert sh.run("echo /home/OPERATOR/*") == ["/home/OPERATOR/*"]
    assert "/home/STUDENT" in sh.run("echo /home/*")[0].split()
    assert sh.run("echo /home/OPER*") == ["/home/OPERATOR"], "the name shows in a directory the profile may list"
    assert sh.run("echo /home/OPERATOR/.p*") == ["/home/OPERATOR/.p*"], "what is inside does not"


def test_a_glob_has_a_cap(store):
    sh = shell(store)
    sh.run("cd /tmp")
    for i in range(30):
        sh.run(f"touch f{i}")
    assert len(sh.run("echo f*")[0].split()) == 30
    from silverlake.system import pase as module
    module.MAX_GLOB = 10
    try:
        assert len(sh.run("echo f*")[0].split()) <= 10
    finally:
        module.MAX_GLOB = 1000


def test_tilde_and_variables_in_words(store):
    sh = shell(store)
    assert sh.run("echo ~") == ["~"] and sh.run("echo ~/x") == ["~/x"], "bsh does not expand a tilde (PUB400)"
    assert sh.run("echo a~") == ["a~"] and sh.run("echo '~'") == ["~"]
    assert sh.run("cd ~") == ["~: No such file or directory"] and sh.run("pwd") == ["/home/STUDENT"]
    sh.run("cd /tmp")
    assert sh.run("cd") == [] and sh.run("pwd") == ["/home/STUDENT"], "cd with no argument still goes home"
    assert sh.run("cat ~/notes.txt") == ["cat: cannot open ~/notes.txt"]
    sh.run("W='two words'")
    assert sh.run('echo "$W" | cat') == ["two words"]
    assert sh.run('ls "$W"') == ["two words not found"], "quoted, so one word"
    assert sh.run("ls $W") == ["two not found", "words not found"], "unquoted, so two"
    assert sh.run("echo $?x ${HOME}y") == ["2x /home/STUDENTy"], "$? is the ls before, which failed"
    assert sh.run("echo a>/tmp/redir; cat /tmp/redir") == ["a"]
    assert sh.run("echo a > b > c")[0].startswith("bsh: the redirection")


def test_scripts_give_the_status_of_their_last_line_and_exit_ends_only_the_script(store):
    sh = shell(store)
    sh.run("echo 'echo in; exit 3; echo not' > /tmp/s1")
    sh.run("chmod 755 /tmp/s1")
    assert sh.run("/tmp/s1; echo $?") == ["in", "3"]
    assert not sh.done
    assert sh.run("exit 4") == [] and sh.done and sh.status == 4


def test_what_pub400_did_with_a_bad_line_and_a_failed_cd(store):
    """From the ssh-pase-p1 capture (2026-10-28). Nothing runs when the line does not parse, and the wording is bsh's."""
    sh = shell(store)
    bad = {";echo a": "end of file", "echo a ;; echo b": ";;", "echo a && && echo b": "&&", "echo a &&": "end of file",
           "echo a || || echo b": "||", "echo a ; ; echo b": ";", "echo a ||": "end of file"}
    for line, token in bad.items():
        assert sh.run(line) == [f"bsh: syntax error at line 1: `{token}' unexpected"], line
        assert sh.status == 2, line
    assert sh.run("echo a;") == ["a"] and sh.run("   ") == [] and sh.run("") == []
    # at a prompt a failed cd is a guess (carries on); with no terminal it ends the line, like PUB400
    assert sh.run("cd /nowhere || echo recovered") == ["/nowhere: No such file or directory", "recovered"]
    batch = shell(store)
    batch.batch = True
    assert batch.run("echo a && cd /nowhere || echo c; echo d") == ["a", "/nowhere: No such file or directory"]
    assert batch.done and batch.status == 1
    again = shell(store)
    again.batch = True
    assert again.run("export 9bad=1; echo $?") == ["bsh: 9bad=1: is not an identifier"] and again.done


def test_a_failed_cd_ends_a_script_and_not_the_shell(store):
    sh = shell(store)
    sh.run("echo 'cd /nowhere; echo after' > /tmp/s2")
    sh.run("chmod 755 /tmp/s2")
    assert sh.run("/tmp/s2; echo back $?") == ["/nowhere: No such file or directory", "back 1"] and not sh.done


def test_dot_star_matches_dot_and_dot_dot_as_it_did_on_pub400(store):
    sh = shell(store)
    assert sh.run("echo /QOpenSys/etc/.*") == ["/QOpenSys/etc/. /QOpenSys/etc/.."]
    assert sh.run("echo [p]rofile") == ["[p]rofile"], "nothing here matches, so it stays as typed"


# -- P2: pipes, input redirection, backticks (checked against the ssh-pase-p2 capture, 2026-10-28) --------------------

def test_a_pipe_feeds_the_next_command_what_the_last_one_printed(store):
    sh = shell(store)
    sh.run("cd /QOpenSys/etc")
    assert sh.run("echo hello | cat") == ["hello"]
    assert sh.run("echo hello | wc") == ["       1       1       6"], "counts of the input, no name after them"
    assert sh.run("echo a b c | wc -w") == ["       3"] and sh.run("echo 'a b' | wc -c") == ["       4"]
    assert sh.run("cat profile | head -n 2") == sh.run("head -n 2 profile") and len(sh.run("head -n 2 profile")) == 2
    assert sh.run("cat profile | tail -n 2") == sh.run("tail -n 2 profile")
    assert sh.run("cat profile | grep -c system") == sh.run("grep -c system profile") != ["0"] and sh.run("echo A | grep -i a") == ["A"]
    assert sh.run("echo a | cat | cat | wc -l") == ["       1"]
    assert sh.run("cat profile | head -n 1 | tail -n 1") == sh.run("head -n 1 profile")
    assert sh.run("echo a | echo b") == ["b"], "echo has no use for its input"
    assert sh.run("echo a | cat -") == ["a"]
    assert sh.run("echo a | grep a profile") == sh.run("grep a profile") != [], "a file on the line beats the pipe"


def test_a_pipeline_exits_with_its_last_commands_status(store):
    sh = shell(store)
    assert sh.run("cat /nosuchfile | cat; echo $?") == ["cat: cannot open /nosuchfile", "0"]
    assert sh.run("nosuchcmd | cat; echo $?") == ["bsh: nosuchcmd: not found", "0"]
    assert sh.run("echo hi | nosuchcmd; echo $?") == ["bsh: nosuchcmd: not found", "1"]
    assert sh.run("cat /QOpenSys/etc/profile | grep nosuchstring; echo $?") == ["1"]
    assert sh.run("echo a || echo b | cat") == ["a"] and sh.run("echo a | cat && echo b") == ["a", "b"]


def test_what_a_command_says_to_stderr_never_goes_down_the_pipe(store):
    sh = shell(store)
    assert sh.run("cat /nosuchfile | grep -c cannot") == ["cat: cannot open /nosuchfile", "0"]
    assert sh.run("cat /nosuchfile | wc -l") == ["cat: cannot open /nosuchfile", "       0"]
    sh.run("cat /nosuchfile > /tmp/out")
    assert sh.run("cat /tmp/out") == [] and sh.run("ls /nowhere > /tmp/out") == ["/nowhere not found"]
    assert sh.run("echo kept | cat > /tmp/out") == [] and sh.run("cat /tmp/out") == ["kept"]
    assert sh.run("echo gone > /dev/null") == [] and sh.run("cat /nosuchfile > /dev/null") == ["cat: cannot open /nosuchfile"]


def test_input_redirection_reads_a_file_the_profile_may_read(store):
    sh = shell(store)
    assert sh.run("wc < /QOpenSys/etc/motd") == [sh.run("wc /QOpenSys/etc/motd")[0].rsplit(" ", 1)[0]]
    assert sh.run("wc -l < /QOpenSys/etc/motd")[0].strip().isdigit()
    assert sh.run("head -n 1 < /QOpenSys/etc/motd") == sh.run("head -n 1 /QOpenSys/etc/motd")
    assert sh.run("cat < /QOpenSys/etc/motd | wc") == sh.run("wc < /QOpenSys/etc/motd")
    assert sh.run("< /QOpenSys/etc/motd head -n 1") == sh.run("head -n 1 /QOpenSys/etc/motd"), "the file may come first"
    assert sh.run("cat < /nosuchfile; echo $?") == ["bsh: /nosuchfile: cannot open", "1"]
    assert sh.run("cat < /home/OPERATOR/.profile; echo $?") == ["bsh: /home/OPERATOR/.profile: cannot open", "1"]
    assert sh.run("echo gone | cat < /QOpenSys/etc/motd") == sh.run("cat /QOpenSys/etc/motd"), "a file beats the pipe"
    assert sh.run("cat < /dev/null") == []
    sh.run("cat < /QOpenSys/etc/motd > /tmp/copy")
    assert sh.run("cat /tmp/copy") == sh.run("cat /QOpenSys/etc/motd")


def test_backticks_bring_back_what_a_command_printed(store):
    sh = shell(store)
    assert sh.run("echo `echo tick`") == ["tick"] and sh.run("echo `echo 'x y'`") == ["x y"]
    assert sh.run('echo "`echo a b`" `echo c d`') == ["a b c d"]
    assert sh.run('ls "`echo a b`"') == ["a b not found"], "quoted, so one word"
    assert sh.run("ls `echo a b`") == ["a not found", "b not found"], "unquoted, so split"
    sh.run("X=`echo val`")
    assert sh.env["X"] == "val" and sh.run("echo `echo $X`!") == ["val!"]
    assert sh.run("echo `echo a; echo b`") == ["a b"] and sh.run("echo `echo a | wc -l`") == ["1"]
    assert sh.run("echo '`echo no`' \\`x") == ["`echo no` `x"]
    assert sh.run("echo `echo \\`echo inner\\``") == ["inner"], "backslash backtick nests"
    assert sh.run("echo `nosuchcmd`; echo $?") == ["bsh: nosuchcmd: not found", "", "0"], "stderr shows, the substitution is empty"


def test_a_backtick_command_cannot_change_the_shell_that_ran_it(store):
    sh = shell(store)
    sh.run("cd /tmp")
    sh.run("echo `cd /QOpenSys; export LEAK=1; exit 3`")
    assert sh.run("pwd") == ["/tmp"] and "LEAK" not in sh.env and not sh.done
    sh.run("echo 'echo `/tmp/rec`' > /tmp/rec")
    sh.run("chmod 755 /tmp/rec")
    out = sh.run("/tmp/rec")                                # a script that runs itself in a backtick has to stop
    assert any("too many nested" in l for l in out) and not sh.done


def test_dollar_paren_is_a_syntax_error_as_in_bsh_and_text_inside_quotes(store):
    sh = shell(store)
    assert sh.run("echo $(echo inner)") == ["bsh: syntax error at line 1: `(' unexpected"] and sh.status == 2
    assert sh.run("echo a; echo $(id)") == ["bsh: syntax error at line 1: `(' unexpected"], "nothing runs"
    assert sh.run('echo "$(echo inner)"') == ["$(echo inner)"] and sh.run("echo '$(id)'") == ["$(id)"]


def test_a_trailing_pipe_runs_nothing_and_a_bad_pipe_is_a_syntax_error(store):
    sh = shell(store)
    sh.status = 5
    assert sh.run("echo a |") == [] and sh.status == 0, "PUB400 printed nothing and exited 0"
    assert sh.run("| cat") == ["bsh: syntax error at line 1: `|' unexpected"] and sh.status == 2
    assert sh.run("echo a | | cat") == ["bsh: syntax error at line 1: `|' unexpected"]
    assert sh.run("cat <") == ["bsh: syntax error at line 1: `end of file' unexpected"] and sh.status == 2
    assert sh.run("echo 'a|b' \"c|d\" e\\|f") == ["a|b c|d e|f"], "a quoted bar is text"


def test_pipelines_and_substitutions_are_capped(store):
    sh = shell(store)
    assert sh.run(" | ".join(["cat"] * 21)) == ["bsh: too many commands in one pipeline (the simulator stops at 20)."]
    assert sh.run("echo a" + " | cat" * 19) == ["a"]
    sh.run("cd /tmp")
    sh.run("echo " + "x" * 200 + " > big")
    from silverlake.system import pase as module
    module.SUB_LIMIT = 50
    try:
        assert len(sh.run("echo `cat big`")[0]) == 50
    finally:
        module.SUB_LIMIT = 64 * 1024


# -- B2: files and lookup (ssh-pase-b2 capture, 2026-10-28) --------------------------------------------------------------

def test_basename_and_dirname_follow_pub400(store):
    sh = shell(store)
    assert sh.run("basename /a/b/c.txt") == ["c.txt"] and sh.run("basename /a/b/c.txt .txt") == ["c"]
    assert sh.run("basename /a/b/") == ["b"] and sh.run("basename /") == ["/"]
    assert sh.run("basename c.txt txt") == ["c."], "the suffix is a plain string, not an extension"
    assert sh.run("basename c.txt c.txt") == ["c.txt"], "a suffix that is the whole name stays"
    assert sh.run("basename") == ["Usage: basename string [suffix]"] and sh.status == 1
    assert sh.run("dirname /a/b/c") == ["/a/b"] and sh.run("dirname c") == ["."] and sh.run("dirname /") == ["/"]
    assert sh.run("dirname /a") == ["/"] and sh.run("dirname /a/b/") == ["/a"]
    assert sh.run("dirname") == ["."] and sh.status == 0, "PUB400 printed a dot and exited 0"
    assert sh.run("echo `dirname /x/y/z`/`basename /x/y/z`") == ["/x/y/z"]


def test_which_and_type_look_along_path_in_order(store):
    sh = shell(store)
    assert sh.run("which ls") == ["/QOpenSys/usr/bin/ls"] and sh.run("which cd") == ["/QOpenSys/usr/bin/cd"]
    assert sh.run("which ls cat") == ["/QOpenSys/usr/bin/ls", "/QOpenSys/usr/bin/cat"]
    assert sh.run("which db2") == ["/usr/bin/db2"]
    assert sh.run("which nosuchcmd; echo $?") == ["no nosuchcmd in /QOpenSys/usr/bin /usr/bin", "1"]
    assert sh.run("which export") == ["no export in /QOpenSys/usr/bin /usr/bin"], "a shell word with no program"
    assert sh.run("type ls") == ["ls is /QOpenSys/usr/bin/ls"]
    assert sh.run("type cd") == ["cd is a shell builtin"] and sh.run("type echo") == ["echo is a shell builtin"]
    assert sh.run("type nosuchcmd; echo $?") == ["nosuchcmd not found ", "1"], "to stdout, with PUB400's trailing space"
    # a planted program in a directory earlier on PATH is what the shell and `which` both find
    sh.run("mkdir /tmp/early")
    sh.run("echo 'echo hijacked' > /tmp/early/id")
    sh.run("chmod 755 /tmp/early/id")
    sh.run("PATH=/tmp/early:/QOpenSys/usr/bin")
    assert sh.run("which id") == ["/tmp/early/id"] and sh.run("type id") == ["id is /tmp/early/id"] and sh.run("id") == ["hijacked"]
    assert sh.run("which ls") == ["/QOpenSys/usr/bin/ls"]


def test_test_and_bracket_answer_in_the_status(store):
    sh = shell(store)
    def t(line):
        sh.run(line)
        return sh.status
    assert t("test -f /QOpenSys/etc/motd") == 0 and t("test -d /QOpenSys/etc") == 0 and t("test -d /QOpenSys/etc/motd") == 1
    assert t("test -e /nosuch") == 1 and t("test -r /QOpenSys/etc/motd") == 0 and t("test -w /QOpenSys/etc/motd") == 1
    assert t("test -s /QOpenSys/etc/motd") == 0 and t("test -s /nosuch") == 1
    assert t("test -x /QOpenSys/usr/bin/ls") == 0, "the simulator's own commands count as programs"
    assert t("test -z ''") == 0 and t("test -n x") == 0 and t("test -n ''") == 1
    assert t("test a = a") == 0 and t("test a = b") == 1 and t("test a != b") == 0
    assert t("test 3 -lt 5") == 0 and t("test 5 -lt 3") == 1 and t("test 3 -lt x") == 1, "not a number is false, with no message"
    assert t("test ! -f /nosuch") == 0 and t("test -f /QOpenSys/etc/motd -a -d /QOpenSys/etc") == 0
    assert t("test -f /nosuch -o -d /QOpenSys/etc") == 0 and t("test -f /nosuch -a -d /QOpenSys/etc") == 1
    assert t("test") == 1 and t("test x") == 0 and t("test ''") == 1
    assert t("[ -f /QOpenSys/etc/motd ]") == 0 and t("[ 2 -gt 3 ]") == 1
    assert sh.run("test -f /QOpenSys/etc/motd && echo yes || echo no") == ["yes"]
    assert sh.run("[ -d /tmp ] && echo dir") == ["dir"]


def test_a_test_with_a_missing_operand_ends_a_shell_with_no_terminal(store):
    sh = shell(store)
    assert sh.run("test -f; echo $?") == ["bsh: test: argument expected", "1"] and not sh.done, "at a prompt it carries on"
    assert sh.run("[ -f /QOpenSys/etc/motd; echo $?") == ["bsh: test: ] missing", "1"]
    batch = shell(store)
    batch.batch = True
    assert batch.run("test -f; echo $?") == ["bsh: test: argument expected"] and batch.done and batch.status == 1
    again = shell(store)
    again.batch = True
    assert again.run("[ -f /QOpenSys/etc/motd; echo $?") == ["bsh: test: ] missing"] and again.done


def test_file_says_what_pub400_said(store):
    sh = shell(store)
    assert sh.run("file /QOpenSys/etc/motd") == ["/QOpenSys/etc/motd: ascii text"]
    assert sh.run("file /QOpenSys/etc") == ["/QOpenSys/etc: directory"]
    assert sh.run("file /nosuchfile; echo $?") == ["file: cannot open /nosuchfile", "0"], "to stdout, exit 0"
    sh.run("touch /tmp/empty")
    assert sh.run("file /tmp/empty") == ["/tmp/empty: empty"]


def test_rmdir_removes_only_an_empty_directory_the_profile_may_change(store):
    sh = shell(store)
    assert sh.run("rmdir; echo $?") == ["Usage: rmdir [-p] Directory ...", "2"]
    assert sh.run("rmdir /nosuchdir; echo $?") == ["rmdir: /nosuchdir not removed.", "Permission denied", "2"], "the parent / is not STUDENT's"
    assert sh.run("rmdir /QOpenSys/etc/motd; echo $?")[-1] == "2"
    sh.run("mkdir /tmp/d1")
    sh.run("touch /tmp/d1/f")
    assert sh.run("rmdir /tmp/d1")[0] == "rmdir: /tmp/d1 not removed." and "/tmp/d1" in store.ifs, "not empty"
    sh.run("rm /tmp/d1/f")
    assert sh.run("rmdir /tmp/d1") == [] and "/tmp/d1" not in store.ifs
    assert sh.run("rmdir /tmp/nowhere")[1] == "No such file or directory"
    sh.run("touch /tmp/afile")
    assert sh.run("rmdir /tmp/afile")[1] == "A path name is not a directory" and "/tmp/afile" in store.ifs, "a file is never removed by rmdir"
    sh.run("mkdir -p /tmp/p/q/r")
    assert sh.run("rmdir -p /tmp/p/q/r") == [] and "/tmp/p" not in store.ifs
    assert sh.run("rmdir /QSYS.LIB/APPLIB.LIB; echo $?")[-1] == "2"


def test_umask_sets_the_permissions_new_files_get(store):
    sh = shell(store)
    assert sh.run("umask") == ["022"]
    sh.run("touch /tmp/u1")
    sh.run("mkdir /tmp/u1d")
    n = store.ifs["/tmp/u1"]
    assert (n.owner_mode, n.public) == ("rw-", "r--") and store.ifs["/tmp/u1d"].public == "r-x"
    assert sh.run("umask 077; umask") == ["077"]
    sh.run("touch /tmp/u2")
    sh.run("echo hi > /tmp/u3")
    sh.run("mkdir /tmp/u2d")
    assert store.ifs["/tmp/u2"].public == "---" and store.ifs["/tmp/u3"].public == "---" and store.ifs["/tmp/u2d"].public == "---"
    assert store.ifs["/tmp/u2"].owner_mode == "rw-"
    sh.run("umask 000")
    sh.run("touch /tmp/u4")
    sh.run("mkdir /tmp/u4d")
    assert store.ifs["/tmp/u4"].public == "rw-" and store.ifs["/tmp/u4d"].public == "rwx", "a mask of 0 opens it to everyone"
    sh.run("umask 027")
    assert sh.run("umask") == ["027"]
    assert sh.run("umask -S; echo $?") == ["0"] and sh.run("umask 99; echo $?") == ["0"], "PUB400 ignored both, silently"
    assert sh.run("umask") == ["027"]
    assert shell(store).run("umask") == ["022"], "each shell starts at 022"


def test_du_counts_blocks_the_way_pub400_did(store):
    sh = shell(store)
    sh.run("cd /tmp")
    sh.run("echo small > f1")
    assert sh.run("du -s f1") == ["8\tf1"] and sh.run("du -k f1") == ["4\tf1"], "512 byte blocks, 4 KB units"
    sh.run("echo " + "x" * 5000 + " > f2")
    assert sh.run("du -s f2") == ["16\tf2"]
    sh.run("mkdir -p tree/a/b")
    sh.run("echo hi > tree/a/b/f")
    assert sh.run("du tree") == ["16\ttree/a/b", "24\ttree/a", "32\ttree"], "directories, deepest first, each with what is below"
    assert sh.run("du -s tree") == ["32\ttree"] and sh.run("du -sk tree") == ["16\ttree"]
    assert sh.run("du -a tree")[0] == "8\ttree/a/b/f"
    assert sh.run("du /nosuchdir; echo $?") == ["du: /nosuchdir: No such file or directory", "2"]
    assert sh.run("du /home/OPERATOR; echo $?")[-1] == "2"


def test_find_walks_a_tree_under_the_profiles_view_of_it(store):
    sh = shell(store)
    assert sh.run("find /QOpenSys/etc/motd") == ["/QOpenSys/etc/motd"]
    assert sh.run("find /nosuchdir; echo $?") == ["find: bad status-- /nosuchdir", "1"]
    assert sh.run("find /QOpenSys/etc -name 'mo*'") == ["/QOpenSys/etc/motd"]
    assert sh.run("find /QOpenSys/etc -name motd -type f") == ["/QOpenSys/etc/motd"]
    assert sh.run("find /QOpenSys/etc -name motd -type d") == [] and "/QOpenSys/etc/ssh" in sh.run("find /QOpenSys/etc -type d")
    assert sh.run("find /QOpenSys/etc -name motd -print") == ["/QOpenSys/etc/motd"]
    assert sh.run("find /QOpenSys/etc -name 'mo*' -o -name 'pro*'") == ["/QOpenSys/etc/motd", "/QOpenSys/etc/profile"]
    assert sh.run("find /QOpenSys/etc -maxdepth 1; echo $?") == ["find: bad option -maxdepth", "1"]
    assert sh.run("find /QOpenSys/etc -user nosuchuser; echo $?") == ["find: cannot find -user name", "1"]
    assert sh.run("find /QOpenSys/etc -user qsys -name motd") == ["/QOpenSys/etc/motd"]
    sh.run("cd /QOpenSys/etc")
    assert sh.run("find . -name motd") == ["./motd"] and sh.run("find ssh -name '*.conf'")[0].startswith("ssh/sshd_config.d/")
    assert sh.run("find") == ["Usage: find path-list [predicate-list]"] and sh.status == 1


def test_find_perm_is_how_a_student_finds_what_anyone_can_write(store):
    sh = shell(store)
    wide = sh.run("find / -perm -002")
    assert "/tmp" in wide and "/tmp/opsbin" in wide and "/QOpenSys/etc/profile" in wide
    assert "/QOpenSys/etc/motd" not in wide and "/QOpenSys/var/ops/README" not in wide
    assert sh.run("find /QOpenSys/etc -perm 644") == ["/QOpenSys/etc/motd"] or "/QOpenSys/etc/motd" in sh.run("find /QOpenSys/etc -perm 644")
    assert "/QOpenSys/etc/motd" in sh.run("find /QOpenSys/etc -perm -004") and "/QOpenSys/etc/motd" not in sh.run("find /QOpenSys/etc -perm -040 -type d")
    assert sh.run("find /QOpenSys/etc -perm 9") and sh.status == 1
    # it only lists what the profile may list
    assert "/home/OPERATOR/.profile" not in sh.run("find /home -name .profile")


def test_find_and_du_stop_at_a_cap(store):
    from silverlake.system import pase as module
    sh = shell(store)
    module.MAX_FIND = 5
    try:
        out = sh.run("find / -name '*'")
        assert out[-1].startswith("find: stopped after 5 entries") and sh.status == 1
    finally:
        module.MAX_FIND = 5000


def test_pase_find_writable_lists_what_anyone_can_write_and_the_fix_closes_it(store):
    from silverlake import flags, scenarios
    base = "/QOpenSys/var/ops"
    want = f"{base}/backup.sh,{base}/jobs.conf,{base}/spool"
    assert flags.FACTS["world_writable_ops"](store) == want
    sh = shell(store)
    assert ",".join(sh.run(f"find {base} -perm -002")) == want, "what find shows is the answer"
    assert f"{base}/README" not in want and f"{base}/notes.txt" not in want
    assert sh.run(f"echo more >> {base}/jobs.conf") == [] and "more" in store.ifs[f"{base}/jobs.conf"].content
    scenarios.apply(store, scenarios.registry()["pase-find-writable"], "secure")
    assert flags.FACTS["world_writable_ops"](store) == "none" and sh.run(f"find {base} -perm -002") == []
    assert sh.run(f"echo more >> {base}/jobs.conf")[0].startswith("bsh:")
    assert sh.run(f"touch {base}/spool/x")[0].startswith("touch:")
