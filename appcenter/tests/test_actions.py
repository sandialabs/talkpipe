"""The actions shared by the CLI and the TUI, against the fake uv."""

from __future__ import annotations

import contextlib
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
    assert any("Needs a language model" in line for line in lines)
    # The outcome is the last line, and marked: uv's own output scrolls past it
    # and ends in lines that themselves start with "Installed".
    assert lines[-1] == "==> Done: Installed talkpipe-vault 1.0.0."
    assert ctx.status(_vault(ctx)).installed == "1.0.0"
    assert ["tool", "update-shell"] in fake_uv.calls()

    lines.clear()
    assert ts.install_app(_vault(ctx), ctx, lines.append)
    assert lines[-1] == "==> Done: talkpipe-vault 1.0.0 is already the newest version."

    fake_uv.set_latest("talkpipe-vault", "1.1.0")
    lines.clear()
    assert ts.install_app(_vault(ctx), ctx, lines.append)
    assert lines[0].startswith("==> Upgrading")
    assert lines[-1] == "==> Done: Upgraded talkpipe-vault 1.0.0 -> 1.1.0."

    lines.clear()
    assert ts.uninstall_app(_vault(ctx), ctx, lines.append)
    assert any(
        "Your data was left in place: ~/.talkpipe-vault" in line for line in lines
    )
    assert lines[-1] == "==> Done: Uninstalled talkpipe-vault."
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
            "(then `ollama pull mistral-small`), point the app at an Ollama server on "
            "another computer in its settings, or enter an OpenAI or Anthropic API "
            "key there."
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
        assert (ctx.state_dir / "vault.pid").read_text() == f"{result.pid}\n{port}\n"
        assert (ctx.state_dir / "vault.log").exists()
        assert ctx.status(entry).pid == result.pid
        assert ctx.status(entry).port == port
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


def _taken_port() -> tuple[socket.socket, int]:
    """A listening socket the caller must close, and the port it holds."""
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    return listener, listener.getsockname()[1]


def test_choose_launch_port_relocates_only_when_it_can(ctx: ts.Context) -> None:
    listener, port = _taken_port()
    lines: list[str] = []
    try:
        stuck = dataclasses.replace(_vault(ctx), port=port)
        refused = (
            f"Port {port} is already in use by another program, and its catalog "
            "entry does not say how to ask for a different one (port_option). "
            f"Stop whatever is using port {port} and launch again."
        )
        assert ts.choose_launch_port(stuck, lines.append) == (None, refused)
        assert lines == []

        movable = dataclasses.replace(stuck, port_option="--port")
        chosen, refusal = ts.choose_launch_port(movable, lines.append)
        assert refusal is None
        assert chosen is not None
        assert chosen > port
        announced = (
            f"Port {port} is already in use by another program; "
            f"starting on port {chosen} instead."
        )
        assert lines == [announced]
    finally:
        listener.close()
    lines.clear()
    assert ts.choose_launch_port(_vault(ctx), lines.append) == (_vault(ctx).port, None)
    assert lines == []


def test_launch_refuses_a_taken_port_it_cannot_move_off(
    ctx: ts.Context, fake_uv: FakeUv
) -> None:
    """Nothing is started, and the reason is immediate rather than a 30 s timeout."""
    listener, port = _taken_port()
    fake_uv.set_installed("talkpipe-vault", "1.0.0", ["vault-server"])
    entry = dataclasses.replace(_vault(ctx), port=port)
    ctx.catalog = dataclasses.replace(ctx.catalog, apps=(entry, ctx.catalog.apps[1]))
    ts.refresh(ctx)
    lines: list[str] = []
    try:
        result = ts.launch_app(entry, ctx, lines.append)
    finally:
        listener.close()

    assert not result.ok
    assert result.pid is None
    assert f"Port {port} is already in use" in result.message
    assert not (ctx.state_dir / "vault.pid").exists()


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX process groups")
def test_launch_starts_on_a_free_port_when_the_default_is_taken(
    ctx: ts.Context, fake_uv: FakeUv
) -> None:
    """The App Center moves the app and then follows it to where it went."""
    listener, taken = _taken_port()
    fake_uv.set_installed("talkpipe-vault", "1.0.0", ["vault-server"])
    server = fake_uv.bin / "vault-server"
    server.write_text(
        f"#!{sys.executable}\nimport http.server, sys\n"
        "port = int(sys.argv[sys.argv.index('--port') + 1])\n"
        "http.server.HTTPServer(('127.0.0.1', port), "
        "http.server.SimpleHTTPRequestHandler).serve_forever()\n"
    )
    server.chmod(0o755)
    entry = dataclasses.replace(
        _vault(ctx), port=taken, port_option="--port", args=(), opens_browser=False
    )
    ctx.catalog = dataclasses.replace(ctx.catalog, apps=(entry, ctx.catalog.apps[1]))
    # The health check answers only for a port something really listens on, and
    # never for the blocker: the program squatting on the port is not this app.
    ctx.fetch = lambda url, timeout: (
        b"ok"
        if (probed := int(url.split("/")[2].split(":")[1])) != taken
        and ts.tcp_open("127.0.0.1", probed)
        else (_ for _ in ()).throw(OSError("no answer"))
    )
    ts.refresh(ctx)
    assert ctx.status(entry).running is False
    lines: list[str] = []

    result = ts.launch_app(entry, ctx, lines.append)

    try:
        assert result.ok, result.message
        moved = ctx.status(entry).port
        assert moved is not None
        assert moved > taken
        assert result.url == f"http://127.0.0.1:{moved}/"
        assert ctx.opened == [result.url]  # type: ignore[attr-defined]
        announced = (
            f"Port {taken} is already in use by another program; "
            f"starting on port {moved} instead."
        )
        assert announced in lines
        assert (ctx.state_dir / "vault.pid").read_text() == f"{result.pid}\n{moved}\n"
        assert ctx.status(entry).running is True
        assert ts.tcp_open("127.0.0.1", moved)
    finally:
        listener.close()
        if result.pid:
            with contextlib.suppress(OSError):
                os.killpg(result.pid, 9)


