from typing import List, Optional

from talkpipe.util.config import get_config
from talkpipe.util.constants import MODEL2VEC_CACHE_DIR, MODEL2VEC_REVISION

from .embedding_adapters import AbstractEmbeddingAdapter
from .model2vec_embeddings import DEFAULT_MODEL, Model2VecEmbedder


class Model2VecEmbeddingAdapter(AbstractEmbeddingAdapter):
    """Embedding adapter for in-process model2vec static embeddings."""

    def __init__(self, model: Optional[str] = None):
        cfg = get_config()
        model_name = model or DEFAULT_MODEL
        super().__init__(model_name, "model2vec")
        self._embedder = Model2VecEmbedder(
            model_name=model_name,
            revision=cfg.get(MODEL2VEC_REVISION),
            cache_folder=cfg.get(MODEL2VEC_CACHE_DIR),
        )

    def execute(self, text: str) -> List[float]:
        return self._embedder.embed_one(text)
