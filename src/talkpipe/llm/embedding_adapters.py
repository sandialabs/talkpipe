from __future__ import annotations

import warnings
from collections.abc import Sequence
from typing import Any, overload

import numpy as np

from talkpipe.util.config import get_config
from talkpipe.util.constants import OLLAMA_SERVER_URL


def _vector_to_list(vec: Any) -> list[float]:
    values: list[float] = np.asarray(vec, dtype=float).tolist()
    return values


def _vectors_to_lists(arr: Any) -> list[list[float]]:
    a = np.asarray(arr, dtype=float)
    if a.size == 0:
        return []
    if a.ndim == 1:
        return [_vector_to_list(a)]
    return [_vector_to_list(row) for row in a]


class AbstractEmbeddingAdapter:
    """Abstract class for embedding text.

    This class represents an abstract adapter to embedding models.
    It defines the API and a common way to interact with different embedding models.  The
    specifics for embedding the text themselves are implemented in subclasses.
    """

    _model_name: str
    _source: str

    def __init__(self, model: str, source: str):
        self._model_name = model
        self._source = source

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def source(self) -> str:
        return self._source

    def description(self) -> str:
        """Return a description of the embedding model, including the name and source."""
        return f"Embedding using {self.model_name} ({self._source})"

    def __str__(self) -> str:
        return self.description()

    def __repr__(self) -> str:
        return self.__str__()

    def execute_one(self, text: str) -> list[float]:
        raise NotImplementedError("Subclasses must implement execute_one.")

    def execute_batch(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        return [self.execute_one(t) for t in texts]

    def execute(self, text: str) -> list[float]:
        """Embed a single string (deprecated).

        .. deprecated::
            Use :meth:`execute_one` or :meth:`execute_batch` instead.
            ``execute`` will be removed in TalkPipe 1.0.
        """
        warnings.warn(
            "EmbeddingAdapter.execute() is deprecated and will be removed in "
            "TalkPipe 1.0. Use execute_one() or execute_batch() instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.execute_one(text)

    @overload
    def __call__(self, text: str) -> list[float]: ...  # type: ignore[overload-overlap]  # str is itself a Sequence[str]; runtime dispatches on isinstance

    @overload
    def __call__(self, text: Sequence[str]) -> list[list[float]]: ...

    def __call__(self, text: str | Sequence[str]) -> list[float] | list[list[float]]:
        if isinstance(text, str):
            return self.execute_one(text)
        return self.execute_batch(list(text))


class OllamaEmbedderAdapter(AbstractEmbeddingAdapter):
    """Embedding adapter for Ollama"""

    def __init__(self, model: str, server_url: str | None = None):
        super().__init__(model, "ollama")
        self._server_url = server_url

    def _resolve_server_url(self) -> str | None:
        server_url = self._server_url
        if not server_url:
            server_url = get_config().get(OLLAMA_SERVER_URL, None)
        return server_url

    def _client(self) -> Any:
        try:
            import ollama
        except ImportError as e:
            raise ImportError(
                "Ollama is not installed. Please install it with: pip install talkpipe[ollama]"
            ) from e
        server_url = self._resolve_server_url()
        return ollama.Client(server_url) if server_url else ollama

    def execute_batch(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        client = self._client()
        try:
            response = client.embed(model=self.model_name, input=list(texts))
        except ConnectionError as exc:
            server_url = self._resolve_server_url()
            raise ConnectionError(
                f"Failed to connect to Ollama at '{server_url or 'http://localhost:11434'}'. "
                "If your Ollama server is remote, set the TALKPIPE_OLLAMA_SERVER_URL environment "
                "variable (e.g. `export TALKPIPE_OLLAMA_SERVER_URL=http://your-ollama-host:11434`) "
                "or OLLAMA_SERVER_URL in ~/.talkpipe.toml. "
                f"Original error: {exc}"
            ) from exc
        return _vectors_to_lists(response["embeddings"])

    def execute_one(self, text: str) -> list[float]:
        return self.execute_batch([text])[0]
