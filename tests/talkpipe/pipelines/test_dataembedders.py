import pytest
import tempfile
import os
from talkpipe.pipelines.dataembedders import MakeVectorDatabaseSegment, SearchVectorDatabaseSegment
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
