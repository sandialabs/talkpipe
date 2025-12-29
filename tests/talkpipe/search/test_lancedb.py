import pytest
from unittest import mock
import tempfile
import os
import time
from talkpipe.search.lancedb import search_lancedb, add_to_lancedb, LanceDBDocumentStore
from talkpipe.pipe.metadata import Flush


@pytest.fixture
def temp_db_path():
    with tempfile.TemporaryDirectory() as temp_dir:
        yield os.path.join(temp_dir, "test_db")


@pytest.fixture
def sample_items():
    return [
        {"vector": [1.0, 2.0, 3.0], "text": "first item"},
        {"vector": [4.0, 5.0, 6.0], "text": "second item"}
    ]

@pytest.fixture
def sample_items_direction_relevant():
    return [
        {"vector": [1.0, 0.0], "text": "first item"},
        {"vector": [1.0, 0.5], "text": "second item"},
        {"vector": [0.0, 1.0], "text": "third item"}
    ]

@pytest.fixture
def sample_search_results():
    from talkpipe.search.abstract import SearchResult
    return [
        SearchResult(score=0.9, doc_id="doc1", document={"text": "similar item"}),
        SearchResult(score=0.8, doc_id="doc2", document={"text": "another similar item"})
    ]


class TestSearchLanceDB:
    def test_search_lancedb_missing_path_raises_error(self, sample_items):
        with pytest.raises(ValueError, match="Both 'path' and 'table' parameters must be provided"):
            seg = search_lancedb(path=None, table_name="test_table")
            list(seg(sample_items))

    def test_search_lancedb_missing_table_raises_error(self, sample_items, temp_db_path):
        with pytest.raises(ValueError, match="Both 'path' and 'table' parameters must be provided"):
            seg = search_lancedb(path=temp_db_path, table_name=None)
            list(seg(sample_items))

    def test_search_lancedb_missing_both_raises_error(self, sample_items):
        with pytest.raises(ValueError, match="Both 'path' and 'table' parameters must be provided"):
            seg = search_lancedb(path=None, table_name=None)
            list(seg(sample_items))

    @mock.patch('talkpipe.search.lancedb.LanceDBDocumentStore')
    @mock.patch('talkpipe.search.lancedb.extract_property')
    def test_search_lancedb_with_field(self, mock_extract_property, mock_doc_store_class, sample_items, sample_search_results, temp_db_path):
        mock_doc_store = mock.Mock()
        mock_doc_store_class.return_value = mock_doc_store
        mock_doc_store.vector_search.return_value = sample_search_results
        mock_extract_property.return_value = [1.0, 2.0, 3.0]

        items_to_search = [sample_items[0]]  # Item with vector field
        seg = search_lancedb(path=temp_db_path, table_name="test_table", field="vector", limit=5)
        results = list(seg(items_to_search))

        mock_doc_store_class.assert_called_once_with(temp_db_path, "test_table", None, 10)
        mock_extract_property.assert_called_once_with(sample_items[0], "vector")
        mock_doc_store.vector_search.assert_called_once_with([1.0, 2.0, 3.0], 5)

        assert len(results) == 2
        assert results == sample_search_results

    @mock.patch('talkpipe.search.lancedb.LanceDBDocumentStore')
    def test_search_lancedb_without_field(self, mock_doc_store_class, sample_search_results, temp_db_path):
        mock_doc_store = mock.Mock()
        mock_doc_store_class.return_value = mock_doc_store
        mock_doc_store.vector_search.return_value = sample_search_results

        # Test with a raw vector (not from dict field)
        items_to_search = [[7.0, 8.0, 9.0]]
        seg = search_lancedb(path=temp_db_path, table_name="test_table", limit=3)
        results = list(seg(items_to_search))

        mock_doc_store_class.assert_called_once_with(temp_db_path, "test_table", None, 10)
        mock_doc_store.vector_search.assert_called_once_with([7.0, 8.0, 9.0], 3)

        assert len(results) == 2

    @mock.patch('talkpipe.search.lancedb.LanceDBDocumentStore')
    @mock.patch('talkpipe.search.lancedb.extract_property')
    def test_search_lancedb_all_results_at_once(self, mock_extract_property, mock_doc_store_class, sample_items, sample_search_results, temp_db_path):
        mock_doc_store = mock.Mock()
        mock_doc_store_class.return_value = mock_doc_store
        mock_doc_store.vector_search.return_value = sample_search_results
        mock_extract_property.return_value = [1.0, 2.0, 3.0]

        items_to_search = [sample_items[0]]
        seg = search_lancedb(path=temp_db_path, table_name="test_table",
                           field="vector", all_results_at_once=True)
        results = list(seg(items_to_search))

        # With all_results_at_once=True and no set_as, should yield the list of search results
        assert len(results) == 1
        assert results[0] == sample_search_results

    @mock.patch('talkpipe.search.lancedb.LanceDBDocumentStore')
    @mock.patch('talkpipe.search.lancedb.extract_property')
    def test_search_lancedb_set_as(self, mock_extract_property, mock_doc_store_class, sample_items, sample_search_results, temp_db_path):
        mock_doc_store = mock.Mock()
        mock_doc_store_class.return_value = mock_doc_store
        mock_doc_store.vector_search.return_value = sample_search_results
        mock_extract_property.return_value = [1.0, 2.0, 3.0]

        items_to_search = [sample_items[0].copy()]  # Make a copy to avoid modifying fixture
        seg = search_lancedb(path=temp_db_path, table_name="test_table",
                           field="vector", set_as="search_results", all_results_at_once=True)
        results = list(seg(items_to_search))

        assert "search_results" in items_to_search[0]
        assert items_to_search[0]["search_results"] == sample_search_results
        assert len(results) == 1  # Only yields the original item with search_results attached

    @mock.patch('talkpipe.search.lancedb.LanceDBDocumentStore')
    @mock.patch('talkpipe.search.lancedb.extract_property')
    def test_search_lancedb_multiple_items(self, mock_extract_property, mock_doc_store_class, sample_items, sample_search_results, temp_db_path):
        mock_doc_store = mock.Mock()
        mock_doc_store_class.return_value = mock_doc_store
        mock_doc_store.vector_search.return_value = sample_search_results
        mock_extract_property.side_effect = [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]]

        items_to_search = sample_items[:2]  # Two items with vector fields
        seg = search_lancedb(path=temp_db_path, table_name="test_table", field="vector")
        results = list(seg(items_to_search))

        assert mock_doc_store.vector_search.call_count == 2
        assert len(results) == 4  # 2 results per item * 2 items

    @mock.patch('talkpipe.search.lancedb.LanceDBDocumentStore')
    def test_search_lancedb_default_limit(self, mock_doc_store_class, sample_search_results, temp_db_path):
        mock_doc_store = mock.Mock()
        mock_doc_store_class.return_value = mock_doc_store
        mock_doc_store.vector_search.return_value = sample_search_results

        # Test with a raw vector to verify default limit
        items_to_search = [[7.0, 8.0, 9.0]]
        seg = search_lancedb(path=temp_db_path, table_name="test_table")
        list(seg(items_to_search))

        mock_doc_store.vector_search.assert_called_once_with([7.0, 8.0, 9.0], 10)  # Default limit


