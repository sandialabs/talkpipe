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

# The pre-split module imported these for its own use, so callers could — and
# did — import them from ``basic`` as well.  They are part of the facade's
# contract even though ``basic`` never defined them.
INHERITED_NAMES = {
    "AbstractFieldSegment": "talkpipe.pipe.core",
    "AbstractSegment": "talkpipe.pipe.core",
    "field_segment": "talkpipe.pipe.core",
    "segment": "talkpipe.pipe.core",
    "source": "talkpipe.pipe.core",
    "configure_logger": "talkpipe.util.config",
    "get_config": "talkpipe.util.config",
    "parse_key_value_str": "talkpipe.util.config",
    "assign_property": "talkpipe.util.data_manipulation",
    "compileLambda": "talkpipe.util.data_manipulation",
    "dict_to_text": "talkpipe.util.data_manipulation",
    "extract_property": "talkpipe.util.data_manipulation",
    "extract_template_field_names": "talkpipe.util.data_manipulation",
    "fill_template": "talkpipe.util.data_manipulation",
    "get_all_attributes": "talkpipe.util.data_manipulation",
    "get_type_safely": "talkpipe.util.data_manipulation",
    "toDict": "talkpipe.util.data_manipulation",
    "run_command": "talkpipe.util.os",
}


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
    assert expected <= set(basic.__all__)
    for name in expected:
        home = next(m for m in THEMED_MODULES if name in _public_names(m))
        assert getattr(basic, name) is getattr(home, name), name


@pytest.mark.parametrize(("name", "home"), sorted(INHERITED_NAMES.items()))
def test_basic_still_reexports_what_it_imported_before_the_split(name: str, home: str):
    assert name in basic.__all__
    assert getattr(basic, name) is getattr(importlib.import_module(home), name)


def test_registry_module_is_still_reachable_from_basic():
    assert basic.registry is importlib.import_module("talkpipe.chatterlang.registry")
    assert "registry" in basic.__all__


def test_all_is_exactly_the_themed_names_plus_the_inherited_ones():
    """``__all__`` drives ``import *``; nothing may creep in or fall out."""
    themed = set().union(*(_public_names(m) for m in THEMED_MODULES))
    assert set(basic.__all__) == themed | set(INHERITED_NAMES) | {"registry"}
    assert sorted(basic.__all__) == list(basic.__all__)


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
