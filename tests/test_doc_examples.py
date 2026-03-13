"""Pytest tests for documentation examples extracted from markdown."""

import shutil

import pytest
from pathlib import Path

from talkpipe.app.doc_examples import extract_all_examples, run_example

# Project root: tests/ -> parent
_project_root = Path(__file__).resolve().parent.parent

# Artifacts created by doc examples (e.g. README RAG example creates my_knowledge_base)
_DOC_EXAMPLE_ARTIFACTS = ["my_knowledge_base"]


@pytest.fixture(autouse=True)
def _cleanup_doc_example_artifacts():
    """Remove artifacts created by doc examples (e.g. vector DBs) after each test."""
    yield
    for name in _DOC_EXAMPLE_ARTIFACTS:
        path = _project_root / name
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    """Collect doc examples at collection time so new examples are picked up after doc edits."""
    if "path" in metafunc.fixturenames and "line_num" in metafunc.fixturenames and "code" in metafunc.fixturenames:
        examples = extract_all_examples(_project_root)
        metafunc.parametrize(
            "path,line_num,code",
            examples,
            ids=[f"{path}:{line_num}" for path, line_num, _ in examples],
        )


@pytest.mark.requires_ollama
def test_doc_example(path: Path, line_num: int, code: str) -> None:
    """Run a documentation example. Requires Ollama for LLM examples."""
    location = f"{path}:{line_num}"
    success, exc = run_example(location, code)
    if not success and exc is not None:
        raise exc from None
    assert success, f"Example {location} failed"
