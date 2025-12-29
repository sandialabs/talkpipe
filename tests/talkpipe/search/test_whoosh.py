import os
import shutil
import tempfile
import uuid
import pytest
from unittest import mock
from talkpipe.util.data_manipulation import toDict
from talkpipe.search.whoosh import WhooshFullTextIndex, indexWhoosh, searchWhoosh
from talkpipe.search.abstract import SearchResult
from talkpipe.chatterlang import compile
from talkpipe.search.whoosh import WhooshWriter, WhooshSearcher, WhooshIndexError
from talkpipe.pipe.metadata import Flush


@pytest.fixture
def temp_index_dir():
    dirpath = tempfile.mkdtemp()
    yield dirpath
    shutil.rmtree(dirpath)

@pytest.fixture
def index_fields():
    return ["title", "content"]

@pytest.fixture
def sample_docs():
    return [
        {"doc_id": str(uuid.uuid4()), "title": "Hello World", "content": "This is a test document."},
        {"doc_id": str(uuid.uuid4()), "title": "Another Doc", "content": "More content here."},
        {"doc_id": str(uuid.uuid4()), "title": "Python", "content": "Python is great for testing."},
    ]

def test_create_index_and_add_document(temp_index_dir, index_fields, sample_docs):
    with WhooshFullTextIndex(temp_index_dir, index_fields) as idx:
        for doc in sample_docs:
            idx.add_document(doc)
    # Reopen and search
    idx = WhooshFullTextIndex(temp_index_dir, index_fields)
    results = idx.text_search("Python")
    assert any("Python" in r.document["title"] for r in results)
    idx.clear()

def test_search_returns_expected_results(temp_index_dir, index_fields, sample_docs):
    with WhooshFullTextIndex(temp_index_dir, index_fields) as idx:
        for doc in sample_docs:
            idx.add_document(doc)
    idx = WhooshFullTextIndex(temp_index_dir, index_fields)
    results = idx.text_search("test")
    assert any("test" in r.document["content"] for r in results)
    assert all(isinstance(r, SearchResult) for r in results)

def test_add_document_without_doc_id(temp_index_dir, index_fields):
    doc = {"title": "No ID", "content": "Should auto-generate doc_id"}
    with WhooshFullTextIndex(temp_index_dir, index_fields) as idx:
        idx.add_document(doc)
    idx = WhooshFullTextIndex(temp_index_dir, index_fields)
    results = idx.text_search("No ID")
    assert len(results) == 1
    assert results[0].doc_id is not None

def test_clear_removes_all_documents(temp_index_dir, index_fields, sample_docs):
    with WhooshFullTextIndex(temp_index_dir, index_fields) as idx:
        for doc in sample_docs:
            idx.add_document(doc)
        idx.clear()
    idx = WhooshFullTextIndex(temp_index_dir, index_fields)
    results = idx.text_search("test")
    assert len(results) == 0

def test_schema_mismatch_raises(temp_index_dir, index_fields, sample_docs):
    with WhooshFullTextIndex(temp_index_dir, index_fields) as idx:
        idx.add_document(sample_docs[0])
    # Try to open with different fields
    with pytest.raises(WhooshIndexError):
        WhooshFullTextIndex(temp_index_dir, ["title", "body"])

def test_context_manager_commits(temp_index_dir, index_fields):
    doc = {"title": "Commit Test", "content": "Check commit on exit"}
    with WhooshFullTextIndex(temp_index_dir, index_fields) as idx:
        idx.add_document(doc)
    idx = WhooshFullTextIndex(temp_index_dir, index_fields)
    results = idx.text_search("Commit")
    assert len(results) == 1

def test_add_document_outside_context(temp_index_dir, index_fields):
    idx = WhooshFullTextIndex(temp_index_dir, index_fields)
    doc = {"title": "Outside", "content": "Added outside context"}
    idx.add_document(doc)
    results = idx.text_search("Outside")
    assert len(results) == 1

