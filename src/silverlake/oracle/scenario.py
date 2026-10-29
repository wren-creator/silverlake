"""Scenarios: what to do on a host, and the capture format.

A scenario is a list of actions. The harness first waits for the host's opening
screen, then for each action presses a key (typing into fields first) and waits
for the next screen. Every screen waited on is snapshotted, so a scenario with
N actions yields N + 1 snapshots.

Field values may use ${NAME} to read an environment variable, so a scenario can
sign on with a real profile without the password ever being written into the
repo. Scenarios that fail a sign-on use a made-up user, never a real one, so a
real profile never racks up failed attempts.
"""

import asyncio
import ipaddress
import os
import random
import re
import time
from datetime import UTC, datetime
from pathlib import Path

from .client import Capture, CaptureError, Client

SCENARIOS: dict[str, list[dict]] = {
    # The opening screen, nothing typed.
    "signon": [],
    # A user that does not exist, so no real profile counts a failed attempt.
    "signon-unknown-user": [
        {"fill": {"0": "SLNOUSR1", "1": "notarealpw1"}, "key": "ENTER"},
    ],
}

# Scenarios that sign on as a real (test) profile. The user and password come
# from the environment, never from a file, and a password is never sent over a
# cleartext connection to anything but loopback. Every scenario ends by typing
# SIGNOFF, so the job does not linger on a shared system. F3 on the real MAIN
# menu does not sign off (the first run on PUB400 showed that).
USER_ENV, PASS_ENV = "SILVERLAKE_ORACLE_USER", "SILVERLAKE_ORACLE_PASS"
# A scenario that creates something names it ${SILVERLAKE_ORACLE_TESTLIB}. The harness
# makes a fresh random name for every run and overrides any value from the environment,
# so a delete can only ever target a library this run created.
TESTLIB_ENV = "SILVERLAKE_ORACLE_TESTLIB"
_SIGNON = {"fill": {"0": "${%s}" % USER_ENV, "1": "${%s}" % PASS_ENV}, "key": "ENTER"}


_SIGNOFF = {"fill": {"0": "SIGNOFF"}, "key": "ENTER"}


def _cmd(line: str) -> list[dict]:
    """Run one command from the menu's command line, then F3 back."""
    return [{"fill": {"0": line}, "key": "ENTER"}, {"key": "F3"}]


_TESTLIB = "${%s}" % TESTLIB_ENV

AUTHENTICATED: dict[str, list[dict]] = {
    # Sign on, look at the first screen, sign off. Run this before any other.
    "auth-probe": [_SIGNON, _SIGNOFF],
    # Read-only questions about libraries and authority.
    "auth-libs": [_SIGNON, *_cmd("DSPLIBL"), *_cmd("DSPOBJAUT OBJ(QSYS) OBJTYPE(*LIB)"),
                  *_cmd("DSPOBJAUT OBJ(QGPL) OBJTYPE(*LIB)"), _SIGNOFF],
    # Read-only questions about finding objects and authorization lists. The two last ones
    # are expected to be refused, and the refusal wording is what is being collected.
    "auth-objects": [_SIGNON, *_cmd("WRKOBJ OBJ(QSYS/QGPL) OBJTYPE(*LIB)"),
                     *_cmd("WRKOBJ OBJ(QSYS/QSYS*) OBJTYPE(*LIB)"),
                     *_cmd("WRKOBJOWN USRPRF(*CURRENT) OBJTYPE(*LIB)"),
                     *_cmd("WRKOBJ OBJ(SLNOSUCH/*ALL)"),
                     *_cmd("WRKAUTL AUTL(*ALL)"), *_cmd("DSPAUTL AUTL(QPWFSERVER)"),
                     *_cmd("WRKOBJOWN USRPRF(QSYS)"), _SIGNOFF],
}
# The only scenario that changes the host. Creates a throwaway library, looks at the
# authority a new library gets, deletes it, and signs off. Delete and display only
# run if the host said the library was created.
AUTHENTICATED["auth-crtlib"] = [
    _SIGNON,
    {"fill": {"0": f"CRTLIB LIB({_TESTLIB}) TEXT('Silverlake oracle test, deleted at once')"}, "key": "ENTER",
     "proceed_if": [_TESTLIB, "created"]},
    *_cmd(f"DSPOBJAUT OBJ({_TESTLIB}) OBJTYPE(*LIB)"),
    {"fill": {"0": f"DLTLIB LIB({_TESTLIB})"}, "key": "ENTER"},
    {**_SIGNOFF, "always": True},
]
# Captures the Edit Authority (2), Display Description (8) and Delete (4) screens of Work with
# Objects. It makes one throwaway data area in QTEMP, which belongs to this job alone and is gone
# at sign-off, with a fresh random name the environment cannot choose, so every option is pressed
# on a list that holds only that object. Nothing here touches a library or an object that was
# there before. Every step after the create is skipped unless the host said it was created, the
# delete is only confirmed on a screen that shows the name and "confirm", and every exit key runs
# whatever happened. Order matters: cancel the first delete, then do it for real.
_QT = f"QTEMP/{_TESTLIB}"
_MADE = [_TESTLIB, "created"]
_LIST = {"proceed_if": [_TESTLIB]}