class TestAddToLanceDB:
    def test_add_to_lancedb_missing_path_raises_error(self, sample_items):
        with pytest.raises(ValueError, match="Both 'path' and 'table' parameters must be provided"):
            seg = add_to_lancedb(path=None, table_name="test_table")
            list(seg(sample_items))

    def test_add_to_lancedb_missing_table_raises_error(self, sample_items, temp_db_path):
        with pytest.raises(ValueError, match="Both 'path' and 'table' parameters must be provided"):
            seg = add_to_lancedb(path=temp_db_path, table_name=None)
            list(seg(sample_items))

    def test_add_to_lancedb_missing_both_raises_error(self, sample_items):
        with pytest.raises(ValueError, match="Both 'path' and 'table' parameters must be provided"):
            seg = add_to_lancedb(path=None, table_name=None)
            list(seg(sample_items))

    @mock.patch('talkpipe.search.lancedb.LanceDBDocumentStore')
    @mock.patch('talkpipe.search.lancedb.extract_property')
    def test_add_to_lancedb_with_vector_field(self, mock_extract_property, mock_doc_store_class, sample_items, temp_db_path):
        mock_doc_store = mock.Mock()
        mock_doc_store._get_table.return_value = [mock.Mock()]
        mock_doc_store_class.return_value = mock_doc_store
        mock_extract_property.return_value = [1.0, 2.0, 3.0]

        items_to_add = [sample_items[0]]  # Item with vector field
        seg = add_to_lancedb(path=temp_db_path, table_name="test_table", vector_field="vector")
        results = list(seg(items_to_add))

        mock_doc_store_class.assert_called_once_with(temp_db_path, "test_table", None)
        mock_extract_property.assert_called_once_with(sample_items[0], "vector", fail_on_missing=True)
        mock_doc_store.add_vectors.assert_called_once()

        assert len(results) == 1
        assert results[0]["_doc_id"] is not None

    @mock.patch('talkpipe.search.lancedb.LanceDBDocumentStore')
    @mock.patch('talkpipe.search.lancedb.extract_property')
    def test_add_to_lancedb_with_overwrite(self, mock_extract_property, mock_doc_store_class, sample_items, temp_db_path):
        mock_doc_store = mock.Mock()
        mock_doc_store._get_table.return_value = [mock.Mock()]
        mock_doc_store_class.return_value = mock_doc_store
        mock_doc_store.add_vector.return_value = "added_doc_id"
        mock_extract_property.return_value = [1.0, 2.0, 3.0]

        # Mock the database for overwrite functionality
        mock_db = mock.Mock()
        mock_doc_store._get_db.return_value = mock_db

        items_to_add = [sample_items[0]]
        seg = add_to_lancedb(path=temp_db_path, table_name="test_table",
                           vector_field="vector", overwrite=True)
        list(seg(items_to_add))

        # Verify that drop_table was called for overwrite
        mock_db.drop_table.assert_called_once_with("test_table")

    @mock.patch('talkpipe.search.lancedb.LanceDBDocumentStore')
    @mock.patch('talkpipe.search.lancedb.extract_property')
    def test_add_to_lancedb_yields_original_items(self, mock_extract_property, mock_doc_store_class, sample_items, temp_db_path):
        mock_doc_store = mock.Mock()
        mock_doc_store._get_table.return_value = [mock.Mock()]
        mock_doc_store_class.return_value = mock_doc_store
        mock_extract_property.side_effect = [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]]

        items_to_add = sample_items
        seg = add_to_lancedb(path=temp_db_path, table_name="test_table", vector_field="vector")
        results = list(seg(items_to_add))

        # Function should yield back the original items with _doc_id added
        assert len(results) == 2
        assert results[0]["_doc_id"] is not None
        assert results[1]["_doc_id"] is not None

    @mock.patch('talkpipe.search.lancedb.AdaptiveBuffer')
    @mock.patch('talkpipe.search.lancedb.LanceDBDocumentStore')
    @mock.patch('talkpipe.search.lancedb.extract_property')
    def test_add_to_lancedb_uses_adaptive_buffer(
        self,
        mock_extract_property,
        mock_doc_store_class,
        mock_adaptive_buffer,
        sample_items,
        temp_db_path,
    ):
        mock_doc_store = mock.Mock()
        mock_doc_store._get_table.return_value = [mock.Mock()]
        mock_doc_store_class.return_value = mock_doc_store
        mock_extract_property.return_value = [1.0, 2.0, 3.0]

        class FakeBuffer:
            def __init__(self):
                self.items = []

            def append(self, item):
                self.items.append(item)
                return None

            def flush(self):
                if not self.items:
                    return None
                items = self.items
                self.items = []
                return items

        buffer_instance = FakeBuffer()
        mock_adaptive_buffer.return_value = buffer_instance

        items_to_add = [sample_items[0]]
        seg = add_to_lancedb(path=temp_db_path, table_name="test_table",
                             vector_field="vector", batch_size=5)
        list(seg(items_to_add))

        mock_adaptive_buffer.assert_called_once_with(max_size=5)
        mock_doc_store.add_vectors.assert_called_once()
        added_batch = mock_doc_store.add_vectors.call_args[0][0]
        assert len(added_batch) == 1

    @mock.patch('talkpipe.search.lancedb.LanceDBDocumentStore')
    @mock.patch('talkpipe.search.lancedb.extract_property')
    @mock.patch('talkpipe.search.lancedb.AdaptiveBuffer')
    def test_add_to_lancedb_handles_flush_events(
        self,
        mock_adaptive_buffer,
        mock_extract_property,
        mock_doc_store_class,
        sample_items,
        temp_db_path,
    ):
        """Test that add_to_lancedb flushes buffer and optimizes on Flush events."""
        mock_doc_store = mock.Mock()
        mock_table = mock.Mock()
        mock_doc_store._get_table.return_value = [mock_table]
        mock_doc_store_class.return_value = mock_doc_store
        mock_extract_property.return_value = [1.0, 2.0, 3.0]

        # Create a fake buffer that tracks flush calls
        class FakeBuffer:
            def __init__(self):
                self.items = []

            def append(self, item):
                self.items.append(item)
                return None  # Never auto-flush, only manual flush

            def flush(self):
                if not self.items:
                    return None
                items = self.items
                self.items = []
                return items

        buffer_instance = FakeBuffer()
        mock_adaptive_buffer.return_value = buffer_instance

        # Add items with a Flush event in the middle
        items_with_flush = [sample_items[0], Flush(), sample_items[1]]
        seg = add_to_lancedb(path=temp_db_path, table_name="test_table",
                             vector_field="vector", batch_size=5, optimize_on_batch=False)
        results = list(seg(items_with_flush))

        # Should yield only the original items (Flush is consumed)
        assert len(results) == 2
        assert results[0]["_doc_id"] is not None
        assert results[1]["_doc_id"] is not None

        # Should have called add_vectors twice: once for first item, once for flush, once for second item
        # Actually, let me reconsider: the first item goes into buffer, flush causes buffer.flush() which adds it,
        # then second item goes into buffer, and at the end buffer.flush() is called again
        assert mock_doc_store.add_vectors.call_count >= 2

        # Should have optimized once (on flush, since optimize_on_batch=False)
        assert mock_table.optimize.call_count >= 1

    @mock.patch('talkpipe.search.lancedb.LanceDBDocumentStore')
    @mock.patch('talkpipe.search.lancedb.extract_property')
    @mock.patch('talkpipe.search.lancedb.AdaptiveBuffer')
    def test_add_to_lancedb_flush_with_optimize_on_batch(
        self,
        mock_adaptive_buffer,
        mock_extract_property,
        mock_doc_store_class,
        sample_items,
        temp_db_path,
    ):
        """Test that add_to_lancedb optimizes on flush even when optimize_on_batch is True."""
        mock_doc_store = mock.Mock()
        mock_table = mock.Mock()
        mock_doc_store._get_table.return_value = [mock_table]
        mock_doc_store_class.return_value = mock_doc_store
        mock_extract_property.return_value = [1.0, 2.0, 3.0]

        class FakeBuffer:
            def __init__(self):
                self.items = []

            def append(self, item):
                self.items.append(item)
                return None

            def flush(self):
                if not self.items:
                    return None
                items = self.items
                self.items = []
                return items

        buffer_instance = FakeBuffer()
        mock_adaptive_buffer.return_value = buffer_instance

        items_with_flush = [sample_items[0], Flush()]
        seg = add_to_lancedb(path=temp_db_path, table_name="test_table",
                             vector_field="vector", batch_size=5, optimize_on_batch=True)
        results = list(seg(items_with_flush))

        # Should yield only the original item (Flush is consumed)
        assert len(results) == 1

        # Should have called add_vectors once (for the item that was flushed)
        assert mock_doc_store.add_vectors.call_count == 1

        # Should have optimized once (on flush, since vectors were added)
        assert mock_table.optimize.call_count == 1


