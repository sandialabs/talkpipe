from typing import List
import numpy as np
from talkpipe.util.config import get_config
from talkpipe.util.constants import OLLAMA_SERVER_URL

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

    def execute(self, text: str) -> List[float]:
        raise NotImplementedError("This method must be implemented in a subclass.")

    def __call__(self, text: str) -> List[float]:
        return self.execute(text)


class OllamaEmbedderAdapter(AbstractEmbeddingAdapter):
    """Embedding adapter for Ollama"""

    def __init__(self, model: str, server_url: str = None):
        super().__init__(model, "ollama")
        self._server_url = server_url

    def execute(self, text: str) -> List[float]:
        try:
            import ollama
        except ImportError:
            raise ImportError(
                "Ollama is not installed. Please install it with: pip install talkpipe[ollama]"
            )

        server_url = self._server_url
        if not server_url:
            server_url = get_config().get(OLLAMA_SERVER_URL, None)
        client = ollama.Client(server_url) if server_url else ollama
        response = client.embed(
            model=self.model_name,
            input=text
        )
        result = response["embeddings"][0]
        return np.array(result)