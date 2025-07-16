from typing import List, Any, Optional
import os
import uuid
import logging
import shutil
from contextlib import contextmanager
from whoosh import index
from whoosh.fields import Schema, TEXT, ID
from whoosh.qparser import MultifieldParser, QueryParserError
from whoosh.writing import LockError
from talkpipe.pipe import segment
from talkpipe.chatterlang import register_segment
from talkpipe.util.data_manipulation import toDict
from talkpipe.util.config import parse_key_value_str
from .abstract import AbstractFullTextIndex, SearchResult

logger = logging.getLogger(__name__)

class WhooshIndexError(Exception):
    """Custom exception for Whoosh indexing errors."""
    pass

class WhooshFullTextIndex(AbstractFullTextIndex):
    def __init__(self, index_path: str, fields: list[str] = None):
        self.index_path = index_path
        self.fields = fields
        self.ix = None
        self.schema = None
        self.writer = None
        
        try:
            self._initialize_index(fields)
        except Exception as e:
            logger.error(f"Failed to initialize Whoosh index at {index_path}: {e}")
            raise WhooshIndexError(f"Index initialization failed: {e}") from e

    def _initialize_index(self, fields: Optional[list[str]]):
        """Initialize the Whoosh index with proper error handling."""
        # Create index directory if it doesn't exist
        try:
            if not os.path.exists(self.index_path):
                os.makedirs(self.index_path, exist_ok=True)
        except OSError as e:
            raise WhooshIndexError(f"Cannot create index directory {self.index_path}: {e}") from e

        if index.exists_in(self.index_path):
            try:
                self.ix = index.open_dir(self.index_path)
                self.schema = self.ix.schema
                ix_fields = set(self.ix.schema.names())
                expected_fields = set(self.ix.schema.names())
                
                if fields is not None:
                    expected_fields = set(['doc_id'] + fields)
                    if ix_fields != expected_fields:
                        raise ValueError(f"Index schema fields {ix_fields} do not match expected {expected_fields}")
                    self.fields = fields
                else:
                    # Use fields from existing index if not provided
                    self.fields = [f for f in self.ix.schema.names() if f != 'doc_id']
            except Exception as e:
                raise WhooshIndexError(f"Cannot open existing index: {e}") from e
        else:
            if fields is None:
                raise ValueError("Fields must be provided when creating a new index.")
            
            try:
                self.schema = Schema(
                    doc_id=ID(stored=True, unique=True),
                    **{field: TEXT(stored=True) for field in fields}
                )
                self.ix = index.create_in(self.index_path, self.schema)
                self.fields = fields
            except Exception as e:
                raise WhooshIndexError(f"Cannot create new index: {e}") from e

    def add_document(self, document: dict[str, Any]) -> bool:
        """Add a document to the index. Returns True if successful, False otherwise."""
        if not self.ix:
            logger.error("Index not initialized")
            return False
            
        try:
            doc_id = str(document.get("doc_id") or uuid.uuid4())
            doc_fields = {field: str(document.get(field, "")) for field in self.fields}
            
            if self.writer is not None:
                self.writer.update_document(doc_id=doc_id, **doc_fields)
            else:
                with self.ix.writer() as writer:
                    writer.update_document(doc_id=doc_id, **doc_fields)
            return True
            
        except LockError as e:
            logger.error(f"Index is locked, cannot add document {document.get('doc_id', 'unknown')}: {e}")
            return False
        except Exception as e:
            logger.error(f"Failed to add document {document.get('doc_id', 'unknown')}: {e}")
            return False

    def search(self, query: str, limit: int = 100) -> List[SearchResult]:
        """Search the index. Returns empty list if search fails."""
        if not self.ix:
            logger.error("Index not initialized")
            return []
            
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
                    try:
                        metadata = {field: hit.get(field) for field in self.fields}
                        search_results.append(
                            SearchResult(
                                doc_id=hit['doc_id'],
                                score=hit.score,
                                snippet=None,
                                metadata=metadata
                            )
                        )
                    except Exception as e:
                        logger.warning(f"Failed to process search result: {e}")
                        continue
                        
                return search_results
                
        except Exception as e:
            logger.error(f"Search failed for query '{query}': {e}")
            return []

    def clear(self) -> bool:
        """Clear the index. Returns True if successful."""
        try:
            # Cancel any active writer
            if self.writer is not None:
                try:
                    self.writer.cancel()
                except Exception as e:
                    logger.warning(f"Failed to cancel writer: {e}")
                finally:
                    self.writer = None
            
            # Close the index
            if self.ix is not None:
                try:
                    self.ix.close()
                except Exception as e:
                    logger.warning(f"Failed to close index: {e}")
            
            # Remove index files
            if os.path.exists(self.index_path):
                try:
                    shutil.rmtree(self.index_path)
                    os.makedirs(self.index_path, exist_ok=True)
                except Exception as e:
                    logger.error(f"Failed to clear index directory: {e}")
                    return False
            
            # Recreate the index
            try:
                self.ix = index.create_in(self.index_path, self.schema)
                return True
            except Exception as e:
                logger.error(f"Failed to recreate index: {e}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to clear index: {e}")
            return False

    def close(self):
        """Safely close the index and cleanup resources."""
        try:
            if self.writer is not None:
                try:
                    self.writer.commit()
                except Exception as e:
                    logger.warning(f"Failed to commit writer: {e}")
                    try:
                        self.writer.cancel()
                    except Exception:
                        pass
                finally:
                    self.writer = None
            
            if self.ix is not None:
                try:
                    self.ix.close()
                except Exception as e:
                    logger.warning(f"Failed to close index: {e}")
                finally:
                    self.ix = None
        except Exception as e:
            logger.error(f"Error during index cleanup: {e}")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