def test_add_and_search_integration(temp_db_path, sample_items_direction_relevant):
    add_segment = add_to_lancedb(path=temp_db_path, table_name="test_table",
                                vector_field="vector", overwrite=True)
    list(add_segment(sample_items_direction_relevant))
    search_segment = search_lancedb(path=temp_db_path, table_name="test_table", field="vector", limit=2)
    results = list(search_segment([{"vector": [1.0, 0.0], "text": "query item"}]))
    assert len(results) == 2  # Should return 2 SearchResult objects
    assert results[0].document["text"] == "first item"
    assert results[1].document["text"] == "second item"

    results = list(search_segment([{"vector": [0.0, 1.0], "text": "query item"}]))
    assert len(results) == 2  # Should return 2 SearchResult objects
    assert results[0].document["text"] == "third item"
    assert results[1].document["text"] == "second item"


def test_upsert_integration(temp_db_path):
    """Test that addToLanceDB can update existing documents by default (upsert behavior)."""
    # Add initial documents
    initial_items = [
        {"vector": [1.0, 0.0, 0.0], "text": "first version", "doc_id": "doc1"},
        {"vector": [0.0, 1.0, 0.0], "text": "second item", "doc_id": "doc2"}
    ]
    add_segment = add_to_lancedb(path=temp_db_path, table_name="test_table",
                                vector_field="vector", doc_id_field="doc_id", overwrite=True)
    list(add_segment(initial_items))

    # Update first document with same doc_id but different content/vector
    updated_items = [
        {"vector": [0.5, 0.5, 0.0], "text": "updated version", "doc_id": "doc1"}
    ]
    add_segment_update = add_to_lancedb(path=temp_db_path, table_name="test_table",
                                        vector_field="vector", doc_id_field="doc_id")
    list(add_segment_update(updated_items))

    # Search to verify the update
    search_segment = search_lancedb(path=temp_db_path, table_name="test_table",
                                   field="vector", limit=10)
    results = list(search_segment([{"vector": [0.5, 0.5, 0.0]}]))

    # Should find the updated document as top result
    assert len(results) >= 1
    # The document with doc_id "doc1" should now have "updated version" text
    doc1_results = [r for r in results if r.doc_id == "doc1"]
    assert len(doc1_results) == 1
    assert doc1_results[0].document["text"] == "updated version"

    # Verify there are only 2 documents total (not 3 - no duplicates)
    store = LanceDBDocumentStore(temp_db_path, "test_table")
    assert store.count() == 2


