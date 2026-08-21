"""Heavy third-party packages used by a single segment are imported inside
that segment, not when its module loads, so importing talkpipe stays light and
those packages can later become optional extras without further change."""

import subprocess
import sys

import pytest


@pytest.mark.parametrize(
    ("module", "package"),
    [
        ("talkpipe.pipe.collect", "pandas"),
        ("talkpipe.pipe.basic", "pandas"),
        ("talkpipe.data.extraction", "docx"),
    ],
)
def test_importing_module_does_not_import_heavy_package(module: str, package: str):
    code = (
        f"import sys, {module}; "
        f"assert {package!r} not in sys.modules, {package!r} + ' imported eagerly'"
    )
    subprocess.run([sys.executable, "-c", code], check=True)


def test_to_dataframe_still_works():
    from talkpipe.pipe.collect import ToDataFrame

    (frame,) = list(ToDataFrame()([{"a": 1}, {"a": 2}]))
    assert list(frame["a"]) == [1, 2]
