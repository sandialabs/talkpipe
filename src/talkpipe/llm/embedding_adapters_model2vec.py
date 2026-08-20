from collections.abc import Sequence

from talkpipe.util.config import get_config
from talkpipe.util.constants import MODEL2VEC_CACHE_DIR, MODEL2VEC_REVISION

from .embedding_adapters import AbstractEmbeddingAdapter, _vectors_to_lists
from .model2vec_embeddings import DEFAULT_MODEL, Model2VecEmbedder


class Model2VecEmbeddingAdapter(AbstractEmbeddingAdapter):
    """Embedding adapter for in-process model2vec static embeddings."""

    def __init__(self, model: str | None = None):
        cfg = get_config()
        model_name = model or DEFAULT_MODEL
        super().__init__(model_name, "model2vec")
        self._embedder = Model2VecEmbedder(
            model_name=model_name,
            revision=cfg.get(MODEL2VEC_REVISION),
            cache_folder=cfg.get(MODEL2VEC_CACHE_DIR),
        )

    def execute_batch(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        return _vectors_to_lists(self._embedder.embed(list(texts)))

    def execute_one(self, text: str) -> list[float]:
        return self.execute_batch([text])[0]
