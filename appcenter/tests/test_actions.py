"""The actions shared by the CLI and the TUI, against the fake uv."""

from __future__ import annotations

import dataclasses
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

import talkpipe_appcenter as ts
from conftest import FakeUv


def _vault(ctx: ts.Context) -> ts.AppEntry:
    entry = ctx.catalog.find("vault")
    assert entry is not None
    return entry


def _tool(ctx: ts.Context) -> ts.AppEntry:
    entry = ctx.catalog.find("tool")
    assert entry is not None
    return entry


def test_install_then_uninstall(ctx: ts.Context, fake_uv: FakeUv) -> None:
    fake_uv.set_canned(
        "talkpipe-vault",
        ["vault-server", "vault-tui"],
        icon="talkpipe_vault/apps/static/icon-256.png",
    )
    fake_uv.set_latest("talkpipe-vault", "1.0.0")
    lines: list[str] = []
    ts.refresh(ctx)

    assert ts.install_app(_vault(ctx), ctx, lines.append)

    assert lines[0].startswith("==> Installing talkpipe-vault (talkpipe-vault) with uv")
    assert any("take a few minutes" in line for line in lines)
    assert "Installed talkpipe-vault 1.0.0." in lines
    assert any("Needs a language model" in line for line in lines)
    assert ctx.status(_vault(ctx)).installed == "1.0.0"
    assert ["tool", "update-shell"] in fake_uv.calls()

    lines.clear()
    assert ts.install_app(_vault(ctx), ctx, lines.append)
    assert "talkpipe-vault 1.0.0 is already the newest version." in lines

    fake_uv.set_latest("talkpipe-vault", "1.1.0")
    lines.clear()
    assert ts.install_app(_vault(ctx), ctx, lines.append)
    assert lines[0].startswith("==> Upgrading")
    assert "Upgraded talkpipe-vault 1.0.0 -> 1.1.0." in lines

    lines.clear()
    assert ts.uninstall_app(_vault(ctx), ctx, lines.append)
    assert any(
        "Your data was left in place: ~/.talkpipe-vault" in line for line in lines
    )
    assert "Uninstalled talkpipe-vault." in lines
    assert ctx.status(_vault(ctx)).installed is None


def test_install_failure_reports_and_returns_false(
    ctx: ts.Context, fake_uv: FakeUv
) -> None:
    fake_uv.fail_next()
    lines: list[str] = []
    ts.refresh(ctx)

    assert not ts.install_app(_tool(ctx), ctx, lines.append)
    assert "uv tool install failed (exit code 1)." in lines
    assert ctx.status(_tool(ctx)).installed is None


def test_uninstall_when_not_installed_is_a_no_op(ctx: ts.Context) -> None:
    lines: list[str] = []
    ts.refresh(ctx)
    assert ts.uninstall_app(_tool(ctx), ctx, lines.append)
    assert lines == ["some-tool is not installed."]


def test_shortcut_add_and_remove_use_the_installed_command(
    ctx: ts.Context, fake_uv: FakeUv, home: Path
) -> None:
    lines: list[str] = []
    ts.refresh(ctx)
    assert ts.add_shortcut(_vault(ctx), ctx, lines.append) == []
    assert "not installed" in lines[0]

    fake_uv.set_installed(
        "talkpipe-vault",
        "1.0.0",
        ["vault-server"],
        icon="talkpipe_vault/apps/static/icon-256.png",
    )
    ts.refresh(ctx)
    lines.clear()
    paths = ts.add_shortcut(_vault(ctx), ctx, lines.append)

    desktop = home / ".local/share/applications/talkpipe-vault.desktop"
    icon = home / ".local/share/icons/hicolor/256x256/apps/talkpipe-vault.png"
    assert paths == [icon, desktop]
    text = desktop.read_text()
    assert f'Exec="{fake_uv.bin / "vault-server"}" "--resume"' in text
    assert "Name=talkpipe-vault" in text
    assert "Icon=talkpipe-vault" in text
    assert ctx.status(_vault(ctx)).launcher
    assert ctx.runs[0][0] == "update-desktop-database"  # type: ignore[attr-defined]

    lines.clear()
    assert ts.remove_shortcut(_vault(ctx), ctx, lines.append) == [desktop, icon]
    assert not ctx.status(_vault(ctx)).launcher
    assert ts.remove_shortcut(_vault(ctx), ctx, lines.append) == []
    assert lines[-1] == "No talkpipe-vault launcher was installed."