def _optkey(opt: str, **extra) -> dict:
    return {"fill": {"0": opt}, "key": "ENTER", **extra}


AUTHENTICATED["auth-objopts"] = [
    _SIGNON,
    {"fill": {"0": f"CRTDTAARA DTAARA({_QT}) TYPE(*CHAR) LEN(10) TEXT('Silverlake oracle test, job-local')"},
     "key": "ENTER", "proceed_if": _MADE},
    {"fill": {"0": f"WRKOBJ OBJ({_QT}) OBJTYPE(*DTAARA)"}, "key": "ENTER", **_LIST},
    _optkey("2", **_LIST), {"key": "F12", "always": True},        # Edit Object Authority, then back
    _optkey("8", **_LIST), {"key": "F12", "always": True},        # Display Object Description
    _optkey("4", proceed_if=[_TESTLIB, "confirm"]), {"key": "F12", "always": True},   # cancel the delete
    _optkey("4", proceed_if=[_TESTLIB, "confirm"]),                # now confirm it, on our own object
    {"key": "ENTER"},
    *[{"key": "F12", "always": True}] * 2,
    *[{"key": "F3", "always": True}] * 3,                          # harmless on the menu
    {**_SIGNOFF, "always": True},
]
# Read only: the basic and full descriptions of a system library, and the second page of the full one.
AUTHENTICATED["auth-objdesc"] = [
    _SIGNON,
    *_cmd("DSPOBJD OBJ(QSYS/QGPL) OBJTYPE(*LIB) DETAIL(*BASIC)"),
    {"fill": {"0": "DSPOBJD OBJ(QSYS/QGPL) OBJTYPE(*LIB) DETAIL(*FULL)"}, "key": "ENTER"},
    {"key": "ROLLUP"}, {"key": "F12", "always": True}, {"key": "F3", "always": True},
    _SIGNOFF,
]
# Read only: the three job, spool and message displays, looked at and left with F3. WRKACTJOB on a
# shared system shows other people's job names, which stay in the local capture and nowhere else.
AUTHENTICATED["auth-jobs"] = [
    _SIGNON, *_cmd("WRKACTJOB"), *_cmd("WRKSPLF"), *_cmd("DSPMSG"), _SIGNOFF,
]
# Read only: opens the first of the profile's own spool files with option 5 (display) and 8 (attributes)
# and backs out. Nothing is changed, held, deleted or sent. Skipped unless the list has a file.
AUTHENTICATED["auth-spool"] = [
    _SIGNON,
    {"fill": {"0": "WRKSPLF"}, "key": "ENTER", "proceed_if": ["QPJOBLOG"]},
    _optkey("5", proceed_if=["QPJOBLOG"]), {"key": "F12", "always": True},
    _optkey("8", proceed_if=["QPJOBLOG"]), {"key": "F12", "always": True},
    *[{"key": "F12", "always": True}] * 2, *[{"key": "F3", "always": True}] * 2,
    {**_SIGNOFF, "always": True},
]
# Read only: the profile's own message queue, the system operator's queue, and the SNDMSG prompt, which
# is opened and cancelled with F12. Nothing is sent, answered, removed or cleared.
AUTHENTICATED["auth-msgs"] = [
    _SIGNON, *_cmd("DSPMSG"), *_cmd("DSPMSG MSGQ(QSYSOPR)"),
    {"fill": {"0": "SNDMSG"}, "key": "ENTER"}, {"key": "F12", "always": True},
    *[{"key": "F3", "always": True}] * 2,
    {**_SIGNOFF, "always": True},
]
# Read only: the profile's own job log and its own Work with Job menu, each looked at and left with F3 and
# F12. Nothing is changed, held, ended or sent. WRKJOB with no parameters is the profile's own job.
AUTHENTICATED["auth-joblog"] = [
    _SIGNON, *_cmd("DSPJOBLOG"), *_cmd("WRKJOB"),
    *[{"key": "F12", "always": True}] * 2, *[{"key": "F3", "always": True}] * 2,
    {**_SIGNOFF, "always": True},
]
# Read only: the profile's own job through DSPJOB, then its status, definition and run attribute pages
# (options 1, 2, 3), each looked at and left with F12. Nothing is changed, held, ended or sent.
AUTHENTICATED["auth-dspjob"] = [
    _SIGNON, {"fill": {"0": "DSPJOB"}, "key": "ENTER"},
    {"fill": {"0": "1"}, "key": "ENTER"}, {"key": "F12", "always": True},
    {"fill": {"0": "2"}, "key": "ENTER"}, {"key": "F12", "always": True},
    {"fill": {"0": "3"}, "key": "ENTER"}, {"key": "F12", "always": True},
    {"key": "F12", "always": True}, {"key": "F3", "always": True},
    {**_SIGNOFF, "always": True},
]
# Read only: the prompts behind options 1, 2, 7 and 9 of Work with All Spooled Files (send, change, messages,
# printing status), each opened on the profile's own first file and left with F12. Never 4, never Enter on a
# prompt: nothing is sent, changed, deleted or answered. Each way back carries the check that the list is
# really there, so a screen that did not appear cannot lead to an option pressed on the wrong one.
_SPLLIST = {"proceed_if": ["Work with All Spooled Files"]}
AUTHENTICATED["auth-splopts"] = [
    _SIGNON, {"fill": {"0": "WRKSPLF"}, "key": "ENTER", "proceed_if": ["QPJOBLOG"]},
    *[step for opt in ("1", "2", "9", "7")      # 7 last: it answers on the list itself, and F12 then leaves it
      for step in (_optkey(opt), {"key": "F12", "always": True, **_SPLLIST})],
    {"key": "F12", "always": True}, {"key": "F3", "always": True},
    {**_SIGNOFF, "always": True},
]
# Read only: what the job screens have behind them that is not built yet. The profile's own job through
# DSPJOB and WRKJOB: page two of each menu, options 11, 12, 14, 15 and 16 (call stack, locks, open files,
# overrides, commitment control), and page two of the status and definition pages. Every screen is looked
# at and left with F12. A check runs on the screen a step produced, so each way back to a menu carries the
# check that the menu is really there: if it is not, no further option is pressed. Nothing is changed,
# held, ended or sent.
_MENU = {"proceed_if": ["Select one of the following"]}
_BACK = {"key": "F12", "always": True, **_MENU}
AUTHENTICATED["auth-dspjob2"] = [
    _SIGNON, {"fill": {"0": "DSPJOB"}, "key": "ENTER", **_MENU},
    {"key": "ROLLUP", **_MENU}, {"key": "ROLLDOWN", **_MENU},
    *[step for opt in ("11", "12", "14", "15", "16") for step in (_optkey(opt), _BACK)],
    _optkey("1"), {"key": "ROLLUP"}, _BACK,
    _optkey("2"), {"key": "ROLLUP"}, _BACK,
    {"key": "F12", "always": True},
    {"fill": {"0": "WRKJOB"}, "key": "ENTER", **_MENU},
    {"key": "ROLLUP", **_MENU}, {"key": "ROLLDOWN", **_MENU},
    _optkey("12"), _BACK,
    {"key": "F12", "always": True}, {"key": "F3", "always": True},
    {**_SIGNOFF, "always": True},
]
# Read only: the job screens' leftovers, all on the profile's own job, in two runs because the first one showed
# that F11 on the locks display only flips its view (the F12 after it went to the menu, not back to the list).
# This one: DSPJOB options 17 to 22 (never 30, which is "all of the above" and may print to a spool file, a
# write), then the locks display with F10 (record locks) and F11 (thread data). A check runs on the screen each
# option produced, so a key is only pressed on the display it was meant for. Nothing is changed, held, ended,
# printed or sent.
_LOCKS = {"proceed_if": ["Display Job Locks"]}
_STACK = {"proceed_if": ["Display Call Stack"]}
_OPEN = {"proceed_if": ["Display Open Files"]}
_WJ = {"proceed_if": ["Work with Job"]}
AUTHENTICATED["auth-dspjob3"] = [
    _SIGNON, {"fill": {"0": "DSPJOB"}, "key": "ENTER", **_MENU},
    *[step for opt in ("17", "18", "19", "20", "21", "22") for step in (_optkey(opt), _BACK)],
    _optkey("12", **_LOCKS),
    {"key": "F10"}, {"key": "F12", "always": True, **_LOCKS},
    {"key": "F11"}, {"key": "F12", "always": True, **_MENU},
    {"key": "F12", "always": True}, {"key": "F3", "always": True},
    {**_SIGNOFF, "always": True},
]
# Read only: the rest. WRKJOB's roll to a third menu page, option 40 (the Change Job prompt, opened and left with
# F12, never Enter) and 19 and 20, whose titles differ from DSPJOB's, then DSPJOB's open files with F11, and its
# call stack with F11 and F22, each in its own visit to the menu so one surprise only costs what comes after it.
# The job log's F10 is its own step at the end.
AUTHENTICATED["auth-dspjob4"] = [
    _SIGNON, {"fill": {"0": "WRKJOB"}, "key": "ENTER", **_MENU},
    {"key": "ROLLUP", **_MENU}, {"key": "ROLLUP", **_MENU}, {"key": "ROLLDOWN", **_MENU},
    _optkey("40"), {"key": "F12", "always": True, **_MENU},
    _optkey("19"), {"key": "F12", "always": True, **_MENU},
    _optkey("20"), {"key": "F12", "always": True, **_MENU},
    {"key": "F12", "always": True},
    {"fill": {"0": "DSPJOB"}, "key": "ENTER", **_MENU},
    _optkey("14", **_OPEN), {"key": "F11"}, {"key": "F12", "always": True, **_MENU},
    _optkey("11", **_STACK), {"key": "F11"}, {"key": "F12", "always": True, **_STACK},
    {"key": "F22"}, {"key": "F12", "always": True, **_STACK},
    {"key": "F12", "always": True, **_MENU},
    {"key": "F12", "always": True},
    {"fill": {"0": "DSPJOBLOG"}, "key": "ENTER", "proceed_if": ["Display Job Log"]},
    {"key": "F10"}, {"key": "F12", "always": True},
    {"key": "F12", "always": True}, {"key": "F3", "always": True},
    {**_SIGNOFF, "always": True},
]
# Read only: what a program call looks like from the outside, to plan running RPG. DSPPGM on the system's own
# QCMDEXC (program attribute, whose authority it runs under, whether it passes adopted authority on), a CALL of
# a program that is not there, and QCMDEXC given a command that checks an object exists (CHKOBJ, which changes
# nothing), a command that does not exist, and a length that cuts the command short. Looked at and left with F3.
# Nothing is created, changed, ended or sent, and no program of ours is compiled (that would be a write).
AUTHENTICATED["auth-callpgm"] = [
    _SIGNON,
    {"fill": {"0": "DSPPGM PGM(QSYS/QCMDEXC)"}, "key": "ENTER"}, {"key": "ROLLUP"}, {"key": "F3", "always": True},
    {"fill": {"0": "CALL PGM(NOSUCHPGM)"}, "key": "ENTER"}, {"key": "F3", "always": True},
    {"fill": {"0": "CALL PGM(QSYS/QCMDEXC) PARM('CHKOBJ OBJ(QSYS/QCMDEXC) OBJTYPE(*PGM)' 38)"}, "key": "ENTER"}, {"key": "F3", "always": True},
    {"fill": {"0": "CALL PGM(QSYS/QCMDEXC) PARM('NOSUCHCMD' 9)"}, "key": "ENTER"}, {"key": "F3", "always": True},
    {"fill": {"0": "CALL PGM(QSYS/QCMDEXC) PARM('CHKOBJ OBJ(QSYS/QCMDEXC) OBJTYPE(*PGM)' 12)"}, "key": "ENTER"}, {"key": "F3", "always": True},
    {**_SIGNOFF, "always": True},
]
# Read only: the PASE terminal, to settle what docs/pase.md lists as unverified (the screen layout, how the
# shell words its refusals, what `id` prints, the default permissions of the top directories). CALL PGM(QP2TERM)
# opens it, a handful of commands that only read run, and F3 leaves it. Nothing is written, no file is made, no
# program is started beyond the shell's own built-ins and ls, id and cat. Looked at and left with F3.
_PASE = [
    {"fill": {"0": "CALL PGM(QP2TERM)"}, "key": "ENTER"},
    *[{"fill": {"0": c}, "key": "ENTER"} for c in (
        "pwd", "id", "ls -ld / /home /tmp /QOpenSys", "ls /nosuchdir", "cat /nosuchfile", "echo $PATH")],
    {"key": "F3", "always": True}, {"key": "F3", "always": True},
]
AUTHENTICATED["auth-qp2term"] = [_SIGNON, *_PASE, {**_SIGNOFF, "always": True}]
# Read only: the output queue display. A queue that does not exist (the refusal wording), then the default
# printer queue, then the job log queue the profile's own spool files sit in. Looked at and left with F3.
# Not the bare WRKOUTQ: that lists every output queue on the host, and on a shared system it did not answer
# in 15 seconds, which is load nobody asked for. A shared system lists other people's spool files and job
# names, which stay in the local capture.
AUTHENTICATED["auth-outq"] = [
    _SIGNON, *_cmd("WRKOUTQ OUTQ(SLNOSUCH/NOQUEUE)"), *_cmd("WRKOUTQ OUTQ(QGPL/QPRINT)"),
    *_cmd("WRKOUTQ OUTQ(QUSRSYS/QEZJOBLOG)"), _SIGNOFF,
]
# Looks at the keys and option the edit screen and the work list offer beyond what is built, on the
# same kind of throwaway job-local data area as auth-objopts. It only presses function keys after
# the option numbers, never Enter on a screen it did not expect, and every back out runs whatever
# happened. F6, F10 and F11 are opened and left with F12, nothing on them is filled in. Option 3
# (copy) is pressed once and left with F12, and anything it makes is in QTEMP, gone at sign-off.
AUTHENTICATED["auth-objopts2"] = [
    _SIGNON,
    {"fill": {"0": f"CRTDTAARA DTAARA({_QT}) TYPE(*CHAR) LEN(10) TEXT('Silverlake oracle test, job-local')"},
     "key": "ENTER", "proceed_if": _MADE},
    {"fill": {"0": f"WRKOBJ OBJ({_QT}) OBJTYPE(*DTAARA)"}, "key": "ENTER", **_LIST},
    _optkey("2", **_LIST),
    {"key": "F6", "proceed_if": [_TESTLIB]}, {"key": "F12", "always": True},
    {"key": "F10", "proceed_if": [_TESTLIB]}, {"key": "F12", "always": True},
    {"key": "F11", "proceed_if": [_TESTLIB]}, {"key": "F12", "always": True},
    {"key": "F12", "always": True},
    _optkey("3", **_LIST), {"key": "F12", "always": True},
    *[{"key": "F12", "always": True}] * 2,
    *[{"key": "F3", "always": True}] * 3,
    {**_SIGNOFF, "always": True},
]
# An authorization list nobody here owns, looked at through the edit screen and left with F12.
AUTHENTICATED["auth-edtautl"] = [
    _SIGNON, {"fill": {"0": "EDTAUTL AUTL(QPWFSERVER)"}, "key": "ENTER"},
    *[{"key": "F12", "always": True}] * 2, *[{"key": "F3", "always": True}] * 2, _SIGNOFF,
]
# Read only: the development side. Where source lives and how it is compiled. PDM's start menu, a source
# file and a library that do not exist (the refusal wording), QGPL's source file if it has one, the
# object list for QGPL (first page only), and the prompts for CRTBNDRPG, CRTPF, CRTDSPF, CRTPRTF and
# CRTSRCPF opened with F4 and left with F12, never Enter. One CRTBNDRPG is run against a library that is
# not there and one STRSEU against a file that is not there: both are refused before anything is made or
# locked, and what they say is the point. Nothing is created, compiled, edited or locked.
AUTHENTICATED["auth-pdm"] = [
    _SIGNON,
    *_cmd("WRKMBRPDM FILE(NOSUCH/NOFILE)"), *_cmd("WRKMBRPDM FILE(QGPL/QCLSRC)"),
    {"fill": {"0": "STRPDM"}, "key": "ENTER"}, {"key": "F3", "always": True},
    {"fill": {"0": "WRKOBJPDM LIB(QGPL)"}, "key": "ENTER"}, {"key": "F3", "always": True},
    *[step for cmd in ("CRTBNDRPG", "CRTPF", "CRTDSPF", "CRTPRTF", "CRTSRCPF")
      for step in ({"fill": {"0": cmd}, "key": "F4"}, {"key": "ROLLUP"}, {"key": "F12", "always": True},
                   {"key": "F12", "always": True})],
    *_cmd("CRTBNDRPG PGM(NOSUCH/NOPGM) SRCFILE(NOSUCH/QRPGLESRC)"),
    *_cmd("STRSEU SRCFILE(NOSUCH/NOFILE) SRCMBR(NOMBR)"),
    {**_SIGNOFF, "always": True},
]
# Read only: the F4 prompt of every command Silverlake has, in batches so no single job stays on the host
# long. Each command is typed bare and F4 is pressed, so it is never run. The prompt is rolled once (the
# second page and the Bottom marker) and left with F12, twice, never Enter. A command the profile may not
# use answers with the refusal instead, which is also worth having.
PROMPT_BATCHES = {
    "a": ("CRTLIB", "DLTLIB", "ADDLIBLE", "RMVLIBLE", "CRTUSRPRF", "CHGUSRPRF", "DLTUSRPRF", "CHGPWD"),
    "b": ("GRTOBJAUT", "RVKOBJAUT", "CHGOBJOWN", "EDTOBJAUT", "DSPOBJAUT", "CRTAUTL", "ADDAUTLE", "CHGAUTLE"),
    "c": ("RMVAUTLE", "DLTAUTL", "DSPAUTL", "WRKAUTL", "WRKOBJ", "WRKOBJOWN", "DSPOBJD", "CHGOBJD"),
    "d": ("DSPLIBL", "WRKLIB", "RNMOBJ", "DLTF", "DLTPGM", "DSPPGM", "DSPPFM", "CPYF"),
    "e": ("CHGJOB", "DSPJOB", "WRKJOB", "WRKACTJOB", "ENDJOB", "HLDJOB", "RLSJOB", "DSPJOBLOG"),
    "f": ("WRKSPLF", "DSPSPLF", "HLDSPLF", "RLSSPLF", "DLTSPLF", "CHGSPLFA", "WRKOUTQ", "CRTOUTQ", "DLTOUTQ"),
    "g": ("DSPMSG", "SNDMSG", "CRTMSGQ", "CHGMSGQ", "CLRMSGQ", "DLTMSGQ", "WRKUSRPRF", "DSPUSRPRF"),
    "h": ("CALL", "GO", "OVRDBF", "DLTOVR", "DLTCMD", "DLTMNU", "CHGPRF", "WRKMBRPDM", "WRKOBJPDM", "STRSEU"),
}
for _batch, _cmds in PROMPT_BATCHES.items():
    AUTHENTICATED["auth-prompts-" + _batch] = [
        _SIGNON,
        *[step for cmd in _cmds
          for step in ({"fill": {"0": cmd}, "key": "F4"}, {"key": "ROLLUP"}, {"key": "F12", "always": True},
                       {"key": "F12", "always": True})],
        {**_SIGNOFF, "always": True},
    ]
