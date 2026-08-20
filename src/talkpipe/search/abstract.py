from typing import Annotated, Protocol

from pydantic import BaseModel

from talkpipe.util.data_manipulation import DocID, Document, VectorLike


class SearchResult(BaseModel):
    score: float
    doc_id: DocID
    document: Document | None = None

    def prompt_worthy_string(
        self,
        priority_fields: Annotated[
            list[str],
            "Fields to list first in output string if they exist in the document",
        ],
    ) -> str:
        """Convert the SearchResult to a string suitable for inclusion in prompts.

        Fields with an underscore-prefixed name (e.g. ``_doc_id``, auto-generated when
        no ``doc_id_field`` is set) are internal bookkeeping, not document content, and
        are excluded so the LLM doesn't mistake them for a citable source.
        """

        document = self.document
        if document is None:
            raise ValueError("SearchResult has no document to render")
        ans = [
            f"{field.capitalize()}: {document[field]}"
            for field in priority_fields
            if field in document
        ]
        ans.extend(
            f"{key.capitalize()}: {document[key]}"
            for key in document
            if key not in priority_fields and not key.startswith("_")
        )
        return "\n".join(ans)


class DocumentStore(Protocol):
    """Abstract base class for a document store."""

    def get_document(self, doc_id: DocID) -> Document | None:
        """Retrieve a document by ID."""
        ...


class TextAddable(Protocol):
    """Protocol for text addable document stores."""

    def add_document(self, doc: Document, doc_id: DocID | None = None) -> DocID:
        """Add a new document and return its ID."""
        ...


class MutableDocumentStore(TextAddable, Protocol):
    """Protocol for a mutable document store."""

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

    def text_search(self, query: str, limit: int = 10) -> list[SearchResult]:
        """Search for documents matching the query."""
        ...


class VectorAddable(Protocol):
    """Protocol for vector addable document stores."""

    def add_vector(
        self, vector: VectorLike, document: Document, doc_id: DocID | None
    ) -> DocID:
        """Add a vector to the store."""
        ...


class VectorSearchable(Protocol):
    """Protocol for vector searchable document stores."""

    def vector_search(self, vector: VectorLike, limit: int = 10) -> list[SearchResult]:
        """Search for vectors similar to the given vector"""
        ...
