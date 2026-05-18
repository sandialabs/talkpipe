from typing import List

from .embedding_adapters import AbstractEmbeddingAdapter


def _require_openai():
    try:
        import openai
    except ImportError as exc:
        raise ImportError(
            "OpenAI is not installed. Please install it with: pip install talkpipe[openai]"
        ) from exc
    return openai


class OpenAIEmbeddingAdapter(AbstractEmbeddingAdapter):
    """Embedding adapter for OpenAI."""

    def __init__(self, model: str):
        super().__init__(model, "openai")
        openai = _require_openai()
        self.client = openai.OpenAI()

    def execute(self, text: str) -> List[float]:
        response = self.client.embeddings.create(
            model=self.model_name,
            input=text,
        )
        return list(response.data[0].embedding)
