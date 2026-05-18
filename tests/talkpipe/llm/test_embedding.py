import pytest
import json
from unittest.mock import Mock, MagicMock
from talkpipe.chatterlang import compile
from talkpipe.llm.embedding import LLMEmbed
from talkpipe.llm.embedding_adapters import OllamaEmbedderAdapter
from talkpipe.llm.embedding_adapters_openai import OpenAIEmbeddingAdapter


def _patch_openai_embedding_client(monkeypatch, embedding=None):
    if embedding is None:
        embedding = [0.1, 0.2, 0.3]

    class DummyEmbeddings:
        @staticmethod
        def create(*, model, input):
            assert model == "text-embedding-3-small"
            assert input == "Hello"
            data_item = MagicMock()
            data_item.embedding = embedding
            response = MagicMock()
            response.data = [data_item]
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


def test_openai_embedding_execute_mocked(monkeypatch):
    _patch_openai_embedding_client(monkeypatch)
    model = OpenAIEmbeddingAdapter("text-embedding-3-small")
    assert model.model_name == "text-embedding-3-small"
    assert model.source == "openai"
    ans = model("Hello")
    assert ans == [0.1, 0.2, 0.3]
    assert all(isinstance(x, float) for x in ans)


def test_create_openai_embedder_mocked(monkeypatch):
    _patch_openai_embedding_client(monkeypatch)
    cmd = LLMEmbed(model="text-embedding-3-small", source="openai")
    assert isinstance(cmd.embedder, OpenAIEmbeddingAdapter)
    response = list(cmd(["Hello"]))
    assert len(response) == 1
    assert response[0] == [0.1, 0.2, 0.3]


def test_openai_embedding(requires_openai):
    model = OpenAIEmbeddingAdapter("text-embedding-3-small")
    assert model.model_name == "text-embedding-3-small"
    assert model.source == "openai"
    ans = model("Hello")
    assert all(isinstance(x, float) for x in ans)
    assert len(ans) > 0

    f = compile("| llmEmbed[model='text-embedding-3-small', source='openai']")
    f = f.as_function(single_in=True, single_out=False)
    response = list(f("Hello"))
    assert len(response) == 1
    assert len(response[0]) > 0
    assert all(isinstance(x, float) for x in response[0])


def test_ollama_embedding(requires_ollama):
    model = OllamaEmbedderAdapter("mxbai-embed-large")
    assert model.model_name == "mxbai-embed-large"
    assert model.source == "ollama"
    ans = model("Hello") 
    assert all([isinstance(x, float) for x in ans])

def test_create_embedder(requires_ollama):
    cmd = LLMEmbed(model="mxbai-embed-large", source="ollama")
    assert isinstance(cmd.embedder, OllamaEmbedderAdapter)    
    response = list(cmd(["Hello"]))
    assert len(response) == 1
    assert all([isinstance(x, float) for x in response[0]])

def test_lingering_nparray_issue(requires_ollama):
    f = compile(
        """
        | llmEmbed[model="mxbai-embed-large", source="ollama", field="example", set_as="vector"]
        | toDict[field_list="example"]
        """)
    f = f.as_function(single_in=True, single_out=False)
    d = {"example": "Hello"}
    response = list(f(d))
    j = json.dumps(response)
    assert j == '[{"example": "Hello"}]'

def test_fail_on_error_parameter():
    """Test that fail_on_error parameter works correctly to prevent duplicate execute() calls."""
    # Create a mock embedder that always fails
    mock_embedder = Mock()
    mock_embedder.execute = Mock(side_effect=RuntimeError("Embedding failed"))

    # Test with fail_on_error=True (should raise exception)
    embedder_true = LLMEmbed(model="test-model", source="ollama", fail_on_error=True)
    embedder_true.embedder = mock_embedder

    with pytest.raises(RuntimeError, match="Embedding failed"):
        list(embedder_true(["test input"]))

    # Verify execute was called only once (not twice due to duplicate line bug)
    assert mock_embedder.execute.call_count == 1

    # Reset mock
    mock_embedder.reset_mock()

    # Test with fail_on_error=False (should silently skip failed items)
    embedder_false = LLMEmbed(model="test-model", source="ollama", fail_on_error=False)
    embedder_false.embedder = mock_embedder

    # Should not raise exception, just skip the failed item
    result = list(embedder_false(["test input"]))

    # Result should be empty since the embedding failed and was skipped
    assert result == []

    # Verify execute was called only once (not twice due to duplicate line bug)
    assert mock_embedder.execute.call_count == 1