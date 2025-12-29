from typing import Annotated, List, Optional
import logging
import lancedb
import uuid
import numpy as np
from datetime import timedelta
from talkpipe.chatterlang import register_segment
from talkpipe import segment
from talkpipe.pipe.core import is_metadata
from talkpipe.pipe.metadata import Flush
from talkpipe.util.collections import AdaptiveBuffer
from talkpipe.util.data_manipulation import extract_property, VectorLike, Document, DocID, toDict, assign_property
from talkpipe.util.os import get_process_temp_dir
from .abstract import DocumentStore, VectorAddable, VectorSearchable, SearchResult

logger = logging.getLogger(__name__)


def parse_db_path(path: str) -> str:
    """
    Parse database path, handling special URI schemes.

    Supported schemes:
    - Regular paths: "/path/to/db" -> "/path/to/db"
    - Temp DBs: "tmp://name" -> process-wide temp directory path

    Args:
        path: Database path or URI

    Returns:
        Resolved path suitable for lancedb.connect()

    Examples:
        >>> parse_db_path("/data/mydb")
        "/data/mydb"

        >>> parse_db_path("memory://")
        ValueError: memory:// is no longer supported

        >>> parse_db_path("tmp://my_cache")
        "/tmp/talkpipe_tmp/my_cache"  # actual temp dir

    Raises:
        ValueError: If tmp:// URI has no name, or if memory:// is used
    """
    if path.startswith("memory://"):
        raise ValueError("memory:// is no longer supported. Use 'tmp://<name>' for process-scoped temp DBs or a filesystem path.")
    if path.startswith("tmp://"):
        # Extract name from URI
        name = path[6:]  # Remove "tmp://" prefix
        if not name:
            raise ValueError("tmp:// URI requires a name (e.g., tmp://my_db)")

        # Get process-wide temp directory
        return get_process_temp_dir(name)

    # Pass through other URIs/paths
    return path

@register_segment("searchLanceDB", "searchLancDB")
@segment()
def search_lancedb(items: Annotated[object, "Items with the query vectors"],
                   path: Annotated[str, "Path to the LanceDB database. Supports file paths or 'tmp://name' for process-scoped temp (auto-cleanup)"],
                   table_name: Annotated[str, "Table name in the LanceDB database"],
                   all_results_at_once: Annotated[bool, "If true, return all results at once"]=False,
                   field: Annotated[str, "Field with the vector"]=None,
                   set_as: Annotated[str, "Set the results as this variable"]=None,
                   limit: Annotated[int, "Number of results to return per query"]=10,
                   vector_dim: Annotated[Optional[int], "Expected dimension of vectors"]=None,
                   read_consistency_interval: Annotated[int, "Read consistency interval in seconds"]=10
                ):
    """Search for similar vectors in a LanceDB vector database.
    
    Searches a vector database created with addToLanceDB using vector similarity search.
    For each input item, extracts a query vector and finds the most similar vectors in
    the database, returning the associated documents.
    
    LanceDB is optimized for vector similarity search and supports approximate nearest
    neighbor (ANN) search for efficient similarity matching. Results are scored by
    similarity distance.
    
    Path supports storage options:
    - "/path/to/db": Persistent file-based database
    - "tmp://name": Process-scoped temporary database (shared by name, auto-cleanup on exit)
    
    Useful for:
    - Building semantic search systems
    - Finding similar items using embeddings
    - Recommendation systems based on vector similarity
    - Image or text similarity matching
    
    Yields:
        SearchResult objects or lists of SearchResult objects.
    """
    if path is None or table_name is None:
        raise ValueError("Both 'path' and 'table' parameters must be provided.")

    if set_as is not None and not all_results_at_once:
        raise ValueError("If 'set_as' is provided, 'all_results_at_once' must be True.")

    # Use LanceDBDocumentStore for consistent interface
    doc_store = LanceDBDocumentStore(path, table_name, vector_dim, read_consistency_interval)

    for item in items:
        if field:
            query_vector = extract_property(item, field)
        else:
            query_vector = item

        # Get SearchResult objects from document store
        search_results = doc_store.vector_search(query_vector, limit)

        if set_as:
            assign_property(item, set_as, search_results)
            yield item
        elif all_results_at_once:
            yield search_results
        else:
            # Yield individual SearchResult objects
            for result in search_results:
                yield result

