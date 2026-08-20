"""talkpipe exposes its installed version as ``talkpipe.__version__``."""

from importlib.metadata import version

import talkpipe


def test_version_matches_installed_metadata() -> None:
    assert talkpipe.__version__ == version("talkpipe")


def test_version_is_exported() -> None:
    assert "__version__" in talkpipe.__all__
