"""The oracle's .env loader: credentials stay out of the shell, the repo and the output."""

import os

import pytest

from silverlake.oracle import envfile


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for k in list(os.environ):
        if k.startswith(envfile.PREFIX) or k == "OTHER_SECRET":
            monkeypatch.delenv(k)


def write(tmp_path, body, mode=0o600):
    f = tmp_path / ".env"
    f.write_text(body)
    f.chmod(mode)
    return f


def test_loads_only_our_names_and_returns_names_not_values(tmp_path, monkeypatch):
    f = write(tmp_path, "# c\nSILVERLAKE_ORACLE_USER=tester\nexport SILVERLAKE_ORACLE_PASS = 's3cret pw'\n"
                        "OTHER_SECRET=nope\nnot a line\n\n")
    names = envfile.load(f)
    assert names == ["SILVERLAKE_ORACLE_USER", "SILVERLAKE_ORACLE_PASS"]
    assert os.environ["SILVERLAKE_ORACLE_USER"] == "tester"
    assert os.environ["SILVERLAKE_ORACLE_PASS"] == "s3cret pw"          # quotes stripped
    assert "OTHER_SECRET" not in os.environ


def test_blank_values_are_not_set_and_the_environment_wins(tmp_path, monkeypatch):
    monkeypatch.setenv("SILVERLAKE_ORACLE_USER", "from-shell")
    f = write(tmp_path, "SILVERLAKE_ORACLE_USER=from-file\nSILVERLAKE_ORACLE_PASS=\n")
    assert envfile.load(f) == []
    assert os.environ["SILVERLAKE_ORACLE_USER"] == "from-shell"
    assert "SILVERLAKE_ORACLE_PASS" not in os.environ


def test_a_file_others_can_read_is_refused_without_reading_it(tmp_path):
    for mode in (0o644, 0o640, 0o604, 0o666):
        f = write(tmp_path, "SILVERLAKE_ORACLE_PASS=x\n", mode)
        with pytest.raises(envfile.EnvFileError, match="chmod 600"):
            envfile.load(f)
        assert "SILVERLAKE_ORACLE_PASS" not in os.environ


def test_a_missing_file_is_fine(tmp_path):
    assert envfile.load(tmp_path / "nope") == []


def test_the_error_never_contains_a_value(tmp_path):
    f = write(tmp_path, "SILVERLAKE_ORACLE_PASS=hunter2hunter2\n", 0o644)
    with pytest.raises(envfile.EnvFileError) as exc:
        envfile.load(f)
    assert "hunter2" not in str(exc.value)


def test_the_shipped_example_is_blank_and_the_real_file_is_ignored():
    import subprocess
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    example = (root / ".env.example").read_text()
    assert "SILVERLAKE_ORACLE_PASS=\n" in example and "SILVERLAKE_ORACLE_USER=\n" in example
    def ignored(name):
        return subprocess.run(["git", "check-ignore", "-q", name], cwd=root).returncode == 0
    assert ignored(".env") and ignored(".env.local")
    assert not ignored(".env.example")
