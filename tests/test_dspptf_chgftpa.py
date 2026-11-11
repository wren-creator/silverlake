"""DSPPTF and CHGFTPA: both were unmodeled commands ("Command X in library *LIBL not found."),
added to round out what the command line recognizes."""

import pytest

from silverlake import scenarios
from silverlake.cl.commands import execute
from silverlake.system import profiles

REG = scenarios.registry()


@pytest.fixture
def store():
    return profiles.load()


def run(store, user, line):
    out = execute(store, store.get(user), line)
    return out.message.line() if out.message else ""


# -- DSPPTF ------------------------------------------------------------------------------------

def test_dspptf_is_no_longer_unknown(store):
    assert "not found" not in run(store, "STUDENT", "DSPPTF LICPGM(5770DG1)")


def test_dspptf_shows_the_one_tracked_product(store):
    assert "Not applied" in run(store, "STUDENT", "DSPPTF LICPGM(5770DG1)")
    scenarios.apply(store, REG["httpadmin-ssi-injection"], "secure")
    assert "Applied" in run(store, "STUDENT", "DSPPTF LICPGM(5770DG1)")


def test_dspptf_says_so_for_anything_else(store):
    assert "No PTF information is modeled for 5770SS1" in run(store, "STUDENT", "DSPPTF LICPGM(5770SS1)")


def test_dspptf_needs_licpgm_and_accepts_a_copied_select(store):
    assert "Required parameter LICPGM" in run(store, "STUDENT", "DSPPTF")
    assert "Not applied" in run(store, "STUDENT", "DSPPTF LICPGM(5770DG1) SELECT(*ALL) OUTPUT(*)")


def test_dspptf_needs_no_special_authority(store):
    assert "not authorized" not in run(store, "GUEST", "DSPPTF LICPGM(5770DG1)").lower()


# -- CHGFTPA ------------------------------------------------------------------------------------

def test_chgftpa_is_no_longer_unknown(store):
    assert "not found" not in run(store, "IOADMIN", "CHGFTPA AUTOSTART(*NO)")


def test_chgftpa_needs_iosyscfg(store):
    assert "*IOSYSCFG" in run(store, "STUDENT", "CHGFTPA AUTOSTART(*NO)")
    assert store.system.ftp_autostart == "*YES"


def test_chgftpa_records_autostart_but_does_not_enforce_it(store):
    assert "changed" in run(store, "IOADMIN", "CHGFTPA AUTOSTART(*NO)")
    assert store.system.ftp_autostart == "*NO"
    assert "changed" in run(store, "IOADMIN", "CHGFTPA AUTOSTART(*SAME)")
    assert store.system.ftp_autostart == "*NO"          # *SAME touches nothing


def test_chgftpa_rejects_a_bad_autostart_value(store):
    assert "AUTOSTART not valid" in run(store, "IOADMIN", "CHGFTPA AUTOSTART(*MAYBE)")


def test_chgftpa_accepts_ccsid_without_acting_on_it(store):
    assert "changed" in run(store, "IOADMIN", "CHGFTPA CCSID(37)")
