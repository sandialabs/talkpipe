"""In-process static embeddings via model2vec with offline-ready HF caching."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

import numpy as np

# ~7.5M params, 256 dims, ~30 MB. Recommended English default from MinishLab.
DEFAULT_MODEL = "minishlab/potion-retrieval-32M"


def _require_model2vec():
    try:
        from model2vec import StaticModel
    except ImportError as exc:
        raise ImportError(
            "Model2Vec is not installed. Install with: pip install talkpipe[model2vec]"
        ) from exc
    return StaticModel


def _resolve_local_path(model_name: str) -> str | None:
    """Return an absolute path if ``model_name`` refers to a local model directory.

    Expands ``~`` and resolves relative paths against the current working
    directory. Returns the resolved path string if it points at an existing
    directory, otherwise ``None`` (in which case ``model_name`` is treated as a
    Hugging Face repo id).
    """
    expanded = Path(model_name).expanduser()
    if expanded.is_dir():
        return str(expanded.resolve())
    return None


def _resolve_snapshot(
    model_name: str,
    revision: str | None,
    cache_dir: str | Path | None,
) -> str:
    """Resolve a HF repo + optional revision to a local snapshot directory.

    Used to honor ``revision`` and ``cache_folder`` semantics that
    ``model2vec.StaticModel.from_pretrained`` does not itself accept: we pin the
    revision via huggingface_hub and then load the model from the resulting
    local path. Idempotent; cached files are not re-downloaded.
    """
    import huggingface_hub

    return huggingface_hub.snapshot_download(
        repo_id=model_name,
        revision=revision,
        cache_dir=str(cache_dir) if cache_dir else None,
    )


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
        local_path = _resolve_local_path(model_name)
        if local_path is not None:
            # A previously downloaded model on disk: load it directly and skip
            # any Hugging Face Hub resolution.
            path = local_path
        elif revision is not None or cache_folder is not None:
            path = _resolve_snapshot(model_name, revision, cache_folder)
        else:
            path = model_name
        self.model = StaticModel.from_pretrained(path)

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
        Dict with: model, revision, snapshot_dir, dimension, smoke_test_length.

    Raises:
        RuntimeError: if the smoke-test embedding is empty.
    """
    snapshot_dir = _resolve_snapshot(model_name, revision, cache_dir)
    StaticModel = _require_model2vec()
    model = StaticModel.from_pretrained(snapshot_dir)
    vec = model.encode("model2vec smoke test")
    arr = np.asarray(vec, dtype=float)
    if arr.size == 0:
        raise RuntimeError(
            f"Model2Vec model {model_name} produced empty output. "
            "The cache may be incomplete."
        )
    return {
        "model": model_name,
        "revision": revision,
        "snapshot_dir": snapshot_dir,
        "dimension": model.dim,
        "smoke_test_length": int(arr.size),
    }
