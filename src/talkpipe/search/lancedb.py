from typing import Annotated, List, Optional
import logging
import lancedb
import uuid
import numpy as np
from datetime import timedelta
from talkpipe.chatterlang import register_segment
from talkpipe import segment
from talkpipe.util.data_manipulation import extract_property, VectorLike, Document, DocID, toDict, assign_property
from talkpipe.util.os import get_process_temp_dir
from .abstract import DocumentStore, VectorAddable, VectorSearchable, SearchResult

logger = logging.getLogger(__name__)


def parse_db_path(path: str) -> str:
    """
    Parse database path, handling special URI schemes.

    Supported schemes:
    - Regular paths: "/path/to/db" -> "/path/to/db"
    - Memory DBs: "memory://" or "" -> passes through to LanceDB
    - Temp DBs: "tmp://name" -> process-wide temp directory path

    Args:
        path: Database path or URI

    Returns:
        Resolved path suitable for lancedb.connect()

    Examples:
        >>> parse_db_path("/data/mydb")
        "/data/mydb"

        >>> parse_db_path("memory://")
        "memory://"

        >>> parse_db_path("tmp://my_cache")
        "/tmp/talkpipe_tmp/my_cache"  # actual temp dir

    Raises:
        ValueError: If tmp:// URI has no name
    """
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
                   path: Annotated[str, "Path to the LanceDB database. Supports file paths, 'memory://' for in-memory, or 'tmp://name' for process-scoped temp (auto-cleanup)"],
                   table_name: Annotated[str, "Table name in the LanceDB database"],
                   all_results_at_once: Annotated[bool, "If true, return all results at once"]=False,
                   field: Annotated[str, "Field with the vector"]=None,
                   set_as: Annotated[str, "Set the results as this variable"]=None,
                   limit: Annotated[int, "Number of results to return per query"]=10,
                   vector_dim: Annotated[Optional[int], "Expected dimension of vectors"]=None,
                   read_consistency_interval: Annotated[int, "Read consistency interval in seconds"]=10
                ):
    """Search for similar vectors in LanceDB and return SearchResult objects.

    The path parameter supports multiple URI schemes:
    - File path: "./my_db" or "/path/to/db" - Persistent storage
    - Memory: "memory://" - Ephemeral in-memory database (faster, no disk I/O)
    - Temp: "tmp://name" - Process-scoped temporary database (shared by name, auto-cleanup on exit)

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
@segment()
def add_to_lancedb(items: Annotated[object, "Items with the vectors and documents"],
                   path: Annotated[str, "Path to the LanceDB database. Supports file paths, 'memory://' for in-memory, or 'tmp://name' for process-scoped temp (auto-cleanup)"],
                   table_name: Annotated[str, "Table name in the LanceDB database"],
                   vector_field: Annotated[str, "The field containing the vector data"] = "vector",
                   doc_id_field: Annotated[Optional[str], "Field containing document ID"] = None,
                   metadata_field_list: Annotated[Optional[str], "Optional metadata field list"] = None,
                   overwrite: Annotated[bool, "If true, overwrite existing table"]=False,
                   upsert: Annotated[bool, "If true (default), update existing documents with same ID. If false, raise error on duplicate ID"]=True,
                   vector_dim: Annotated[Optional[int], "Expected dimension of vectors"]=None
                   ):
    """Add vectors and documents to LanceDB using LanceDBDocumentStore.

    The path parameter supports multiple URI schemes:
    - File path: "./my_db" or "/path/to/db" - Persistent storage
    - Memory: "memory://" - Ephemeral in-memory database (faster, no disk I/O)
    - Temp: "tmp://name" - Process-scoped temporary database (shared by name, auto-cleanup on exit)

    By default, this segment uses upsert behavior: if a document with the same ID already exists,
    it will be updated with the new vector and metadata. Set upsert=False to raise an error on
    duplicate IDs instead.

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

    for item in items:
        # Extract vector
        vector = extract_property(item, vector_field, fail_on_missing=True)
        if not isinstance(vector, (list, tuple, np.ndarray)):
            raise ValueError(f"Vector field '{vector_field}' must be a list, tuple, or numpy array")

        # Extract document ID if specified
        doc_id = None
        if doc_id_field:
            doc_id = extract_property(item, doc_id_field, fail_on_missing=False)

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

        # Add to document store (upsert by default, or strict add if upsert=False)
        if upsert:
            added_doc_id = doc_store.upsert_vector(vector, document, doc_id)
        else:
            added_doc_id = doc_store.add_vector(vector, document, doc_id)

        # Add the document ID to the item for reference (only if item is a dict)
        if isinstance(item, dict):
            item["_doc_id"] = added_doc_id

        yield item


