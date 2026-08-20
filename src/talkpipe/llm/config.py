from collections.abc import Callable
from typing import TypeVar

from .embedding_adapters import AbstractEmbeddingAdapter, OllamaEmbedderAdapter
from .embedding_adapters_model2vec import Model2VecEmbeddingAdapter
from .embedding_adapters_openai import OpenAIEmbeddingAdapter
from .prompt_adapters import (
    AbstractLLMPromptAdapter,
    AnthropicPromptAdapter,
    ElizaPromptAdapter,
    OllamaPromptAdapter,
    OpenAIPromptAdapter,
)

# Kept for backwards compatibility with code that imports these names.
T_PROMPTADAPTER = TypeVar("T_PROMPTADAPTER", bound=AbstractLLMPromptAdapter)
T_EMBEDDINGADAPTER = TypeVar("T_EMBEDDINGADAPTER", bound=AbstractEmbeddingAdapter)

# Values are adapter classes; typed as callables because each subclass has its
# own constructor signature (the abstract base's signature is not shared).
_promptAdapter: dict[str, Callable[..., AbstractLLMPromptAdapter]] = {
    "ollama": OllamaPromptAdapter,
    "openai": OpenAIPromptAdapter,
    "anthropic": AnthropicPromptAdapter,
    "eliza": ElizaPromptAdapter,
}


def registerPromptAdapter(
    name: str, promptAdapter: type[AbstractLLMPromptAdapter]
) -> None:
    _promptAdapter[name] = promptAdapter


def getPromptAdapter(name: str) -> Callable[..., AbstractLLMPromptAdapter]:
    return _promptAdapter[name]


def getPromptSources() -> list[str]:
    return list(_promptAdapter.keys())


_embeddingAdapter: dict[str, Callable[..., AbstractEmbeddingAdapter]] = {
    "ollama": OllamaEmbedderAdapter,
    "openai": OpenAIEmbeddingAdapter,
    "model2vec": Model2VecEmbeddingAdapter,
}


def registerEmbeddingAdapter(
    name: str, embeddingAdapter: type[AbstractEmbeddingAdapter]
) -> None:
    _embeddingAdapter[name] = embeddingAdapter


def getEmbeddingAdapter(name: str) -> Callable[..., AbstractEmbeddingAdapter]:
    return _embeddingAdapter[name]


def getEmbeddingSources() -> list[str]:
    return list(_embeddingAdapter.keys())
