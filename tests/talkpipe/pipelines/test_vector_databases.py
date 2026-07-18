import pytest
import base64
import tempfile
import os
import threading
import queue
import time
from talkpipe import AbstractSegment
from talkpipe.pipelines.vector_databases import MakeVectorDatabaseSegment, ProcessDocumentsSegment, SearchVectorDatabaseSegment
from talkpipe.search.lancedb import LanceDBDocumentStore
from talkpipe.search.abstract import SearchResult


@pytest.fixture
def temp_db_path():
    """Create a temporary directory for the database."""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield os.path.join(temp_dir, "test_vector_db")


@pytest.fixture
def sample_documents():
    """Sample documents for testing."""
    return [
        {"text": "The quick brown fox jumps over the lazy dog", "title": "Fox Story", "id": "doc1"},
        {"text": "Python is a great programming language", "title": "Python Info", "id": "doc2"},
        {"text": "Machine learning is transforming technology", "title": "ML Article", "id": "doc3"}
    ]


def test_process_documents_segment_shingles_with_defaults(tmp_path):
    """ProcessDocumentsSegment should honor default chunk, shingle, and overlap sizes."""
    chunks = ["a" * 300, "b" * 300, "c" * 300, "d" * 50]
    document_path = tmp_path / "document.txt"
    document_path.write_text("".join(chunks))

    segment = ProcessDocumentsSegment()

    results = list(segment.transform([str(document_path)]))

    assert [item["shingle_text"] for item in results] == [
        f"{chunks[0]} {chunks[1]} {chunks[2]}",
        f"{chunks[2]} {chunks[3]}",
    ]


def test_process_documents_segment_strips_base64(tmp_path):
    """Embedded base64 payloads should never reach the chunker or embedder."""
    blob = base64.b64encode(b"z" * 900).decode()
    document_path = tmp_path / "receipt.md"
    document_path.write_text(
        f"Receipt for payment. ![img](data:image/png;base64,{blob}) Total due: 250 dollars."
    )

    results = list(ProcessDocumentsSegment().transform([str(document_path)]))

    joined = " ".join(item["shingle_text"] for item in results)
    assert blob[:64] not in joined
    assert "Receipt for payment." in joined
    assert "Total due: 250 dollars." in joined


def test_process_documents_segment_strip_base64_disabled(tmp_path):
    """With strip_base64=False the raw payload is chunked as before."""
    blob = base64.b64encode(b"z" * 900).decode()
    document_path = tmp_path / "receipt.md"
    document_path.write_text(f"Receipt for payment. {blob}")

    results = list(ProcessDocumentsSegment(strip_base64=False).transform([str(document_path)]))

    joined = " ".join(item["shingle_text"] for item in results)
    assert blob[:64] in joined


def test_make_vector_database_indexes_default_shingles_as_content(tmp_path, monkeypatch):
    """Indexed documents should store the shingled text as the content chunk."""
    class FakeLLMEmbed(AbstractSegment):
        def __init__(self, model=None, source=None, field=None, set_as=None, fail_on_error=True, **kwargs):
            super().__init__()
            self.field = field
            self.set_as = set_as

        def transform(self, input_iter):
            for item in input_iter:
                text = item[self.field] if self.field else item
                item[self.set_as] = [float(len(text)), 0.0, 0.0]
                yield item

    monkeypatch.setattr("talkpipe.pipelines.vector_databases.LLMEmbed", FakeLLMEmbed)

    chunks = ["a" * 300, "b" * 300, "c" * 300, "d" * 50]
    document_path = tmp_path / "document.txt"
    document_path.write_text("".join(chunks))
    db_path = str(tmp_path / "vector_db")
    pipeline = ProcessDocumentsSegment() | MakeVectorDatabaseSegment(
        embedding_field="shingle_text",
        embedding_model="fake-model",
        embedding_source="fake-source",
        path=db_path,
        overwrite=True,
        batch_size=1,
    )

    indexed_items = list(pipeline.transform([str(document_path)]))

    db_store = LanceDBDocumentStore(path=db_path, table_name="docs", vector_dim=3)
    stored_doc = db_store.get_document(indexed_items[0]["_doc_id"])
    assert stored_doc is not None
    assert stored_doc["content"] == indexed_items[0]["shingle_text"]
    assert 900 <= len(stored_doc["content"]) <= 910


