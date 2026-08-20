"""The package ships a PEP 561 marker so consumers' type checkers use its annotations."""

from importlib import resources


def test_py_typed_marker_is_packaged() -> None:
    assert resources.files("talkpipe").joinpath("py.typed").is_file()
