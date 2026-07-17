"""Tests for /api/suggest, /api/suggest/stats and /api/settings."""

import json

import pytest
from fastapi.testclient import TestClient

from talkpipe.app import chatterlang_workbench
from talkpipe.app.workbench import suggest, suggest_api, workspace
from talkpipe.util.config import reset_config, get_config


class FakeAdapter:
    """Stands in for an LLM prompt adapter."""

    canned_output = '[{"segment": "print", "params_hint": "", "rationale": "show results"}]'
    available = True
    last_prompt = None

    def __init__(self, model, **kwargs):
        self.model = model

    def is_available(self):
        return FakeAdapter.available

    def complete_text_without_context(self, prompt, **kwargs):
        FakeAdapter.last_prompt = prompt
        return FakeAdapter.canned_output


@pytest.fixture
def client(tmp_path, monkeypatch):
    workspace.set_workspace_dir(tmp_path)
    suggest_api.invalidate_stats_cache()
    suggest.invalidate_availability_cache()
    FakeAdapter.canned_output = (
        '[{"segment": "print", "params_hint": "", "rationale": "show results"}]'
    )
    FakeAdapter.available = True
    FakeAdapter.last_prompt = None
    yield TestClient(chatterlang_workbench.app)
    workspace.set_workspace_dir(None)
    suggest_api.invalidate_stats_cache()
    suggest.invalidate_availability_cache()


@pytest.fixture
def with_fake_llm(client, monkeypatch):
    monkeypatch.setattr(suggest, "getPromptAdapter", lambda name: FakeAdapter)
    monkeypatch.setattr(suggest, "getPromptSources", lambda: ["ollama", "fake"])
    monkeypatch.setenv("TALKPIPE_default_model_source", "ollama")
    monkeypatch.setenv("TALKPIPE_default_model_name", "test-model")
    reset_config()
    get_config()
    yield client
    reset_config()


# --- stats -----------------------------------------------------------------

def test_stats_endpoint_shape(client):
    response = client.get("/api/suggest/stats")
    assert response.status_code == 200
    data = response.json()
    assert "starts" in data and "bigrams" in data


def test_stats_reflect_saved_pipelines(client):
    before = client.get("/api/suggest/stats").json()
    client.post("/api/pipelines", json={
        "name": "Mine", "script": "INPUT FROM echo | firstN[n=2]",
    })
    after = client.get("/api/suggest/stats").json()
    gained = (after["bigrams"].get("echo", {}).get("firstN", 0)
              - before["bigrams"].get("echo", {}).get("firstN", 0))
    assert gained >= 3


# --- /api/suggest -----------------------------------------------------------

def test_suggest_unavailable_without_model(client, monkeypatch):
    monkeypatch.delenv("TALKPIPE_default_model_source", raising=False)
    monkeypatch.delenv("TALKPIPE_default_model_name", raising=False)
    reset_config()
    response = client.post("/api/suggest", json={"script": "| print"})
    assert response.status_code == 200
    data = response.json()
    assert data["available"] is False
    assert data["suggestions"] == []
    # The response says why, so API consumers aren't left guessing.
    assert data["error"] == "no model configured"
    reset_config()


def test_suggest_happy_path(with_fake_llm):
    response = with_fake_llm.post("/api/suggest", json={
        "script": "INPUT FROM echo |", "cursor_offset": 17,
    })
    data = response.json()
    assert data["available"] is True
    assert data["model"] == "test-model"
    assert data["suggestions"] == [
        {"segment": "print", "params_hint": "", "rationale": "show results"}
    ]
    assert "<CURSOR>" in FakeAdapter.last_prompt
    assert "ChatterLang" in FakeAdapter.last_prompt


def test_suggest_filters_hallucinated_segments(with_fake_llm):
    FakeAdapter.canned_output = json.dumps([
        {"segment": "totallyMadeUpSegment", "rationale": "nope"},
        {"segment": "print", "rationale": "real"},
    ])
    data = with_fake_llm.post("/api/suggest", json={"script": "| x"}).json()
    assert [s["segment"] for s in data["suggestions"]] == ["print"]


def test_suggest_unparseable_output_degrades(with_fake_llm):
    FakeAdapter.canned_output = "I think you should use the print segment!"
    data = with_fake_llm.post("/api/suggest", json={"script": "| x"}).json()
    assert data["available"] is True
    assert data["suggestions"] == []
    assert data["error"] == "unparseable model output"


