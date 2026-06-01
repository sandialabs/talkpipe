"""Tests for batch embedding adapters and hybrid llmEmbed batching."""

import numpy as np
import pytest
from unittest.mock import MagicMock, Mock

from talkpipe.llm.embedding import LLMEmbed
from talkpipe.llm.embedding_adapters import AbstractEmbeddingAdapter, OllamaEmbedderAdapter
from talkpipe.llm.embedding_adapters_openai import OpenAIEmbeddingAdapter
from talkpipe.llm.embedding_adapters_model2vec import Model2VecEmbeddingAdapter


def _patch_openai_embedding_client_batch(monkeypatch, embeddings=None):
    if embeddings is None:
        embeddings = [[0.1, 0.2], [0.3, 0.4]]

    class DummyEmbeddings:
        @staticmethod
        def create(*, model, input):
            assert model == "text-embedding-3-small"
            if isinstance(input, str):
                inputs = [input]
            else:
                inputs = list(input)
            response = MagicMock()
            response.data = []
            for i, text in enumerate(inputs):
                assert text in ("Hello", "World", "a", "b")
                data_item = MagicMock()
                data_item.embedding = embeddings[i] if i < len(embeddings) else embeddings[-1]
                response.data.append(data_item)
            return response

    class DummyClient:
        embeddings = DummyEmbeddings()

    class DummyOpenAI:
        class OpenAI:
            def __new__(cls):
                return DummyClient()

    monkeypatch.setattr(
        "talkpipe.llm.embedding_adapters_openai._require_openai",
        lambda: DummyOpenAI,
    )


def test_openai_execute_batch_mocked(monkeypatch):
    _patch_openai_embedding_client_batch(monkeypatch)
    model = OpenAIEmbeddingAdapter("text-embedding-3-small")
    result = model.execute_batch(["Hello", "World"])
    assert result == [[0.1, 0.2], [0.3, 0.4]]


def test_openai_call_list_dispatch_mocked(monkeypatch):
    _patch_openai_embedding_client_batch(monkeypatch)
    model = OpenAIEmbeddingAdapter("text-embedding-3-small")
    result = model(["a", "b"])
    assert len(result) == 2
    assert all(isinstance(row, list) for row in result)


def test_openai_execute_one_mocked(monkeypatch):
    _patch_openai_embedding_client_batch(monkeypatch, embeddings=[[0.1, 0.2, 0.3]])
    model = OpenAIEmbeddingAdapter("text-embedding-3-small")
    result = model.execute_one("Hello")
    assert result == [0.1, 0.2, 0.3]
    assert all(isinstance(x, float) for x in result)


def test_execute_deprecated_warns_and_delegates_to_execute_one(monkeypatch):
    _patch_openai_embedding_client_batch(monkeypatch, embeddings=[[0.1, 0.2, 0.3]])
    model = OpenAIEmbeddingAdapter("text-embedding-3-small")
    with pytest.warns(DeprecationWarning, match="execute_one\\(\\) or execute_batch\\(\\)"):
        result = model.execute("Hello")
    assert result == [0.1, 0.2, 0.3]


def test_ollama_execute_batch_mocked(monkeypatch):
    embed_calls = []

    class DummyClient:
        def embed(self, *, model, input):
            embed_calls.append((model, list(input) if not isinstance(input, str) else [input]))
            if isinstance(input, str):
                texts = [input]
            else:
                texts = list(input)
            return {
                "embeddings": [
                    [float(i), float(i + 1)] for i, _ in enumerate(texts)
                ]
            }

    model = OllamaEmbedderAdapter("test-model")
    monkeypatch.setattr(model, "_client", lambda: DummyClient())
    result = model.execute_batch(["Hello", "World"])
    assert result == [[0.0, 1.0], [1.0, 2.0]]
    assert embed_calls[0][1] == ["Hello", "World"]


