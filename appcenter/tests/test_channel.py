"""The experimental channel: pre-release detection, the flag, and the record."""

from __future__ import annotations

from pathlib import Path

import pytest

import talkpipe_appcenter as ts
from conftest import SMALL_CATALOG, FakeUv


@pytest.fixture
def small_catalog_file(tmp_path: Path) -> Path:
    path = tmp_path / "small.toml"
    path.write_text(SMALL_CATALOG)
    return path


def _main(*argv: str, catalog: Path) -> int:
    return ts.main(["--no-default-catalog", "--catalog", str(catalog), *argv])


def _last_install(fake_uv: FakeUv) -> list[str]:
    """The most recent `tool install` argv; later calls (list, update-shell) are not it."""
    installs = [c for c in fake_uv.calls() if c[:2] == ["tool", "install"]]
    assert installs, "no install was attempted"
    return installs[-1]


@pytest.mark.parametrize(
    ("version", "expected"),
    [
        ("1.1.0b1", True),
        ("1.1.0a2", True),
        ("2.0rc1", True),
        ("v1.1.0b1", True),
        ("1.0.1", False),
        ("1.0.1.post1", False),
        # A development copy of the file: a local version, not a pre-release, so
        # a checkout stays on the stable channel.
        ("0.0.0+unknown", False),
        ("", False),
    ],
)
def test_is_prerelease(version: str, expected: bool) -> None:
    assert ts.is_prerelease(version) is expected


def test_default_channel_reads_the_environment() -> None:
    assert ts.default_channel({}) == ts.STABLE
    assert ts.default_channel({ts.CHANNEL_ENV: "experimental"}) == ts.EXPERIMENTAL
    assert ts.default_channel({ts.CHANNEL_ENV: " experimental "}) == ts.EXPERIMENTAL
    assert ts.default_channel({ts.CHANNEL_ENV: "stable"}) == ts.STABLE
    assert ts.default_channel({ts.CHANNEL_ENV: "yes"}) == ts.STABLE


def test_install_argv_asks_uv_for_prereleases(ctx: ts.Context) -> None:
    entry = ctx.catalog.apps[0]
    argv = ctx.uv.install_argv(entry, prerelease=True)
    assert argv[argv.index("--upgrade") + 1 : argv.index("--upgrade") + 3] == [
        "--prerelease",
        "allow",
    ]
    # Off by default, so every existing caller's argv is unchanged.
    assert "--prerelease" not in ctx.uv.install_argv(entry)


def test_channels_file_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "channels.txt"
    ts.write_channels(path, {"talkpipe-vault": ts.EXPERIMENTAL})
    assert ts.read_channels(path) == {"talkpipe-vault": ts.EXPERIMENTAL}

    ts.record_channel(path, "talkpipe", ts.EXPERIMENTAL)
    assert ts.read_channels(path) == {
        "talkpipe-vault": ts.EXPERIMENTAL,
        "talkpipe": ts.EXPERIMENTAL,
    }

    ts.record_channel(path, "talkpipe-vault", None)
    assert ts.read_channels(path) == {"talkpipe": ts.EXPERIMENTAL}


def test_read_channels_tolerates_junk_and_absence(tmp_path: Path) -> None:
    assert ts.read_channels(tmp_path / "nothing.txt") == {}
    path = tmp_path / "channels.txt"
    path.write_text(
        "# a comment\n"
        "\n"
        "talkpipe-vault experimental\n"
        "some-app nightly\n"  # a channel this version does not know
        "bare-name\n",
        encoding="utf-8",
    )
    assert ts.read_channels(path) == {"talkpipe-vault": ts.EXPERIMENTAL}


def test_experimental_for_prefers_the_explicit_choice(ctx: ts.Context) -> None:
    entry = ctx.catalog.apps[0]
    ctx.channels = {"talkpipe-vault": ts.EXPERIMENTAL}
    assert ctx.experimental_for(entry) is True

    ctx.experimental = False
    assert ctx.experimental_for(entry) is False

    ctx.experimental = None
    ctx.channels = {}
    assert ctx.experimental_for(entry) is False


def test_flag_works_before_and_after_the_subcommand() -> None:
    parser = ts.build_parser()
    assert ts.channel_options(parser.parse_args(["--experimental", "install", "x"]))
    assert ts.channel_options(parser.parse_args(["install", "x", "--experimental"]))
    assert ts.channel_options(parser.parse_args(["install", "x", "--pre"]))
    assert (
        ts.channel_options(parser.parse_args(["--no-experimental", "install", "x"]))
        is False
    )
    assert ts.channel_options(parser.parse_args(["install", "x"])) is None


def test_contradictory_flags_are_refused() -> None:
    parser = ts.build_parser()
    args = parser.parse_args(["install", "x", "--experimental", "--no-experimental"])
    with pytest.raises(ts.CatalogError, match="contradict"):
        ts.channel_options(args)


