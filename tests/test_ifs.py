"""The virtual IFS: stored nodes, the mapped /QSYS.LIB, and who may do what."""

import pytest

from silverlake import flags
from silverlake.system import ifs, profiles, state
from silverlake.system.authority import Auth


@pytest.fixture
def store():
    return profiles.load()


def who(store, name):
    return store.profiles[name]


def test_the_seed_has_a_root_and_the_usual_places(store):
    for p in ("/", "/QOpenSys", "/QOpenSys/etc/profile", "/home/STUDENT", "/tmp"):
        assert p in store.ifs
    assert "/QSYS.LIB" not in store.ifs                       # mapped, not stored


def test_paths_are_normalised_against_the_directory_and_home():
    n = ifs.normalize
    assert n("/a/b/../c") == "/a/c" and n("x", "/home/S") == "/home/S/x" and n("..", "/home/S") == "/home"
    assert n("~", "/", "/home/S") == "/home/S" and n("~/f", "/", "/home/S") == "/home/S/f"
    assert n("//x") == "/x" and n("/") == "/" and n("/..") == "/"


def test_the_owner_gets_the_owner_bits_everyone_else_the_public_ones_and_allobj_everything(store):
    notes = store.ifs["/home/STUDENT/notes.txt"]
    assert ifs.mode_for(store, who(store, "STUDENT"), notes) == "rw"
    assert ifs.mode_for(store, who(store, "OPERATOR"), notes) == ""
    assert ifs.mode_for(store, who(store, "QSECOFR"), notes) == "rwx"


def test_a_private_entry_overrides_the_public_bits(store):
    notes = store.ifs["/home/STUDENT/notes.txt"]
    notes.private["OPERATOR"] = "r--"
    assert ifs.mode_for(store, who(store, "OPERATOR"), notes) == "r"


def test_every_directory_on_the_way_needs_search_permission(store):
    assert ifs.read(store, who(store, "STUDENT"), "/home/STUDENT/notes.txt").startswith("Things")
    with pytest.raises(ifs.IfsError) as exc:
        ifs.read(store, who(store, "OPERATOR"), "/home/STUDENT/notes.txt")           # /home/STUDENT is ---
    assert exc.value.kind == "EACCES"
    store.ifs["/home/STUDENT"].public = "--x"                                      # search, but not list
    with pytest.raises(ifs.IfsError):
        ifs.read(store, who(store, "OPERATOR"), "/home/STUDENT/notes.txt")           # file itself is ---
    store.ifs["/home/STUDENT/notes.txt"].public = "r--"
    assert ifs.read(store, who(store, "OPERATOR"), "/home/STUDENT/notes.txt")
    with pytest.raises(ifs.IfsError):
        ifs.listdir(store, who(store, "OPERATOR"), "/home/STUDENT")                  # no r on the directory


def test_missing_things_and_wrong_kinds_say_what_they_are(store):
    s = who(store, "STUDENT")
    for path, kind in (("/nope", "ENOENT"), ("/home/STUDENT/notes.txt/x", "ENOTDIR"), ("/home/nothing/x", "ENOENT")):
        with pytest.raises(ifs.IfsError) as exc:
            ifs.lookup(store, s, path)
        assert exc.value.kind == kind
    with pytest.raises(ifs.IfsError) as exc:
        ifs.read(store, s, "/home")
    assert exc.value.kind == "EISDIR"
    with pytest.raises(ifs.IfsError) as exc:
        ifs.listdir(store, s, "/home/STUDENT/notes.txt")
    assert exc.value.kind == "ENOTDIR"


def test_listing_the_root_includes_the_mapped_library_system(store):
    assert [e.path for e in ifs.listdir(store, who(store, "STUDENT"), "/")] == ["/QOpenSys", "/QSYS.LIB", "/home", "/tmp"]