def test_read_consistency_interval(temp_db_path):
    """Test that documents cannot be retrieved before read_consistency_interval passes.

    This test demonstrates that when using a read_consistency_interval, a connection
    that has cached table metadata will not see new writes from other connections
    until the interval has passed.
    """
    # Create a short read_consistency_interval for testing
    read_interval = 2  # 2 seconds

    # Create first document store and add initial data to establish the table
    # This will cache the table metadata
    reader_store = LanceDBDocumentStore(
        path=temp_db_path,
        table_name="consistency_test",
        vector_dim=3,
        read_consistency_interval=read_interval
    )

    # Add initial document to create the table
    initial_vector = [0.0, 0.0, 0.0]
    initial_document = {"text": "initial document", "category": "initial"}
    initial_doc_id = reader_store.add_vector(initial_vector, initial_document)

    # Verify initial document is readable
    assert reader_store.get_document(initial_doc_id) is not None

    # Force table to be opened and cached by performing a count operation
    initial_count = reader_store.count()
    assert initial_count == 1

    # Now create a WRITER connection (separate connection) and add a new document
    writer_store = LanceDBDocumentStore(
        path=temp_db_path,
        table_name="consistency_test",
        vector_dim=3,
        read_consistency_interval=read_interval
    )

    test_vector = [1.0, 2.0, 3.0]
    test_document = {"text": "new document", "category": "test"}
    new_doc_id = writer_store.add_vector(test_vector, test_document)

    # The reader connection should still see only 1 document (cached metadata)
    # because the read_consistency_interval hasn't passed
    count_before_wait = reader_store.count()
    assert count_before_wait == 1, f"Reader should not see new document before interval passes, but saw {count_before_wait} documents"

    # Wait for the read_consistency_interval to pass
    time.sleep(read_interval + 0.5)  # Add 0.5s buffer to ensure interval has passed

    # Now the reader should see the new document after the interval
    count_after_wait = reader_store.count()
    assert count_after_wait == 2, f"Reader should see new document after interval passes, but saw {count_after_wait} documents"

    # Verify we can now retrieve the new document
    retrieved_doc = reader_store.get_document(new_doc_id)
    assert retrieved_doc is not None, "New document should be retrievable after consistency interval passes"
    assert retrieved_doc["text"] == "new document"
    assert retrieved_doc["category"] == "test"


