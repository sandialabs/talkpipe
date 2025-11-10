from typing import List, Optional, Tuple, Union, Annotated, Protocol
from pydantic import BaseModel

from talkpipe.util.data_manipulation import VectorLike, Document, DocID

class SearchResult(BaseModel):
    score: float
    doc_id: DocID
    document: Optional[Document] = None

    def prompt_worthy_string(self, priority_fields: Annotated[List[str], "Fields to list first in output string if they exist in the document"]) -> str:
        """Convert the SearchResult to a string suitable for inclusion in prompts."""

        ans = []
        for field in priority_fields:
            if field in self.document:
                ans.append(f"{field.capitalize()}: {self.document[field]}")
        for key in self.document:
            if key not in priority_fields:
                ans.append(f"{key.capitalize()}: {self.document[key]}")
        return "\n".join(ans)


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

