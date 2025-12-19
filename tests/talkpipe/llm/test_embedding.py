import pytest
import json
from unittest.mock import Mock, patch
from talkpipe.chatterlang import compile
from talkpipe.llm.embedding import LLMEmbed
from talkpipe.llm.embedding_adapters import OllamaEmbedderAdapter

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