# Read only: the second page of the two prompts whose Roll Up complained about a missing parameter (the
# host checks the required name before it rolls). The first field gets a made-up name, the prompt is rolled
# once and left with F12. Enter is never pressed on a prompt, so nothing is run and the name is never looked up.
PROMPT_PAGES = ("HLDSPLF", "OVRDBF")
AUTHENTICATED["auth-prompts-pages"] = [
    _SIGNON,
    *[step for cmd in PROMPT_PAGES
      for step in ({"fill": {"0": cmd}, "key": "F4"}, {"fill": {"0": "SLPLACE"}, "key": "ROLLUP"},
                   {"key": "ROLLUP"}, {"key": "ROLLUP"}, {"key": "F12", "always": True}, {"key": "F12", "always": True})],
    {**_SIGNOFF, "always": True},
]
# Read only: what F10=Additional parameters shows on the prompts that offer it (29 of them, in the F4 captures).
# Each command is typed bare, F4 opens the prompt, F10 asks for the additional parameters and Roll Up looks at the
# next page of them. Then F12 three times to get back to the command line (one too many is harmless there).
# Enter is never pressed on a prompt and nothing is typed into one, so nothing is run.
F10_BATCHES = {
    "a": ("CHGJOB", "CHGMSGQ", "CHGPRF", "CHGSPLFA", "CHGUSRPRF", "CPYF", "CRTAUTL", "CRTBNDRPG", "CRTDSPF", "CRTMSGQ"),
    "b": ("CRTOUTQ", "CRTPF", "CRTPRTF", "CRTSRCPF", "CRTUSRPRF", "DLTF", "DSPJOB", "DSPJOBLOG", "DSPMSG", "DSPSPLF"),
    "c": ("ENDJOB", "HLDJOB", "RLSJOB", "SNDMSG", "WRKACTJOB", "WRKJOB", "WRKLIB", "WRKSPLF", "WRKUSRPRF"),
}
for _batch, _cmds in F10_BATCHES.items():
    AUTHENTICATED["auth-f10-" + _batch] = [
        _SIGNON,
        *[step for cmd in _cmds
          for step in ({"fill": {"0": cmd}, "key": "F4"}, {"key": "F10"}, {"key": "ROLLUP"},
                       {"key": "F12", "always": True}, {"key": "F12", "always": True}, {"key": "F12", "always": True})],
        {**_SIGNOFF, "always": True},
    ]
