import pytest
from talkpipe.llm.embedding import LLMEmbed
from talkpipe.llm.embedding_adapters import OllamaEmbedderAdapter

@pytest.mark.online
def test_ollama_embedding():
    model = OllamaEmbedderAdapter("mxbai-embed-large")
    assert model.model_name == "mxbai-embed-large"
    assert model.source == "ollama"
    ans = model("Hello") 
    assert all([isinstance(x, float) for x in ans])

@pytest.mark.online
def test_create_embedder():
    cmd = LLMEmbed(model="mxbai-embed-large", source="ollama")
    assert isinstance(cmd.embedder, OllamaEmbedderAdapter)    
    response = list(cmd(["Hello"]))
    assert len(response) == 1
    assert all([isinstance(x, float) for x in response[0]])
    
