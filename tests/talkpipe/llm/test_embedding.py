import pytest
import json
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
        | llmEmbed[model="mxbai-embed-large", source="ollama", field="example", append_as="vector"] 
        | toDict[field_list="example"]
        """)
    f = f.asFunction(single_in=True, single_out=False)
    d = {"example": "Hello"}
    response = list(f(d))
    j = json.dumps(response)
    assert j == '[{"example": "Hello"}]'