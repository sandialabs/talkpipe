"""The App Center screen, driven with Textual's Pilot against the fake uv."""

from __future__ import annotations

from pathlib import Path

import pytest
from textual.pilot import Pilot
from textual.widgets import DataTable, RichLog, Static

import talkpipe_appcenter as ts
from conftest import FakeUv

SIZE = (110, 36)


async def _settle(pilot: Pilot[None], rounds: int = 12) -> None:
    """Let thread workers and renders finish; never waits on a modal-blocked worker."""
    for _ in range(rounds):
        await pilot.pause(0.05)
    await pilot.pause()


async def _wait_workers(
    app: ts.AppCenterApp, pilot: Pilot[None], timeout: float = 20.0
) -> None:
    import time

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not any(w.is_running and w.group != "modal" for w in app.workers):
            await _settle(pilot)
            return
        await pilot.pause(0.05)
    raise AssertionError("workers did not finish")


def _cell(app: ts.AppCenterApp, row: str, column: int) -> str:
    table = app.query_one("#apps", DataTable)
    return str(table.get_cell(row, table.ordered_columns[column].key))


def _log_text(app: ts.AppCenterApp) -> str:
    log = app.query_one("#log", RichLog)
    return "\n".join(line.text for line in log.lines)


async def test_screen_lists_apps_with_status(ctx: ts.Context, fake_uv: FakeUv) -> None:
    fake_uv.set_installed("talkpipe-vault", "1.0.0", ["vault-server"])
    app = ts.AppCenterApp(ctx)
    async with app.run_test(size=SIZE) as pilot:
        await _wait_workers(app, pilot)

        assert _cell(app, "vault", 1) == "talkpipe-vault"
        assert _cell(app, "vault", 2) == "installed"
        assert _cell(app, "vault", 3) == "1.0.0"
        assert _cell(app, "vault", 4) == "?"  # offline
        assert _cell(app, "tool", 2) == "not installed"
        assert _cell(app, ts.APPCENTER_ROW_ID, 1) == "TalkPipe App Center"
        detail = str(app.query_one("#detail", Static).content)
        assert "talkpipe-vault" in detail
        assert "package:   talkpipe-vault" in detail
        assert "Needs a language model" in str(app.query_one("#needs", Static).content)


async def test_install_key_streams_uv_output_and_updates_row(
    ctx: ts.Context, fake_uv: FakeUv
) -> None:
    fake_uv.set_canned("some-tool", ["some-tool"])
    app = ts.AppCenterApp(ctx)
    async with app.run_test(size=SIZE) as pilot:
        await _wait_workers(app, pilot)
        await pilot.press("down")  # cursor on "tool"
        await _settle(pilot)
        await pilot.press("i")
        await _wait_workers(app, pilot)

        log = _log_text(app)
        assert "==> Installing some-tool" in log
        assert "Resolved 12 packages" in log
        assert "Installed some-tool 1.2.3." in log
        assert " + somedep" not in log
        assert _cell(app, "tool", 2) == "installed"
        assert _cell(app, "tool", 3) == "1.2.3"


async def test_space_selects_for_batch_install(
    ctx: ts.Context, fake_uv: FakeUv
) -> None:
    fake_uv.set_canned("talkpipe-vault", ["vault-server"])
    fake_uv.set_canned("some-tool", ["some-tool"])
    app = ts.AppCenterApp(ctx)
    async with app.run_test(size=SIZE) as pilot:
        await _wait_workers(app, pilot)
        await pilot.press("space", "down", "space")
        await _settle(pilot)
        assert _cell(app, "vault", 0) == "*"
        assert _cell(app, "tool", 0) == "*"

        await pilot.press("i")
        await _wait_workers(app, pilot)

        assert sorted(fake_uv.state["tools"]) == ["some-tool", "talkpipe-vault"]
        assert _cell(app, "vault", 0) == ""


async def test_uninstall_asks_and_honours_no_then_yes(
    ctx: ts.Context, fake_uv: FakeUv
) -> None:
    fake_uv.set_installed("some-tool", "0.1", ["some-tool"])
    app = ts.AppCenterApp(ctx)
    async with app.run_test(size=SIZE) as pilot:
        await _wait_workers(app, pilot)
        await pilot.press("down", "x")
        await _settle(pilot)
        assert isinstance(app.screen, ts.ConfirmScreen)
        await pilot.click("#no")
        await _settle(pilot)
        assert "some-tool" in fake_uv.state["tools"]

        await pilot.press("x")
        await _settle(pilot)
        await pilot.click("#yes")
        await _wait_workers(app, pilot)
        assert "some-tool" not in fake_uv.state["tools"]
        assert _cell(app, "tool", 2) == "not installed"
        assert "Uninstalled some-tool." in _log_text(app)


