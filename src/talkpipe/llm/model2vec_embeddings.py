"""In-process static embeddings via model2vec with offline-ready HF caching."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

import numpy as np

# ~7.5M params, 256 dims, ~30 MB. Recommended English default from MinishLab.
DEFAULT_MODEL = "minishlab/potion-base-8M"


def _require_model2vec():
    try:
        from model2vec import StaticModel
    except ImportError as exc:
        raise ImportError(
            "Model2Vec is not installed. Install with: pip install talkpipe[model2vec]"
        ) from exc
    return StaticModel


class Model2VecEmbedder:
    """Generates embeddings using a locally cached model2vec StaticModel."""

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        *,
        revision: str | None = None,
        cache_folder: str | Path | None = None,
    ) -> None:
        self.model_name = model_name
        self.revision = revision
        StaticModel = _require_model2vec()
        kwargs = {}
        if revision is not None:
            kwargs["revision"] = revision
        if cache_folder is not None:
            kwargs["cache_folder"] = str(cache_folder)
        self.model = StaticModel.from_pretrained(model_name, **kwargs)

    @property
    def dimension(self) -> int:
        """Output embedding dimension."""
        return self.model.dim

    @property
    def normalize(self) -> bool:
        """Whether the model L2-normalizes embeddings (model-defined)."""
        return bool(self.model.normalize)

    def embed(
        self,
        texts: str | Sequence[str],
        **encode_kwargs,
    ) -> np.ndarray:
        """Encode one string or many."""
        return self.model.encode(texts, **encode_kwargs)

    def embed_one(self, text: str, **encode_kwargs) -> list[float]:
        """Encode a single string and return a JSON-serializable list of floats."""
        vec = self.embed(text, **encode_kwargs)
        return np.asarray(vec, dtype=float).tolist()


def precache_model(
    model_name: str,
    *,
    revision: str | None = None,
    cache_dir: str | Path | None = None,
) -> dict:
    """Download and load a model2vec model into the local HF cache.

    Designed to be called at container-build time so the resulting image can
    run with ``HF_HUB_OFFLINE=1``. Idempotent: already-cached files are not
    re-downloaded.

    Returns:
        Dict with: model, revision, dimension, smoke_test_length.

    Raises:
        RuntimeError: if the smoke-test embedding is empty.
    """
    embedder = Model2VecEmbedder(
        model_name,
        revision=revision,
        cache_folder=cache_dir,
    )
    vec = embedder.embed("model2vec smoke test")
    arr = np.asarray(vec, dtype=float)
    if arr.size == 0:
        raise RuntimeError(
            f"Model2Vec model {model_name} produced empty output. "
            "The cache may be incomplete."
        )
    return {
        "model": model_name,
        "revision": revision,
        "dimension": embedder.dimension,
        "smoke_test_length": int(arr.size),
    }
