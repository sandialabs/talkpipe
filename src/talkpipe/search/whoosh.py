from typing import List, Any, Optional, Dict, Annotated
import os
import uuid
import logging
import shutil
from contextlib import contextmanager
from whoosh import index
from whoosh.fields import Schema, TEXT, ID
from whoosh.qparser import MultifieldParser, QueryParserError
from whoosh.writing import LockError
from talkpipe.pipe import segment, field_segment
from talkpipe.chatterlang import register_segment
from talkpipe.pipe.core import is_metadata
from talkpipe.pipe.metadata import Flush
from talkpipe.util.data_manipulation import DocID, Document, toDict, extract_property, assign_property
from talkpipe.util.config import parse_key_value_str
import time

from .abstract import (
    SearchResult, 
    DocumentStore, 
    MutableDocumentStore, 
    TextSearchable
)

logger = logging.getLogger(__name__)

class WhooshIndexError(Exception):
    pass

class WhooshFullTextIndex(DocumentStore, MutableDocumentStore, TextSearchable):
    def __init__(self, index_path: str, fields: list[str] = None):
        self.index_path = index_path
        self.fields = fields
        self._initialize_index(fields)

    def _initialize_index(self, fields: Optional[list[str]]):
        os.makedirs(self.index_path, exist_ok=True)

        if index.exists_in(self.index_path):
            self.ix = index.open_dir(self.index_path)
            self.schema = self.ix.schema
            if fields is not None:
                ix_fields = set(self.ix.schema.names())
                expected_fields = set(['doc_id'] + fields)
                if ix_fields != expected_fields:
                    raise WhooshIndexError(f"Index schema fields {ix_fields} do not match expected {expected_fields}")
                self.fields = fields
            else:
                self.fields = [f for f in self.ix.schema.names() if f != 'doc_id']
        else:
            if fields is None:
                raise WhooshIndexError("Fields must be provided when creating a new index.")
            self.schema = Schema(
                doc_id=ID(stored=True, unique=True),
                **{field: TEXT(stored=True) for field in fields}
            )
            self.ix = index.create_in(self.index_path, self.schema)
            self.fields = fields

    def get_document(self, doc_id: DocID) -> Optional[Document]:
        """Retrieve a document by ID."""
        try:
            with self.ix.searcher() as searcher:
                results = searcher.document_numbers(doc_id=doc_id)
                for num in results:
                    doc = searcher.stored_fields(num)
                    return {k: str(v) for k, v in doc.items() if k != 'doc_id'}
            return None
        except Exception as e:
            logger.error(f"Failed to get document {doc_id}: {e}")
            return None

    def add_document(self, doc: Document, doc_id: Optional[DocID] = None) -> DocID:
        """Add a new document and return its ID."""
        if doc_id is None:
            doc_id = str(uuid.uuid4())
        
        doc_fields = {field: str(doc.get(field, "")) for field in self.fields if field in doc}
        
        with self.ix.writer() as writer:
            writer.update_document(doc_id=doc_id, **doc_fields)
        return doc_id

    def update_document(self, doc_id: DocID, doc: Document) -> bool:
        """Update an existing document by ID."""
        if self.get_document(doc_id) is None:
            logger.warning(f"Document {doc_id} not found for update")
            return False
        
        try:
            doc_fields = {field: str(doc.get(field, "")) for field in self.fields if field in doc}
            with self.ix.writer() as writer:
                writer.update_document(doc_id=doc_id, **doc_fields)
            return True
        except Exception as e:
            logger.error(f"Failed to update document {doc_id}: {e}")
            return False

    def delete_document(self, doc_id: DocID) -> bool:
        """Delete a document by ID."""
        try:
            with self.ix.writer() as writer:
                writer.delete_by_term('doc_id', doc_id)
            return True
        except Exception as e:
            logger.error(f"Failed to delete document {doc_id}: {e}")
            return False

    def clear(self) -> None:
        """Clear all documents in the store."""
        self.close()
        if os.path.exists(self.index_path):
            shutil.rmtree(self.index_path)
            os.makedirs(self.index_path, exist_ok=True)
        self.ix = index.create_in(self.index_path, self.schema)

    def text_search(self, query: str, limit: int = 10) -> List[SearchResult]:
        """Search for documents matching the query."""
        try:
            with self.ix.searcher() as searcher:
                parser = MultifieldParser(self.fields, schema=self.ix.schema)
                try:
                    q = parser.parse(query)
                except QueryParserError as e:
                    logger.error(f"Invalid query syntax '{query}': {e}")
                    return []
                
                results = searcher.search(q, limit=limit)
                search_results = []
                for hit in results:
                    document = {field: str(hit.get(field, "")) for field in self.fields if field in hit}
                    search_results.append(
                        SearchResult(
                            doc_id=hit['doc_id'],
                            score=hit.score,
                            document=document
                        )
                    )
                return search_results
        except Exception as e:
            logger.error(f"Search failed for query '{query}': {e}")
            return []

    def upsert_document(self, document: Document, doc_id: Optional[DocID] = None) -> DocID:
        """Add or update a document, returning its ID."""
        if doc_id is None:
            doc_id = str(uuid.uuid4())
        
        if self.get_document(doc_id):
            self.update_document(doc_id, document)
        else:
            self.add_document(document, doc_id)
        
        return doc_id

    def close(self):
        """Close the index."""
        if hasattr(self, 'ix') and self.ix is not None:
            try:
                self.ix.close()
            except Exception as e:
                logger.warning(f"Failed to close index: {e}")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