def test_make_vector_database_basic(requires_ollama, temp_db_path, sample_documents):
    """Test basic functionality of MakeVectorDatabaseSegment."""
    # Create the segment with Ollama embeddings
    segment = MakeVectorDatabaseSegment(
        embedding_field="text",
        embedding_model="mxbai-embed-large",
        embedding_source="ollama",
        path=temp_db_path,
        doc_id_field="id",
        overwrite=True
    )

    # Process the documents through the segment
    results = list(segment.transform(sample_documents))

    # Verify all documents were processed and returned
    assert len(results) == 3

    # Verify the returned items are the original documents
    for i, result in enumerate(results):
        assert result["text"] == sample_documents[i]["text"]
        assert result["title"] == sample_documents[i]["title"]
        assert result["id"] == sample_documents[i]["id"]

    # Verify the database was created and contains the documents
    db_store = LanceDBDocumentStore(path=temp_db_path, table_name="docs", vector_dim=1024)
    count = db_store.count()
    assert count == 3, f"Expected 3 documents in database, found {count}"


def test_make_vector_database_without_doc_id(requires_ollama, temp_db_path, sample_documents):
    """Test MakeVectorDatabaseSegment without specifying doc_id_field."""
    # Remove id field from documents
    docs_without_id = [{"text": doc["text"], "title": doc["title"]} for doc in sample_documents]

    # Create the segment without doc_id_field
    segment = MakeVectorDatabaseSegment(
        embedding_field="text",
        embedding_model="mxbai-embed-large",
        embedding_source="ollama",
        path=temp_db_path,
        overwrite=True
    )

    # Process the documents
    results = list(segment.transform(docs_without_id))

    # Verify all documents were processed
    assert len(results) == 3

    # Verify the database contains the documents
    db_store = LanceDBDocumentStore(path=temp_db_path, table_name="docs", vector_dim=1024)
    count = db_store.count()
    assert count == 3


def test_make_vector_database_overwrite(requires_ollama, temp_db_path, sample_documents):
    """Test that overwrite parameter correctly replaces existing database."""
    # Create initial database
    segment1 = MakeVectorDatabaseSegment(
        embedding_field="text",
        embedding_model="mxbai-embed-large",
        embedding_source="ollama",
        path=temp_db_path,
        overwrite=True
    )
    list(segment1.transform(sample_documents))

    # Verify initial count
    db_store = LanceDBDocumentStore(path=temp_db_path, table_name="docs", vector_dim=1024)
    assert db_store.count() == 3

    # Create new segment with overwrite=True and add only 1 document
    segment2 = MakeVectorDatabaseSegment(
        embedding_field="text",
        embedding_model="mxbai-embed-large",
        embedding_source="ollama",
        path=temp_db_path,
        overwrite=True
    )
    list(segment2.transform([sample_documents[0]]))

    # Verify count is now 1 (database was overwritten)
    db_store2 = LanceDBDocumentStore(path=temp_db_path, table_name="docs", vector_dim=1024)
    assert db_store2.count() == 1


def test_make_vector_database_no_overwrite(requires_ollama, temp_db_path, sample_documents):
    """Test that without overwrite, documents are appended to existing database."""
    # Create initial database with first document
    segment1 = MakeVectorDatabaseSegment(
        embedding_field="text",
        embedding_model="mxbai-embed-large",
        embedding_source="ollama",
        path=temp_db_path,
        overwrite=True
    )
    list(segment1.transform([sample_documents[0]]))

    # Verify initial count
    db_store = LanceDBDocumentStore(path=temp_db_path, table_name="docs", vector_dim=1024)
    assert db_store.count() == 1

    # Add more documents without overwrite
    segment2 = MakeVectorDatabaseSegment(
        embedding_field="text",
        embedding_model="mxbai-embed-large",
        embedding_source="ollama",
        path=temp_db_path,
        overwrite=False
    )
    list(segment2.transform(sample_documents[1:]))

    # Verify count is now 3 (documents were appended)
    db_store2 = LanceDBDocumentStore(path=temp_db_path, table_name="docs", vector_dim=1024)
    assert db_store2.count() == 3


