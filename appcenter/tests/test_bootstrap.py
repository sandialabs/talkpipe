"""The bootstrap scripts stay coherent with the App Center; nothing here executes them."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

import talkpipe_appcenter as ts

APPCENTER_DIR = Path(__file__).resolve().parent.parent
INSTALL_SH = APPCENTER_DIR / "install.sh"
INSTALL_PS1 = APPCENTER_DIR / "install.ps1"


@pytest.mark.parametrize("shell", ["sh", "dash", "bash"])
def test_install_sh_parses(shell: str) -> None:
    if shutil.which(shell) is None:
        pytest.skip(f"{shell} not installed")
    result = subprocess.run(
        [shell, "-n", str(INSTALL_SH)], check=False, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr


def test_install_sh_runs_nothing_until_fully_downloaded() -> None:
    assert INSTALL_SH.read_text().rstrip().endswith('main "$@"')


@pytest.mark.parametrize("path", [INSTALL_SH, INSTALL_PS1])
def test_scripts_point_at_the_store_url(path: Path) -> None:
    text = path.read_text()
    assert ts.APPCENTER_URL in text
    assert "astral.sh/uv/install" in text
    assert "uv is the only thing this script installs" in text


def test_install_sh_reattaches_the_terminal_when_piped() -> None:
    text = INSTALL_SH.read_text()
    assert "</dev/tty" in text
    assert 'exec "$uv" run "$APPCENTER_URL" "$@"' in text


@pytest.mark.parametrize("path", [INSTALL_SH, INSTALL_PS1])
def test_scripts_offer_the_experimental_channel(path: Path) -> None:
    """Both need it: ``releases/latest`` cannot serve a pre-release at all."""
    text = path.read_text()
    assert ts.APPCENTER_EXPERIMENTAL_URL in text
    assert ts.CHANNEL_ENV in text


def test_install_sh_switches_channel_by_name_not_by_url() -> None:
    """The script runs what it downloads, so the URL must not come from outside."""
    text = INSTALL_SH.read_text()
    assert 'APPCENTER_URL="$APPCENTER_EXPERIMENTAL_URL"' in text
    assert "TALKPIPE_APPCENTER_URL" not in text


def _run_install_sh(
    tmp_path: Path, *args: str, env: dict[str, str] | None = None
) -> str:
    """Run install.sh with a uv that only reports how it was called."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    uv = bin_dir / "uv"
    uv.write_text('#!/bin/sh\necho "uv $*"\n')
    uv.chmod(0o755)
    result = subprocess.run(
        ["sh", str(INSTALL_SH), *args],
        check=True,
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        env={
            "PATH": f"{bin_dir}:/usr/bin:/bin",
            "HOME": str(tmp_path),
            **(env or {}),
        },
    )
    return result.stdout


def test_install_sh_runs_the_stable_url_by_default(tmp_path: Path) -> None:
    out = _run_install_sh(tmp_path)
    assert f"uv run {ts.APPCENTER_URL}" in out


def test_install_sh_starts_where_there_is_no_controlling_terminal(
    tmp_path: Path,
) -> None:
    """Regression: it used to exit 2 instead of starting.

    /dev/tty exists and passes ``-r`` even with no controlling terminal to open
    (a CI runner, a cron job, a detached session), so the reattach redirect has
    to be guarded by actually opening it. ``_run_install_sh`` reproduces the
    case, since its stdin is not a terminal.
    """
    out = _run_install_sh(tmp_path)
    assert "uv run" in out


def test_install_sh_experimental_flag_switches_the_url(tmp_path: Path) -> None:
    out = _run_install_sh(tmp_path, "--experimental")
    assert f"uv run {ts.APPCENTER_EXPERIMENTAL_URL}" in out


def test_install_sh_channel_env_switches_the_url(tmp_path: Path) -> None:
    """The only mechanism Windows has, where a piped `irm | iex` takes no arguments."""
    out = _run_install_sh(tmp_path, env={ts.CHANNEL_ENV: "experimental"})
    assert f"uv run {ts.APPCENTER_EXPERIMENTAL_URL}" in out


def test_install_sh_forwards_arguments_after_the_channel_flag(tmp_path: Path) -> None:
    out = _run_install_sh(tmp_path, "--experimental", "install", "vault")
    assert f"uv run {ts.APPCENTER_EXPERIMENTAL_URL} install vault" in out
