"""Every configuration key the docs advertise must be one TalkPipe actually reads.

``talkpipe.util.constants`` is the single list of keys the code looks up; the
docs may not mention a ``TALKPIPE_*`` variable that is not there (that is how
phantom keys such as ``TALKPIPE_DEFAULT_PORT`` lived in the docs for years).
"""

import re
from pathlib import Path

import pytest

from talkpipe.util import constants

ROOT = Path(__file__).resolve().parent.parent
DOCS = [*sorted((ROOT / "docs").rglob("*.md")), ROOT / "README.md", ROOT / "AGENTS.md"]

# Prose placeholders that stand for "any key", not real keys.
PLACEHOLDERS = {"KEY", "*", "VAR_NAME"}


def _known_keys() -> set[str]:
    return {
        value.lower()
        for name, value in vars(constants).items()
        if name.isupper() and isinstance(value, str)
    }


def _appcenter_keys() -> set[str]:
    """``TALKPIPE_APPCENTER_*`` variables the App Center reads.

    The App Center is a single file that is deliberately not part of the
    ``talkpipe`` package and never imports it, so its variables are not in
    ``constants`` -- but a phantom one should still fail, so they are checked
    against the file itself.
    """
    text = (ROOT / "appcenter" / "talkpipe_appcenter.py").read_text(encoding="utf-8")
    return {
        m.group(1).lower() for m in re.finditer(r'"TALKPIPE_(APPCENTER_\w+)"', text)
    }


def _documented_env_keys(path: Path) -> set[str]:
    text = path.read_text(encoding="utf-8")
    keys = set()
    for match in re.finditer(r"TALKPIPE_([A-Za-z0-9_*]+)", text):
        tail = match.group(1)
        if tail.upper() in PLACEHOLDERS:
            continue
        keys.add(tail)
    return keys


def test_constants_are_nonempty_and_distinct() -> None:
    values = [
        value
        for name, value in vars(constants).items()
        if name.isupper() and isinstance(value, str)
    ]
    assert values
    assert all(values)
    lowered = [v.lower() for v in values]
    assert len(set(lowered)) == len(lowered), "two constants name the same key"


@pytest.mark.parametrize("doc", DOCS, ids=[str(d.relative_to(ROOT)) for d in DOCS])
def test_every_documented_env_var_is_a_key_talkpipe_reads(doc: Path) -> None:
    if not doc.exists():
        pytest.skip(f"{doc} not present")
    known = _known_keys() | _appcenter_keys()
    unknown = sorted(k for k in _documented_env_keys(doc) if k.lower() not in known)
    assert not unknown, (
        f"{doc.name} documents TALKPIPE_ variables that nothing reads: {unknown}. "
        "Add the key to talkpipe.util.constants (and read it) or fix the docs."
    )