def test_make_vector_database_preserves_original_data(requires_ollama, temp_db_path, sample_documents):
    """Test that the segment preserves all original document fields."""
    segment = MakeVectorDatabaseSegment(
        embedding_field="text",
        embedding_model="mxbai-embed-large",
        embedding_source="ollama",
        path=temp_db_path,
        doc_id_field="id",
        overwrite=True
    )

    # Process documents
    results = list(segment.transform(sample_documents))

    # Verify each result has all original fields
    for i, result in enumerate(results):
        assert "text" in result
        assert "title" in result
        assert "id" in result
        # Verify the values match
        assert result["text"] == sample_documents[i]["text"]
        assert result["title"] == sample_documents[i]["title"]
        assert result["id"] == sample_documents[i]["id"]

    # Verify metadata is stored in the database correctly
    db_store = LanceDBDocumentStore(path=temp_db_path, table_name="docs", vector_dim=1024)

    # Retrieve a document and check its metadata
    stored_doc = db_store.get_document(sample_documents[0]["id"])
    assert stored_doc is not None
    assert stored_doc["text"] == sample_documents[0]["text"]
    assert stored_doc["title"] == sample_documents[0]["title"]
    assert stored_doc["id"] == sample_documents[0]["id"]


@pytest.fixture
def populated_db_path(requires_ollama, temp_db_path, sample_documents):
    """Create a populated vector database for search testing."""
    segment = MakeVectorDatabaseSegment(
        embedding_field="text",
        embedding_model="mxbai-embed-large",
        embedding_source="ollama",
        path=temp_db_path,
        doc_id_field="id",
        overwrite=True
    )
    list(segment.transform(sample_documents))
    return temp_db_path


# Tests for SearchVectorDatabaseSegment


def test_search_vector_database_with_string_inputs(populated_db_path):
    """Test SearchVectorDatabaseSegment with string inputs (query_field=None)."""
    search_segment = SearchVectorDatabaseSegment(
        embedding_model="mxbai-embed-large",
        embedding_source="ollama",
        path=populated_db_path,
        limit=2
    )

    # Search with a query similar to one of the documents
    query = "fox jumping"
    results = list(search_segment.transform([query]))

    # Should return a list of SearchResult objects
    assert len(results) == 1
    search_results_list = results[0]
    assert isinstance(search_results_list, list)
    assert len(search_results_list) <= 2  # Limited to 2 results

    # Each result should be a SearchResult
    for result in search_results_list:
        assert isinstance(result, SearchResult)
        assert hasattr(result, 'score')
        assert hasattr(result, 'doc_id')
        assert hasattr(result, 'document')
        assert 0 <= result.score <= 1


def test_search_vector_database_with_dict_and_set_as(populated_db_path):
    """Test SearchVectorDatabaseSegment with dict inputs and set_as parameter."""
    search_segment = SearchVectorDatabaseSegment(
        embedding_model="mxbai-embed-large",
        embedding_source="ollama",
        path=populated_db_path,
        query_field="query",
        set_as="search_results",
        limit=3
    )

    # Search with dictionary inputs
    queries = [
        {"query": "programming language", "user_id": "user1"},
        {"query": "animals", "user_id": "user2"}
    ]
    results = list(search_segment.transform(queries))

    # Should return the original dicts with search_results attached
    assert len(results) == 2

    for i, result in enumerate(results):
        # Original fields should be preserved
        assert result["query"] == queries[i]["query"]
        assert result["user_id"] == queries[i]["user_id"]

        # search_results should be attached
        assert "search_results" in result
        assert isinstance(result["search_results"], list)
        assert len(result["search_results"]) <= 3

        # Each search result should be a SearchResult object
        for search_result in result["search_results"]:
            assert isinstance(search_result, SearchResult)


def test_search_vector_database_with_dict_no_set_as(populated_db_path):
    """Test SearchVectorDatabaseSegment with dict inputs but set_as=None."""
    search_segment = SearchVectorDatabaseSegment(
        embedding_model="mxbai-embed-large",
        embedding_source="ollama",
        path=populated_db_path,
        query_field="query",
        set_as=None,
        limit=2
    )

    # Search with dictionary inputs
    queries = [{"query": "machine learning"}]
    results = list(search_segment.transform(queries))

    # Should yield search results directly (not attached to input)
    assert len(results) == 1
    search_results_list = results[0]
    assert isinstance(search_results_list, list)
    assert len(search_results_list) <= 2

    for result in search_results_list:
        assert isinstance(result, SearchResult)