@contextmanager
def WhooshWriter(index_path: str, fields: list[str] = None, overwrite: bool = False, commit_seconds: int = -1):
    """Context manager for Whoosh index writer with optional periodic commit."""
    idx = WhooshFullTextIndex(index_path, fields)
    if overwrite:
        idx.clear()

    writer = idx.ix.writer()
    
    class WriterWrapper:
        def __init__(self, idx, writer, commit_seconds):
            self.idx = idx
            self.writer = writer
            self.commit_seconds = commit_seconds
            self.last_commit = time.time()
        
        def add_document(self, doc, doc_id=None):
            # Check if we need to commit
            if self.commit_seconds >= 0 and (time.time() - self.last_commit) > self.commit_seconds:
                self.commit()
            
            # Add document using the writer directly
            if doc_id is None:
                doc_id = str(uuid.uuid4())
            doc_fields = {field: str(doc.get(field, "")) for field in self.idx.fields if field in doc}
            self.writer.update_document(doc_id=doc_id, **doc_fields)
            return doc_id
        
        def commit(self):
            """Commit the current writer and create a new one."""
            self.writer.commit()
            self.writer = self.idx.ix.writer()
            self.last_commit = time.time()
            logger.debug("Index commit performed")
        
        def __getattr__(self, name):
            # Delegate other attributes to the index
            return getattr(self.idx, name)
    
    wrapper = WriterWrapper(idx, writer, commit_seconds)

    try:
        yield wrapper
        wrapper.writer.commit()
        logger.debug("Successfully committed index changes")
    except Exception as e:
        wrapper.writer.cancel()
        raise
    finally:
        idx.close()
        wrapper.writer = None


@contextmanager
def WhooshSearcher(index_path: str, reload_seconds: int = -1):
    """Context manager for Whoosh index searcher with optional periodic reload."""
    class SearcherWrapper:
        def __init__(self, index_path, reload_seconds):
            self.index_path = index_path
            self.reload_seconds = reload_seconds
            self.idx = WhooshFullTextIndex(index_path)
            self.last_reload = time.time()
        
        def text_search(self, query, limit=10):
            # Check if we need to reload
            if self.reload_seconds >= 0 and (time.time() - self.last_reload) > self.reload_seconds:
                self.reload()
            
            return self.idx.text_search(query, limit=limit)
        
        def reload(self):
            """Reload the index to pick up any changes."""
            self.idx.close()
            self.idx = WhooshFullTextIndex(self.index_path)
            self.last_reload = time.time()
            logger.debug("Index reloaded")
        
        def __getattr__(self, name):
            # Delegate other attributes to the index
            return getattr(self.idx, name)
        
        def close(self):
            if self.idx:
                self.idx.close()
    
    searcher = SearcherWrapper(index_path, reload_seconds)
    try:
        yield searcher
    finally:
        searcher.close()