def test_install_experimental_gets_the_prerelease(
    small_catalog_file: Path,
    fake_uv: FakeUv,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fake_uv.set_latest("talkpipe-vault", "1.0.1")
    fake_uv.set_latest_pre("talkpipe-vault", "1.1.0b1")

    assert _main("install", "vault", "--experimental", catalog=small_catalog_file) == 0
    out = capsys.readouterr().out
    assert "1.1.0b1" in out
    assert "pre-release" in out
    assert fake_uv.state["tools"]["talkpipe-vault"]["version"] == "1.1.0b1"
    assert ts.read_channels(ts.channels_path()) == {"talkpipe-vault": ts.EXPERIMENTAL}


def test_plain_upgrade_does_not_downgrade_a_prerelease(
    small_catalog_file: Path,
    fake_uv: FakeUv,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The reason the record exists.

    uv replays its own recorded settings for ``uv tool upgrade``, but the App
    Center runs ``uv tool install --upgrade``, which takes them from argv. So
    without the record a later upgrade drops the pre-release out of the
    candidate set and reinstalls the newest release over it.
    """
    fake_uv.set_latest("talkpipe-vault", "1.0.1")
    fake_uv.set_latest_pre("talkpipe-vault", "1.1.0b1")
    assert _main("install", "vault", "--experimental", catalog=small_catalog_file) == 0
    capsys.readouterr()

    assert _main("upgrade", "--all", catalog=small_catalog_file) == 0
    assert fake_uv.state["tools"]["talkpipe-vault"]["version"] == "1.1.0b1"
    argv = _last_install(fake_uv)
    assert argv[argv.index("--prerelease") + 1] == "allow"


def test_no_experimental_leaves_the_channel(
    small_catalog_file: Path,
    fake_uv: FakeUv,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fake_uv.set_latest("talkpipe-vault", "1.0.1")
    fake_uv.set_latest_pre("talkpipe-vault", "1.1.0b1")
    assert _main("install", "vault", "--experimental", catalog=small_catalog_file) == 0
    capsys.readouterr()

    assert (
        _main("install", "vault", "--no-experimental", catalog=small_catalog_file) == 0
    )
    assert fake_uv.state["tools"]["talkpipe-vault"]["version"] == "1.0.1"
    assert ts.read_channels(ts.channels_path()) == {}
    # Opting out passes no flag at all rather than `disallow`, which would also
    # reject a dependency that publishes only pre-releases.
    assert "--prerelease" not in _last_install(fake_uv)


def test_uninstall_forgets_the_channel(
    small_catalog_file: Path,
    fake_uv: FakeUv,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fake_uv.set_latest_pre("talkpipe-vault", "1.1.0b1")
    assert _main("install", "vault", "--experimental", catalog=small_catalog_file) == 0
    assert _main("uninstall", "vault", "--yes", catalog=small_catalog_file) == 0
    assert ts.read_channels(ts.channels_path()) == {}


def test_env_var_defaults_the_channel(
    small_catalog_file: Path,
    fake_uv: FakeUv,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv(ts.CHANNEL_ENV, "experimental")
    fake_uv.set_latest("talkpipe-vault", "1.0.1")
    fake_uv.set_latest_pre("talkpipe-vault", "1.1.0b1")
    assert _main("install", "vault", catalog=small_catalog_file) == 0
    assert fake_uv.state["tools"]["talkpipe-vault"]["version"] == "1.1.0b1"


def test_flag_beats_the_env_var(
    small_catalog_file: Path,
    fake_uv: FakeUv,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv(ts.CHANNEL_ENV, "experimental")
    fake_uv.set_latest("talkpipe-vault", "1.0.1")
    fake_uv.set_latest_pre("talkpipe-vault", "1.1.0b1")
    assert (
        _main("install", "vault", "--no-experimental", catalog=small_catalog_file) == 0
    )
    assert fake_uv.state["tools"]["talkpipe-vault"]["version"] == "1.0.1"


def test_status_does_not_offer_to_downgrade_a_prerelease(
    small_catalog_file: Path,
    fake_uv: FakeUv,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """PyPI's newest *release* is not an upgrade target for a pre-release."""
    fake_uv.set_latest("talkpipe-vault", "1.0.1")
    fake_uv.set_latest_pre("talkpipe-vault", "1.1.0b1")
    assert _main("install", "vault", "--experimental", catalog=small_catalog_file) == 0
    capsys.readouterr()

    assert _main("info", "vault", catalog=small_catalog_file) == 0
    out = capsys.readouterr().out
    assert "installed (pre-release)" in out
    assert "upgrade available" not in out
    assert "channel:   experimental" in out


def test_stable_install_is_untouched(
    small_catalog_file: Path,
    fake_uv: FakeUv,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fake_uv.set_latest("talkpipe-vault", "1.0.1")
    fake_uv.set_latest_pre("talkpipe-vault", "1.1.0b1")
    assert _main("install", "vault", catalog=small_catalog_file) == 0
    assert fake_uv.state["tools"]["talkpipe-vault"]["version"] == "1.0.1"
    assert "--prerelease" not in _last_install(fake_uv)
    assert ts.read_channels(ts.channels_path()) == {}