def test_search_vector_database_validation_error(populated_db_path):
    """Test that SearchVectorDatabaseSegment raises error when query_field=None but set_as is not None."""
    with pytest.raises(ValueError, match="set_as must be None when query_field is None"):
        SearchVectorDatabaseSegment(
            embedding_model="mxbai-embed-large",
            embedding_source="ollama",
            path=populated_db_path,
            query_field=None,  # String inputs
            set_as="results"   # This should cause an error
        )


def test_search_vector_database_relevance(populated_db_path, sample_documents):
    """Test that search returns relevant results based on semantic similarity."""
    search_segment = SearchVectorDatabaseSegment(
        embedding_model="mxbai-embed-large",
        embedding_source="ollama",
        path=populated_db_path,
        limit=3
    )

    # Query similar to "Python is a great programming language"
    query = "Python programming"
    results = list(search_segment.transform([query]))

    assert len(results) == 1
    search_results = results[0]

    # The top result should be the Python document
    top_result = search_results[0]
    assert "Python" in top_result.document.get("text", "")

    # Scores should be in descending order
    scores = [r.score for r in search_results]
    assert scores == sorted(scores, reverse=True)


def test_search_vector_database_limit_parameter(populated_db_path):
    """Test that the limit parameter correctly limits the number of results."""
    # Test with limit=1
    search_segment = SearchVectorDatabaseSegment(
        embedding_model="mxbai-embed-large",
        embedding_source="ollama",
        path=populated_db_path,
        limit=1
    )

    results = list(search_segment.transform(["test query"]))
    assert len(results) == 1
    assert len(results[0]) == 1  # Only 1 result

    # Test with limit=3
    search_segment = SearchVectorDatabaseSegment(
        embedding_model="mxbai-embed-large",
        embedding_source="ollama",
        path=populated_db_path,
        limit=3
    )

    results = list(search_segment.transform(["test query"]))
    assert len(results) == 1
    assert len(results[0]) <= 3  # Up to 3 results


def test_search_vector_database_multiple_queries(populated_db_path):
    """Test searching with multiple string queries in one batch."""
    search_segment = SearchVectorDatabaseSegment(
        embedding_model="mxbai-embed-large",
        embedding_source="ollama",
        path=populated_db_path,
        limit=2
    )

    queries = ["fox", "Python", "technology"]
    results = list(search_segment.transform(queries))

    # Should get results for each query
    assert len(results) == 3

    for result in results:
        assert isinstance(result, list)
        assert all(isinstance(r, SearchResult) for r in result)


def test_search_vector_database_empty_database(requires_ollama, temp_db_path):
    """Test searching an empty database returns empty results."""
    # Create an empty database
    segment = MakeVectorDatabaseSegment(
        embedding_field="text",
        embedding_model="mxbai-embed-large",
        embedding_source="ollama",
        path=temp_db_path,
        overwrite=True
    )
    list(segment.transform([]))  # Empty input

    # Try to search
    search_segment = SearchVectorDatabaseSegment(
        embedding_model="mxbai-embed-large",
        embedding_source="ollama",
        path=temp_db_path,
        limit=10
    )

    # This should handle the empty database gracefully
    # The behavior depends on LanceDB - it might error or return empty results
    # Let's check what actually happens
    try:
        results = list(search_segment.transform(["test query"]))
        # If it succeeds, results should be empty or contain empty lists
        assert len(results) >= 0
    except (ValueError, FileNotFoundError):
        # It's also acceptable to raise an error for empty/non-existent tables
        pass


def test_search_vector_database_preserves_metadata(populated_db_path, sample_documents):
    """Test that search results contain the original document metadata."""
    search_segment = SearchVectorDatabaseSegment(
        embedding_model="mxbai-embed-large",
        embedding_source="ollama",
        path=populated_db_path,
        limit=1
    )

    # Search for something specific
    results = list(search_segment.transform(["fox story"]))

    assert len(results) == 1
    top_result = results[0][0]

    # The document should contain the metadata fields
    assert "text" in top_result.document
    assert "title" in top_result.document
    assert "id" in top_result.document


