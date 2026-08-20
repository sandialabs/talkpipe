"""Every source/segment registered with a decorator inside talkpipe must also
be declared as an entry point in pyproject.toml, otherwise it is invisible to
name lookup, suggestions and ``talkpipe_plugins --list`` until its module
happens to be imported."""

import importlib
import pkgutil
import tomllib
from pathlib import Path

import pytest

import talkpipe
from talkpipe.chatterlang import registry

PYPROJECT = Path(__file__).resolve().parents[3] / "pyproject.toml"


def _import_everything() -> None:
    for module_info in pkgutil.walk_packages(talkpipe.__path__, "talkpipe."):
        try:
            importlib.import_module(module_info.name)
        except Exception:  # optional deps missing, app modules with side effects
            continue


def _declared(group: str) -> set[str]:
    with PYPROJECT.open("rb") as f:
        data = tomllib.load(f)
    return set(data["project"]["entry-points"][group])


def _origin_module(cls: object) -> str:
    """Module of the object the user actually decorated (decorator-built classes
    all live in ``talkpipe.pipe.core``, so look through to the wrapped function)."""
    original = getattr(cls, "_original_func", cls)
    return getattr(original, "__module__", "") or ""


def _registered(reg: registry.HybridRegistry) -> set[str]:
    return {
        name
        for name, cls in reg._registry.items()
        if _origin_module(cls).startswith("talkpipe.")
    }


@pytest.mark.skipif(not PYPROJECT.exists(), reason="pyproject.toml not available")
@pytest.mark.parametrize(
    ("reg", "group"),
    [
        (registry.segment_registry, "talkpipe.segments"),
        (registry.input_registry, "talkpipe.sources"),
    ],
    ids=["segments", "sources"],
)
def test_every_registered_component_has_an_entry_point(
    reg: registry.HybridRegistry, group: str
) -> None:
    _import_everything()
    missing = _registered(reg) - _declared(group)
    assert not missing, (
        f"Registered but not declared in pyproject.toml [{group}]: {sorted(missing)}. "
        "Run `chatterlang_generate_entry_points src/talkpipe` and update pyproject.toml."
    )


def test_strip_base64_declared() -> None:
    assert "stripBase64" in _declared("talkpipe.segments")