def test_add_vectors_batch_operation(temp_db_path):
    """Test the add_vectors method for batch operations."""
    store = LanceDBDocumentStore(temp_db_path, "test_table")
    
    # Prepare batch data
    documents = [
        ([1.0, 2.0, 3.0], {"text": "first doc", "category": "A"}, "doc1"),
        ([4.0, 5.0, 6.0], {"text": "second doc", "category": "B"}, "doc2"),
        ([7.0, 8.0, 9.0], {"text": "third doc", "category": "C"}, None)  # No doc_id provided
    ]
    
    # Add vectors in batch
    doc_ids = store.add_vectors(documents)
    
    # Verify return values
    assert len(doc_ids) == 3
    assert doc_ids[0] == "doc1"
    assert doc_ids[1] == "doc2" 
    assert doc_ids[2] is not None  # Auto-generated UUID
    
    # Verify documents were added correctly
    assert store.count() == 3
    
    # Verify first document
    doc1 = store.get_document("doc1")
    assert doc1 is not None
    assert doc1["text"] == "first doc"
    assert doc1["category"] == "A"
    
    # Verify second document
    doc2 = store.get_document("doc2")
    assert doc2 is not None
    assert doc2["text"] == "second doc"
    assert doc2["category"] == "B"
    
    # Verify third document (auto-generated ID)
    doc3 = store.get_document(doc_ids[2])
    assert doc3 is not None
    assert doc3["text"] == "third doc"
    assert doc3["category"] == "C"


