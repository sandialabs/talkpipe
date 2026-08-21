"""``talkpipe.pipe.basic`` is a facade over the themed modules it was split into.

Scripts and Python callers that import from ``basic`` must keep working, and
the registry must resolve every name to its new home.
"""

import importlib
import tomllib
from pathlib import Path

import pytest

from talkpipe.chatterlang import registry
from talkpipe.pipe import basic, collect, debug, fields, filters, flow, hashing, shell

THEMED_MODULES = [debug, flow, fields, filters, collect, hashing, shell]
PYPROJECT = Path(__file__).resolve().parents[3] / "pyproject.toml"


def _origin_module(obj) -> str:
    """Decorator-built segments live in ``talkpipe.pipe.core``; look through
    to the function the user decorated."""
    original = getattr(obj, "_original_func", obj)
    return getattr(original, "__module__", "") or ""


def _public_names(module) -> set[str]:
    return {
        name
        for name, obj in vars(module).items()
        if not name.startswith("_")
        and callable(obj)
        and _origin_module(obj) == module.__name__
    }


def test_basic_reexports_every_public_name_of_the_themed_modules():
    expected = set().union(*(_public_names(m) for m in THEMED_MODULES))
    assert set(basic.__all__) == expected
    for name in expected:
        home = next(m for m in THEMED_MODULES if name in _public_names(m))
        assert getattr(basic, name) is getattr(home, name), name


@pytest.mark.parametrize(
    ("name", "module"),
    [
        ("diagPrint", "talkpipe.pipe.debug"),
        ("firstN", "talkpipe.pipe.flow"),
        ("toDict", "talkpipe.pipe.fields"),
        ("lambda", "talkpipe.pipe.filters"),
        ("toList", "talkpipe.pipe.collect"),
        ("hash", "talkpipe.pipe.hashing"),
    ],
)
def test_segment_entry_points_point_at_the_new_homes(name: str, module: str):
    with PYPROJECT.open("rb") as f:
        declared = tomllib.load(f)["project"]["entry-points"]["talkpipe.segments"]
    assert declared[name].split(":")[0] == module
    # ...and the registry resolves the name from that module (lazy import path).
    registered = registry.segment_registry.get(name)
    origin = getattr(registered, "_original_func", registered)
    assert origin.__module__ == module


def test_exec_source_entry_point_points_at_shell():
    with PYPROJECT.open("rb") as f:
        declared = tomllib.load(f)["project"]["entry-points"]["talkpipe.sources"]
    assert declared["exec"] == "talkpipe.pipe.shell:exec"


def test_importing_only_basic_registers_everything():
    """A plain ``import talkpipe.pipe.basic`` must still register the segments."""
    importlib.import_module("talkpipe.pipe.basic")
    for name in ("diagPrint", "cast", "isTrue", "debounce", "toDataFrame", "hash"):
        assert name in registry.segment_registry._registry
    assert "exec" in registry.input_registry._registry
