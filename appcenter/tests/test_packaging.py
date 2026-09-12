"""The single file stays self-contained and stampable."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import talkpipe_appcenter as ts

APPCENTER_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = APPCENTER_DIR.parent
SCRIPT = APPCENTER_DIR / "talkpipe_appcenter.py"


def _pep723_block() -> dict[str, object]:
    text = SCRIPT.read_text()
    match = re.search(
        r"^# /// script\n(?P<body>(?:^#(?: .*)?\n)+?)^# ///$", text, re.MULTILINE
    )
    assert match, "no PEP 723 block at the top of the file"
    body = "\n".join(
        line[2:] if line.startswith("# ") else line[1:]
        for line in match.group("body").splitlines()
    )
    return tomllib.loads(body)


def test_pep723_header_declares_only_textual() -> None:
    """Textual is the App Center's one dependency, capped at its major on purpose."""
    header = _pep723_block()
    assert header["dependencies"] == ["textual>=8,<9"]


def test_pep723_python_floor_matches_talkpipe() -> None:
    project = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text())["project"]
    assert _pep723_block()["requires-python"] == project["requires-python"]


def test_pep723_block_is_the_first_thing_in_the_file() -> None:
    assert SCRIPT.read_text().startswith("# /// script\n")


def test_version_placeholder_is_stampable() -> None:
    """CI replaces the placeholder line with the tag; it must exist exactly once."""
    text = SCRIPT.read_text()
    assert text.count('STAMPED_VERSION = "0.0.0+unknown"') == 1
    assert ts.__version__ == ts.STAMPED_VERSION == "0.0.0+unknown"


def test_store_url_is_the_latest_talkpipe_release_asset() -> None:
    assert ts.APPCENTER_URL == (
        "https://github.com/sandialabs/talkpipe/releases/latest/download/talkpipe_appcenter.py"
    )


def test_experimental_url_is_the_rolling_prerelease_asset() -> None:
    """``releases/latest`` skips pre-releases, so a beta needs its own release."""
    assert ts.APPCENTER_EXPERIMENTAL_URL == (
        "https://github.com/sandialabs/talkpipe/releases/download/experimental/talkpipe_appcenter.py"
    )
    assert ts.ROLLING_URLS == (ts.APPCENTER_URL, ts.APPCENTER_EXPERIMENTAL_URL)