def test_add_vectors_empty_list(temp_db_path):
    """Test add_vectors with empty list returns empty list."""
    store = LanceDBDocumentStore(temp_db_path, "test_table")
    doc_ids = store.add_vectors([])
    assert doc_ids == []
    assert store.count() == 0


def test_add_vectors_with_existing_documents(temp_db_path):
    """Test add_vectors can update existing documents (upsert behavior)."""
    store = LanceDBDocumentStore(temp_db_path, "test_table")
    
    # Add initial document
    initial_doc_id = store.add_vector([1.0, 2.0, 3.0], {"text": "original", "version": "1"}, "doc1")
    assert store.count() == 1
    
    # Use add_vectors to update existing document and add new one
    documents = [
        ([1.5, 2.5, 3.5], {"text": "updated", "version": "2"}, "doc1"),  # Update existing
        ([4.0, 5.0, 6.0], {"text": "new doc", "version": "1"}, "doc2")   # Add new
    ]
    
    doc_ids = store.add_vectors(documents)
    
    # Should still have 2 documents (not 3)
    assert store.count() == 2
    assert doc_ids == ["doc1", "doc2"]
    
    # Verify updated document
    updated_doc = store.get_document("doc1")
    assert updated_doc["text"] == "updated"
    assert updated_doc["version"] == "2"
    
    # Verify new document
    new_doc = store.get_document("doc2")
    assert new_doc["text"] == "new doc"
    assert new_doc["version"] == "1"
