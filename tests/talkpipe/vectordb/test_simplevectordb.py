import pytest
import numpy as np
from talkpipe.vectordb.simplevectordb import SimpleVectorDB
from talkpipe.vectordb.abstract import VectorRecord

@pytest.fixture
def db():
    return SimpleVectorDB()

def test_add_and_get_vector(db):
    vec = [1.0, 2.0, 3.0]
    meta = {"foo": "bar"}
    vid = db.add(vec, meta)
    record = db.get(vid)
    assert isinstance(record, VectorRecord)
    assert record.vector == vec
    assert record.metadata == meta

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
    assert rec.metadata == {"b": 2}
    assert db.update("nope", [1,2,3]) is False

def test_vector_dimension_validation(db):
    db.add([1,2,3])
    with pytest.raises(ValueError):
        db.add([1,2])  # Wrong dimension

def test_cosine_similarity(db):
    v1 = [1,0,0]
    v2 = [0,1,0]
    sim = db._cosine_similarity(v1, v2)
    assert pytest.approx(sim) == 0.0
    sim2 = db._cosine_similarity([1,0], [1,0])
    assert pytest.approx(sim2) == 1.0

def test_euclidean_distance(db):
    v1 = [1,2,3]
    v2 = [4,5,6]
    dist = db._euclidean_distance(v1, v2)
    assert pytest.approx(dist) == np.linalg.norm(np.array(v1)-np.array(v2))

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
    assert results[0][2].metadata["cat"] == "A"

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
    assert rec.metadata == {"x": 1}

def test_export_and_import_json(tmp_path, db):
    vid = db.add([1,2,3], {"foo": "bar"})
    path = tmp_path / "db.json"
    db.export_json(str(path))
    db2 = SimpleVectorDB()
    db2.import_json(str(path))
    assert db2.count() == 1
    rec = db2.get(vid)
    assert rec.vector == [1,2,3]
    assert rec.metadata == {"foo": "bar"}

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