def test_search_specific_field(temp_index_dir, index_fields, sample_docs):
    with WhooshFullTextIndex(temp_index_dir, index_fields) as idx:
        for doc in sample_docs:
            idx.add_document(doc)
    idx = WhooshFullTextIndex(temp_index_dir, index_fields)
    # Search in a specific field
    results = idx.text_search("title:another")
    assert len(results) == 1
    assert results[0].document["title"] == "Another Doc"
    results = idx.text_search("title:test")
    assert len(results) == 0

class SomeDataClass:
    def __init__(self, title, content, value):
        self.title = title
        self.content = content
        self.value = value

def test_indexWhoosh(temp_index_dir):
    data = [
        SomeDataClass("Doc 1", "Content for doc 1", 42),
        SomeDataClass("Doc 2", "Content for doc 2", 100),
        SomeDataClass("Doc 3", "Content for doc 3", 7),
    ]
    f = compile(f"""| indexWhoosh[field_list="title,content,value", index_path="{temp_index_dir}"]""")
    results = list(f(data))
    assert len(results) == len(data)

    idx = WhooshFullTextIndex(temp_index_dir, ["title", "content", "value"])
    search_results = idx.text_search("Content")
    assert len(search_results) == 3
    assert all(isinstance(r, SearchResult) for r in search_results)

    f = compile(f"""| indexWhoosh[field_list="title,content,value", index_path="{temp_index_dir}", yield_doc=True]""")
    results = list(f(data))
    assert len(results) == len(data)
    assert all([isinstance(r, dict) for r in results])

def test_searchWhoosh(temp_index_dir):
    data = [
        {"doc_id": str(uuid.uuid4()), "title": "Test Search 1", "content": "This is a test document."},
        {"doc_id": str(uuid.uuid4()), "title": "Test Search 2", "content": "Another test document."},
        {"doc_id": str(uuid.uuid4()), "title": "Python Search", "content": "Python is great for testing."},
    ]
    f = compile(f"""| indexWhoosh[field_list="title,content", index_path="{temp_index_dir}"]""")
    list(f(data))  # Index the documents

    # Test searching with yield_doc=True
    f = compile(f"""| searchWhoosh[index_path="{temp_index_dir}"]""")
    indexed_docs = list(f(["another"]))
    assert len(indexed_docs) == 1
    assert indexed_docs[0].document["title"] == "Test Search 2"

def test_WhooshWriter_context_manager(temp_index_dir, index_fields, sample_docs):
    # Use context manager to add documents
    with WhooshWriter(temp_index_dir, index_fields) as idx:
        for doc in sample_docs:
            idx.add_document(doc)
        # Writer should be active inside context
        assert idx.writer is not None
    # Writer should be None after context
    assert idx.writer is None
    # Documents should be committed
    idx2 = WhooshFullTextIndex(temp_index_dir, index_fields)
    results = idx2.text_search("Python")
    assert any("Python" in r.document["title"] for r in results)

def test_WhooshWriter_commit_and_rollback(temp_index_dir, index_fields):
    # Test that commit happens on normal exit
    with WhooshWriter(temp_index_dir, index_fields) as idx:
        idx.add_document({"title": "CommitDoc", "content": "Should be committed"})
    
    idx2 = WhooshFullTextIndex(temp_index_dir, index_fields)
    results = idx2.text_search("CommitDoc")
    assert len(results) == 1  # ✓ Should pass
    
    # Test that rollback happens if exception is raised
    try:
        with WhooshWriter(temp_index_dir, index_fields) as idx:
            idx.add_document({"title": "ExceptionDoc", "content": "Should NOT be committed"})
            raise RuntimeError("Force exit")
    except RuntimeError as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"Expected RuntimeError during test rollback verification: {e}")
    
    idx3 = WhooshFullTextIndex(temp_index_dir, index_fields)
    results = idx3.text_search("ExceptionDoc")
    assert len(results) == 0  # ✓ Should be rolled back