@contextmanager
def WhooshWriter(index_path: str, fields: list[str] = None):
    """Context manager for Whoosh index writer with robust error handling."""
    idx = None
    writer = None
    
    try:
        idx = WhooshFullTextIndex(index_path, fields)
        if not idx.ix:
            raise WhooshIndexError("Failed to initialize index")
            
        try:
            writer = idx.ix.writer()
            idx.writer = writer
        except LockError as e:
            raise WhooshIndexError(f"Cannot acquire index lock: {e}") from e
        except Exception as e:
            raise WhooshIndexError(f"Cannot create writer: {e}") from e
            
        yield idx
        
    except Exception as e:
        logger.error(f"Error in WhooshWriter context: {e}")
        # Cancel the writer if something went wrong
        if writer is not None:
            try:
                writer.cancel()
            except Exception as cancel_e:
                logger.warning(f"Failed to cancel writer: {cancel_e}")
        raise
        
    else:
        # Commit only if no exceptions occurred
        if writer is not None:
            try:
                writer.commit()
                logger.debug("Successfully committed index changes")
            except Exception as e:
                logger.error(f"Failed to commit writer: {e}")
                try:
                    writer.cancel()
                except Exception:
                    pass
                raise WhooshIndexError(f"Failed to commit index: {e}") from e
                
    finally:
        # Cleanup
        if idx is not None:
            idx.writer = None
            try:
                if idx.ix:
                    idx.ix.close()
            except Exception as e:
                logger.warning(f"Failed to close index: {e}")

@contextmanager
def WhooshSearcher(index_path: str):
    """Context manager for Whoosh index searcher with error handling."""
    idx = None
    try:
        idx = WhooshFullTextIndex(index_path)
        if not idx.ix:
            raise WhooshIndexError("Failed to initialize index for searching")
        yield idx
    except Exception as e:
        logger.error(f"Error in WhooshSearcher context: {e}")
        raise
    finally:
        if idx is not None:
            try:
                idx.close()
            except Exception as e:
                logger.warning(f"Failed to close searcher: {e}")

@register_segment("indexWhoosh")
@segment()
def indexWhoosh(items, index_path: str, field_list: list[str] = ["_:content"], 
                yield_doc=False, continue_on_error=True):
    """Index documents using Whoosh full-text indexing with robust error handling.

    Args:
        items: Iterator of items to index
        index_path (str): Path to the Whoosh index directory.
        field_list (list[str]): List of fields to index.
        yield_doc (bool): If True, yield each indexed document. Otherwise yield the original item.
        continue_on_error (bool): If True, continue processing other documents when one fails.
    """
    field_list_dict = parse_key_value_str(field_list)
    indexed_count = 0
    error_count = 0
    
    try:
        with WhooshWriter(index_path, list(field_list_dict.values())) as idx:
            for item in items:
                try:
                    d = toDict(item, field_list, fail_on_missing=False)
                    d['doc_id'] = str(d.get('doc_id', uuid.uuid4()))
                    d_str = {k: str(v) for k, v in d.items()}
                    
                    success = idx.add_document(d_str)
                    if success:
                        indexed_count += 1
                        yield d if yield_doc else item
                    else:
                        error_count += 1
                        if not continue_on_error:
                            break
                        logger.warning(f"Failed to index document {d.get('doc_id', 'unknown')}")
                        
                except Exception as e:
                    error_count += 1
                    logger.error(f"Error processing document: {e}")
                    if not continue_on_error:
                        raise
                    # Continue with next document if continue_on_error is True
                    
    except WhooshIndexError as e:
        logger.error(f"Index error during indexing: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error during indexing: {e}")
        raise
    finally:
        logger.info(f"Indexing completed: {indexed_count} documents indexed, {error_count} errors")

@register_segment("searchWhoosh")
@segment()
def searchWhoosh(queries, index_path: str, limit: int = 100, 
                 all_results_at_once: bool = False, continue_on_error=True):
    """Search documents using Whoosh full-text indexing with error handling.

    Args:
        queries: Iterator of query strings
        index_path (str): Path to the Whoosh index directory.
        limit (int): Maximum number of results to return for each query. Defaults to 100.
        all_results_at_once (bool): If True, yield all results at once. Otherwise, yield one result at a time.
        continue_on_error (bool): If True, continue with next query when one fails.
    """
    try:
        with WhooshSearcher(index_path) as idx:
            for query in queries:
                try:
                    results = idx.search(query, limit=limit)
                    if all_results_at_once:
                        yield results
                    else:
                        for result in results:
                            yield result
                except Exception as e:
                    logger.error(f"Error searching for query '{query}': {e}")
                    if not continue_on_error:
                        raise
                    # Continue with next query if continue_on_error is True
                    
    except WhooshIndexError as e:
        logger.error(f"Index error during searching: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error during searching: {e}")
        raise