def test_ollama_execute_one_returns_list_not_ndarray(monkeypatch):
    class DummyClient:
        def embed(self, *, model, input):
            return {"embeddings": [[0.1, 0.2, 0.3]]}

    model = OllamaEmbedderAdapter("test-model")
    monkeypatch.setattr(model, "_client", lambda: DummyClient())
    result = model.execute_one("Hello")
    assert isinstance(result, list)
    assert not isinstance(result, np.ndarray)
    assert result == pytest.approx([0.1, 0.2, 0.3])


def test_model2vec_execute_batch_mocked(monkeypatch):
    embedding = np.array([0.1, 0.2, 0.3], dtype=np.float32)

    class DummyModel:
        dim = 3
        normalize = True

        @classmethod
        def from_pretrained(cls, *args, **kwargs):
            return cls()

        def encode(self, text, **kwargs):
            if isinstance(text, str):
                return embedding
            return np.stack([embedding, embedding * 2])

    monkeypatch.setattr(
        "talkpipe.llm.model2vec_embeddings._require_model2vec",
        lambda: DummyModel,
    )
    model = Model2VecEmbeddingAdapter("minishlab/potion-base-8M")
    result = model.execute_batch(["first", "second"])
    assert len(result) == 2
    assert result[0] == pytest.approx([0.1, 0.2, 0.3])
    assert result[1] == pytest.approx([0.2, 0.4, 0.6])


def test_custom_adapter_default_execute_batch_loop():
    class SimpleAdapter(AbstractEmbeddingAdapter):
        def __init__(self):
            super().__init__("m", "custom")

        def execute_one(self, text: str):
            return [float(len(text))]

    adapter = SimpleAdapter()
    assert adapter.execute_batch(["ab", "cde"]) == [[2.0], [3.0]]


def test_llmembed_batch_size_calls_execute_batch():
    batch_calls = []

    def record_batch(texts):
        batch_calls.append(list(texts))
        if len(texts) == 3:
            return [[1.0], [2.0], [3.0]]
        return [[4.0], [5.0]]

    mock_embedder = Mock()
    mock_embedder.execute_batch = Mock(side_effect=record_batch)
    embedder = LLMEmbed(model="test-model", source="ollama", batch_size=3)
    embedder.embedder = mock_embedder
    result = list(embedder(["a", "b", "c", "d", "e"]))
    assert result == [[1.0], [2.0], [3.0], [4.0], [5.0]]
    assert batch_calls == [["a", "b", "c"], ["d", "e"]]


def test_llmembed_list_input_expands_with_set_as():
    mock_embedder = Mock()
    mock_embedder.execute_batch = Mock(return_value=[[1.0, 2.0], [3.0, 4.0]])
    embedder = LLMEmbed(
        model="test-model",
        source="ollama",
        field="text",
        set_as="vector",
    )
    embedder.embedder = mock_embedder
    batch = [{"text": "one"}, {"text": "two"}]
    result = list(embedder([batch]))
    assert len(result) == 2
    assert result[0]["vector"] == [1.0, 2.0]
    assert result[1]["vector"] == [3.0, 4.0]
    mock_embedder.execute_batch.assert_called_once_with(["one", "two"])


def test_llmembed_batch_failure_fallback_when_fail_on_error_false():
    mock_embedder = Mock()
    mock_embedder.execute_batch = Mock(side_effect=RuntimeError("batch failed"))
    mock_embedder.execute_one = Mock(side_effect=[[1.0], RuntimeError("bad"), [3.0]])
    embedder = LLMEmbed(
        model="test-model",
        source="ollama",
        batch_size=3,
        fail_on_error=False,
    )
    embedder.embedder = mock_embedder
    result = list(embedder(["a", "b", "c"]))
    assert result == [[1.0], [3.0]]
    assert mock_embedder.execute_one.call_count == 3


def test_llmembed_empty_batch_input():
    mock_embedder = Mock()
    mock_embedder.execute_batch = Mock(return_value=[])
    embedder = LLMEmbed(model="test-model", source="ollama")
    embedder.embedder = mock_embedder
    assert list(embedder([[]])) == []