def test_WhooshSearcher_context_manager(temp_index_dir, index_fields, sample_docs):
    # Add docs first
    idx = WhooshFullTextIndex(temp_index_dir, index_fields)
    for doc in sample_docs:
        idx.add_document(doc)
    # Use WhooshSearcher to search
    with WhooshSearcher(temp_index_dir) as idx_search:
        results = idx_search.text_search("World")
        assert any("World" in r.document["title"] for r in results)
        # Index should be open inside context
        assert hasattr(idx_search, "idx")
        assert hasattr(idx_search.idx, "ix")
        assert idx_search.idx.ix is not None

def test_WhooshWriter_and_WhooshSearcher_integration(temp_index_dir, index_fields):
    docs = [
        {"title": "Integration1", "content": "First doc"},
        {"title": "Integration2", "content": "Second doc"},
    ]
    with WhooshWriter(temp_index_dir, index_fields) as idx:
        for doc in docs:
            idx.add_document(doc)
    with WhooshSearcher(temp_index_dir) as idx_search:
        results = idx_search.text_search("Integration*")
        assert len(results) == 2
        titles = [r.document["title"] for r in results]
        assert "Integration1" in titles and "Integration2" in titles


# Additional tests to increase coverage


def test_create_index_without_fields_raises_error(temp_index_dir):
    """Test that creating a new index without specifying fields raises an error."""
    with pytest.raises(WhooshIndexError, match="Fields must be provided"):
        WhooshFullTextIndex(temp_index_dir, fields=None)


def test_get_document(temp_index_dir, index_fields):
    """Test get_document method."""
    doc_id = str(uuid.uuid4())
    doc = {"doc_id": doc_id, "title": "GetTest", "content": "Content for retrieval"}

    with WhooshFullTextIndex(temp_index_dir, index_fields) as idx:
        idx.add_document(doc, doc_id)

    idx = WhooshFullTextIndex(temp_index_dir, index_fields)
    retrieved = idx.get_document(doc_id)
    assert retrieved is not None
    assert retrieved["title"] == "GetTest"
    assert retrieved["content"] == "Content for retrieval"


def test_get_document_not_found(temp_index_dir, index_fields):
    """Test get_document returns None for non-existent document."""
    idx = WhooshFullTextIndex(temp_index_dir, index_fields)
    result = idx.get_document("nonexistent-id")
    assert result is None


def test_update_document(temp_index_dir, index_fields):
    """Test update_document method."""
    doc_id = str(uuid.uuid4())
    doc = {"doc_id": doc_id, "title": "Original", "content": "Original content"}

    with WhooshFullTextIndex(temp_index_dir, index_fields) as idx:
        idx.add_document(doc, doc_id)

    idx = WhooshFullTextIndex(temp_index_dir, index_fields)
    # Update the document
    success = idx.update_document(doc_id, {"title": "Updated", "content": "Updated content"})
    assert success is True

    # Verify update
    updated = idx.get_document(doc_id)
    assert updated["title"] == "Updated"
    assert updated["content"] == "Updated content"


def test_update_nonexistent_document(temp_index_dir, index_fields):
    """Test updating a document that doesn't exist returns False."""
    idx = WhooshFullTextIndex(temp_index_dir, index_fields)
    success = idx.update_document("nonexistent-id", {"title": "Won't work", "content": "Nope"})
    assert success is False


def test_delete_document(temp_index_dir, index_fields):
    """Test delete_document method."""
    doc_id = str(uuid.uuid4())
    doc = {"doc_id": doc_id, "title": "ToDelete", "content": "Will be deleted"}

    with WhooshFullTextIndex(temp_index_dir, index_fields) as idx:
        idx.add_document(doc, doc_id)

    idx = WhooshFullTextIndex(temp_index_dir, index_fields)
    # Verify document exists
    assert idx.get_document(doc_id) is not None

    # Delete it
    success = idx.delete_document(doc_id)
    assert success is True

    # Verify it's gone
    assert idx.get_document(doc_id) is None


