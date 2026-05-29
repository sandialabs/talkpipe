"""Local paragraph embeddings with offline-ready caching.

Models are downloaded from Hugging Face into a local cache; once cached, the embedder
works fully offline when ``HF_HUB_OFFLINE=1`` is set.
"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

import numpy as np


# Long-context (8192 tokens), 768 dims, ~330 MB. Good general-purpose default
# for paragraph-length inputs without silent truncation.
DEFAULT_MODEL = "jinaai/jina-embeddings-v2-base-en"

# Files sufficient to tokenize without loading the full model.
_TOKENIZER_PATTERNS = [
    "tokenizer.json",
    "tokenizer_config.json",
    "special_tokens_map.json",
]


def _require_sentence_transformers():
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise ImportError(
            "Local embeddings require optional deps. "
            "Install with: pip install talkpipe[local-embeddings]"
        ) from exc
    return SentenceTransformer


class LocalEmbedder:
    """Generates embeddings for paragraphs using a locally cached Hugging Face model."""

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        *,
        revision: str | None = None,
        device: str | None = None,
        cache_folder: str | Path | None = None,
        trust_remote_code: bool = True,
        normalize: bool = True,
    ) -> None:
        self.model_name = model_name
        self.revision = revision
        self._normalize_default = normalize
        SentenceTransformer = _require_sentence_transformers()
        self.model = SentenceTransformer(
            model_name,
            revision=revision,
            device=device,
            cache_folder=str(cache_folder) if cache_folder else None,
            trust_remote_code=trust_remote_code,
        )

    @property
    def dimension(self) -> int:
        """Output embedding dimension."""
        return self.model.get_embedding_dimension()

    @property
    def max_tokens(self) -> int:
        """Maximum input length in tokens. Longer inputs are silently truncated."""
        return self.model.max_seq_length

    def embed(
        self,
        paragraphs: str | Sequence[str],
        *,
        normalize: bool | None = None,
        batch_size: int = 16,
        show_progress: bool = False,
    ) -> np.ndarray:
        """Encode one paragraph or many."""
        if normalize is None:
            normalize = self._normalize_default
        single = isinstance(paragraphs, str)
        texts = [paragraphs] if single else list(paragraphs)

        embeddings = self.model.encode(
            texts,
            batch_size=batch_size,
            show_progress_bar=show_progress,
            normalize_embeddings=normalize,
            convert_to_numpy=True,
        )

        if single:
            arr = np.asarray(embeddings)
            if arr.ndim == 1:
                return arr
            return arr[0]
        return embeddings

    def embed_one(self, text: str, *, normalize: bool | None = None) -> list[float]:
        """Encode a single string and return a JSON-serializable list of floats."""
        vec = self.embed(text, normalize=normalize)
        return vec.tolist()


def precache_model(
    model_name: str,
    *,
    revision: str | None = None,
    cache_dir: str | Path | None = None,
    tokenizer_only: bool = False,
) -> dict:
    """Download a model (or just its tokenizer) into the local HF cache.

    Designed to be called at container-build time so the resulting image can
    run with ``HF_HUB_OFFLINE=1`` / ``TRANSFORMERS_OFFLINE=1``. Idempotent: safe to
    call repeatedly; already-cached files are not re-downloaded.

    After download, runs a smoke test by loading the tokenizer and encoding
    a short string when ``tokenizer.json`` is present.

    Returns:
        Dict with: model, revision, snapshot_dir, tokenizer_only, smoke_test_tokens.

    Raises:
        RuntimeError: if the tokenizer smoke test fails after download.
    """
    from huggingface_hub import snapshot_download
    from tokenizers import Tokenizer

    allow_patterns = _TOKENIZER_PATTERNS if tokenizer_only else None

    snapshot_dir = snapshot_download(
        repo_id=model_name,
        revision=revision,
        cache_dir=str(cache_dir) if cache_dir else None,
        allow_patterns=allow_patterns,
    )

    tokenizer_json = Path(snapshot_dir) / "tokenizer.json"
    if tokenizer_json.exists():
        tok = Tokenizer.from_file(str(tokenizer_json))
        ids = tok.encode("paragraph embeddings smoke test").ids
        if not ids:
            raise RuntimeError(
                f"Tokenizer for {model_name} produced empty output. "
                f"Cache at {snapshot_dir} may be incomplete."
            )
        token_count = len(ids)
    else:
        token_count = None

    return {
        "model": model_name,
        "revision": revision,
        "snapshot_dir": str(snapshot_dir),
        "tokenizer_only": tokenizer_only,
        "smoke_test_tokens": token_count,
    }
