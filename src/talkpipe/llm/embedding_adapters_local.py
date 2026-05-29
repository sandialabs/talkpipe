from typing import List, Optional

from talkpipe.util.config import get_config
from talkpipe.util.constants import (
    LOCAL_EMBEDDING_CACHE_DIR,
    LOCAL_EMBEDDING_DEVICE,
    LOCAL_EMBEDDING_NORMALIZE,
    LOCAL_EMBEDDING_REVISION,
    LOCAL_EMBEDDING_TRUST_REMOTE_CODE,
)

from .embedding_adapters import AbstractEmbeddingAdapter
from .local_embeddings import DEFAULT_MODEL, LocalEmbedder


def _config_bool(value, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).lower() in ("1", "true", "yes")


class LocalEmbeddingAdapter(AbstractEmbeddingAdapter):
    """Embedding adapter for locally hosted Hugging Face models via sentence-transformers."""

    def __init__(self, model: Optional[str] = None):
        cfg = get_config()
        model_name = model or DEFAULT_MODEL
        super().__init__(model_name, "local")
        self._embedder = LocalEmbedder(
            model_name=model_name,
            revision=cfg.get(LOCAL_EMBEDDING_REVISION),
            device=cfg.get(LOCAL_EMBEDDING_DEVICE),
            cache_folder=cfg.get(LOCAL_EMBEDDING_CACHE_DIR),
            trust_remote_code=_config_bool(
                cfg.get(LOCAL_EMBEDDING_TRUST_REMOTE_CODE), True
            ),
            normalize=_config_bool(cfg.get(LOCAL_EMBEDDING_NORMALIZE), True),
        )

    def execute(self, text: str) -> List[float]:
        return self._embedder.embed_one(text)