def test_upsert_document_new(temp_index_dir, index_fields):
    """Test upsert_document with a new document."""
    doc_id = str(uuid.uuid4())
    doc = {"title": "New Upsert", "content": "New content"}

    idx = WhooshFullTextIndex(temp_index_dir, index_fields)
    result_id = idx.upsert_document(doc, doc_id)
    assert result_id == doc_id

    # Verify it was added
    retrieved = idx.get_document(doc_id)
    assert retrieved is not None
    assert retrieved["title"] == "New Upsert"


def test_upsert_document_existing(temp_index_dir, index_fields):
    """Test upsert_document with an existing document."""
    doc_id = str(uuid.uuid4())
    doc = {"title": "Original Upsert", "content": "Original"}

    with WhooshFullTextIndex(temp_index_dir, index_fields) as idx:
        idx.add_document(doc, doc_id)

    idx = WhooshFullTextIndex(temp_index_dir, index_fields)
    # Upsert with new content
    updated_doc = {"title": "Updated Upsert", "content": "Updated"}
    result_id = idx.upsert_document(updated_doc, doc_id)
    assert result_id == doc_id

    # Verify it was updated
    retrieved = idx.get_document(doc_id)
    assert retrieved["title"] == "Updated Upsert"


def test_upsert_document_without_id(temp_index_dir, index_fields):
    """Test upsert_document without providing an ID generates one."""
    doc = {"title": "Auto ID Upsert", "content": "Content"}

    idx = WhooshFullTextIndex(temp_index_dir, index_fields)
    result_id = idx.upsert_document(doc)
    assert result_id is not None

    # Verify it was added
    retrieved = idx.get_document(result_id)
    assert retrieved is not None


def test_invalid_query_syntax(temp_index_dir, index_fields, sample_docs):
    """Test that invalid query syntax is handled gracefully."""
    with WhooshFullTextIndex(temp_index_dir, index_fields) as idx:
        for doc in sample_docs:
            idx.add_document(doc)

    idx = WhooshFullTextIndex(temp_index_dir, index_fields)
    # Use an invalid query (unclosed quote)
    results = idx.text_search('title:"unclosed')
    # Should return empty list instead of raising an error
    assert results == []


def test_WhooshWriter_with_overwrite(temp_index_dir, index_fields):
    """Test WhooshWriter with overwrite=True."""
    # Create initial data
    with WhooshWriter(temp_index_dir, index_fields) as idx:
        idx.add_document({"title": "Initial", "content": "Will be cleared"})

    # Reopen with overwrite
    with WhooshWriter(temp_index_dir, index_fields, overwrite=True) as idx:
        idx.add_document({"title": "New Start", "content": "After overwrite"})

    # Verify only new document exists
    idx = WhooshFullTextIndex(temp_index_dir, index_fields)
    results = idx.text_search("Initial")
    assert len(results) == 0
    results = idx.text_search("New Start")
    assert len(results) == 1


def test_WhooshWriter_periodic_commit(temp_index_dir, index_fields):
    """Test WhooshWriter with periodic commits."""
    import time

    # Use a very short commit interval
    with WhooshWriter(temp_index_dir, index_fields, commit_seconds=0.1) as idx:
        idx.add_document({"title": "Doc1", "content": "First"})
        time.sleep(0.15)  # Wait for commit interval to pass
        idx.add_document({"title": "Doc2", "content": "Second"})

    # Verify both documents were indexed
    idx = WhooshFullTextIndex(temp_index_dir, index_fields)
    results = idx.text_search("Doc1 OR Doc2")
    assert len(results) == 2