SCENARIOS.update(AUTHENTICATED)

MIN_REMOTE_INTERVAL = 10.0  # seconds between connections to the same remote host
ALLOW_ENV = "SILVERLAKE_ORACLE_HOSTS"


def is_loopback(host: str) -> bool:
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return host == "localhost"


def check_target(host: str, state_dir: Path) -> None:
    """Loopback is always fine. Anything else must be named in
    SILVERLAKE_ORACLE_HOSTS, and is rate limited, so this tool cannot be
    pointed at a system by accident or in a loop."""
    if is_loopback(host):
        return
    allowed = {h.strip().lower() for h in os.environ.get(ALLOW_ENV, "").split(",") if h.strip()}
    if host.lower() not in allowed:
        raise CaptureError(
            f"{host} is not allowlisted. Set {ALLOW_ENV}={host} to capture from it deliberately.")
    state_dir.mkdir(parents=True, exist_ok=True)
    stamp = state_dir / f".oracle-last-{re.sub(r'[^a-z0-9.-]', '_', host.lower())}"
    now = time.time()
    if stamp.exists():
        wait = MIN_REMOTE_INTERVAL - (now - float(stamp.read_text() or 0))
        if wait > 0:
            raise CaptureError(f"last connection to {host} was moments ago, wait {wait:.0f}s")
    stamp.write_text(str(now))


