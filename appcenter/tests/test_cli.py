"""The command-line interface, end to end against the fake uv."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import talkpipe_appcenter as ts
from conftest import SMALL_CATALOG, FakeUv

APPCENTER_DIR = Path(__file__).resolve().parent.parent


@pytest.fixture
def small_catalog_file(tmp_path: Path) -> Path:
    path = tmp_path / "small.toml"
    path.write_text(SMALL_CATALOG)
    return path


def _main(*argv: str, catalog: Path) -> int:
    return ts.main(["--no-default-catalog", "--catalog", str(catalog), *argv])


def test_version_flag(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        ts.main(["--version"])
    assert excinfo.value.code == 0
    assert capsys.readouterr().out.strip() == f"talkpipe-appcenter {ts.__version__}"


def test_list_text_and_json(
    fake_uv: FakeUv, small_catalog_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fake_uv.set_installed("talkpipe-vault", "1.0.0", ["vault-server"])

    assert _main("list", catalog=small_catalog_file) == 0
    out = capsys.readouterr().out
    for expected in (
        "ID",
        "STATUS",
        "vault",
        "installed",
        "1.0.0",
        "tool",
        "not installed",
    ):
        assert expected in out
    assert "Install one with: talkpipe-appcenter install <id>" in out

    assert _main("list", "--json", catalog=small_catalog_file) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["catalog"] == "Test"
    by_id = {row["id"]: row for row in data["apps"]}
    assert by_id["vault"]["installed"] == "1.0.0"
    assert by_id["vault"]["latest"] is None  # offline
    assert by_id["vault"]["running"] is False
    assert by_id["vault"]["url"] == "http://127.0.0.1:18002/"
    assert by_id["tool"]["status"] == "not installed"
    assert by_id["tool"]["url"] is None


def test_info(
    fake_uv: FakeUv, small_catalog_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fake_uv.set_installed("talkpipe-vault", "1.0.0", ["vault-server", "vault-tui"])

    assert _main("info", "vault", catalog=small_catalog_file) == 0
    out = capsys.readouterr().out
    assert out.startswith("talkpipe-vault (vault)")
    assert "package:   talkpipe-vault" in out
    assert "installed: 1.0.0  [installed]" in out
    assert "command:   vault-server --resume" in out
    assert "provides:  vault-server, vault-tui" in out
    assert "url:       http://127.0.0.1:18002/" in out
    assert "data:      ~/.talkpipe-vault" in out


def test_unknown_app_lists_known_ids(
    small_catalog_file: Path, fake_uv: FakeUv, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as excinfo:
        _main("info", "nope", catalog=small_catalog_file)
    assert "no app 'nope' in the catalog (known: vault, tool)" in str(excinfo.value)


def test_install_upgrade_uninstall_flow(
    fake_uv: FakeUv, small_catalog_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fake_uv.set_canned("talkpipe-vault", ["vault-server"])
    fake_uv.set_latest("talkpipe-vault", "1.0.0")

    assert _main("install", "vault", "tool", catalog=small_catalog_file) == 0
    out = capsys.readouterr().out
    assert "Installed talkpipe-vault 1.0.0." in out
    assert "Installed some-tool 1.2.3." in out
    assert "Open a NEW terminal" in out
    installs = [c for c in fake_uv.calls() if c[:2] == ["tool", "install"]]
    assert installs[0] == [
        "tool",
        "install",
        "--python",
        ts.DEFAULT_PYTHON,
        "--upgrade",
        "--from",
        "talkpipe-vault",
        "talkpipe-vault",
    ]

    with pytest.raises(SystemExit, match="name the apps to upgrade"):
        _main("upgrade", catalog=small_catalog_file)

    fake_uv.set_latest("talkpipe-vault", "1.1.0")
    assert _main("upgrade", "--all", catalog=small_catalog_file) == 0
    out = capsys.readouterr().out
    assert "Upgraded talkpipe-vault 1.0.0 -> 1.1.0." in out
    assert "some-tool 1.2.3 is already the newest version." in out

    assert _main("uninstall", "-y", "vault", catalog=small_catalog_file) == 0
    assert "Uninstalled talkpipe-vault." in capsys.readouterr().out
    assert "talkpipe-vault" not in fake_uv.state["tools"]


def test_uninstall_asks_unless_yes(
    fake_uv: FakeUv,
    small_catalog_file: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fake_uv.set_installed("some-tool", "0.1", ["some-tool"])
    monkeypatch.setattr("builtins.input", lambda prompt: "n")

    assert _main("uninstall", "tool", catalog=small_catalog_file) == 0
    assert "Skipped." in capsys.readouterr().out
    assert "some-tool" in fake_uv.state["tools"]

    monkeypatch.setattr("builtins.input", lambda prompt: "y")
    assert _main("uninstall", "tool", catalog=small_catalog_file) == 0
    assert "some-tool" not in fake_uv.state["tools"]


def test_install_failure_exit_code(fake_uv: FakeUv, small_catalog_file: Path) -> None:
    fake_uv.fail_next()
    assert _main("install", "tool", catalog=small_catalog_file) == 1


def test_shortcut_add_remove_and_store(
    fake_uv: FakeUv,
    small_catalog_file: Path,
    home: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The real runner is used here on purpose: it must cope with a desktop that
    # lacks update-desktop-database (CI runners do), so nothing is patched and
    # PATH deliberately holds no such command.
    monkeypatch.setenv("PATH", str(fake_uv.bin))
    fake_uv.set_installed("talkpipe-vault", "1.0.0", ["vault-server"])

    assert _main("shortcut", "add", "vault", catalog=small_catalog_file) == 0
    assert (home / ".local/share/applications/talkpipe-vault.desktop").exists()
    assert "Added the talkpipe-vault launcher" in capsys.readouterr().out
    assert _main("shortcut", "remove", "vault", catalog=small_catalog_file) == 0
    assert not (home / ".local/share/applications/talkpipe-vault.desktop").exists()

    assert _main("shortcut", "add", "appcenter", catalog=small_catalog_file) == 0
    assert (home / ".local/share/applications/talkpipe-appcenter.desktop").exists()
    assert _main("shortcut", "remove", "appcenter", catalog=small_catalog_file) == 0

    assert _main("shortcut", "add", "tool", catalog=small_catalog_file) == 1
    assert "not installed" in capsys.readouterr().out


def test_bad_catalog_is_reported_not_raised(
    capsys: pytest.CaptureFixture[str], fake_uv: FakeUv
) -> None:
    assert ts.main(["--catalog", "/nonexistent/cat.toml", "list"]) == 1
    assert "error: could not read catalog" in capsys.readouterr().err


def test_catalog_options_are_accepted_after_the_subcommand(
    capsys: pytest.CaptureFixture[str], fake_uv: FakeUv, small_catalog_file: Path
) -> None:
    assert (
        ts.main(["list", "--no-default-catalog", "--catalog", str(small_catalog_file)])
        == 0
    )
    out = capsys.readouterr().out
    assert "tool" in out
    assert "writing-assistant" not in out


def _saved_file(home: Path) -> Path:
    return home / ".config" / "talkpipe-appcenter" / "catalogs.txt"


def test_remember_saves_the_catalog_for_later_runs(
    capsys: pytest.CaptureFixture[str],
    fake_uv: FakeUv,
    small_catalog_file: Path,
    home: Path,
) -> None:
    fake_uv.set_canned("some-tool", ["some-tool"])
    source = str(small_catalog_file.resolve())

    assert ts.main(["install", "tool", "--catalog", source, "--remember"]) == 0
    out = capsys.readouterr().out
    assert f"Saved catalog {source}; every run now loads it." in out
    assert "Installed some-tool" in out
    assert ts.read_saved_catalogs(_saved_file(home)) == [source]

    # Later runs need no --catalog: "tool" is known and the built-in apps remain.
    assert ts.main(["info", "tool"]) == 0
    assert "some-tool" in capsys.readouterr().out
    assert ts.main(["list", "--json"]) == 0
    ids = [row["id"] for row in json.loads(capsys.readouterr().out)["apps"]]
    assert ids == ["vault", "writing-assistant", "talkpipe", "tool"]

    assert ts.main(["catalog", "list"]) == 0
    assert source in capsys.readouterr().out
    assert ts.main(["catalog", "remove", source]) == 0
    assert ts.read_saved_catalogs(_saved_file(home)) == []
    with pytest.raises(SystemExit, match="no app 'tool'"):
        ts.main(["info", "tool"])
    assert ts.main(["catalog", "remove", source]) == 1
    assert "is not a saved catalog" in capsys.readouterr().out


def test_remember_without_a_catalog_is_an_error(
    capsys: pytest.CaptureFixture[str], fake_uv: FakeUv, home: Path
) -> None:
    assert ts.main(["list", "--remember"]) == 1
    assert "--remember needs at least one --catalog" in capsys.readouterr().err
    assert not _saved_file(home).exists()


def test_catalog_add_checks_the_catalog_before_saving_it(
    capsys: pytest.CaptureFixture[str],
    fake_uv: FakeUv,
    small_catalog_file: Path,
    home: Path,
) -> None:
    assert ts.main(["catalog", "add", "/nonexistent/cat.toml"]) == 1
    assert "could not read catalog" in capsys.readouterr().err
    assert not _saved_file(home).exists()

    assert ts.main(["catalog", "list"]) == 0
    assert "No saved catalogs" in capsys.readouterr().out
    assert ts.main(["catalog", "add", str(small_catalog_file)]) == 0
    assert ts.main(["catalog", "add", str(small_catalog_file)]) == 0
    assert "is already saved" in capsys.readouterr().out
    assert ts.read_saved_catalogs(_saved_file(home)) == [
        str(small_catalog_file.resolve())
    ]


def test_a_saved_catalog_that_stops_loading_says_how_to_forget_it(
    capsys: pytest.CaptureFixture[str],
    fake_uv: FakeUv,
    small_catalog_file: Path,
    home: Path,
) -> None:
    assert ts.main(["catalog", "add", str(small_catalog_file)]) == 0
    small_catalog_file.unlink()

    assert ts.main(["list"]) == 1
    err = capsys.readouterr().err
    assert "could not read catalog" in err
    assert "catalog remove" in err
    assert ts.main(["catalog", "remove", str(small_catalog_file)]) == 0
    assert ts.main(["list"]) == 0


def test_missing_uv_is_reported(
    monkeypatch: pytest.MonkeyPatch,
    small_catalog_file: Path,
    home: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("UV", raising=False)
    monkeypatch.setattr(ts.shutil, "which", lambda name: None)
    assert _main("list", catalog=small_catalog_file) == 1
    assert "uv was not found" in capsys.readouterr().err


def test_no_subcommand_off_a_tty_prints_help(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, fake_uv: FakeUv
) -> None:
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    assert ts.main([]) == 2
    assert "usage: talkpipe-appcenter" in capsys.readouterr().out


def test_script_form_runs_as_a_file(
    fake_uv: FakeUv, small_catalog_file: Path, home: Path
) -> None:
    """The product is the file: ``python talkpipe_appcenter.py`` must work without installation."""
    env = dict(os.environ)
    result = subprocess.run(
        [
            sys.executable,
            str(APPCENTER_DIR / "talkpipe_appcenter.py"),
            "--no-default-catalog",
            "--catalog",
            str(small_catalog_file),
            "list",
            "--json",
        ],
        check=False,
        capture_output=True,
        text=True,
        env=env,
        cwd=str(APPCENTER_DIR),
    )
    assert result.returncode == 0, result.stderr
    assert [row["id"] for row in json.loads(result.stdout)["apps"]] == ["vault", "tool"]