def test_WhooshWriter_wrapper_delegation(temp_index_dir, index_fields):
    """Test that WriterWrapper delegates attributes to the index."""
    with WhooshWriter(temp_index_dir, index_fields) as idx:
        # Access an attribute that should be delegated
        assert hasattr(idx, 'fields')
        assert idx.fields == index_fields


def test_WhooshSearcher_periodic_reload(temp_index_dir, index_fields):
    """Test WhooshSearcher with periodic reload."""
    import time

    # Create initial index
    with WhooshWriter(temp_index_dir, index_fields) as idx:
        idx.add_document({"title": "Initial", "content": "First batch"})

    # Search with short reload interval
    with WhooshSearcher(temp_index_dir, reload_seconds=0.1) as searcher:
        results1 = searcher.text_search("Initial")
        assert len(results1) == 1

        # Add more documents outside the searcher
        with WhooshWriter(temp_index_dir, index_fields) as idx:
            idx.add_document({"title": "Added Later", "content": "Second batch"})

        time.sleep(0.15)  # Wait for reload interval

        # Search again - should pick up new document after reload
        results2 = searcher.text_search("Added Later")
        assert len(results2) == 1


def test_WhooshSearcher_wrapper_delegation(temp_index_dir, index_fields):
    """Test that SearcherWrapper delegates attributes to the index."""
    with WhooshWriter(temp_index_dir, index_fields) as idx:
        idx.add_document({"title": "Test", "content": "Content"})

    with WhooshSearcher(temp_index_dir) as searcher:
        # Access an attribute that should be delegated
        assert hasattr(searcher, 'fields')
        assert set(searcher.fields) == set(index_fields)


def test_indexWhoosh_continue_on_error(temp_index_dir):
    """Test indexWhoosh with continue_on_error=True."""
    # Create data with one item that will cause an error during str() conversion
    class BadItem:
        def __init__(self):
            self.title = "Bad"
            self.content = self  # This will cause infinite recursion or error during str()

        def __str__(self):
            raise ValueError("Cannot convert to string")

    data = [
        {"title": "Good1", "content": "Content 1"},
        BadItem(),  # This will fail during str() conversion
        {"title": "Good2", "content": "Content 2"},
    ]

    f = compile(f"""| indexWhoosh[field_list="title,content", index_path="{temp_index_dir}", continue_on_error=True]""")
    results = list(f(data))

    # Only good items are yielded (BadItem was skipped due to error)
    assert len(results) == 2

    # Verify only good documents were indexed (BadItem failed to index)
    idx = WhooshFullTextIndex(temp_index_dir, ["title", "content"])
    search_results = idx.text_search("Good1 OR Good2")
    assert len(search_results) == 2
    # Bad should not be in index
    bad_results = idx.text_search("Bad")
    assert len(bad_results) == 0


def test_indexWhoosh_stop_on_error(temp_index_dir):
    """Test indexWhoosh with continue_on_error=False."""
    class BadItem:
        def __init__(self):
            self.title = "Bad"
            self.content = self

        def __str__(self):
            raise ValueError("Cannot convert to string")

    data = [
        {"title": "Good1", "content": "Content 1"},
        BadItem(),  # This will fail and stop processing
        {"title": "Good2", "content": "Content 2"},
    ]

    f = compile(f"""| indexWhoosh[field_list="title,content", index_path="{temp_index_dir}", continue_on_error=False]""")

    # Should raise an error
    with pytest.raises(ValueError):
        list(f(data))


def test_searchWhoosh_with_set_as_and_all_results_at_once(temp_index_dir):
    """Test searchWhoosh with set_as parameter and all_results_at_once=True."""
    # Index some documents
    data = [
        {"title": "Test1", "content": "Python programming"},
        {"title": "Test2", "content": "Python testing"},
    ]
    f = compile(f"""| indexWhoosh[field_list="title,content", index_path="{temp_index_dir}"]""")
    list(f(data))

    # Search with set_as
    queries = [{"query": "Python"}]
    f = compile(f"""| searchWhoosh[index_path="{temp_index_dir}", field="query", set_as="results", all_results_at_once=True]""")
    results = list(f(queries))

    assert len(results) == 1
    assert "results" in results[0]
    assert len(results[0]["results"]) == 2