def _not_signed_on(snapshot: dict) -> bool:
    """Still at a password prompt, or the host answered with a message ID. Either
    way the next action is not safe to send, so the run stops. Stopping is the
    cautious side: a legitimate screen with a message ID ends the run early."""
    return bool(snapshot["message_ids"]) or any(f["hidden"] for f in snapshot["fields"])


def _is_notice(snapshot: dict) -> bool:
    """A notice screen after sign-on, like "Message queue X is allocated to another job" when the same profile
    is signed on somewhere else. It takes no input and says "Press Enter to continue"."""
    seen = " ".join(r["text"] for r in snapshot["runs"]).lower()
    return not snapshot["fields"] and "press enter to continue" in seen


MAX_NOTICES = 2


def expand(value: str) -> str:
    def sub(m: re.Match) -> str:
        name = m.group(1)
        if name not in os.environ:
            raise CaptureError(f"scenario needs environment variable {name}")
        return os.environ[name]
    return re.sub(r"\$\{(\w+)\}", sub, value)


async def run_scenario(host: str, port: int, name: str, devname: str | None = None,
                       timeout: float = 15.0, tls: bool = False) -> dict:
    if name not in SCENARIOS:
        raise CaptureError(f"unknown scenario {name!r}, have: {', '.join(sorted(SCENARIOS))}")
    if name in AUTHENTICATED and not tls and not is_loopback(host):
        raise CaptureError(f"{name} sends a password. Use TLS (--tls) for anything but loopback.")
    # Resolve every value before connecting, so a missing variable cannot leave
    # a half finished session on someone else's system.
    os.environ[TESTLIB_ENV] = "SLT" + "".join(random.choices("0123456789", k=5))
    actions = [({int(k): expand(v) for k, v in a.get("fill", {}).items()}, a["key"],
                [expand(t).lower() for t in a.get("proceed_if", [])], bool(a.get("always")))
               for a in SCENARIOS[name]]
    client = Client(host, port, devname, tls=tls)
    await client.connect()
    captures: list[Capture] = []
    skipped: list[int] = []
    stopped: dict | None = None
    try:
        captures.append(await client.wait_screen(timeout))
        skipping = False
        for i, (fill, key, proceed_if, always) in enumerate(actions):
            if skipping and not always:
                skipped.append(i)
                continue
            try:
                client.send_aid(key, fill)
            except CaptureError as exc:
                if not str(exc).startswith("no input field"):
                    raise
                # The screen in front of us is not the one the scenario expects. Keep what was gathered,
                # say which action it was, and send nothing more.
                stopped = {"action": i, "key": key, "reason": str(exc)}
                break
            try:
                captures.append(await client.wait_screen(timeout))
            except CaptureError as exc:
                if not str(exc).startswith(("no screen within", "could not decode")):
                    raise
                # The host answered nothing, or answered with a record we cannot read. Keep what was
                # gathered, say where it stopped, and send nothing more: a key into a screen we cannot
                # see is not worth guessing. An unreadable record is kept raw so the decoder can learn it.
                stopped = {"action": i, "key": key, "reason": str(exc)}
                if str(exc).startswith("could not decode"):
                    stopped["raw_records_hex"] = [r.hex() for r in client._records]
                break
            if proceed_if:
                seen = " ".join(r["text"] for r in captures[-1].snapshot["runs"]).lower()
                if not all(t in seen for t in proceed_if):
                    skipping = True       # the host did not do what we asked: ask nothing more, just sign off
            if name in AUTHENTICATED and i == 0 and _not_signed_on(captures[-1].snapshot):
                # One attempt only. Never retype a password the host refused, and
                # do not type commands into a screen we did not expect.
                ids = ", ".join(captures[-1].snapshot["message_ids"]) or "none"
                raise CaptureError(f"did not get past sign-on, stopping (message IDs: {ids}). "
                                   "Nothing further was sent.")
            if name in AUTHENTICATED and i == 0:
                # Dismiss a notice (and only a notice) the host puts in front of the first screen. Enter on a
                # screen with no fields and "Press Enter to continue" is what a person would do, and it
                # cannot run anything.
                for _ in range(MAX_NOTICES):
                    if not _is_notice(captures[-1].snapshot):
                        break
                    client.send_aid("ENTER")
                    captures.append(await client.wait_screen(timeout))
    finally:
        await client.close()
    return {
        "target": f"{host}:{port}",
        "scenario": name,
        "captured_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "testlib": os.environ.get(TESTLIB_ENV) if "TESTLIB" in repr(SCENARIOS[name]) else None,
        "skipped_actions": skipped,
        "stopped": stopped,
        "snapshots": [c.snapshot for c in captures],
        "error_lines": [c.error_line for c in captures],
        # Raw host records, hex. Local only: this is the real system's wording.
        "records_hex": [[r.hex() for r in c.records] for c in captures],
    }


def reanalyze(cap: dict) -> dict:
    """Rebuild a capture's snapshots from its raw records, so a capture taken
    before the decoder learned something new is still comparable. Records for
    one screen are applied in order on a terminal that carries state across
    screens, as a real one does. Captures without raw records keep what they
    have."""
    from ..proto import datastream as ds
    from .terminal import Terminal

    if not cap.get("records_hex"):
        return cap
    term = Terminal()
    snaps, errors = [], []
    for records in cap["records_hex"]:
        term.error_line = ""
        for rec in records:
            term.apply(ds.split_gds(bytes.fromhex(rec))[1])
        snaps.append(term.snapshot())
        errors.append(term.error_line)
    return {**cap, "snapshots": snaps, "error_lines": errors}


def run(host: str, port: int, name: str, **kw) -> dict:
    return asyncio.run(run_scenario(host, port, name, **kw))
