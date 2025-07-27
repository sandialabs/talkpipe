import pytest
from unittest import mock
import numpy as np
from talkpipe.search.simplevectordb import SimpleVectorDB
from talkpipe.search.simplevectordb import SimpleVectorDB, add_vector, search_vector, VectorEntry
    
@pytest.fixture
def db():
    return SimpleVectorDB()

def test_add_and_get_vector(db):
    vec = [1.0, 2.0, 3.0]
    document = {"foo": "bar"}
    vid = db.add(vec, document)
    record = db.get(vid)
    assert isinstance(record, VectorEntry)
    assert record.vector == vec
    assert record.document == document

def test_add_duplicate_id_raises(db):
    vid = db.add([1,2,3])
    with pytest.raises(ValueError):
        db.add([4,5,6], vector_id=vid)

def test_delete_vector(db):
    vid = db.add([1,2,3])
    assert db.delete(vid) is True
    assert db.get(vid) is None
    assert db.delete("nonexistent") is False

def test_update_vector_and_metadata(db):
    vid = db.add([1,2,3], {"a": 1})
    assert db.update(vid, [4,5,6], {"b": 2}) is True
    rec = db.get(vid)
    assert rec.vector == [4,5,6]
    # there's no need to force values to be strings here.
    assert rec.document == {"b": '2'}
    assert db.update("nope", [1,2,3]) is False

def test_vector_dimension_validation(db):
    db.add([1,2,3])
    with pytest.raises(ValueError):
        db.add([1,2])  # Wrong dimension

def test_cosine_similarity_via_search(db):
    # Add vectors
    db.add([1,0,0], {}, "v1")
    db.add([0,1,0], {}, "v2") 
    db.add([1,0,0], {}, "v3")  # Same as v1
    
    # Search should return v3 (identical) with score 1.0, v2 (orthogonal) with score 0.0
    results = db.search([1,0,0], top_k=3, metric="cosine")

    assert results[0][0] == "v3"  or results[1][0] == "v1" # First result should be identical vector
    assert results[1][0] == "v3"  or results[1][0] == "v1" # First result should be identical vector
    assert abs(results[2][1] - 0.0) < 1e-6  # Orthogonal vectors

def test_cosine_similarity_via_vector_search(db):
    # Add vectors
    db.add([1,0,0], {}, "v1")
    db.add([0,1,0], {}, "v2") 
    db.add([1,0,0], {}, "v3")  # Same as v1
    
    # Search should return v3 (identical) with score 1.0, v2 (orthogonal) with score 0.0
    results = db.vector_search([1,0,0], limit=3, metric="cosine")

    assert results[0].doc_id == "v3"  or results[1].doc_id == "v1" # First result should be identical vector
    assert results[1].doc_id == "v3"  or results[1].doc_id == "v1" # First result should be identical vector
    assert abs(results[2].score - 0.0) < 1e-6  # Orthogonal vectors

def test_search_brute_force(db):
    v1 = db.add([1,2,3])
    v2 = db.add([4,5,6])
    results = db.search([1,2,3], top_k=1)
    assert results[0][0] == v1

def test_search_kmeans(db):
    db.add([1,2,3])
    db.add([4,5,6])
    db.add([7,8,9])
    db.run_kmeans_clustering(n_clusters=2)
    results = db.search([1,2,3], top_k=2, method="k-means")
    assert len(results) == 2

def test_filter_search(db):
    db.add([1,2,3], {"cat": "A"})
    db.add([4,5,6], {"cat": "B"})
    results = db.filter_search([1,2,3], {"cat": "A"}, top_k=2)
    assert len(results) == 1
    assert results[0][2].document["cat"] == "A"

def test_count_and_list_ids(db):
    ids = [db.add([i,i+1,i+2]) for i in range(3)]
    assert db.count() == 3
    assert set(db.list_ids()) == set(ids)

def test_save_and_load(tmp_path, db):
    vid = db.add([1,2,3], {"x": 1})
    path = tmp_path / "db.pkl"
    db.save(str(path))
    db2 = SimpleVectorDB()
    db2.load(str(path))
    assert db2.count() == 1
    rec = db2.get(vid)
    assert rec.vector == [1,2,3]
    assert rec.document == {"x": '1'}

def test_export_and_import_json(tmp_path, db):
    vid = db.add([1,2,3], {"foo": "bar"})
    path = tmp_path / "db.json"
    db.export_json(str(path))
    db2 = SimpleVectorDB()
    db2.import_json(str(path))
    assert db2.count() == 1
    rec = db2.get(vid)
    assert rec.vector == [1,2,3]
    assert rec.document == {"foo": "bar"}

def test_invalid_vector_type(db):
    with pytest.raises(ValueError):
        db.add("not a vector")

def test_search_empty_db(db):
    assert db.search([1,2,3]) == []

def test_invalid_search_method(db):
    db.add([1,2,3])
    with pytest.raises(ValueError):
        db.search([1,2,3], method="unknown")

def test_invalid_metric(db):
    db.add([1,2,3])
    with pytest.raises(ValueError):
        db.search([1,2,3], metric="badmetric")

@pytest.fixture
def items_list():
    return [
        {"vector": [1.0, 2.0, 3.0], "foo": "bar"},
        {"vector": [4.0, 5.0, 6.0], "foo": "baz"},
    ]

def test_add_vector_segment_with_path(tmp_path, items_list):
    # Test add_vector with file path (save/load)
    path = tmp_path / "db.pkl"
    seg = add_vector(vector_field="vector", metadata_field_list="foo", path=str(path))
    results = list(seg(items_list))
    assert results == items_list
    # Check file was created and DB can be loaded
    db = SimpleVectorDB()
    db.load(str(path))
    assert db.count() == 2

def test_add_vector_segment_overwrite(tmp_path, items_list):
    # Test add_vector with overwrite option
    path = tmp_path / "db.pkl"
    seg = add_vector(vector_field="vector", metadata_field_list="foo", path=str(path), overwrite=True)
    results = list(seg([{"vector": [1.0, 2.0, 3.0], "foo": "bar"}]))
    seg = add_vector(vector_field="vector", metadata_field_list="foo", path=str(path), overwrite=True)
    results = list(seg(items_list))
    assert results == items_list
    # Check file was created and DB can be loaded
    db = SimpleVectorDB()
    db.load(str(path))
    assert db.count() == 2

def test_add_vector_segment_invalid_vector(items_list, tmp_path):
    path = tmp_path / "db.pkl"
    bad_items = [{"vector": "not_a_vector"}]
    seg = add_vector(path=path, vector_field="vector")
    with pytest.raises(ValueError):
        list(seg(bad_items))

def test_search_vector_segment_with_path(tmp_path, items_list):
    # Add vectors and save DB
    path = tmp_path / "db.pkl"
    db = SimpleVectorDB()
    for item in items_list:
        db.add(item["vector"], {"foo": item["foo"]})
    db.save(str(path))
    # Now search using segment with path
    seg = search_vector(path=str(path), vector_field="vector", top_k=1, all_results_at_once=True)
    results = list(seg([{"vector": [1.0, 2.0, 3.0]}]))
    assert isinstance(results[0], list)
    assert len(results[0]) == 1
    assert results[0][0].document == {"foo": "bar"}

def test_search_vector_segment_invalid_query(tmp_path):
    bad_items = [{"vector": "not_a_vector"}]
    seg = search_vector(vector_field="vector", path=str(tmp_path / "db.pkl"))
    with pytest.raises(ValueError):
        list(seg(bad_items))