def test_searchWhoosh_set_as_without_all_results_at_once_raises_error(temp_index_dir):
    """Test that searchWhoosh raises error when set_as is used without all_results_at_once."""
    # Index a document
    data = [{"title": "Test", "content": "Content"}]
    f = compile(f"""| indexWhoosh[field_list="title,content", index_path="{temp_index_dir}"]""")
    list(f(data))

    # Try to use set_as without all_results_at_once (with continue_on_error=False to propagate the error)
    queries = [{"query": "Test"}]
    f = compile(f"""| searchWhoosh[index_path="{temp_index_dir}", field="query", set_as="results", all_results_at_once=False, continue_on_error=False]""")

    with pytest.raises(ValueError, match="set_as only works with this segment if all_results_at_once is True"):
        list(f(queries))


def test_searchWhoosh_continue_on_error(temp_index_dir):
    """Test searchWhoosh with continue_on_error=True."""
    # Index some documents
    data = [{"title": "Test", "content": "Content"}]
    f = compile(f"""| indexWhoosh[field_list="title,content", index_path="{temp_index_dir}"]""")
    list(f(data))

    # Search with one invalid query (unclosed quote) and one valid
    queries = ['title:"unclosed', "Test"]
    f = compile(f"""| searchWhoosh[index_path="{temp_index_dir}", continue_on_error=True]""")
    results = list(f(queries))

    # Should get results for the valid query
    assert len(results) > 0


def test_searchWhoosh_stop_on_error(temp_index_dir):
    """Test searchWhoosh with continue_on_error=False."""
    # Create an index path that doesn't exist
    nonexistent_path = os.path.join(temp_index_dir, "nonexistent")

    queries = ["Test"]
    f = compile(f"""| searchWhoosh[index_path="{nonexistent_path}", continue_on_error=False]""")

    # Should raise an error
    with pytest.raises(Exception):
        list(f(queries))


def test_searchWhoosh_yield_from_results(temp_index_dir):
    """Test searchWhoosh with all_results_at_once=False and no set_as (yield from results)."""
    # Index some documents
    data = [
        {"title": "Python1", "content": "Python programming"},
        {"title": "Python2", "content": "Python testing"},
    ]
    f = compile(f"""| indexWhoosh[field_list="title,content", index_path="{temp_index_dir}"]""")
    list(f(data))

    # Search with all_results_at_once=False and no set_as - should yield individual results
    f = compile(f"""| searchWhoosh[index_path="{temp_index_dir}", all_results_at_once=False]""")
    results = list(f(["Python"]))

    # Should get individual SearchResult objects, not lists
    assert len(results) == 2
    assert all(isinstance(r, SearchResult) for r in results)


def test_searchWhoosh_all_results_at_once_without_set_as(temp_index_dir):
    """Test searchWhoosh with all_results_at_once=True but no set_as (yield list of results)."""
    # Index some documents
    data = [
        {"title": "Test1", "content": "Content 1"},
        {"title": "Test2", "content": "Content 2"},
    ]
    f = compile(f"""| indexWhoosh[field_list="title,content", index_path="{temp_index_dir}"]""")
    list(f(data))

    # Search with all_results_at_once=True but no set_as
    f = compile(f"""| searchWhoosh[index_path="{temp_index_dir}", all_results_at_once=True]""")
    results = list(f(["Test"]))

    # Should get a list containing one list of SearchResults
    assert len(results) == 1
    assert isinstance(results[0], list)
    assert all(isinstance(r, SearchResult) for r in results[0])


