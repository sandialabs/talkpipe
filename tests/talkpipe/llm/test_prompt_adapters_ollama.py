import pytest

from prompt_adapter_contract_suite import (
    PromptAdapterSpec,
    run_shared_live_contract_checks,
    run_shared_offline_contract_checks,
)
from talkpipe.llm.prompt_adapters import OllamaPromptAdapter


def _patch_ollama_constructor(monkeypatch):
    class DummyOllamaModule:
        @staticmethod
        def chat(*_args, **_kwargs):
            return None

    monkeypatch.setattr(
        OllamaPromptAdapter,
        "_require_dependency",
        lambda *_args, **_kwargs: DummyOllamaModule,
    )


def _patch_ollama_execute(monkeypatch, adapter, response_text: str):
    class DummyMessage:
        content = response_text

    class DummyResponse:
        message = DummyMessage()

    monkeypatch.setattr(
        adapter, "_chat_completion", lambda *_args, **_kwargs: DummyResponse()
    )


OLLAMA_SPEC = PromptAdapterSpec(
    name="ollama",
    adapter_cls=OllamaPromptAdapter,
    model="llama3.2",
    source="ollama",
    availability_fixture="requires_ollama",
    constructor_patch=_patch_ollama_constructor,
    execute_patch=_patch_ollama_execute,
)


def test_ollama_shared_offline_contract(monkeypatch):
    run_shared_offline_contract_checks(OLLAMA_SPEC, monkeypatch)


def test_ollama_shared_live_contract(request):
    run_shared_live_contract_checks(OLLAMA_SPEC, request)


def test_ollama_availability_probe_caps_generation(monkeypatch):
    # is_available() is called from latency-sensitive paths (the workbench
    # settings endpoint probes it before responding); the test completion must
    # not run an uncapped generation, which on a thinking model takes minutes.
    _patch_ollama_constructor(monkeypatch)
    adapter = OllamaPromptAdapter(model="llama3.2")
    seen = {}

    def fake_chat_completion(_model, messages=None, options=None, **_kwargs):
        seen["options"] = options or {}

        class DummyMessage:
            content = "ok"

        class DummyResponse:
            message = DummyMessage()

        return DummyResponse()

    monkeypatch.setattr(adapter, "_chat_completion", fake_chat_completion)
    assert adapter.is_available() is True
    assert seen["options"].get("num_predict") == 1


def test_ollama_chat_completion_uses_configured_server_url(monkeypatch):
    _patch_ollama_constructor(monkeypatch)
    adapter = OllamaPromptAdapter("llama3.2", server_url="http://custom")
    captured = {}

    class DummyClient:
        def __init__(self, host=None, **_kwargs):
            captured["host"] = host

        def chat(self, *_args, **_kwargs):
            class DummyMessage:
                content = "ok"

            class DummyResponse:
                message = DummyMessage()

            return DummyResponse()

    class DummyOllamaModule:
        Client = DummyClient

    monkeypatch.setattr(
        OllamaPromptAdapter,
        "_require_dependency",
        lambda *_args, **_kwargs: DummyOllamaModule,
    )

    adapter._chat_completion("llama3.2", [{"role": "user", "content": "hello"}])
    assert captured["host"] == "http://custom"


def test_ollama_chat_completion_missing_model_reports_status_code_once(monkeypatch):
    import ollama

    adapter = OllamaPromptAdapter("llama9.99", server_url="http://custom:11434")

    class DummyClient:
        def __init__(self, host=None, **_kwargs):
            pass

        def chat(self, *_args, **_kwargs):
            raise ollama.ResponseError("model 'llama9.99' not found", status_code=404)

    class DummyOllamaModule:
        Client = DummyClient
        ResponseError = ollama.ResponseError

    monkeypatch.setattr(
        OllamaPromptAdapter,
        "_require_dependency",
        lambda *_args, **_kwargs: DummyOllamaModule,
    )

    try:
        adapter._chat_completion("llama9.99", [{"role": "user", "content": "hello"}])
        raise AssertionError("expected ResponseError")
    except ollama.ResponseError as exc:
        message = str(exc)
        assert (
            "Model 'llama9.99' is not available on the Ollama server at http://custom:11434"
            in message
        )
        assert "ollama pull llama9.99" in message
        assert message.count("(status code: 404)") == 1


def test_ollama_chat_completion_connection_error_names_url_and_env_var(monkeypatch):
    adapter = OllamaPromptAdapter("llama3.2", server_url="http://custom:11434")

    class DummyClient:
        def __init__(self, host=None, **_kwargs):
            pass

        def chat(self, *_args, **_kwargs):
            raise ConnectionError("Failed to connect to Ollama.")

    class DummyOllamaModule:
        Client = DummyClient

    monkeypatch.setattr(
        OllamaPromptAdapter,
        "_require_dependency",
        lambda *_args, **_kwargs: DummyOllamaModule,
    )

    with pytest.raises(ConnectionError) as exc_info:
        adapter._chat_completion("llama3.2", [{"role": "user", "content": "hello"}])
    message = str(exc_info.value)
    assert "http://custom:11434" in message
    assert "TALKPIPE_OLLAMA_SERVER_URL" in message
    # The example must stay paste-safe: an angle-bracket placeholder like
    # <host> is parsed as a shell redirection when copied into a terminal.
    assert "http://your-ollama-host:11434" in message
    assert "<host>" not in message