@register_segment("indexWhoosh")
@segment(process_metadata=True)
def indexWhoosh(items: Annotated[object, "Iterator of items to index"], index_path: Annotated[str, "Path to the Whoosh index directory"], field_list: Annotated[list[str], "List of fields to index"] = ["_:content"], 
                yield_doc: Annotated[bool, "If True, yield each indexed document. Otherwise yield the original item"] = False, continue_on_error: Annotated[bool, "If True, continue processing other documents when one fails"] = True, overwrite: Annotated[bool, "If True, clear existing index before indexing"] = False,
                commit_seconds: Annotated[int, "If > 0, commit changes if it has been this many seconds since the last commit"] = -1):
    """Index documents using Whoosh full-text search engine.
    
    Creates a searchable full-text index from items. Each item is indexed with specified
    fields, allowing fast text search using searchWhoosh. Indexes are persistent and can
    be updated incrementally by calling indexWhoosh again on new items.
    
    The Whoosh index is optimized for searching and supports complex query syntax including
    boolean operators (AND, OR, NOT), field-specific searches, and phrase queries.
    
    Useful for:
    - Building searchable document repositories
    - Creating local search capabilities for text data
    - Indexing log files, emails, or document collections
    
    Yields:
        Indexed documents (if yield_doc=True) or original items otherwise.
    """
    field_list_dict = parse_key_value_str(field_list)
    indexed_count = 0
    error_count = 0
    
    with WhooshWriter(index_path, list(field_list_dict.values()), overwrite=overwrite, commit_seconds=commit_seconds) as idx:
        for item in items:
            # Check if this is a Flush event
            if is_metadata(item) and isinstance(item, Flush):
                # Commit the index to ensure all buffered changes are persisted
                idx.commit()
                # Don't yield Flush events - consume them
                continue
            
            try:
                d = toDict(item, field_list, fail_on_missing=False)
                doc_id = str(d.get('doc_id', uuid.uuid4()))
                
                # Convert to Document format
                document = {k: str(v) for k, v in d.items() if k != 'doc_id'}
                
                result_doc_id = idx.add_document(document, doc_id)
                indexed_count += 1
                yield d if yield_doc else item
                    
            except Exception as e:
                error_count += 1
                logger.error(f"Error processing document: {e}")
                if not continue_on_error:
                    raise
                    
    logger.info(f"Indexing completed: {indexed_count} documents indexed, {error_count} errors")


@register_segment("searchWhoosh")
@segment(process_metadata=True)
def searchWhoosh(queries: Annotated[object, "Iterator of query strings"], index_path: Annotated[str, "Path to the Whoosh index directory"], limit: Annotated[int, "Maximum number of results to return for each query"] = 100, 
                 all_results_at_once: Annotated[bool, "If True, yield all results at once. Otherwise, yield one result at a time"] = False, continue_on_error: Annotated[bool, "If True, continue with next query when one fails"] = True,
                 reload_seconds: Annotated[int, "If > 0, reload the index if the last search was at least this many seconds ago"] = 60, field: Annotated[str, "Field to extract query from"] = "_", set_as: Annotated[Optional[str], "Field name to set results on input items"] = None):
    """Search a Whoosh full-text index for matching documents.
    
    Searches a previously indexed Whoosh index using text queries. Supports complex
    query syntax including boolean operators (AND, OR, NOT), field-specific searches,
    wildcards, and phrase queries wrapped in quotes.
    
    Results are returned as SearchResult objects containing the document ID, relevance
    score, and the document content. Can return all results for a query at once or
    stream individual results one at a time.
    
    Useful for:
    - Searching previously indexed document collections
    - Building interactive search interfaces
    - Filtering documents by text content
    
    Query Examples:
    - "hello world": phrase search
    - hello AND world: documents containing both words
    - hello OR world: documents containing either word
    - hello NOT world: documents with hello but not world
    - content:python: search in specific field
    - hel*: wildcard search (prefix matching)
    
    Yields:
        SearchResult objects if all_results_at_once=False (one per result).
        List of SearchResult objects if all_results_at_once=True (all per query).
    """
    with WhooshSearcher(index_path, reload_seconds=reload_seconds) as idx:
        for item in queries:
            # Check if this is a Flush event
            if is_metadata(item) and isinstance(item, Flush):
                # Reload the index to pick up any changes
                idx.reload()
                # Don't yield Flush events - consume them
                continue
            
            query = extract_property(item, field, fail_on_missing=True)
            try:
                results = idx.text_search(query, limit=limit)
                if all_results_at_once:
                    if set_as:
                        assign_property(item, set_as, results)
                        yield item
                    else:
                        yield results
                else:
                    if set_as:
                        raise ValueError("set_as only works with this segment if all_results_at_once is True.")
                    yield from results
                    
            except Exception as e:
                logger.error(f"Error searching for query '{query}': {e}")
                if not continue_on_error:
                    raise