def test_indexWhoosh_handles_flush_events(temp_index_dir):
    """Test that indexWhoosh commits the index on Flush events."""
    data = [
        {"title": "Doc 1", "content": "Content 1"},
        Flush(),  # Flush event should trigger commit
        {"title": "Doc 2", "content": "Content 2"},
    ]
    
    f = indexWhoosh(index_path=temp_index_dir, field_list="title,content")
    results = list(f(data))
    
    # Should yield only the original items (Flush is consumed)
    assert len(results) == 2
    assert results[0]["title"] == "Doc 1"
    assert results[1]["title"] == "Doc 2"
    
    # Verify both documents were indexed (commit happened on Flush)
    idx = WhooshFullTextIndex(temp_index_dir, ["title", "content"])
    search_results = idx.text_search("Content")
    assert len(search_results) == 2


def test_indexWhoosh_flush_triggers_commit(temp_index_dir):
    """Test that Flush events trigger commit in indexWhoosh."""
    # Use mock to verify commit is called
    with mock.patch('talkpipe.search.whoosh.WhooshWriter') as mock_writer_class:
        mock_writer = mock.Mock()
        mock_writer_class.return_value.__enter__.return_value = mock_writer
        mock_writer.add_document.return_value = "doc_id"
        
        data = [{"title": "Test", "content": "Content"}, Flush()]
        f = indexWhoosh(index_path=temp_index_dir, field_list="title,content")
        list(f(data))
        
        # Verify commit was called on Flush
        assert mock_writer.commit.called


def test_searchWhoosh_handles_flush_events(temp_index_dir):
    """Test that searchWhoosh reloads the index on Flush events."""
    # Index some documents first
    data = [
        {"title": "Initial Doc", "content": "Initial content"},
    ]
    f = indexWhoosh(index_path=temp_index_dir, field_list="title,content")
    list(f(data))
    
    # Search with a Flush event
    queries = ["Initial", Flush(), "Initial"]
    f = searchWhoosh(index_path=temp_index_dir)
    results = list(f(queries))
    
    # Should yield only search results (Flush is consumed)
    assert len(results) == 2  # Two searches, both should return results
    assert all(isinstance(r, SearchResult) for r in results)


def test_searchWhoosh_flush_triggers_reload(temp_index_dir):
    """Test that Flush events trigger reload in searchWhoosh."""
    # Index a document
    data = [{"title": "Test", "content": "Content"}]
    f = indexWhoosh(index_path=temp_index_dir, field_list="title,content")
    list(f(data))
    
    # Use mock to verify reload is called
    with mock.patch('talkpipe.search.whoosh.WhooshSearcher') as mock_searcher_class:
        mock_searcher = mock.Mock()
        mock_searcher.text_search.return_value = [SearchResult(doc_id="1", score=1.0, document={"title": "Test"})]
        mock_searcher_class.return_value.__enter__.return_value = mock_searcher
        
        queries = ["Test", Flush()]
        f = searchWhoosh(index_path=temp_index_dir)
        list(f(queries))
        
        # Verify reload was called on Flush
        assert mock_searcher.reload.called


def test_indexWhoosh_flush_integration_with_search(temp_index_dir):
    """Test that indexWhoosh Flush events make documents searchable immediately."""
    # Index documents with Flush in the middle
    data = [
        {"title": "Before Flush", "content": "First document"},
        Flush(),  # This should commit, making the document searchable
        {"title": "After Flush", "content": "Second document"},
    ]
    
    f = indexWhoosh(index_path=temp_index_dir, field_list="title,content")
    list(f(data))
    
    # Search - both documents should be found (Flush committed the first one)
    idx = WhooshFullTextIndex(temp_index_dir, ["title", "content"])
    results1 = idx.text_search("Before Flush")
    results2 = idx.text_search("After Flush")
    
    assert len(results1) == 1
    assert len(results2) == 1


