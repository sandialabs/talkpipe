from __future__ import annotations

import warnings
from typing import List, overload, Sequence, Union

import numpy as np

from talkpipe.util.config import get_config
from talkpipe.util.constants import OLLAMA_SERVER_URL


def _vector_to_list(vec) -> List[float]:
    return np.asarray(vec, dtype=float).tolist()


def _vectors_to_lists(arr) -> List[List[float]]:
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

    def description(self):
        """Return a description of the embedding model, including the name and source."""
        return f"Embedding using {self.model_name} ({self._source})"

    def __str__(self):
        return self.description()

    def __repr__(self):
        return self.__str__()

    def execute_one(self, text: str) -> List[float]:
        raise NotImplementedError("Subclasses must implement execute_one.")

    def execute_batch(self, texts: Sequence[str]) -> List[List[float]]:
        if not texts:
            return []
        return [self.execute_one(t) for t in texts]

    def execute(self, text: str) -> List[float]:
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
    def __call__(self, text: str) -> List[float]: ...

    @overload
    def __call__(self, text: Sequence[str]) -> List[List[float]]: ...

    def __call__(
        self, text: Union[str, Sequence[str]]
    ) -> Union[List[float], List[List[float]]]:
        if isinstance(text, str):
            return self.execute_one(text)
        return self.execute_batch(list(text))


class OllamaEmbedderAdapter(AbstractEmbeddingAdapter):
    """Embedding adapter for Ollama"""

    def __init__(self, model: str, server_url: str = None):
        super().__init__(model, "ollama")
        self._server_url = server_url

    def _client(self):
        try:
            import ollama
        except ImportError:
            raise ImportError(
                "Ollama is not installed. Please install it with: pip install talkpipe[ollama]"
            )
        server_url = self._server_url
        if not server_url:
            server_url = get_config().get(OLLAMA_SERVER_URL, None)
        return ollama.Client(server_url) if server_url else ollama

    def execute_batch(self, texts: Sequence[str]) -> List[List[float]]:
        if not texts:
            return []
        client = self._client()
        response = client.embed(model=self.model_name, input=list(texts))
        return _vectors_to_lists(response["embeddings"])

    def execute_one(self, text: str) -> List[float]:
        return self.execute_batch([text])[0]