def test_launch_reports_an_app_that_dies_at_startup(
    ctx: ts.Context, fake_uv: FakeUv
) -> None:
    """A server that exits is reported at once, with what it printed."""
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    free = probe.getsockname()[1]
    probe.close()
    fake_uv.set_installed("talkpipe-vault", "1.0.0", ["vault-server"])
    server = fake_uv.bin / "vault-server"
    server.write_text("#!/bin/sh\necho 'Error: cannot bind' >&2\nexit 2\n")
    server.chmod(0o755)
    entry = dataclasses.replace(_vault(ctx), port=free, args=(), opens_browser=False)
    ctx.catalog = dataclasses.replace(ctx.catalog, apps=(entry, ctx.catalog.apps[1]))
    ts.refresh(ctx)
    lines: list[str] = []

    started = time.monotonic()
    result = ts.launch_app(entry, ctx, lines.append)

    assert not result.ok
    assert time.monotonic() - started < 15  # not the full 30 s wait
    assert "exited with status 2 instead of starting" in result.message
    assert "Error: cannot bind" in lines
    assert result.pid is None
    assert not (ctx.state_dir / "vault.pid").exists()


def _alive_child(ctx: ts.Context) -> subprocess.Popen[bytes]:
    """A process in its own session, recorded as the vault the App Center started."""
    child = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        start_new_session=True,
    )
    ctx.state_dir.mkdir(parents=True, exist_ok=True)
    (ctx.state_dir / "vault.pid").write_text(f"{child.pid}\n18002\n")
    return child


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX process groups")
def test_launch_does_not_start_a_second_copy_of_an_instance_it_owns(
    ctx: ts.Context, fake_uv: FakeUv
) -> None:
    """A live process of ours that is not answering (still starting, or an
    older release without the health route) is reported, not doubled: a
    second start would relocate to the next port, overwrite the pid record,
    and leave the first server with nothing tracking it."""
    fake_uv.set_installed("talkpipe-vault", "1.0.0", ["vault-server"])
    child = _alive_child(ctx)
    try:
        ts.refresh(ctx)
        assert ctx.status(_vault(ctx)).pid == child.pid
        assert ctx.status(_vault(ctx)).running is False
        lines: list[str] = []

        result = ts.launch_app(_vault(ctx), ctx, lines.append)

        assert not result.ok
        assert result.pid == child.pid
        assert f"started by the App Center (pid {child.pid})" in result.message
        assert "not answering on port 18002" in result.message
        assert "Stop it" in result.message
        assert not any("Starting" in line for line in lines)
        assert (ctx.state_dir / "vault.pid").read_text() == f"{child.pid}\n18002\n"
    finally:
        with contextlib.suppress(OSError):
            os.killpg(child.pid, 9)
        child.wait()


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX process groups")
def test_uninstall_stops_an_instance_it_started(
    ctx: ts.Context, fake_uv: FakeUv
) -> None:
    """Otherwise the server keeps serving out of an environment that is gone,
    with no row that says so."""
    fake_uv.set_installed("talkpipe-vault", "1.0.0", ["vault-server"])
    child = _alive_child(ctx)
    try:
        ts.refresh(ctx)
        lines: list[str] = []

        assert ts.uninstall_app(_vault(ctx), ctx, lines.append)

        assert "talkpipe-vault is running; stopping it first." in lines
        assert f"==> Stopping talkpipe-vault (pid {child.pid})" in lines
        assert lines[-1] == "==> Done: Uninstalled talkpipe-vault."
        assert not (ctx.state_dir / "vault.pid").exists()
        assert child.wait(timeout=5) != 0
        assert ctx.status(_vault(ctx)).pid is None
    finally:
        with contextlib.suppress(OSError):
            os.killpg(child.pid, 9)


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