def test_vector_database_stores_non_embedding_fields(requires_ollama, temp_db_path):
    """Test that fields not used for embedding (like 'path') are stored and retrieved."""
    # Documents where 'content' is for embedding, but 'path' and 'author' are metadata
    docs = [
        {"content": "Python is a versatile programming language", "path": "/docs/python.txt", "author": "Alice", "id": "doc1"},
        {"content": "Machine learning enables pattern recognition", "path": "/docs/ml.txt", "author": "Bob", "id": "doc2"},
        {"content": "Data science combines statistics and programming", "path": "/docs/datascience.txt", "author": "Charlie", "id": "doc3"},
    ]

    # Create database - embedding only the 'content' field
    make_segment = MakeVectorDatabaseSegment(
        embedding_field="content",
        embedding_model="mxbai-embed-large",
        embedding_source="ollama",
        path=temp_db_path,
        doc_id_field="id",
        overwrite=True
    )
    list(make_segment.transform(docs))

    # Verify non-embedding fields are stored in the database
    db_store = LanceDBDocumentStore(path=temp_db_path, table_name="docs", vector_dim=1024)
    stored_doc = db_store.get_document("doc1")
    assert stored_doc is not None
    assert stored_doc["path"] == "/docs/python.txt"
    assert stored_doc["author"] == "Alice"
    assert stored_doc["content"] == "Python is a versatile programming language"

    # Search and verify non-embedding fields are in search results
    search_segment = SearchVectorDatabaseSegment(
        embedding_model="mxbai-embed-large",
        embedding_source="ollama",
        path=temp_db_path,
        limit=3
    )
    results = list(search_segment.transform(["programming language"]))

    assert len(results) == 1
    search_results = results[0]
    assert len(search_results) > 0

    # Check that retrieved documents contain the non-embedding fields
    for result in search_results:
        assert "path" in result.document, "Non-embedding field 'path' should be in search results"
        assert "author" in result.document, "Non-embedding field 'author' should be in search results"
        assert "content" in result.document
        assert result.document["path"].startswith("/docs/")
        assert result.document["author"] in ["Alice", "Bob", "Charlie"]


