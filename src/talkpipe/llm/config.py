from collections.abc import Callable
from typing import TypeVar

from talkpipe.util.config import get_config
from talkpipe.util.constants import TALKPIPE_MODEL_NAME, TALKPIPE_SOURCE

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


def resolve_source_and_model(source: str | None, model: str | None) -> tuple[str, str]:
    """Return the (source, model) a chat/vision segment should use.

    Each argument is used as passed when given; a missing one is read from
    ``get_config()`` (``default_model_source`` / ``default_model_name``, i.e.
    ``TALKPIPE_DEFAULT_MODEL_SOURCE`` / ``TALKPIPE_DEFAULT_MODEL_NAME`` or
    ``~/.talkpipe.toml``). Raises ``ValueError`` if either is still missing.

    The source is not checked against the registered prompt adapters; callers
    do that with :func:`getPromptSources` (external consumers keep their own
    registries), so only the naming step is shared here.
    """
    if not source or not model:
        cfg = get_config()
        source = source or cfg.get(TALKPIPE_SOURCE, None)
        model = model or cfg.get(TALKPIPE_MODEL_NAME, None)
    if source is None or model is None:
        raise ValueError(
            "Model name and source must be provided, specified in the configuration file, or in environment variables."
        )
    return source, model


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
