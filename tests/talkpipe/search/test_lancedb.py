import pytest
from unittest import mock
import tempfile
import os
from talkpipe.search.lancedb import search_lancedb, add_to_lancedb


@pytest.fixture
def temp_db_path():
    with tempfile.TemporaryDirectory() as temp_dir:
        yield os.path.join(temp_dir, "test_db")


@pytest.fixture
def sample_items():
    return [
        {"vector": [1.0, 2.0, 3.0], "text": "first item"},
        {"vector": [4.0, 5.0, 6.0], "text": "second item"},
        [7.0, 8.0, 9.0]  # Vector without field
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

        mock_doc_store_class.assert_called_once_with(temp_db_path, "test_table", None)
        mock_extract_property.assert_called_once_with(sample_items[0], "vector")
        mock_doc_store.vector_search.assert_called_once_with([1.0, 2.0, 3.0], 5)

        assert len(results) == 2
        assert results == sample_search_results

    @mock.patch('talkpipe.search.lancedb.LanceDBDocumentStore')
    def test_search_lancedb_without_field(self, mock_doc_store_class, sample_items, sample_search_results, temp_db_path):
        mock_doc_store = mock.Mock()
        mock_doc_store_class.return_value = mock_doc_store
        mock_doc_store.vector_search.return_value = sample_search_results

        items_to_search = [sample_items[2]]  # Raw vector
        seg = search_lancedb(path=temp_db_path, table_name="test_table", limit=3)
        results = list(seg(items_to_search))

        mock_doc_store_class.assert_called_once_with(temp_db_path, "test_table", None)
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
    def test_search_lancedb_default_limit(self, mock_doc_store_class, sample_items, sample_search_results, temp_db_path):
        mock_doc_store = mock.Mock()
        mock_doc_store_class.return_value = mock_doc_store
        mock_doc_store.vector_search.return_value = sample_search_results

        items_to_search = [sample_items[2]]
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
        mock_doc_store_class.return_value = mock_doc_store
        mock_doc_store.add_vector.return_value = "added_doc_id"
        mock_extract_property.return_value = [1.0, 2.0, 3.0]

        items_to_add = [sample_items[0]]  # Item with vector field
        seg = add_to_lancedb(path=temp_db_path, table_name="test_table", vector_field="vector")
        results = list(seg(items_to_add))

        mock_doc_store_class.assert_called_once_with(temp_db_path, "test_table", None)
        mock_extract_property.assert_called_once_with(sample_items[0], "vector", fail_on_missing=True)
        mock_doc_store.add_vector.assert_called_once_with([1.0, 2.0, 3.0], {"text": "first item"}, None)

        assert len(results) == 1
        assert results[0]["_doc_id"] == "added_doc_id"

    @mock.patch('talkpipe.search.lancedb.LanceDBDocumentStore')
    @mock.patch('talkpipe.search.lancedb.extract_property')
    def test_add_to_lancedb_with_overwrite(self, mock_extract_property, mock_doc_store_class, sample_items, temp_db_path):
        mock_doc_store = mock.Mock()
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
        mock_doc_store_class.return_value = mock_doc_store
        mock_doc_store.add_vector.side_effect = ["doc1", "doc2", "doc3"]
        mock_extract_property.side_effect = [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0], [7.0, 8.0, 9.0]]

        items_to_add = sample_items
        seg = add_to_lancedb(path=temp_db_path, table_name="test_table", vector_field="vector")
        results = list(seg(items_to_add))

        # Function should yield back the original items with _doc_id added (for dict items only)
        assert len(results) == 3
        assert results[0]["_doc_id"] == "doc1"
        assert results[1]["_doc_id"] == "doc2"
        # The third item is a list, so it doesn't get _doc_id added
        assert results[2] == [7.0, 8.0, 9.0]


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