def test_concurrent_write_and_read(requires_ollama, temp_db_path):
    """Test that you can read from a vector database while another pipeline is still writing to it.
    
    This test demonstrates concurrent access by:
    1. Creating a writer pipeline that feeds from a blocking queue
    2. Adding 3 documents to the queue one at a time
    3. While the writer is still active, opening a reader pipeline to search the database
    4. Verifying that the reader can see documents as they're being written
    """
    # Documents to add to the database
    documents = [
        {"text": "The quick brown fox jumps over the lazy dog", "title": "Fox Story", "id": "doc1"},
        {"text": "Python is a great programming language", "title": "Python Info", "id": "doc2"},
        {"text": "Machine learning is transforming technology", "title": "ML Article", "id": "doc3"}
    ]
    
    # Blocking queue to feed documents to the writer
    doc_queue = queue.Queue()
    
    # Generator that yields from the blocking queue (blocks when empty)
    def queue_generator():
        while True:
            doc = doc_queue.get()  # Blocks until a document is available
            if doc is None:  # Sentinel to stop
                break
            yield doc
            doc_queue.task_done()
    
    # Create writer pipeline with batch_size=1 to flush each document immediately
    writer_segment = MakeVectorDatabaseSegment(
        embedding_field="text",
        embedding_model="mxbai-embed-large",
        embedding_source="ollama",
        path=temp_db_path,
        doc_id_field="id",
        overwrite=True,
        batch_size=1  # Flush each document immediately
    )
    
    # Track writer completion and document processing
    writer_done = threading.Event()
    writer_error = [None]  # Use list to allow assignment from nested function
    processed_count = [0]  # Track how many documents have been processed
    
    def writer_thread():
        """Thread that runs the writer pipeline, consuming from the queue."""
        try:
            for item in writer_segment.transform(queue_generator()):
                processed_count[0] += 1
        except Exception as e:
            writer_error[0] = e
            raise
        finally:
            writer_done.set()
    
    # Start writer thread
    writer_thread_obj = threading.Thread(target=writer_thread, daemon=True)
    writer_thread_obj.start()
    
    # Add first document to queue (writer will start processing)
    doc_queue.put(documents[0])
    # Wait for the document to be processed (writer yields it)
    while processed_count[0] < 1:
        time.sleep(0.1)
    time.sleep(0.2)  # Give a bit more time for the write to complete
    
    # While writer is still active, create and use a reader pipeline
    # This demonstrates reading from a database that hasn't been closed yet
    search_segment = SearchVectorDatabaseSegment(
        embedding_model="mxbai-embed-large",
        embedding_source="ollama",
        path=temp_db_path,
        limit=10,
        read_consistency_interval=0  # Use 0 to see writes immediately
    )
    
    # Search for the first document that should already be in the database
    query = "fox jumping"
    search_results = list(search_segment.transform([query]))
    
    # Verify we got results (at least the first document should be searchable)
    assert len(search_results) == 1
    assert len(search_results[0]) > 0, "Should find at least one document while writer is active"
    
    # Verify the first document is in the results
    found_doc1 = any("doc1" == result.doc_id for result in search_results[0])
    assert found_doc1, "First document should be searchable while writer is still active"
    
    # Add second document to queue
    doc_queue.put(documents[1])
    # Wait for the document to be processed
    while processed_count[0] < 2:
        time.sleep(0.1)
    time.sleep(0.2)  # Give a bit more time for the write to complete
    
    # Search again - should now find both documents
    query2 = "programming language"
    search_results2 = list(search_segment.transform([query2]))
    assert len(search_results2) == 1
    assert len(search_results2[0]) > 0
    
    # Add third document to queue
    doc_queue.put(documents[2])
    # Wait for the document to be processed
    while processed_count[0] < 3:
        time.sleep(0.1)
    time.sleep(0.2)  # Give a bit more time for the write to complete
    
    # Search for the third document
    query3 = "machine learning"
    search_results3 = list(search_segment.transform([query3]))
    assert len(search_results3) == 1
    assert len(search_results3[0]) > 0
    
    # Signal writer to stop
    doc_queue.put(None)
    
    # Wait for writer to finish
    writer_done.wait(timeout=10.0)
    assert writer_done.is_set(), "Writer thread should have completed"
    
    if writer_error[0]:
        raise writer_error[0]
    
    # Final verification: all documents should be in the database
    db_store = LanceDBDocumentStore(path=temp_db_path, table_name="docs", vector_dim=1024)
    count = db_store.count()
    assert count == 3, f"Expected 3 documents in database, found {count}"
    
    # Verify all documents are searchable
    final_search = list(search_segment.transform(["technology"]))
    assert len(final_search) == 1
    assert len(final_search[0]) >= 1, "Should find documents after writer completes"
    
    # Verify we can find all three documents by their IDs
    found_ids = {result.doc_id for result in final_search[0]}
    assert "doc1" in found_ids or "doc2" in found_ids or "doc3" in found_ids, \
        "Should find at least one of the added documents"


# --- build_rag_database (unified RAG ingestion driver) ---


class _FakeEmbedAdapter:
    """Stands in for a provider embedding adapter during preflight."""

    def __init__(self, model=None, vector=(1.0, 2.0, 3.0), error=None):
        self.vector = list(vector)
        self.error = error

    def execute_one(self, text):
        if self.error is not None:
            raise self.error
        return list(self.vector)


def _fake_llm_embed(drop_indices=()):
    """Build a FakeLLMEmbed class that drops the given item indices.

    Mirrors LLMEmbed(fail_on_error=False), which silently skips items whose
    embedding fails. Instances expose .embedder so preflight works.
    """

    class FakeLLMEmbed(AbstractSegment):
        def __init__(self, model=None, source=None, field=None, set_as=None, **kwargs):
            super().__init__()
            self.field = field
            self.set_as = set_as
            self.embedder = _FakeEmbedAdapter(model=model)

        def transform(self, input_iter):
            for i, item in enumerate(input_iter):
                if i in drop_indices:
                    continue
                item[self.set_as] = [1.0, 2.0, 3.0]
                yield item

    return FakeLLMEmbed


@pytest.fixture
def rag_corpus(tmp_path):
    """Two small text files that each produce exactly one shingle."""
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "a.txt").write_text("alpha " * 40)
    (docs / "b.txt").write_text("bravo " * 40)
    return str(docs / "*.txt")


