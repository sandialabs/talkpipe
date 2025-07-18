import os
import shutil
import tempfile
import uuid
import pytest
from talkpipe.util.data_manipulation import toDict
from talkpipe.search.whoosh import WhooshFullTextIndex, indexWhoosh
from talkpipe.search.abstract import SearchResult
from talkpipe.chatterlang import compile
from talkpipe.search.whoosh import WhooshWriter, WhooshSearcher, WhooshIndexError


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
    except RuntimeError:
        pass
    
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
