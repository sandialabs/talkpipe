"""Tests for the workbench /api/reference and /api/lint endpoints."""

import pytest
from fastapi.testclient import TestClient

from talkpipe.app import chatterlang_workbench
from talkpipe.app.workbench import reference_api
from talkpipe.chatterlang.compiler import CompileError, compile as chatterlang_compile


@pytest.fixture
def client():
    return TestClient(chatterlang_workbench.app)


@pytest.fixture(autouse=True)
def fresh_reference_cache():
    reference_api.invalidate_reference_cache()
    yield
    reference_api.invalidate_reference_cache()


# --- /api/reference ---------------------------------------------------------

def test_reference_contains_known_components(client):
    response = client.get("/api/reference")
    assert response.status_code == 200
    components = {c["name"]: c for c in response.json()["components"]}

    assert "echo" in components
    assert components["echo"]["type"] == "source"

    assert "print" in components
    assert components["print"]["type"] in ("segment", "field_segment")

    llm_prompt = components["llmPrompt"]
    assert llm_prompt["type"] == "segment"
    param_names = [p["name"] for p in llm_prompt["params"]]
    assert "model" in param_names
    assert llm_prompt["summary"]


def test_reference_is_cached(client, monkeypatch):
    client.get("/api/reference")

    def boom():
        raise AssertionError("reference rebuilt despite cache")

    monkeypatch.setattr(reference_api.chatterlang_reference_generator,
                        "analyze_registered_items", boom)
    response = client.get("/api/reference")
    assert response.status_code == 200


# --- /api/lint: parse mode ----------------------------------------------------

def test_lint_clean_script(client):
    response = client.post("/api/lint", json={"script": 'INPUT FROM echo[data="hi"] | print'})
    assert response.status_code == 200
    assert response.json()["diagnostics"] == []


def test_lint_empty_script(client):
    response = client.post("/api/lint", json={"script": "   "})
    assert response.json()["diagnostics"] == []


def test_lint_syntax_error_has_position(client):
    script = 'INPUT FROM echo[data="hi"] |\n| print'
    response = client.post("/api/lint", json={"script": script})
    diagnostics = response.json()["diagnostics"]
    assert len(diagnostics) == 1
    d = diagnostics[0]
    assert d["kind"] == "syntax"
    assert d["severity"] == "error"
    assert d["line"] >= 1 and d["column"] >= 1


def test_lint_unquoted_string_hint(client):
    response = client.post("/api/lint", json={"script": "| llmPrompt[model=llama3.2]"})
    diagnostics = response.json()["diagnostics"]
    assert len(diagnostics) == 1
    assert "quoted" in diagnostics[0]["message"]


def test_lint_unknown_segment_did_you_mean(client):
    response = client.post("/api/lint", json={"script": 'INPUT FROM echo[data="x"] | prnt'})
    diagnostics = response.json()["diagnostics"]
    assert len(diagnostics) == 1
    d = diagnostics[0]
    assert d["kind"] == "unknown_name"
    assert "'prnt' not found" in d["message"]
    assert "print" in d["message"]  # did-you-mean suggestion
    assert d["line"] == 1
    assert d["column"] == 29


def test_lint_unknown_source(client):
    response = client.post("/api/lint", json={"script": "INPUT FROM nosuchsource | print"})
    diagnostics = response.json()["diagnostics"]
    assert len(diagnostics) == 1
    assert diagnostics[0]["kind"] == "unknown_name"
    assert "nosuchsource" in diagnostics[0]["message"]


def test_lint_bad_param_name(client):
    # llmPrompt is class-based, so its __init__ signature is introspectable.
    response = client.post("/api/lint", json={"script": '| llmPrompt[nonsense_param="x"]'})
    diagnostics = response.json()["diagnostics"]
    assert len(diagnostics) == 1
    d = diagnostics[0]
    assert d["kind"] == "bad_param"
    assert d["severity"] == "warning"
    assert "nonsense_param" in d["message"]


def test_lint_skips_param_check_for_uninspectable_components(client):
    # Function-based components forward **kwargs; no false positives allowed.
    response = client.post("/api/lint", json={"script": 'INPUT FROM echo[data="x", delimiter=","] | print'})
    assert response.json()["diagnostics"] == []


def test_lint_checks_inside_loops(client):
    script = 'INPUT FROM echo[data="1"] | @x;\nLOOP 2 TIMES { INPUT FROM @x | bogusSegment | @x };\nINPUT FROM @x | print'
    response = client.post("/api/lint", json={"script": script})
    diagnostics = response.json()["diagnostics"]
    assert any(d["kind"] == "unknown_name" and "bogusSegment" in d["message"]
               for d in diagnostics)
    bogus = next(d for d in diagnostics if "bogusSegment" in d["message"])
    assert bogus["line"] == 2


# --- /api/lint: full mode -----------------------------------------------------

def test_lint_full_mode_reports_compile_error(client, monkeypatch):
    def fake_compile(script):
        raise CompileError("Segment 'x' exploded", kind="unknown_name", bad_name="x")

    monkeypatch.setattr(reference_api.chatterlang_compiler, "compile", fake_compile)
    response = client.post("/api/lint", json={"script": "| something", "mode": "full"})
    diagnostics = response.json()["diagnostics"]
    assert len(diagnostics) == 1
    assert diagnostics[0]["message"] == "Segment 'x' exploded"
    assert diagnostics[0]["kind"] == "unknown_name"


def test_lint_full_mode_clean(client):
    response = client.post(
        "/api/lint",
        json={"script": 'INPUT FROM echo[data="hi"] | print', "mode": "full"},
    )
    assert response.json()["diagnostics"] == []


# --- CompileError backward compatibility ---------------------------------------

def test_compile_error_message_format_unchanged():
    """The formatted messages existing callers rely on must not change."""
    with pytest.raises(CompileError) as excinfo:
        chatterlang_compile('INPUT FROM echo[data="x"] | prnt')
    message = str(excinfo.value)
    assert "Segment 'prnt' not found." in message
    assert "Did you mean" in message
    assert excinfo.value.kind == "unknown_name"
    assert excinfo.value.bad_name == "prnt"


def test_compile_error_syntax_attributes():
    with pytest.raises(CompileError) as excinfo:
        chatterlang_compile("| llmPrompt[model=llama3.2]")
    assert excinfo.value.kind == "syntax"
    assert excinfo.value.line == 1
    assert excinfo.value.column is not None
    assert "quoted" in str(excinfo.value)


def test_compile_error_plain_construction_still_works():
    err = CompileError("boom")
    assert str(err) == "boom"
    assert err.line is None and err.kind is None
