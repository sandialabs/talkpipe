from talkpipe.llm.prompt_adapters import OllamaPromptAdapter

from prompt_adapter_contract_suite import (
    PromptAdapterSpec,
    run_shared_live_contract_checks,
    run_shared_offline_contract_checks,
)


def _patch_ollama_constructor(monkeypatch):
    class DummyOllamaModule:
        @staticmethod
        def chat(*_args, **_kwargs):
            return None

    monkeypatch.setattr(OllamaPromptAdapter, "_require_dependency", lambda *_args, **_kwargs: DummyOllamaModule)


def _patch_ollama_execute(monkeypatch, adapter, response_text: str):
    class DummyMessage:
        content = response_text

    class DummyResponse:
        message = DummyMessage()

    monkeypatch.setattr(adapter, "_chat_completion", lambda *_args, **_kwargs: DummyResponse())


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


def test_ollama_chat_completion_uses_configured_server_url(monkeypatch):
    _patch_ollama_constructor(monkeypatch)
    adapter = OllamaPromptAdapter("llama3.2", server_url="http://custom")
    captured = {}

    class DummyClient:
        def __init__(self, host):
            captured["host"] = host

        def chat(self, *_args, **_kwargs):
            class DummyMessage:
                content = "ok"

            class DummyResponse:
                message = DummyMessage()

            return DummyResponse()

    class DummyOllamaModule:
        Client = DummyClient

    monkeypatch.setattr(OllamaPromptAdapter, "_require_dependency", lambda *_args, **_kwargs: DummyOllamaModule)

    adapter._chat_completion("llama3.2", [{"role": "user", "content": "hello"}])
    assert captured["host"] == "http://custom"
