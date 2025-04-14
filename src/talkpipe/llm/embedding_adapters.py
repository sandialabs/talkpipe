from typing import List

import numpy as np
import ollama

class AbstractEmbeddingAdapter:
    """Abstract class for embedding text.

    This class represents an abstract adapter to embedding models.
    It defines the API and a common way to interact with different embedding models.  The
    specifics for embedding the text themselves are implemented in subclasses.
    """
    _model_name: str
    _source: str

    def __init__(self, model_name: str, source: str):
        self._model_name = model_name
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

    def __init__(self, model_name: str):
        super().__init__(model_name, "ollama")

    def execute(self, text: str) -> List[float]:
        response = ollama.embed(
            model=self.model_name,
            input=text
        )
        result = response["embeddings"][0]
        return np.array(result)