@register_segment("addToLanceDB", "addToLancDB")
@segment(process_metadata=True)
def add_to_lancedb(items: Annotated[object, "Items with the vectors and documents"],
                   path: Annotated[str, "Path to the LanceDB database. Supports file paths or 'tmp://name' for process-scoped temp (auto-cleanup)"],
                   table_name: Annotated[str, "Table name in the LanceDB database"],
                   vector_field: Annotated[str, "The field containing the vector data"] = "vector",
                   doc_id_field: Annotated[Optional[str], "Field containing document ID"] = None,
                   metadata_field_list: Annotated[Optional[str], "Optional metadata field list"] = None,
                   overwrite: Annotated[bool, "If true, overwrite existing table"]=False,
                   vector_dim: Annotated[Optional[int], "Expected dimension of vectors"]=None,
                   batch_size: Annotated[int, "Maximum batch size for adding vectors"]=1,
                   optimize_on_batch: Annotated[bool, "If true, optimize the table after each batch.  Otherwise optimize after last batch."]=False,
                   ):
    """Add vectors and documents to a LanceDB vector database.
    
    Builds a searchable vector index from items containing embeddings (vectors).
    Each item should have a vector field (typically embeddings from a model) and
    associated metadata or documents to return in search results.
    
    LanceDB stores both the vectors for similarity search and the associated documents
    for retrieval. Vectors are indexed for efficient approximate nearest neighbor search.
    
    Path supports storage options:
    - "/path/to/db": Persistent file-based database
    - "tmp://name": Process-scoped temporary database (shared by name, auto-cleanup on exit)
    
    By default uses upsert behavior: if a document with the same ID already exists,
    it will be updated with the new vector and metadata. Set upsert=False to raise
    an error on duplicate IDs instead.
    
    Useful for:
    - Creating semantic search indexes from embeddings
    - Building recommendation systems
    - Storing document embeddings for similarity matching
    - Building multi-modal search systems
    
    Returns:
        The original items with the document IDs added.
    """
    if path is None or table_name is None:
        raise ValueError("Both 'path' and 'table' parameters must be provided.")

    # Use LanceDBDocumentStore for consistent interface
    doc_store = LanceDBDocumentStore(path, table_name, vector_dim)

    # Handle overwrite by dropping table if it exists
    if overwrite:
        try:
            db = doc_store._get_db()
            # Try to drop the table if it exists
            try:
                db.drop_table(table_name)
            except (FileNotFoundError, ValueError):
                # Table doesn't exist, which is fine
                logger.info(f"Table '{table_name}' does not exist, nothing to drop.")
            # Reset the cached table reference
            doc_store._table = None
        except Exception:
            # If there's any issue with dropping, continue
            logger.warning(f"Could not drop table '{table_name}' for overwrite. Continuing without dropping.")

    max_batch_size = max(1, batch_size)
    buffer = AdaptiveBuffer(max_size=max_batch_size)
    optimized_since_last_add = False  # Track if optimization has occurred since last add
    
    for item in items:
        # Check if this is a Flush event
        if is_metadata(item) and isinstance(item, Flush):
            # Flush the buffer and add any partial items
            flush_batch = buffer.flush()
            if flush_batch is not None:
                doc_store.add_vectors(flush_batch)
                # Optimize if it hasn't been optimized since the last add
                if not optimized_since_last_add:
                    doc_store._get_table()[0].optimize()
                    optimized_since_last_add = True
            # Don't yield Flush events - consume them
            continue
        
        # Extract vector
        vector = extract_property(item, vector_field, fail_on_missing=True)
        if not isinstance(vector, (list, tuple, np.ndarray)):
            raise ValueError(f"Vector field '{vector_field}' must be a list, tuple, or numpy array")

        if doc_id_field:
            doc_id = extract_property(item, doc_id_field, fail_on_missing=False)
        else:
            doc_id = str(uuid.uuid4())
            assign_property(item, "_doc_id", doc_id)

        # Extract metadata
        if metadata_field_list:
            metadata = toDict(item, metadata_field_list, fail_on_missing=False)
        else:
            # Use the entire item as metadata, excluding the vector field
            if isinstance(item, dict):
                metadata = {k: v for k, v in item.items() if k != vector_field}
            else:
                raise ValueError("If 'metadata_field_list' is not provided, item must be a dict to extract fields.")
            
        # Convert metadata to Document format (string keys and values)
        document = {str(k): str(v) for k, v in metadata.items()}

        batch = buffer.append((vector, document, doc_id))
        if batch is not None:
            doc_store.add_vectors(batch)
            optimized_since_last_add = False  # Mark that optimization hasn't occurred since last add
            if optimize_on_batch:
                doc_store._get_table()[0].optimize()
                optimized_since_last_add = True

        yield item
        
    final_batch = buffer.flush()
    if final_batch is not None:
        doc_store.add_vectors(final_batch)
        # Optimize at the end: if optimize_on_batch is False, only optimize if we haven't optimized since last add
        # If optimize_on_batch is True, optimize at the end (existing behavior)
        if optimize_on_batch or not optimized_since_last_add:
            doc_store._get_table()[0].optimize() 