def test_uninstall_removes_the_launcher_first(
    ctx: ts.Context, fake_uv: FakeUv, home: Path
) -> None:
    fake_uv.set_installed("talkpipe-vault", "1.0.0", ["vault-server"])
    ts.refresh(ctx)
    ts.add_shortcut(_vault(ctx), ctx, lambda line: None)
    desktop = home / ".local/share/applications/talkpipe-vault.desktop"
    assert desktop.exists()

    assert ts.uninstall_app(_vault(ctx), ctx, lambda line: None)
    assert not desktop.exists()


def test_store_shortcut_runs_uv_run_store_url(
    ctx: ts.Context, fake_uv: FakeUv, home: Path
) -> None:
    lines: list[str] = []
    assert not ts.appcenter_launcher_present(ctx)

    paths = ts.add_appcenter_shortcut(ctx, lines.append)

    desktop = home / ".local/share/applications/talkpipe-appcenter.desktop"
    assert paths == [desktop]
    text = desktop.read_text()
    assert f'Exec="{fake_uv.exe}" "run" "{ts.APPCENTER_URL}"' in text
    assert "Name=TalkPipe App Center" in text
    assert ts.appcenter_launcher_present(ctx)
    assert ts.remove_appcenter_shortcut(ctx, lines.append) == [desktop]
    assert not ts.appcenter_launcher_present(ctx)


def test_explain_needs(ctx: ts.Context, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ts.shutil, "which", lambda name: None)
    assert ts.explain_needs(_vault(ctx), ctx) == [
        (
            "Needs a language model: install Ollama from https://ollama.com/download "
            "(then `ollama pull mistral-small`), or enter an OpenAI or Anthropic API "
            "key in the app's settings."
        )
    ]
    monkeypatch.setattr(ts.shutil, "which", lambda name: "/usr/bin/ollama")
    assert ts.explain_needs(_vault(ctx), ctx) == [
        "Ollama detected: local models will work out of the box."
    ]
    other = dataclasses.replace(_vault(ctx), needs=("postgres",))
    assert ts.explain_needs(other, ctx) == [
        "Needs postgres (not something the App Center can install)."
    ]
    assert ts.explain_needs(_tool(ctx), ctx) == []


def test_open_app_only_when_running(ctx: ts.Context, fake_uv: FakeUv) -> None:
    lines: list[str] = []
    ts.refresh(ctx)
    assert not ts.open_app(_tool(ctx), ctx, lines.append)
    assert "no web page" in lines[-1]
    assert not ts.open_app(_vault(ctx), ctx, lines.append)
    assert "not running" in lines[-1]
    ctx.statuses["vault"] = dataclasses.replace(ctx.status(_vault(ctx)), running=True)
    assert ts.open_app(_vault(ctx), ctx, lines.append)
    assert ctx.opened == ["http://127.0.0.1:18002/"]  # type: ignore[attr-defined]


