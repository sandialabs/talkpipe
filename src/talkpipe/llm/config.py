from typing import Dict, Type, TypeVar, List
from .prompt_adapters import AbstractLLMPromptAdapter, OllamaPromptAdapter, OpenAIPromptAdapter
from .embedding_adapters import AbstractEmbeddingAdapter, OllamaEmbedderAdapter

T_PROMPTADAPTER = TypeVar("T_PROMPTADAPTER", bound=AbstractLLMPromptAdapter)
T_EMBEDDINGADAPTER = TypeVar("T_EMBEDDINGADAPTER", bound=AbstractEmbeddingAdapter)

_promptAdapter:Dict[str, Type[T_PROMPTADAPTER]] = {
    "ollama": OllamaPromptAdapter,
    "openai": OpenAIPromptAdapter
}

def registerPromptAdapter(name:str, promptAdapter:Type[T_PROMPTADAPTER]):
    _promptAdapter[name] = promptAdapter

def getPromptAdapter(name:str)->Type[T_PROMPTADAPTER]:
    return _promptAdapter[name]

def getPromptSources()->List[str]:
    return list(_promptAdapter.keys()) 

_embeddingAdapter:Dict[str, Type[T_PROMPTADAPTER]] = {
    "ollama": OllamaEmbedderAdapter
}

def registerEmbeddingAdapter(name:str, embeddingAdapter:Type[T_EMBEDDINGADAPTER]):
    _embeddingAdapter[name] = embeddingAdapter

def getEmbeddingAdapter(name:str)->Type[T_EMBEDDINGADAPTER]:
    return _embeddingAdapter[name]

def getEmbeddingSources()->List[str]:
    return list(_embeddingAdapter.keys())


TALKPIPE_MODEL_NAME = "default_model_name"
TALKPIPE_SOURCE = "default_model_source"