class LanceDBDocumentStore(DocumentStore, VectorAddable, VectorSearchable):
    """A LanceDB-based document store that implements vector storage and search capabilities."""

    def __init__(self, path: str, table_name: str = "documents", vector_dim: Optional[int] = None, read_consistency_interval: int = 10):
        """
        Initialize the LanceDB document store.

        Args:
            path: Path to the LanceDB database. Supports:
                  - Regular paths: "/path/to/db"
                  - Memory DBs: "memory://"
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
        if self._table is None:
            db = self._get_db()
            try:
                self._table = db.open_table(self.table_name)
            except (FileNotFoundError, ValueError):  # ValueError for "Table not found"
                if schema_if_missing is not None:
                    # Create table with provided schema data
                    self._table = db.create_table(self.table_name, schema_if_missing)
                else:
                    raise ValueError(f"Table '{self.table_name}' not found and no schema provided. Please provide a LanceDB compatible schema.")
        return self._table

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
            table = self._get_table()
            results = table.search().where(f"id = '{doc_id}'").to_list()
            if results:
                return self._deserialize_document(results[0]["document"])
            return None
        except Exception:
            return None

    # VectorAddable protocol implementation
    def add_vector(self, vector: VectorLike, document: Document, doc_id: Optional[DocID] = None) -> DocID:
        """Add a vector to the store."""
        vec_list = self._validate_vector(vector)

        if doc_id is None:
            doc_id = str(uuid.uuid4())

        # Check if document already exists
        existing = self.get_document(doc_id)
        if existing is not None:
            raise ValueError(f"Document with ID {doc_id} already exists")

        # Prepare schema data for table creation if needed
        schema_data = [{
            "id": doc_id,
            "vector": vec_list,
            "document": self._serialize_document(document)
        }]

        table = self._get_table(schema_if_missing=schema_data)

        # If table was just created, data is already there, otherwise add it
        try:
            # Check if this is a newly created table by seeing if our data is already there
            existing_check = table.search().where(f"id = '{doc_id}'").to_list()
            if not existing_check:
                table.add(schema_data)
        except Exception:
            # If there's any issue with the check, just try to add the data
            table.add(schema_data)

        return doc_id

    def upsert_vector(self, vector: VectorLike, document: Document, doc_id: Optional[DocID] = None) -> DocID:
        """Add or update a vector in the store (upsert behavior).

        If a document with the given doc_id exists, it will be updated.
        If it doesn't exist, a new document will be created.

        Args:
            vector: The vector to store
            document: The document metadata to associate with the vector
            doc_id: Optional document ID. If not provided, a UUID will be generated.

        Returns:
            The document ID of the added/updated document.
        """
        vec_list = self._validate_vector(vector)

        if doc_id is None:
            doc_id = str(uuid.uuid4())

        # Check if document already exists
        existing = self.get_document(doc_id)
        if existing is not None:
            # Delete existing document first
            self.delete_document(doc_id)

        # Prepare schema data for table creation if needed
        schema_data = [{
            "id": doc_id,
            "vector": vec_list,
            "document": self._serialize_document(document)
        }]

        table = self._get_table(schema_if_missing=schema_data)

        # If table was just created, data is already there, otherwise add it
        try:
            # Check if this is a newly created table by seeing if our data is already there
            existing_check = table.search().where(f"id = '{doc_id}'").to_list()
            if not existing_check:
                table.add(schema_data)
        except Exception:
            # If there's any issue with the check, just try to add the data
            table.add(schema_data)

        return doc_id

    # VectorSearchable protocol implementation
    def vector_search(self, vector: VectorLike, limit: int = 10) -> List[SearchResult]:
        """Search for vectors similar to the given vector."""
        vec_list = self._validate_vector(vector)

        try:
            table = self._get_table()
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
            table = self._get_table()
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
                table = self._get_table()
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
            table = self._get_table()
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
            table = self._get_table()
            results = table.search().select(["id"]).to_list()
            return [result["id"] for result in results]
        except Exception:
            return []

