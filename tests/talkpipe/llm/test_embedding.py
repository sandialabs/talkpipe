import pytest
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
    