def test_launch_requires_install_and_opens_when_running(
    ctx: ts.Context, fake_uv: FakeUv
) -> None:
    ts.refresh(ctx)
    result = ts.launch_app(_vault(ctx), ctx, lambda line: None)
    assert not result.ok
    assert "not installed" in result.message

    fake_uv.set_installed("talkpipe-vault", "1.0.0", ["vault-server"])
    ts.refresh(ctx)
    ctx.statuses["vault"] = dataclasses.replace(ctx.status(_vault(ctx)), running=True)
    result = ts.launch_app(_vault(ctx), ctx, lambda line: None)
    assert result.ok
    assert "already running" in result.message
    assert ctx.opened == ["http://127.0.0.1:18002/"]  # type: ignore[attr-defined]


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX process groups")
def test_launch_web_app_detached_then_stop(
    ctx: ts.Context, fake_uv: FakeUv, home: Path
) -> None:
    """A tiny real server stands in for the app: launch waits for its port, stop kills it."""
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()
    fake_uv.set_installed("talkpipe-vault", "1.0.0", ["vault-server"])
    server = fake_uv.bin / "vault-server"
    server.write_text(
        f"#!{sys.executable}\nimport http.server\n"
        f"http.server.HTTPServer(('127.0.0.1', {port}), http.server.SimpleHTTPRequestHandler).serve_forever()\n"
    )
    server.chmod(0o755)
    entry = dataclasses.replace(
        _vault(ctx), port=port, health=None, args=(), opens_browser=False
    )
    ctx.catalog = dataclasses.replace(ctx.catalog, apps=(entry, ctx.catalog.apps[1]))
    ctx.fetch = lambda url, timeout: (
        b"ok"
        if url.startswith(f"http://127.0.0.1:{port}")
        else (_ for _ in ()).throw(OSError())
    )
    ts.refresh(ctx)
    lines: list[str] = []

    result = ts.launch_app(entry, ctx, lines.append)

    try:
        assert result.ok, result.message
        assert result.pid is not None
        assert ctx.opened == [f"http://127.0.0.1:{port}/"]  # type: ignore[attr-defined]
        assert (ctx.state_dir / "vault.pid").read_text() == str(result.pid)
        assert (ctx.state_dir / "vault.log").exists()
        assert ctx.status(entry).pid == result.pid
        assert ctx.status(entry).running is True

        lines.clear()
        assert ts.stop_app(entry, ctx, lines.append)
        assert lines[-1] == "Stopped talkpipe-vault."
        assert not (ctx.state_dir / "vault.pid").exists()
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and ts.tcp_open("127.0.0.1", port):
            time.sleep(0.1)
        assert not ts.tcp_open("127.0.0.1", port)
    finally:
        if result.pid:
            with pytest.raises((ProcessLookupError, PermissionError)) as _:
                os.killpg(result.pid, 9)


def test_stop_without_pid_explains(ctx: ts.Context, fake_uv: FakeUv) -> None:
    lines: list[str] = []
    ts.refresh(ctx)
    assert not ts.stop_app(_vault(ctx), ctx, lines.append)
    assert lines == ["talkpipe-vault is not running."]
    ctx.statuses["vault"] = dataclasses.replace(ctx.status(_vault(ctx)), running=True)
    assert not ts.stop_app(_vault(ctx), ctx, lines.append)
    assert "not started by the App Center" in lines[-1]


def test_launch_cli_app_runs_in_foreground(ctx: ts.Context, fake_uv: FakeUv) -> None:
    fake_uv.set_installed("some-tool", "0.1", ["some-tool"])
    (fake_uv.bin / "some-tool").write_text("#!/bin/sh\nexit 3\n")
    ts.refresh(ctx)
    lines: list[str] = []

    result = ts.launch_app(_tool(ctx), ctx, lines.append)

    assert not result.ok
    assert result.message == "some-tool exited with status 3."
    assert lines[0].startswith("==> Running ")


def test_default_state_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    assert (
        ts.default_state_dir("linux", {"XDG_STATE_HOME": str(tmp_path)})
        == tmp_path / "talkpipe-appcenter"
    )
    assert (
        ts.default_state_dir("linux", {})
        == Path.home() / ".local" / "state" / "talkpipe-appcenter"
    )
    assert (
        ts.default_state_dir("win32", {"LOCALAPPDATA": str(tmp_path)})
        == tmp_path / "talkpipe-appcenter"
    )


def test_process_alive(ctx: ts.Context) -> None:
    assert ts._process_alive(os.getpid(), "linux")
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait()
    assert not ts._process_alive(proc.pid, "linux")