def test_qsys_lib_maps_libraries_and_objects_with_the_object_authority(store):
    s, q = who(store, "STUDENT"), who(store, "QSECOFR")
    libs = [e.path for e in ifs.listdir(store, s, "/QSYS.LIB")]
    assert "/QSYS.LIB/APPLIB.LIB" in libs and "/QSYS.LIB/QTEMP.LIB" in libs
    objs = [e.path for e in ifs.listdir(store, s, "/QSYS.LIB/APPLIB.LIB")]
    assert "/QSYS.LIB/APPLIB.LIB/CUSTOMERS.FILE" in objs
    assert "/QSYS.LIB/APPLIB.LIB/PAYROLL.FILE" not in objs and "/QSYS.LIB/APPLIB.LIB/VAULT.FILE" not in objs
    assert "/QSYS.LIB/APPLIB.LIB/PAYROLL.FILE" in [e.path for e in ifs.listdir(store, q, "/QSYS.LIB/APPLIB.LIB")]


def test_a_physical_file_reads_as_its_records_only_with_read_authority(store):
    with pytest.raises(ifs.IfsError) as exc:
        ifs.read(store, who(store, "STUDENT"), "/QSYS.LIB/APPLIB.LIB/PAYROLL.FILE")
    assert exc.value.kind == "EACCES"
    text = ifs.read(store, who(store, "OPERATOR"), "/QSYS.LIB/APPLIB.LIB/PAYROLL.FILE")
    assert "Chen, Priya" in text and text.count("\n") == 7
    with pytest.raises(ifs.IfsError):
        ifs.lookup(store, who(store, "OPERATOR"), "/QSYS.LIB/NOPE.LIB")
    with pytest.raises(ifs.IfsError) as exc:
        ifs.lookup(store, who(store, "OPERATOR"), "/QSYS.LIB/APPLIB.LIB/PAYROLL.FILE/x")
    assert exc.value.kind == "ENOTDIR"


def test_the_object_authority_is_the_same_one_the_5250_side_uses(store):
    payroll = store.objects[("APPLIB", "PAYROLL", "*FILE")]
    payroll.private["STUDENT"] = Auth.OBJOPR | Auth.READ | Auth.EXECUTE
    assert "Chen, Priya" in ifs.read(store, who(store, "STUDENT"), "/QSYS.LIB/APPLIB.LIB/PAYROLL.FILE")


def test_long_listing_permissions_and_ids(store):
    e = ifs.lookup(store, who(store, "STUDENT"), "/home/STUDENT/notes.txt")
    assert ifs.perms(e) == "-rw-------"
    d = ifs.lookup(store, who(store, "STUDENT"), "/home")
    assert ifs.perms(d) == "drwxr-xr-x"
    assert ifs.uid_of(store, who(store, "QSECOFR")) == 0
    assert ifs.uid_of(store, who(store, "STUDENT")) >= 500
    assert len({ifs.uid_of(store, p) for p in store.profiles.values()}) == len(store.profiles)


def test_the_ifs_is_saved_with_the_state_and_an_older_state_gets_the_seed(tmp_path):
    store, db = state.open_store(None, tmp_path)
    store.ifs["/tmp/mine"] = ifs.Node("/tmp/mine", "file", "STUDENT", content="hello\n")
    db.write(store)
    db.close()
    again, db2 = state.open_store(None, tmp_path)
    assert again.ifs["/tmp/mine"].content == "hello\n" and "/home/STUDENT/notes.txt" in again.ifs
    db2.close()
    data = state.to_dict(again)
    del data["ifs"]
    assert "/QOpenSys/etc/motd" in state.from_dict(data).ifs


def test_a_flag_placeholder_in_the_seed_would_be_filled(tmp_path):
    seed = tmp_path / "x.toml"
    seed.write_text('[[node]]\npath = "/"\n[[node]]\npath = "/f"\nkind = "file"\ncontent = "@@FLAG:httpadmin-ssi-injection@@"\n')
    assert flags.flag("httpadmin-ssi-injection") in ifs.load_seed(seed)["/f"].content
