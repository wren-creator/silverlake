"""The object model: identity by library, name and type, the library gate,
and the tables that hold it."""

import sqlite3
import textwrap

import pytest

from silverlake.cl.commands import execute
from silverlake.system import profiles, state
from silverlake.system.authority import ALL, CHANGE, EXCLUDE, USE, Auth


@pytest.fixture
def store():
    return profiles.load()


def file_(store, lib, name):
    return store.objects[(lib, name, "*FILE")]


def auth(store, user, lib, name):
    return store.authority_to_object(store.get(user), file_(store, lib, name))


def test_objects_are_identified_by_library_name_and_type(store):
    p = file_(store, "APPLIB", "PAYROLL")
    assert p.key == ("APPLIB", "PAYROLL", "*FILE")
    assert store.find_library("applib").key == ("QSYS", "APPLIB", "*LIB")
    assert store.find_library("NOSUCH") is None
    # Same name, different library or type, is a different object.
    assert ("SRCLIB", "PAYROLL", "*FILE") not in store.objects


def test_a_wide_open_object_in_a_locked_library_is_out_of_reach(store):
    qrpgsrc = file_(store, "SRCLIB", "QRPGSRC")
    assert qrpgsrc.public == CHANGE                      # the object itself is wide open
    assert store.object_authority(store.get("STUDENT"), qrpgsrc) == CHANGE
    assert store.authority_to_object(store.get("STUDENT"), qrpgsrc) == Auth.NONE   # the library says no
    assert store.authority_to_object(store.get("DEVELOPER"), qrpgsrc) == qrpgsrc.owner_auth   # owner
    assert Auth.EXECUTE in store.authority_to_object(store.get("OPERATOR"), store.find_library("APPLIB"))


def test_group_access_to_the_library_opens_it(store):
    # DEVELOPER's group holds *CHANGE on SRCLIB, so a group member reaches the object.
    store.get("OPERATOR").supplemental_groups.append("GRPDEV")
    assert store.authority_to_object(store.get("OPERATOR"), file_(store, "SRCLIB", "QRPGSRC")) == CHANGE


def test_allobj_skips_the_library_gate(store):
    assert store.authority_to_object(store.get("SVCACCT"), file_(store, "SRCLIB", "QRPGSRC")) == ALL


def test_authorization_lists_still_work_through_an_open_library(store):
    assert auth(store, "OPERATOR", "APPLIB", "PAYROLL") == USE
    assert auth(store, "STUDENT", "APPLIB", "PAYROLL") == EXCLUDE
    assert auth(store, "GUEST", "APPLIB", "CUSTOMERS") == EXCLUDE


def test_locking_a_library_hides_what_public_could_reach(store):
    assert auth(store, "STUDENT", "APPLIB", "CUSTOMERS") == USE
    store.find_library("APPLIB").public = EXCLUDE
    assert auth(store, "STUDENT", "APPLIB", "CUSTOMERS") == Auth.NONE


def test_an_object_whose_library_is_gone_is_unreachable(store):
    del store.objects[("QSYS", "APPLIB", "*LIB")]
    assert auth(store, "OPERATOR", "APPLIB", "CUSTOMERS") == Auth.NONE


def test_deleting_an_owner_with_dlt_takes_a_librarys_contents_with_it(store):
    execute(store, store.get("QSECOFR"), "DLTUSRPRF DEVELOPER OWNOBJOPT(*DLT)")
    assert store.find_library("SRCLIB") is None
    assert not [o for o in store.objects.values() if o.library == "SRCLIB"]


# -- seed validation ---------------------------------------------------------------------------

BASE = """
[[profile]]
name = "QSECOFR"
user_class = "*SECOFR"
[[object]]
name = "LIBA"
owner = "QSECOFR"
"""


def load_text(tmp_path, body):
    f = tmp_path / "seed.toml"
    f.write_text(textwrap.dedent(BASE + body))
    return profiles.load(f)


@pytest.mark.parametrize("body,why", [
    ('[[object]]\nlibrary="NOLIB"\nname="X"\ntype="*FILE"\nowner="QSECOFR"\n', "library NOLIB does not exist"),
    ('[[object]]\nname="LIBA"\nowner="QSECOFR"\n', "duplicate object"),
    ('[[object]]\nname="LIBB"\nowner="NOBODY"\n', "owner NOBODY does not exist"),
    ('[[object]]\nname="LIBB"\nowner="QSECOFR"\nautl="NOLIST"\n', "authorization list NOLIST does not exist"),
    ('[[object]]\nname="LIBB"\nowner="QSECOFR"\npublic="*AUTL"\n', "needs an authorization list"),
])
def test_bad_object_seeds_are_refused(tmp_path, body, why):
    with pytest.raises(profiles.SeedError, match=why):
        load_text(tmp_path, body)


def test_a_library_must_live_in_qsys(tmp_path):
    with pytest.raises(profiles.SeedError, match="must live in QSYS"):
        load_text(tmp_path, '[[object]]\nlibrary="LIBA"\nname="LIBC"\nowner="QSECOFR"\n')


def test_a_minimal_seed_with_objects_loads(tmp_path):
    s = load_text(tmp_path, '[[object]]\nlibrary="LIBA"\nname="F"\ntype="*file"\nowner="QSECOFR"\n')
    assert ("LIBA", "F", "*FILE") in s.objects


# -- tables ---------------------------------------------------------------------------------------

def test_objects_live_in_real_tables_keyed_by_library_name_type(tmp_path):
    st, db = state.open_store(state_dir=tmp_path)
    db.close()
    con = sqlite3.connect(tmp_path / state.DB_NAME)
    row = con.execute("SELECT owner, public, autl FROM objects WHERE library='APPLIB' AND name='PAYROLL' "
                      "AND type='*FILE'").fetchone()
    assert row == ("QSECOFR", "*AUTL", "PAYAUTL")
    assert con.execute("SELECT auth FROM object_auth WHERE name='CUSTOMERS' AND grantee='GUEST'").fetchone() \
        == ("*EXCLUDE",)
    assert con.execute("SELECT auth FROM autl_entries WHERE autl='PAYAUTL' AND grantee='OPERATOR'").fetchone() \
        == ("*USE",)
    pk = [r[1] for r in con.execute("PRAGMA table_info(objects)") if r[5]]
    assert pk == ["library", "name", "type"]
    con.close()


def test_a_changed_object_is_saved_and_a_removed_one_is_gone(tmp_path):
    st, db = state.open_store(state_dir=tmp_path)
    st.find_library("APPLIB").public = EXCLUDE
    del st.objects[("APPLIB", "CUSTOMERS", "*FILE")]
    st.on_change()
    db.close()
    again, db2 = state.open_store(state_dir=tmp_path)
    assert again.find_library("APPLIB").public == EXCLUDE
    assert ("APPLIB", "CUSTOMERS", "*FILE") not in again.objects
    assert not again.autls["PAYAUTL"].entries.get("NOBODY")
    db2.close()
