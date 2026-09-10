"""The desktop launcher writer, ported from the applications with the App Center's names.

Every test runs against a throwaway home directory with the platform passed
explicitly, so the three branches are exercised on any OS and the
developer's real menus are never touched.
"""

import os
import plistlib
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

import talkpipe_appcenter as shortcut
from talkpipe_appcenter import (
    ShortcutError,
    ShortcutSpec,
    install_shortcut,
    resolve_command,
    uninstall_shortcut,
)


@pytest.fixture
def home(tmp_path, monkeypatch):
    """An isolated home; XDG/APPDATA are cleared so defaults derive from it."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    monkeypatch.delenv("APPDATA", raising=False)
    return tmp_path


@pytest.fixture
def fake_command(monkeypatch, tmp_path):
    """Pretend the console script is installed at a known absolute path."""
    exe = tmp_path / "bin" / "vault-server"
    exe.parent.mkdir()
    exe.write_text("#!/bin/sh\n")
    monkeypatch.setattr(shutil, "which", lambda name: str(exe))
    return exe


@pytest.fixture
def runs():
    """Recording stand-in for the external-command runner."""
    calls: list[list[str]] = []
    return calls


@pytest.fixture
def run(runs):
    return lambda argv: runs.append(list(argv))


@pytest.fixture
def spec(tmp_path):
    png = tmp_path / "icon.png"
    png.write_bytes(b"\x89PNG fake")
    ico = tmp_path / "icon.ico"
    ico.write_bytes(b"ico fake")
    return ShortcutSpec(
        app_id="talkpipe-vault-server",
        name="TalkPipe Vault",
        comment="Search your documents",
        command="vault-server",
        args=("--resume",),
        icon_png=png,
        icon_ico=ico,
    )


# --- Linux --------------------------------------------------------------------


def test_linux_writes_desktop_entry_and_icon(home, fake_command, spec, run, runs):
    written = install_shortcut(spec, platform="linux", home=home, run=run)

    desktop = home / ".local/share/applications/talkpipe-vault-server.desktop"
    icon = home / ".local/share/icons/hicolor/256x256/apps/talkpipe-vault-server.png"
    assert written == [icon, desktop]
    assert icon.read_bytes() == spec.icon_png.read_bytes()

    text = desktop.read_text()
    assert "[Desktop Entry]" in text
    assert "Type=Application" in text
    assert "Name=TalkPipe Vault" in text
    assert f'Exec="{fake_command}" "--resume"' in text
    assert "Icon=talkpipe-vault-server" in text
    assert "Terminal=true" in text
    assert "Categories=Office;" in text
    assert desktop.stat().st_mode & stat.S_IXUSR
    assert runs == [["update-desktop-database", str(desktop.parent)]]


def test_linux_honours_xdg_data_home(
    home, fake_command, spec, run, monkeypatch, tmp_path
):
    data = tmp_path / "xdg"
    monkeypatch.setenv("XDG_DATA_HOME", str(data))

    written = install_shortcut(spec, platform="linux", home=home, run=run)

    assert all(p.is_relative_to(data) for p in written)
    assert (data / "applications/talkpipe-vault-server.desktop").is_file()


def test_linux_omits_icon_when_none_shipped(home, fake_command, spec, run):
    bare = ShortcutSpec(
        app_id=spec.app_id,
        name=spec.name,
        comment=spec.comment,
        command=spec.command,
    )

    written = install_shortcut(bare, platform="linux", home=home, run=run)

    assert len(written) == 1
    assert "Icon=" not in written[0].read_text()


def test_linux_exec_quotes_special_characters(home, spec, run, monkeypatch, tmp_path):
    exe = tmp_path / 'odd dir$"' / "vault-server"
    exe.parent.mkdir()
    exe.write_text("")
    monkeypatch.setattr(shutil, "which", lambda name: str(exe))

    install_shortcut(spec, platform="linux", home=home, run=run)

    text = (
        home / ".local/share/applications/talkpipe-vault-server.desktop"
    ).read_text()
    exec_line = next(line for line in text.splitlines() if line.startswith("Exec="))
    assert exec_line == f'Exec="{tmp_path}/odd dir\\$\\"/vault-server" "--resume"'


def test_linux_uninstall_removes_both_and_is_idempotent(
    home, fake_command, spec, run, runs
):
    written = install_shortcut(spec, platform="linux", home=home, run=run)
    runs.clear()

    removed = uninstall_shortcut(spec, platform="linux", home=home, run=run)

    assert sorted(removed) == sorted(written)
    assert not any(p.exists() for p in written)
    assert runs == [["update-desktop-database", str(written[1].parent)]]

    assert uninstall_shortcut(spec, platform="linux", home=home, run=run) == []


def test_linux_reinstall_replaces_existing(home, fake_command, spec, run):
    first = install_shortcut(spec, platform="linux", home=home, run=run)
    second = install_shortcut(spec, platform="linux", home=home, run=run)

    assert first == second
    assert second[1].read_text().count("[Desktop Entry]") == 1


@pytest.mark.skipif(
    shutil.which("desktop-file-validate") is None,
    reason="desktop-file-validate not installed",
)
def test_linux_desktop_entry_validates(home, fake_command, spec, run):
    written = install_shortcut(spec, platform="linux", home=home, run=run)

    result = subprocess.run(
        ["desktop-file-validate", str(written[1])],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr


# --- macOS --------------------------------------------------------------------


def test_macos_writes_app_bundle(home, fake_command, spec, run, runs):
    written = install_shortcut(spec, platform="darwin", home=home, run=run)

    bundle = home / "Applications" / "TalkPipe Vault.app"
    assert written == [bundle]
    contents = bundle / "Contents"

    launcher = contents / "MacOS" / "talkpipe-vault-server"
    assert launcher.stat().st_mode & stat.S_IXUSR
    assert "open -a Terminal" in launcher.read_text()
    assert "Resources/run.command" in launcher.read_text()

    run_command = contents / "Resources" / "run.command"
    assert run_command.stat().st_mode & stat.S_IXUSR
    assert run_command.read_text() == f"#!/bin/sh\nexec '{fake_command}' '--resume'\n"

    with (contents / "Info.plist").open("rb") as fh:
        info = plistlib.load(fh)
    assert info["CFBundleName"] == "TalkPipe Vault"
    assert info["CFBundleExecutable"] == "talkpipe-vault-server"
    assert info["CFBundleIdentifier"] == "gov.sandia.talkpipe-vault-server"
    assert info["CFBundlePackageType"] == "APPL"
    # The icon is built by sips/iconutil, which the stub runner did not run.
    assert "CFBundleIconFile" not in info
    assert runs[-1][:4] == ["iconutil", "-c", "icns", runs[-1][3]]
    assert [c[0] for c in runs[:-1]] == ["sips"] * 5
    assert all(str(spec.icon_png) in c for c in runs[:-1])


def test_macos_bundle_names_icon_when_built(home, fake_command, spec):
    def fake_iconutil(argv):
        if argv[0] == "iconutil":
            Path(argv[-1]).write_bytes(b"icns")

    written = install_shortcut(spec, platform="darwin", home=home, run=fake_iconutil)

    with (written[0] / "Contents" / "Info.plist").open("rb") as fh:
        info = plistlib.load(fh)
    assert info["CFBundleIconFile"] == "talkpipe-vault-server.icns"


def test_macos_uninstall_removes_bundle(home, fake_command, spec, run):
    written = install_shortcut(spec, platform="darwin", home=home, run=run)

    assert uninstall_shortcut(spec, platform="darwin", home=home, run=run) == written
    assert not written[0].exists()
    assert uninstall_shortcut(spec, platform="darwin", home=home, run=run) == []


# --- Windows ------------------------------------------------------------------


def test_windows_creates_start_menu_link_via_powershell(
    home, fake_command, spec, run, runs
):
    written = install_shortcut(spec, platform="win32", home=home, run=run)

    link = (
        home
        / "AppData/Roaming/Microsoft/Windows/Start Menu/Programs"
        / "TalkPipe Vault.lnk"
    )
    assert written == [link]
    assert link.parent.is_dir()
    assert len(runs) == 1
    argv = runs[0]
    assert argv[:6] == [
        "powershell",
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
    ]
    script = argv[6]
    assert f"CreateShortcut('{link}')" in script
    assert f"$s.TargetPath = '{fake_command}'" in script
    assert "$s.Arguments = '--resume'" in script
    assert f"$s.IconLocation = '{spec.icon_ico},0'" in script
    assert script.endswith("$s.Save()")


def test_windows_honours_appdata(home, fake_command, spec, run, monkeypatch, tmp_path):
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))

    written = install_shortcut(spec, platform="win32", home=home, run=run)

    assert written[0].is_relative_to(tmp_path / "Roaming")


def test_windows_omits_icon_when_none_shipped(home, fake_command, spec, run, runs):
    no_ico = ShortcutSpec(
        app_id=spec.app_id,
        name=spec.name,
        comment=spec.comment,
        command=spec.command,
        icon_png=spec.icon_png,
    )

    install_shortcut(no_ico, platform="win32", home=home, run=run)

    assert "IconLocation" not in runs[0][6]


def test_windows_uninstall_removes_link(home, fake_command, spec, run):
    written = install_shortcut(spec, platform="win32", home=home, run=run)
    written[0].write_bytes(b"lnk")  # the stub runner did not create it

    assert uninstall_shortcut(spec, platform="win32", home=home, run=run) == written
    assert uninstall_shortcut(spec, platform="win32", home=home, run=run) == []


# --- common -------------------------------------------------------------------


def test_unsupported_platform_raises(home, fake_command, spec, run):
    with pytest.raises(ShortcutError, match="not supported on plan9"):
        install_shortcut(spec, platform="plan9", home=home, run=run)
    with pytest.raises(ShortcutError, match="not supported on plan9"):
        uninstall_shortcut(spec, platform="plan9", home=home, run=run)


def test_resolve_command_prefers_path(fake_command):
    assert resolve_command("vault-server") == fake_command


def test_resolve_command_falls_back_to_interpreter_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(shutil, "which", lambda name: None)
    exe = tmp_path / "python"
    exe.write_text("")
    script = tmp_path / "vault-server"
    script.write_text("")
    monkeypatch.setattr(shortcut.sys, "executable", str(exe))

    assert resolve_command("vault-server") == script


def test_resolve_command_reports_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(shutil, "which", lambda name: None)
    monkeypatch.setattr(shortcut.sys, "executable", str(tmp_path / "python"))

    with pytest.raises(ShortcutError, match="cannot find the 'vault-server'"):
        resolve_command("vault-server")


def test_default_home_is_the_users(monkeypatch, tmp_path, fake_command, spec, run):
    """Without ``home`` the launcher lands under the real home directory."""
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    os.environ.pop("XDG_DATA_HOME", None)

    written = install_shortcut(spec, platform="linux", run=run)

    assert all(p.is_relative_to(tmp_path) for p in written)


def test_default_runner_tolerates_a_missing_helper_command() -> None:
    """update-desktop-database, sips, and friends are conveniences, not requirements."""
    shortcut._shortcut_run(["talkpipe-appcenter-no-such-helper-command", "--x"])
