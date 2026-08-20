"""Every network-facing LLM client must be constructed with a timeout.

A hung LLM server must not block a pipeline forever, so each adapter passes an
explicit timeout to its SDK client: an explicit ``timeout=`` argument wins,
otherwise the ``llm_timeout`` config key, otherwise the built-in default.
"""

from talkpipe.llm.chat import LLMPrompt
from talkpipe.llm.embedding_adapters import OllamaEmbedderAdapter
from talkpipe.llm.embedding_adapters_openai import OpenAIEmbeddingAdapter
from talkpipe.llm.prompt_adapters import (
    AnthropicPromptAdapter,
    OllamaPromptAdapter,
    OpenAIPromptAdapter,
)
from talkpipe.util.config import reset_config
from talkpipe.util.constants import DEFAULT_LLM_TIMEOUT


class _RecordingOllamaModule:
    """Stand-in for the ``ollama`` package that records Client kwargs."""

    def __init__(self):
        self.captured = {}
        module = self

        class Client:
            def __init__(self, host=None, **kwargs):
                module.captured["host"] = host
                module.captured.update(kwargs)

            def chat(self, *_args, **_kwargs):
                class Message:
                    content = "ok"

                class Response:
                    message = Message()

                return Response()

            def embed(self, **_kwargs):
                return {"embeddings": [[0.0, 1.0]]}

        self.Client = Client
        self.ResponseError = type("ResponseError", (Exception,), {})


def _install_ollama(monkeypatch, cls):
    module = _RecordingOllamaModule()
    monkeypatch.setattr(cls, "_require_dependency", lambda *_a, **_k: module)
    return module


def test_ollama_prompt_adapter_passes_explicit_timeout(monkeypatch):
    module = _install_ollama(monkeypatch, OllamaPromptAdapter)
    adapter = OllamaPromptAdapter("llama3.2", timeout=7.5)
    adapter.execute("hi")
    assert module.captured["timeout"] == 7.5


def test_ollama_prompt_adapter_timeout_defaults_from_config(monkeypatch):
    module = _install_ollama(monkeypatch, OllamaPromptAdapter)
    monkeypatch.setenv("TALKPIPE_llm_timeout", "33")
    reset_config()
    try:
        OllamaPromptAdapter("llama3.2").execute("hi")
    finally:
        reset_config()
    assert module.captured["timeout"] == 33.0


def test_ollama_prompt_adapter_timeout_builtin_default(monkeypatch):
    module = _install_ollama(monkeypatch, OllamaPromptAdapter)
    monkeypatch.delenv("TALKPIPE_llm_timeout", raising=False)
    reset_config()
    try:
        OllamaPromptAdapter("llama3.2").execute("hi")
    finally:
        reset_config()
    assert module.captured["timeout"] == DEFAULT_LLM_TIMEOUT
    # No server_url configured still goes through a Client so the timeout applies.
    assert "host" in module.captured


def test_ollama_embedding_adapter_passes_timeout(monkeypatch):
    module = _RecordingOllamaModule()
    monkeypatch.setattr(OllamaEmbedderAdapter, "_import_ollama", lambda self: module)
    OllamaEmbedderAdapter("nomic", timeout=4).execute_batch(["a"])
    assert module.captured["timeout"] == 4


def _openai_double():
    captured = {}

    class Client:
        pass

    class Module:
        NOT_GIVEN = object()

        class OpenAI:
            def __new__(cls, **kwargs):
                captured.update(kwargs)
                return Client()

    return Module, captured


def test_openai_prompt_adapter_passes_timeout(monkeypatch):
    module, captured = _openai_double()
    monkeypatch.setattr(
        OpenAIPromptAdapter, "_require_dependency", lambda *_a, **_k: module
    )
    OpenAIPromptAdapter("gpt", timeout=12)
    assert captured["timeout"] == 12


def test_openai_embedding_adapter_passes_timeout(monkeypatch):
    module, captured = _openai_double()
    monkeypatch.setattr(
        "talkpipe.llm.embedding_adapters_openai._require_openai", lambda: module
    )
    OpenAIEmbeddingAdapter("emb", timeout=9)
    assert captured["timeout"] == 9


def test_anthropic_prompt_adapter_passes_timeout(monkeypatch):
    captured = {}

    class Module:
        class Anthropic:
            def __new__(cls, **kwargs):
                captured.update(kwargs)
                return object()

    monkeypatch.setattr(
        AnthropicPromptAdapter, "_require_dependency", lambda *_a, **_k: Module
    )
    AnthropicPromptAdapter("claude", timeout=15)
    assert captured["timeout"] == 15


def test_llm_prompt_segment_threads_timeout_to_adapter(monkeypatch):
    module = _install_ollama(monkeypatch, OllamaPromptAdapter)
    seg = LLMPrompt(model="llama3.2", source="ollama", timeout=21)
    list(seg(["hi"]))
    assert module.captured["timeout"] == 21


def test_llm_prompt_segment_tolerates_adapter_without_timeout():
    """Adapters with no network (eliza) or third-party ones predating the
    option keep working when no timeout is requested, and reject an explicit
    one loudly instead of ignoring it."""
    import pytest

    assert LLMPrompt(model="x", source="eliza") is not None
    with pytest.raises(ValueError, match="timeout"):
        LLMPrompt(model="x", source="eliza", timeout=5)
