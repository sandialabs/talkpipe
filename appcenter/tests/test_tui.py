"""The App Center screen, driven with Textual's Pilot against the fake uv."""

from __future__ import annotations

from pathlib import Path

import pytest
from textual.pilot import Pilot
from textual.widgets import DataTable, Footer, RichLog, Static
from textual.widgets._footer import FooterKey

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


def _footer_keys(app: ts.AppCenterApp) -> dict[str, str]:
    """What the footer offers right now: key -> description, as rendered."""
    footer = app.query_one(Footer)
    return {item.key: item.description for item in footer.query(FooterKey)}


def _notices(app: ts.AppCenterApp) -> str:
    return "\n".join(n.message for n in app._notifications)


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


async def test_title_states_the_experimental_channel(
    ctx: ts.Context, fake_uv: FakeUv
) -> None:
    """The title is the only line visible at every terminal size."""
    ctx.experimental = True
    app = ts.AppCenterApp(ctx)
    async with app.run_test(size=SIZE) as pilot:
        await _wait_workers(app, pilot)
        assert "experimental channel" in str(app.query_one("#title", Static).content)


async def test_title_is_quiet_on_the_stable_channel(
    ctx: ts.Context, fake_uv: FakeUv
) -> None:
    app = ts.AppCenterApp(ctx)
    async with app.run_test(size=SIZE) as pilot:
        await _wait_workers(app, pilot)
        assert "experimental" not in str(app.query_one("#title", Static).content)


async def test_channel_key_switches_one_app_between_channels(
    ctx: ts.Context, fake_uv: FakeUv
) -> None:
    """One copy of the App Center serves both channels, per application.

    No flag for the run, no environment variable, no second copy of the file:
    ``e`` installs the pre-release of the app under the cursor, and ``e``
    again returns it to releases. The record follows, so a later plain
    upgrade keeps whichever channel was chosen.
    """
    fake_uv.set_latest("talkpipe-vault", "1.0.1")
    fake_uv.set_latest_pre("talkpipe-vault", "1.1.0b1")
    fake_uv.set_canned("talkpipe-vault", ["vault-server"])
    app = ts.AppCenterApp(ctx)
    async with app.run_test(size=SIZE) as pilot:
        await _wait_workers(app, pilot)
        detail = str(app.query_one("#detail", Static).content)
        assert "channel:   stable (press e for the pre-release)" in detail

        await pilot.press("e")
        await _wait_workers(app, pilot)
        assert _cell(app, "vault", 2) == "installed (pre-release)"
        assert _cell(app, "vault", 3) == "1.1.0b1"
        assert ts.read_channels(ts.channels_path()) == {
            "talkpipe-vault": ts.EXPERIMENTAL
        }
        detail = str(app.query_one("#detail", Static).content)
        assert "channel:   experimental (press e to return to releases)" in detail
        assert "Press e on the talkpipe-vault row for its release again." in _log_text(
            app
        )
        # The other app is untouched: the choice is per application.
        assert _cell(app, "tool", 2) == "not installed"

        await pilot.press("e")
        await _wait_workers(app, pilot)
        assert _cell(app, "vault", 2) == "installed"
        assert _cell(app, "vault", 3) == "1.0.1"
        assert ts.read_channels(ts.channels_path()) == {}
        assert "Switched talkpipe-vault to the release channel" in _log_text(app)


async def test_footer_names_the_channel_the_key_moves_to(
    ctx: ts.Context, fake_uv: FakeUv
) -> None:
    """The way back has to be visible without the detail pane, which a short
    terminal hides: the footer names the direction ``e`` goes for this row."""
    fake_uv.set_latest_pre("talkpipe-vault", "1.1.0b1")
    fake_uv.set_canned("talkpipe-vault", ["vault-server"])
    app = ts.AppCenterApp(ctx)
    async with app.run_test(size=SIZE) as pilot:
        await _wait_workers(app, pilot)
        assert _footer_keys(app)["e"] == "Pre-release"

        await pilot.press("e")
        await _wait_workers(app, pilot)
        assert _footer_keys(app)["e"] == "Release"

        # Per application: the row below is still on releases.
        await pilot.press("down")
        await _settle(pilot)
        assert _footer_keys(app)["e"] == "Pre-release"


async def test_channel_key_moves_a_whole_selection_one_way(
    ctx: ts.Context, fake_uv: FakeUv
) -> None:
    """A batch goes where the key says it goes, not one flip per application."""
    for name in ("talkpipe-vault", "some-tool"):
        fake_uv.set_latest_pre(name, "9.9.9b1")
        fake_uv.set_canned(name, [name])
    app = ts.AppCenterApp(ctx)
    async with app.run_test(size=SIZE) as pilot:
        await _wait_workers(app, pilot)
        await pilot.press("space", "down", "space")
        await _settle(pilot)
        assert _footer_keys(app)["e"] == "Pre-release"

        await pilot.press("e")
        await _wait_workers(app, pilot)
        assert _cell(app, "vault", 2) == "installed (pre-release)"
        assert _cell(app, "tool", 2) == "installed (pre-release)"
        assert ts.read_channels(ts.channels_path()) == {
            "talkpipe-vault": ts.EXPERIMENTAL,
            "some-tool": ts.EXPERIMENTAL,
        }


async def test_channel_key_says_where_the_choice_lives_off_an_app_row(
    ctx: ts.Context, fake_uv: FakeUv
) -> None:
    """The App Center's own row has no channel to switch, so ``e`` explains
    rather than silently doing nothing, and the footer does not offer it."""
    app = ts.AppCenterApp(ctx)
    async with app.run_test(size=SIZE) as pilot:
        await _wait_workers(app, pilot)
        await pilot.press("down", "down")  # past both apps, onto the last row
        await _settle(pilot)
        assert "e" not in _footer_keys(app)

        await pilot.press("e")
        await _settle(pilot)
        assert "chosen per application" in _notices(app)
        assert not [c for c in fake_uv.calls() if c[:2] == ["tool", "install"]]


async def test_channel_key_defers_to_a_flag_for_the_whole_run(
    ctx: ts.Context, fake_uv: FakeUv
) -> None:
    """With ``--experimental`` for the run, every install is on that channel."""
    ctx.experimental = True
    app = ts.AppCenterApp(ctx)
    async with app.run_test(size=SIZE) as pilot:
        await _wait_workers(app, pilot)
        # Nothing to toggle, so nothing is advertised in either place.
        assert "e" not in _footer_keys(app)
        detail = str(app.query_one("#detail", Static).content)
        assert "channel:   experimental (this run: --experimental)" in detail

        await pilot.press("e")
        await _wait_workers(app, pilot)
        assert "--experimental" in _notices(app)
        assert not [c for c in fake_uv.calls() if c[:2] == ["tool", "install"]]
        assert _cell(app, "vault", 2) == "not installed"


async def test_row_does_not_offer_to_downgrade_a_prerelease(
    ctx: ts.Context, fake_uv: FakeUv
) -> None:
    fake_uv.set_installed("talkpipe-vault", "1.1.0b1", ["vault-server"])
    ctx.channels = {"talkpipe-vault": ts.EXPERIMENTAL}
    app = ts.AppCenterApp(ctx)
    async with app.run_test(size=SIZE) as pilot:
        await _wait_workers(app, pilot)
        assert _cell(app, "vault", 2) == "installed (pre-release)"
        assert _cell(app, "vault", 3) == "1.1.0b1"
