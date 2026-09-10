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
