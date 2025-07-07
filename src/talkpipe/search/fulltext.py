from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
import uuid
from talkpipe.util.data_manipulation import extract_property
from whoosh import index
from whoosh.fields import Schema, TEXT, ID, STORED
from whoosh.qparser import MultifieldParser
import os

class SearchResult:
    """A single search result."""
    def __init__(self, doc_id: str, score: float, snippet: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None):
        self.doc_id = doc_id
        self.score = score
        self.snippet = snippet
        self.metadata = metadata or {}

class AbstractFullTextIndex(ABC):
    """Abstract base class for a full text index."""

    @abstractmethod
    def add_document(self, document: dict[str, Any]) -> None:
        """Add or update a document in the index."""
        pass

    @abstractmethod
    def search(self, query: str, limit: int = 10) -> List[SearchResult]:
        """Search for documents matching the query."""
        pass

    @abstractmethod
    def clear(self) -> None:
        """Remove all documents from the index."""
        pass

    def __enter__(self):
        """Support context manager for resource management."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Support context manager for resource management."""
        pass