async def test_shortcut_key_toggles_launcher(
    ctx: ts.Context, fake_uv: FakeUv, home: Path
) -> None:
    fake_uv.set_installed("talkpipe-vault", "1.0.0", ["vault-server"])
    desktop = home / ".local/share/applications/talkpipe-vault.desktop"
    app = ts.AppCenterApp(ctx)
    async with app.run_test(size=SIZE) as pilot:
        await _wait_workers(app, pilot)
        await pilot.press("s")
        await _wait_workers(app, pilot)
        assert desktop.exists()
        assert _cell(app, "vault", 6) == "yes"

        await pilot.press("s")
        await _wait_workers(app, pilot)
        assert not desktop.exists()
        assert _cell(app, "vault", 6) == ""

        await pilot.press("down", "down", "s")  # the App Center's own row (last)
        await _settle(pilot)
        assert (home / ".local/share/applications/talkpipe-appcenter.desktop").exists()
        assert _cell(app, ts.APPCENTER_ROW_ID, 6) == "yes"


async def test_open_and_stop_report_when_not_running(
    ctx: ts.Context, fake_uv: FakeUv
) -> None:
    fake_uv.set_installed("talkpipe-vault", "1.0.0", ["vault-server"])
    app = ts.AppCenterApp(ctx)
    async with app.run_test(size=SIZE) as pilot:
        await _wait_workers(app, pilot)
        await pilot.press("o")
        await _settle(pilot)
        assert "not running; launch it first" in _log_text(app)
        await pilot.press("c")
        await _wait_workers(app, pilot)
        assert "is not running." in _log_text(app)


async def test_refresh_key_announces_start_and_finish(
    ctx: ts.Context, fake_uv: FakeUv
) -> None:
    app = ts.AppCenterApp(ctx)
    async with app.run_test(size=SIZE) as pilot:
        await _wait_workers(app, pilot)
        assert "Refreshed." not in _log_text(app)  # the mount refresh is quiet
        fake_uv.set_installed("talkpipe-vault", "1.0.0", ["vault-server"])
        await pilot.press("r")
        await _wait_workers(app, pilot)

        log = _log_text(app).splitlines()
        assert log.index("Refreshing...") < log.index("Refreshed.")
        assert _cell(app, "vault", 2) == "installed"


async def test_refresh_key_reports_a_failed_refresh(
    ctx: ts.Context, fake_uv: FakeUv, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = ts.AppCenterApp(ctx)
    async with app.run_test(size=SIZE) as pilot:
        await _wait_workers(app, pilot)

        def broken(_ctx: ts.Context) -> None:
            raise ts.UvError("uv tool list exited 1")

        monkeypatch.setattr(ts, "refresh", broken)
        await pilot.press("r")
        await _wait_workers(app, pilot)

        log = _log_text(app)
        assert "Refresh failed: uv tool list exited 1" in log
        assert "Refreshed." not in log


@pytest.mark.parametrize("size", [(80, 24), (80, 20)])
async def test_small_terminals_keep_the_table_and_log_on_screen(
    ctx: ts.Context, fake_uv: FakeUv, size: tuple[int, int]
) -> None:
    app = ts.AppCenterApp(ctx)
    async with app.run_test(size=size) as pilot:
        await _wait_workers(app, pilot)
        assert app.screen.has_class("compact") == (size[1] < ts.COMPACT_ROWS)
        table = app.query_one("#apps", DataTable)
        log = app.query_one("#log", RichLog)
        assert table.region.y >= 0
        assert log.region.bottom <= size[1]
        assert log.region.height >= 3


async def test_quit_key(ctx: ts.Context, fake_uv: FakeUv) -> None:
    app = ts.AppCenterApp(ctx)
    async with app.run_test(size=SIZE) as pilot:
        await _wait_workers(app, pilot)
        await pilot.press("q")
        await _settle(pilot)
    assert app.return_code == 0 or app._exit
