"""Pytest tests for documentation examples extracted from markdown."""

import shutil
from pathlib import Path

import pytest

from talkpipe.app.doc_examples import (
    extract_all_examples_with_requirements,
    extract_python_blocks_with_requirements,
    run_example,
)

# Project root: tests/ -> parent
_project_root = Path(__file__).resolve().parent.parent

# Artifacts created by doc examples (e.g. README RAG example creates my_knowledge_base)
_DOC_EXAMPLE_ARTIFACTS = ["my_knowledge_base", "my_kb"]


def _is_safe_to_delete(root: Path, name: str) -> bool:
    """Return True only if name is a safe child of root (no path traversal)."""
    if not name or "/" in name or "\\" in name or ".." in name:
        return False
    try:
        child = (root / name).resolve()
        root_resolved = root.resolve()
        return child != root_resolved and child.is_relative_to(root_resolved)
    except (OSError, RuntimeError, ValueError):
        return False


def test_is_safe_to_delete():
    """Ensure cleanup only deletes paths strictly under project root."""
    root = _project_root
    assert _is_safe_to_delete(root, "my_knowledge_base") is True
    assert _is_safe_to_delete(root, "foo") is True
    assert _is_safe_to_delete(root, "") is False
    assert _is_safe_to_delete(root, "..") is False
    assert _is_safe_to_delete(root, "a/b") is False
    assert _is_safe_to_delete(root, "a\\b") is False
    assert _is_safe_to_delete(root, "../etc") is False


@pytest.fixture(autouse=True)
def _cleanup_doc_example_artifacts():
    """Remove artifacts created by doc examples (e.g. vector DBs) after each test."""
    yield
    for name in _DOC_EXAMPLE_ARTIFACTS:
        if not _is_safe_to_delete(_project_root, name):
            continue
        path = _project_root / name
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)


def _safe_test_id(path: Path, line_num: int) -> str:
    """Produce a test ID safe for shell and IDE parsing (no brackets, colons, or dots in ID)."""
    # e.g. README.md:277 -> README_md-277, docs/foo.md:74 -> docs_foo_md-74
    stem = str(path).replace(".", "_").replace("/", "_").replace("\\", "_")
    return f"{stem}-{line_num}"


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    """Collect doc examples at collection time so new examples are picked up after doc edits.

    Examples that declare a requirement (``<!-- doc-example: requires-ollama -->``
    on the line before the fence) get the matching marker and skip when the
    service is unavailable; every other example runs unconditionally.
    """
    if (
        "path" in metafunc.fixturenames
        and "line_num" in metafunc.fixturenames
        and "code" in metafunc.fixturenames
    ):
        examples = extract_all_examples_with_requirements(_project_root)
        params = [
            pytest.param(
                path,
                line_num,
                code,
                sorted(requirements),
                marks=[getattr(pytest.mark, f"requires_{r}") for r in requirements],
                id=_safe_test_id(path, line_num),
            )
            for path, line_num, code, requirements in examples
        ]
        metafunc.parametrize("path,line_num,code,requirements", params)


def test_directive_parsing() -> None:
    """The doc-example directive gates, skips, and rejects typos."""
    content = (
        "<!-- doc-example: requires-ollama -->\n```python\nx = 1\n```\n"
        "text\n```python\ny = 2\n```\n"
        "<!-- doc-example: skip -->\n```python\nraise SystemExit\n```\n"
        "<!-- doc-example: requires-openai, requires-ollama -->\n```python\nz = 3\n```\n"
    )
    blocks = extract_python_blocks_with_requirements(content)
    assert [(c, set(r)) for _, c, r in blocks] == [
        ("x = 1", {"ollama"}),
        ("y = 2", set()),
        ("z = 3", {"openai", "ollama"}),
    ]
    with pytest.raises(ValueError, match="Unknown doc-example requirement"):
        extract_python_blocks_with_requirements(
            "<!-- doc-example: requires-olama -->\n```python\nx\n```\n"
        )


def test_doc_example(
    request: pytest.FixtureRequest,
    path: Path,
    line_num: int,
    code: str,
    requirements: list[str],
) -> None:
    """Run a documentation example, skipping if a declared service is unavailable."""
    for requirement in requirements:
        request.getfixturevalue(f"requires_{requirement}")
    location = f"{path}:{line_num}"
    success, exc = run_example(location, code)
    if not success and exc is not None:
        raise exc from None
    assert success, f"Example {location} failed"