def test_indexWhoosh_flush_makes_documents_searchable_immediately(temp_index_dir):
    """Test that without Flush, documents aren't searchable until context manager exits."""
    # Create a generator that we can control
    def document_generator():
        yield {"title": "FlushCommitted", "content": "UniqueContentXYZ123"}
        yield Flush()  # Commit here
        yield {"title": "NotYetCommitted", "content": "UniqueContentABC456"}
        # Don't yield anything else - we'll check before context manager exits
    
    f = indexWhoosh(index_path=temp_index_dir, field_list="title,content")
    
    # Process items one at a time to control when we check
    gen = f(document_generator())
    
    # Get the first item (FlushCommitted)
    first_result = next(gen)
    assert first_result["title"] == "FlushCommitted"
    
    # Get the Flush (consumed, not yielded)
    result2 = next(gen)
    assert result2["title"] == "NotYetCommitted"
    
    # At this point, "FlushCommitted" should be searchable (Flush committed it)
    # but "NotYetCommitted" should NOT be searchable yet (it's in the writer buffer)
    idx1 = WhooshFullTextIndex(temp_index_dir, ["title", "content"])
    committed_results = idx1.text_search("UniqueContentXYZ123")
    uncommitted_results = idx1.text_search("UniqueContentABC456")
    
    # The committed doc should be searchable after Flush
    assert len(committed_results) == 1, "Document should be searchable immediately after Flush commit"
    assert committed_results[0].document["title"] == "FlushCommitted"
    
    # The uncommitted doc should NOT be searchable yet (it's still in the writer buffer)
    assert len(uncommitted_results) == 0, "Document should NOT be searchable before context manager exits (no Flush)"
    
    # Finish the generator to commit everything
    try:
        list(gen)  # Exhaust the generator, which will commit on context exit
    except:
        pass
    
    # Now both should be searchable after context manager exits
    idx2 = WhooshFullTextIndex(temp_index_dir, ["title", "content"])
    final_committed = idx2.text_search("UniqueContentXYZ123")
    final_uncommitted = idx2.text_search("UniqueContentABC456")
    
    assert len(final_committed) == 1
    assert len(final_uncommitted) == 1


def test_indexWhoosh_flush_commit_visibility(temp_index_dir):
    """Test that Flush events make documents visible to separate searcher instances."""
    # Test mid-stream commit with Flush
    def controlled_indexing():
        yield {"title": "BeforeFlush", "content": "UniqueSearchTermDEF789"}
        yield Flush()  # This commits
        yield {"title": "AfterFlush", "content": "UniqueSearchTermGHI012"}
    
    f = indexWhoosh(index_path=temp_index_dir, field_list="title,content")
    gen = f(controlled_indexing())
    
    # Process first document
    result1 = next(gen)
    assert result1["title"] == "BeforeFlush"
    
    # Process Flush (consumed)
    result2 = next(gen)
    assert result2["title"] == "AfterFlush"
    
    # Now check with a separate searcher instance
    # "BeforeFlush" should be searchable (committed by Flush)
    # "AfterFlush" should NOT be searchable yet (in writer buffer, not committed)
    searcher = WhooshFullTextIndex(temp_index_dir, ["title", "content"])
    before_results = searcher.text_search("UniqueSearchTermDEF789")
    after_results = searcher.text_search("UniqueSearchTermGHI012")
    
    # The document committed by Flush should be searchable
    assert len(before_results) == 1, "Document should be searchable after Flush commit"
    assert before_results[0].document["title"] == "BeforeFlush"
    
    # The document after Flush should NOT be searchable yet (not committed)
    assert len(after_results) == 0, "Document should NOT be searchable before context manager exits (no Flush)"
    
    # Finish the generator to commit everything
    try:
        list(gen)
    except:
        pass
    
    # Now both should be searchable
    final_searcher = WhooshFullTextIndex(temp_index_dir, ["title", "content"])
    final_before = final_searcher.text_search("UniqueSearchTermDEF789")
    final_after = final_searcher.text_search("UniqueSearchTermGHI012")
    
    assert len(final_before) == 1
    assert len(final_after) == 1