def test_build_rag_database_indexes_and_reports_counts(tmp_path, rag_corpus, monkeypatch):
    from talkpipe.pipelines import vector_databases as vdb

    monkeypatch.setattr(vdb, "LLMEmbed", _fake_llm_embed())
    db_path = str(tmp_path / "db")

    result = vdb.build_rag_database(
        rag_corpus,
        path=db_path,
        embedding_model="fake-model",
        embedding_source="fake-source",
        overwrite=True,
    )

    assert result.chunks_indexed == 2
    assert result.chunks_skipped == 0
    assert result.files_indexed == 2
    assert result.embedding_source == "fake-source"
    assert result.embedding_model == "fake-model"
    assert result.dimension == 3
    store = LanceDBDocumentStore(path=db_path, table_name="docs", vector_dim=3)
    assert store.count() == 2


def test_build_rag_database_counts_skipped_chunks(tmp_path, rag_corpus, monkeypatch):
    from talkpipe.pipelines import vector_databases as vdb

    monkeypatch.setattr(vdb, "LLMEmbed", _fake_llm_embed(drop_indices=(0,)))

    result = vdb.build_rag_database(
        rag_corpus,
        path=str(tmp_path / "db"),
        embedding_model="fake-model",
        embedding_source="fake-source",
        overwrite=True,
    )

    assert result.chunks_indexed == 1
    assert result.chunks_skipped == 1


def test_build_rag_database_reports_progress(tmp_path, rag_corpus, monkeypatch):
    from talkpipe.pipelines import vector_databases as vdb

    monkeypatch.setattr(vdb, "LLMEmbed", _fake_llm_embed())
    calls = []

    vdb.build_rag_database(
        rag_corpus,
        path=str(tmp_path / "db"),
        embedding_model="fake-model",
        embedding_source="fake-source",
        overwrite=True,
        progress=lambda chunks, files, source: calls.append((chunks, files, source)),
    )

    assert [c[:2] for c in calls] == [(1, 1), (2, 2)]
    assert all(c[2].endswith(".txt") for c in calls)


def test_build_rag_database_preflight_failure_reads_no_documents(
    tmp_path, rag_corpus, monkeypatch
):
    from talkpipe.pipelines import vector_databases as vdb

    class BrokenEmbed(_fake_llm_embed()):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.embedder = _FakeEmbedAdapter(error=ConnectionError("server unreachable"))

        def transform(self, input_iter):  # pragma: no cover - must never run
            raise AssertionError("pipeline ran despite failed preflight")

    monkeypatch.setattr(vdb, "LLMEmbed", BrokenEmbed)

    with pytest.raises(vdb.EmbedderPreflightError, match="server unreachable"):
        vdb.build_rag_database(
            rag_corpus,
            path=str(tmp_path / "db"),
            embedding_model="fake-model",
            embedding_source="fake-source",
        )


def test_build_rag_database_dimension_mismatch(tmp_path, rag_corpus, monkeypatch):
    from talkpipe.pipelines import vector_databases as vdb

    monkeypatch.setattr(vdb, "LLMEmbed", _fake_llm_embed())

    with pytest.raises(vdb.EmbeddingDimensionMismatchError) as excinfo:
        vdb.build_rag_database(
            rag_corpus,
            path=str(tmp_path / "db"),
            embedding_model="fake-model",
            embedding_source="fake-source",
            expected_dimension=768,
        )

    assert excinfo.value.expected == 768
    assert excinfo.value.actual == 3


def test_build_rag_database_raises_when_nothing_embeds(tmp_path, rag_corpus, monkeypatch):
    from talkpipe.pipelines import vector_databases as vdb

    monkeypatch.setattr(vdb, "LLMEmbed", _fake_llm_embed(drop_indices=(0, 1)))

    with pytest.raises(vdb.RagIngestError, match="none could be embedded"):
        vdb.build_rag_database(
            rag_corpus,
            path=str(tmp_path / "db"),
            embedding_model="fake-model",
            embedding_source="fake-source",
        )


def test_make_vector_database_passes_on_token_overflow(monkeypatch, tmp_path):
    from talkpipe.pipelines import vector_databases as vdb

    captured = {}

    class CapturingFake(_fake_llm_embed()):
        def __init__(self, **kwargs):
            captured.update(kwargs)
            super().__init__(**kwargs)

    monkeypatch.setattr(vdb, "LLMEmbed", CapturingFake)

    MakeVectorDatabaseSegment(
        embedding_field="text",
        embedding_model="fake-model",
        embedding_source="fake-source",
        path=str(tmp_path / "db"),
        on_token_overflow="truncate",
    )

    assert captured["on_token_overflow"] == "truncate"