class LanceDBDocumentStore(DocumentStore, VectorAddable, VectorSearchable):
    """A LanceDB-based document store that implements vector storage and search capabilities."""

    def __init__(self, path: str, table_name: str = "documents", vector_dim: Optional[int] = None, read_consistency_interval: int = 10):
        """
        Initialize the LanceDB document store.

        Args:
            path: Path to the LanceDB database. Supports:
                  - Regular paths: "/path/to/db"
                  - Temp DBs: "tmp://name" (process-wide, auto-cleanup)
            table_name: Name of the table to store documents in
            vector_dim: Expected dimension of vectors (optional, inferred from first vector)
        """
        self.original_path = path  # Keep original for reference
        self.path = parse_db_path(path)  # Resolve tmp:// and other URIs
        self.table_name = table_name
        self.vector_dim = vector_dim
        self._db = None
        self._table = None
        self.read_consistency_interval = read_consistency_interval

    def _get_db(self):
        """Get or create database connection."""
        if self._db is None:
            # Convert integer seconds to timedelta if needed
            if self.read_consistency_interval is not None:
                interval = timedelta(seconds=self.read_consistency_interval)
            else:
                interval = None
            self._db = lancedb.connect(self.path, read_consistency_interval=interval)
        return self._db

    def _get_table(self, schema_if_missing=None):
        """Get or create table with provided schema."""
        created_and_updated = False
        if self._table is None:
            db = self._get_db()
            try:
                self._table = db.open_table(self.table_name)
            except (FileNotFoundError, ValueError):  # ValueError for "Table not found"
                if schema_if_missing is not None:
                    # Create table with provided schema data
                    self._table = db.create_table(self.table_name, schema_if_missing)
                    created_and_updated = True
                else:
                    raise ValueError(f"Table '{self.table_name}' not found and no schema provided. Please provide a LanceDB compatible schema.")
        return self._table, created_and_updated

    def _validate_vector(self, vector: VectorLike) -> List[float]:
        """Validate vector and return as list of floats."""
        if isinstance(vector, np.ndarray):
            vec_array = vector
        else:
            vec_array = np.array(vector, dtype=np.float32)

        if vec_array.ndim != 1:
            raise ValueError("Vector must be 1-dimensional")
        if not np.issubdtype(vec_array.dtype, np.number):
            raise ValueError("Vector must contain only numbers")

        if self.vector_dim is None:
            self.vector_dim = len(vec_array)
        elif len(vec_array) != self.vector_dim:
            raise ValueError(f"Vector dimension {len(vec_array)} doesn't match expected {self.vector_dim}")

        return vec_array.tolist()

    def _serialize_document(self, document: Document) -> str:
        """Serialize document to JSON string for storage."""
        import json
        return json.dumps(document)

    def _deserialize_document(self, document_str: str) -> Document:
        """Deserialize document from JSON string."""
        import json
        return json.loads(document_str)

    # DocumentStore protocol implementation
    def get_document(self, doc_id: DocID) -> Optional[Document]:
        """Retrieve a document by ID."""
        try:
            table, created_and_updated = self._get_table()
            results = table.search().where(f"id = '{doc_id}'").to_list()
            if results:
                return self._deserialize_document(results[0]["document"])
            return None
        except Exception:
            return None

    # VectorAddable protocol implementation
    def add_vector(self, vector: VectorLike, document: Document, doc_id: Optional[DocID] = None) -> DocID:
        return self.add_vectors([(vector, document, doc_id)])[0]

    def add_vectors(self, documents: List[tuple]) -> List[DocID]:
        """Add multiple vectors to the store in a batch operation.
        
        Args:
            documents: List of tuples in format (vector, document, doc_id) where:
                      - vector: VectorLike - the vector data
                      - document: Document - the document metadata
                      - doc_id: Optional[DocID] - document ID (generated if None)
        
        Returns:
            List of document IDs for the added vectors
        """
        if not documents:
            return []
        
        doc_ids = []
        schema_data = []
        
        for vector, document, doc_id in documents:
            vec_list = self._validate_vector(vector)
            
            if doc_id is None:
                doc_id = str(uuid.uuid4())
            
            doc_ids.append(doc_id)
            
            schema_data.append({
                "id": doc_id,
                "vector": vec_list,
                "document": self._serialize_document(document)
            })
        
        table, created_and_updated = self._get_table(schema_if_missing=schema_data)
        
        if not created_and_updated:
            # Table exists, use merge_insert for upsert behavior
            table.merge_insert('id').when_matched_update_all().when_not_matched_insert_all().execute(schema_data)
        
        return doc_ids

    # VectorSearchable protocol implementation
    def vector_search(self, vector: VectorLike, limit: int = 10) -> List[SearchResult]:
        """Search for vectors similar to the given vector."""
        vec_list = self._validate_vector(vector)

        try:
            table, created_and_updated = self._get_table()
            results = table.search(vec_list).limit(limit).to_list()

            search_results = []
            for result in results:
                # LanceDB returns distance, we convert to similarity score (1 - normalized_distance)
                distance = result.get("_distance", 0.0)
                # Normalize distance to similarity score (higher is better)
                score = max(0.0, 1.0 - distance)

                search_result = SearchResult(
                    score=score,
                    doc_id=result["id"],
                    document=self._deserialize_document(result["document"])
                )
                search_results.append(search_result)

            return search_results
        except Exception:
            return []

    def delete_document(self, doc_id: DocID) -> bool:
        """Delete a document by ID."""
        try:
            table, created_and_updated = self._get_table()
            table = table.delete(f"id = '{doc_id}'")
            return True
        except Exception:
            return False

    def update_document(self, doc_id: DocID, document: Document, vector: Optional[VectorLike] = None) -> bool:
        """Update an existing document."""
        try:
            # Check if document exists
            existing = self.get_document(doc_id)
            if existing is None:
                return False

            # Delete existing document
            self.delete_document(doc_id)

            # If vector is provided, validate it, otherwise we need to get the old vector
            if vector is not None:
                vec_list = self._validate_vector(vector)
            else:
                # Get the old vector from the table before deletion
                table, created_and_updated = self._get_table()
                results = table.search().where(f"id = '{doc_id}'").to_list()
                if not results:
                    return False
                vec_list = results[0]["vector"]

            # Add updated document
            self.add_vector(vec_list, document, doc_id)
            return True
        except Exception:
            return False

    def count(self) -> int:
        """Return the number of documents in the store."""
        try:
            table, created_and_updated = self._get_table()
            # Use count_rows method if available, otherwise fallback to counting all results
            if hasattr(table, 'count_rows'):
                return table.count_rows()
            else:
                return len(table.search().to_list())
        except Exception:
            return 0

    def list_ids(self) -> List[DocID]:
        """Return a list of all document IDs."""
        try:
            table, created_and_updated = self._get_table()
            results = table.search().select(["id"]).to_list()
            return [result["id"] for result in results]
        except Exception:
            return []
