import pytest
from fastapi.testclient import TestClient

from talkpipe.app import chatterlang_workbench


FORK_SYNTAX_ERROR = (
    'INPUT FROM echo[data="x"] | fork(print, llmPrompt[model=llama3.2])'
)


@pytest.fixture
def client():
    return TestClient(chatterlang_workbench.app)


def test_compile_reports_syntax_error_inside_fork(client):
    response = client.post("/compile", json={"script": FORK_SYNTAX_ERROR})

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "Compilation error:" in detail
    assert "Syntax error in ChatterLang script" in detail
    assert "quoted" in detail


@pytest.mark.parametrize("mode", ["parse", "full"])
def test_lint_reports_syntax_error_inside_fork(client, mode):
    payload = {"script": FORK_SYNTAX_ERROR, "mode": mode}
    response = client.post("/api/lint", json=payload)

    assert response.status_code == 200
    diagnostics = response.json()["diagnostics"]
    assert len(diagnostics) == 1
    diagnostic = diagnostics[0]
    assert diagnostic["kind"] == "syntax"
    assert diagnostic["severity"] == "error"
    assert diagnostic["line"] == 1
    assert diagnostic["column"] > 1
    assert "quoted" in diagnostic["message"]
