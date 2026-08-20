from collections.abc import Sequence
from typing import Any

from talkpipe.util.config import resolve_timeout
from talkpipe.util.constants import DEFAULT_LLM_TIMEOUT, LLM_TIMEOUT

from .embedding_adapters import AbstractEmbeddingAdapter


def _require_openai() -> Any:
    try:
        import openai
    except ImportError as exc:
        raise ImportError(
            "OpenAI is not installed. Please install it with: pip install talkpipe[openai]"
        ) from exc
    return openai


class OpenAIEmbeddingAdapter(AbstractEmbeddingAdapter):
    """Embedding adapter for OpenAI."""

    def __init__(self, model: str, timeout: float | None = None):
        super().__init__(model, "openai")
        openai = _require_openai()
        self._timeout = resolve_timeout(timeout, LLM_TIMEOUT, DEFAULT_LLM_TIMEOUT)
        self.client = openai.OpenAI(timeout=self._timeout)

    def execute_batch(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        response = self.client.embeddings.create(
            model=self.model_name,
            input=list(texts),
        )
        return [list(d.embedding) for d in response.data]

    def execute_one(self, text: str) -> list[float]:
        response = self.client.embeddings.create(
            model=self.model_name,
            input=text,
        )
        return list(response.data[0].embedding)
