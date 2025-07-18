from typing import List, Dict, Any, Optional, Tuple, Union, Protocol
from pydantic import BaseModel
import numpy as np

# Type aliases
VectorLike = Union[List[float], np.ndarray]
Document = Dict[str, str]
DocID = str

class SearchResult(BaseModel):
    score: float
    doc_id: DocID
    document: Optional[Document] = None

class DocumentStore(Protocol):
    """Abstract base class for a document store."""

    def get_document(self, doc_id: DocID) -> Optional[Document]:
        """Retrieve a document by ID."""
        ...

class TextAddable(Protocol):
    """Protocol for text addable document stores."""

    def add_document(self, doc: Document, doc_id: Optional[DocID] = None) -> DocID:
        """Add a new document and return its ID."""
        ...

class MutableDocumentStore(TextAddable):
    """Abstract base class for a mutable document store."""

    def update_document(self, doc_id: DocID, doc: Document) -> bool:
        """Update an existing document by ID."""
        ...

    def delete_document(self, doc_id: DocID) -> bool:
        """Delete a document by ID."""
        ...

    def clear(self) -> None:
        """Clear all documents in the store."""
        ...

class TextSearchable(Protocol):
    """Protocol for text searchable document stores."""

    def text_search(self, query: str, limit: int = 10) -> List[SearchResult]:
        """Search for documents matching the query."""
        ...

class VectorAddable(Protocol):
    """Protocol for vector addable document stores."""

    def add_vector(self, vector: VectorLike, document: Document, doc_id: Optional[DocID]) -> DocID:
        """Add a vector to the store."""
        ...

class VectorSearchable(Protocol):
    """Protocol for vector searchable document stores."""

    def vector_search(self, vector: VectorLike, limit: int = 10) -> List[SearchResult]:
        """Search for vectors similar to the given vector"""
        ...