def test_suggest_unavailable_adapter(with_fake_llm):
    FakeAdapter.available = False
    data = with_fake_llm.post("/api/suggest", json={"script": "| x"}).json()
    assert data["available"] is False


def test_suggest_includes_similar_saved_pipelines(with_fake_llm):
    with_fake_llm.post("/api/pipelines", json={
        "name": "Related", "description": "uses echo",
        "script": 'INPUT FROM echo[data="x"] | print',
    })
    with_fake_llm.post("/api/suggest", json={
        "script": "INPUT FROM echo |", "cursor_offset": 17,
    })
    assert "Related" in FakeAdapter.last_prompt


def test_no_llm_suggestions_kill_switch(with_fake_llm, monkeypatch):
    monkeypatch.setenv("TALKPIPE_workbench_llm_suggestions", "false")
    reset_config()
    data = with_fake_llm.post("/api/suggest", json={"script": "| x"}).json()
    assert data["available"] is False
    assert data["error"] == "LLM suggestions disabled (--no-llm-suggestions)"
    reset_config()


# --- settings -----------------------------------------------------------------

def test_settings_roundtrip(with_fake_llm, tmp_path):
    response = with_fake_llm.get("/api/settings")
    assert response.status_code == 200
    data = response.json()
    assert data["suggest_source"] is None
    assert "ollama" in data["known_sources"]
    assert data["resolved"]["available"] is True  # from env default + FakeAdapter

    response = with_fake_llm.put("/api/settings", json={
        "suggest_source": "fake", "suggest_model": "other-model",
        "auto_suggest": True,
    })
    data = response.json()
    assert data["suggest_model"] == "other-model"
    assert data["auto_suggest"] is True
    assert data["resolved"]["source"] == "fake"
    assert data["resolved"]["model"] == "other-model"

    # persisted to <workspace>/settings.json
    stored = json.loads((tmp_path / "settings.json").read_text())
    assert stored["suggest_model"] == "other-model"

    # settings override the env default in resolution
    data = with_fake_llm.post("/api/suggest", json={"script": "| x"}).json()
    assert data["model"] == "other-model"


def test_settings_put_unknown_source_rejected(with_fake_llm):
    response = with_fake_llm.put("/api/settings", json={
        "suggest_source": "notaprovider", "suggest_model": "x",
    })
    assert response.status_code == 422
    assert "notaprovider" in response.json()["detail"]
    # nothing was persisted
    data = with_fake_llm.get("/api/settings").json()
    assert data["suggest_source"] is None


def test_resolved_reason_distinguishes_kill_switch(with_fake_llm, monkeypatch):
    monkeypatch.setenv("TALKPIPE_workbench_llm_suggestions", "false")
    reset_config()
    data = with_fake_llm.get("/api/settings").json()
    assert data["resolved"]["available"] is False
    assert "disabled" in data["resolved"]["reason"]
    reset_config()


def test_resolved_reason_unreachable_ollama_mentions_server_url(with_fake_llm):
    FakeAdapter.available = False
    data = with_fake_llm.get("/api/settings").json()
    resolved = data["resolved"]
    assert resolved["available"] is False
    assert "not reachable" in resolved["reason"]
    assert "TALKPIPE_OLLAMA_SERVER_URL" in resolved["reason"]
    assert "test-model" in resolved["reason"]


def test_resolved_reason_unknown_stored_source(with_fake_llm, tmp_path):
    # A stale settings.json can hold a source the install no longer knows.
    (tmp_path / "settings.json").write_text(json.dumps({
        "suggest_source": "notaprovider", "suggest_model": "x",
    }))
    data = with_fake_llm.get("/api/settings").json()
    resolved = data["resolved"]
    assert resolved["available"] is False
    assert "unknown LLM source 'notaprovider'" in resolved["reason"]


def test_suggest_unreachable_error_has_hint(with_fake_llm):
    FakeAdapter.available = False
    data = with_fake_llm.post("/api/suggest", json={"script": "| x"}).json()
    assert data["available"] is False
    assert "not reachable" in data["error"]


def test_settings_precedence(with_fake_llm, monkeypatch):
    monkeypatch.setenv("TALKPIPE_workbench_suggest_model", "cli-model")
    reset_config()
    # CLI/env beats the default...
    data = with_fake_llm.get("/api/settings").json()
    assert data["resolved"]["model"] == "cli-model"
    # ...but the settings file beats the CLI/env.
    with_fake_llm.put("/api/settings", json={"suggest_model": "ui-model"})
    data = with_fake_llm.get("/api/settings").json()
    assert data["resolved"]["model"] == "ui-model"
    reset_config()
