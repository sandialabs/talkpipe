"""Contract tests for the built-in embedding adapters and the abstract base."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

from embedding_adapter_contract_suite import run_embedding_adapter_contract
from talkpipe.llm import embedding_adapters, embedding_adapters_openai
from talkpipe.llm.embedding_adapters import (
    AbstractEmbeddingAdapter,
    OllamaEmbedderAdapter,
    _vectors_to_lists,
)
from talkpipe.llm.embedding_adapters_openai import OpenAIEmbeddingAdapter
from talkpipe.llm.embedding_errors import is_token_overflow_error


def _vec(text: str) -> list[float]:
    return [float(len(text)), 1.0, 0.5]


class MinimalAdapter(AbstractEmbeddingAdapter):
    """Only overrides execute_one — the base must supply the rest."""

    def __init__(self) -> None:
        super().__init__("mini", "test")

    def execute_one(self, text: str) -> list[float]:
        return _vec(text)


def test_base_class_contract_with_minimal_subclass() -> None:
    run_embedding_adapter_contract(
        MinimalAdapter, expected_source="test", expected_model="mini"
    )


def test_base_execute_one_is_abstract() -> None:
    with pytest.raises(NotImplementedError):
        AbstractEmbeddingAdapter("m", "s").execute_one("x")


def test_vectors_to_lists_shapes() -> None:
    assert _vectors_to_lists(np.array([])) == []
    assert _vectors_to_lists(np.array([1, 2])) == [[1.0, 2.0]]
    assert _vectors_to_lists(np.array([[1, 2], [3, 4]])) == [[1.0, 2.0], [3.0, 4.0]]


class FakeOllama:
    """A fake ``ollama`` module: Client(host, timeout).embed(model, input)."""

    def __init__(self) -> None:
        self.clients: list[Any] = []

    def Client(self, host: Any = None, timeout: Any = None) -> Any:
        fake = self

        class _Client:
            def __init__(self) -> None:
                self.host = host
                self.timeout = timeout
                fake.clients.append(self)

            def embed(self, model: str, input: list[str]) -> dict[str, Any]:
                return {"embeddings": [_vec(t) for t in input]}

        return _Client()


def test_ollama_adapter_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeOllama()
    monkeypatch.setattr(OllamaEmbedderAdapter, "_import_ollama", lambda self: fake)
    run_embedding_adapter_contract(
        lambda: OllamaEmbedderAdapter("embed-model", server_url="http://h:1"),
        expected_source="ollama",
        expected_model="embed-model",
    )
    assert fake.clients
    assert all(c.host == "http://h:1" for c in fake.clients)


def test_ollama_adapter_import_error_names_the_extra(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import builtins

    real_import = builtins.__import__

    def no_ollama(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "ollama":
            raise ImportError("nope")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_ollama)
    with pytest.raises(ImportError, match=r"talkpipe\[ollama\]"):
        OllamaEmbedderAdapter("m").execute_one("x")


def test_ollama_adapter_connection_error_mentions_server_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Boom:
        def Client(self, host: Any = None, timeout: Any = None) -> Any:
            class _C:
                def embed(self, **kwargs: Any) -> Any:
                    raise ConnectionError("refused")

            return _C()

    monkeypatch.setattr(OllamaEmbedderAdapter, "_import_ollama", lambda self: Boom())
    with pytest.raises(ConnectionError, match="http://h:1"):
        OllamaEmbedderAdapter("m", server_url="http://h:1").execute_one("x")


def test_openai_adapter_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeEmbeddings:
        def create(self, model: str, input: Any) -> Any:
            texts = [input] if isinstance(input, str) else list(input)
            return SimpleNamespace(
                data=[SimpleNamespace(embedding=_vec(t)) for t in texts]
            )

    class FakeOpenAI:
        def __init__(self, timeout: Any = None) -> None:
            self.embeddings = FakeEmbeddings()

    monkeypatch.setattr(
        embedding_adapters_openai,
        "_require_openai",
        lambda: SimpleNamespace(OpenAI=FakeOpenAI),
    )
    run_embedding_adapter_contract(
        lambda: OpenAIEmbeddingAdapter("text-embedding-3-small"),
        expected_source="openai",
        expected_model="text-embedding-3-small",
    )


def test_openai_adapter_import_error_names_the_extra(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import builtins

    real_import = builtins.__import__

    def no_openai(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "openai":
            raise ImportError("nope")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_openai)
    with pytest.raises(ImportError, match=r"talkpipe\[openai\]"):
        OpenAIEmbeddingAdapter("m")


@pytest.mark.parametrize(
    "message",
    [
        "This model's maximum context length is 8192 tokens",
        "input is too long",
        "Please reduce the length of your input",
        "Request exceeds the maximum allowed size",
    ],
)
def test_token_overflow_detection_positive(message: str) -> None:
    assert is_token_overflow_error(RuntimeError(message))


def test_token_overflow_detection_negative_and_empty_message() -> None:
    assert not is_token_overflow_error(RuntimeError("connection reset"))
    assert not is_token_overflow_error(RuntimeError())  # falls back to repr


def test_module_exports_stable() -> None:
    assert embedding_adapters.AbstractEmbeddingAdapter is AbstractEmbeddingAdapter
