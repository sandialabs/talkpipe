import math
import os
import time
import pytest

from talkpipe.search.lancedb import LanceDBDocumentStore
from talkpipe.search.lancedb import add_to_lancedb, search_lancedb


def make_items(n, dim=3, start=0):
    items = []
    for i in range(n):
        vec = [float(start + i + j) for j in range(dim)]
        items.append({
            "vector": vec,
            "meta": f"item-{start+i}"
        })
    return items


def test_add_to_lancedb_flushes_last_partial_batch_tmp_db():
    """Ensure final partial batch is flushed when batch_size doesn't divide item count (tmp:// shared DB)."""
    path = "tmp://docs_tmp_partial"
    table_name = "docs"
    batch_size = 2

    items = make_items(3, dim=4)

    # Add 3 items with batch_size=2 (1 partial batch at end)
    seg = add_to_lancedb(
        path=path,
        table_name=table_name,
        vector_field="vector",
        metadata_field_list="meta",
        batch_size=batch_size,
        optimize_on_batch=False,
    )
    result = list(seg(items))
    assert len(result) == 3

    # Verify count reflects flushed last partial batch
    store = LanceDBDocumentStore(path=path, table_name=table_name, read_consistency_interval=0)
    assert store.count() == 3

    # Verify we can search and get at least one result
    q = items[0]["vector"]
    results = store.vector_search(q, limit=3)
    assert len(results) >= 1


def test_add_to_lancedb_flushes_last_partial_batch_tmp_uri():
    """Ensure final partial batch is flushed using tmp:// path as well."""
    path = "tmp://lancedb_cache_test"
    table_name = "docs"
    batch_size = 3

    items = make_items(5, dim=5)

    seg = add_to_lancedb(
        path=path,
        table_name=table_name,
        vector_field="vector",
        metadata_field_list="meta",
        batch_size=batch_size,
        optimize_on_batch=False,
    )
    _ = list(seg(items))

    store = LanceDBDocumentStore(path=path, table_name=table_name, read_consistency_interval=0)
    assert store.count() == 5

    # Check IDs list length to ensure persistence
    ids = store.list_ids()
    assert len(ids) == 5


def test_search_after_add_uses_read_consistency_param():
    """Search segment should see recent writes when read_consistency_interval is small (tmp:// shared DB)."""
    path = "tmp://docs_tmp_search"
    table_name = "docs2"

    items = make_items(4, dim=3)
    seg = add_to_lancedb(
        path=path, table_name=table_name,
        vector_field="vector", metadata_field_list="meta",
        batch_size=2, optimize_on_batch=False,
    )
    _ = list(seg(items))

    # Use search segment with read_consistency_interval=0 to ensure immediate visibility
    search_seg = search_lancedb(
        path=path, table_name=table_name,
        all_results_at_once=True,
        field=None, set_as=None,
        limit=3, vector_dim=3,
        read_consistency_interval=0,
    )
    # Query using the first vector
    out = list(search_seg([items[0]["vector"]]))
    assert len(out) == 1
    results = out[0]
    assert len(results) >= 1


def test_add_to_lancedb_multiple_batches_then_count():
    """Add items across multiple batches; ensure final count equals total items (tmp:// shared DB)."""
    path = "tmp://docs_tmp_multi"
    table_name = "docs3"
    items = make_items(7, dim=6)

    seg = add_to_lancedb(
        path=path, table_name=table_name,
        vector_field="vector", metadata_field_list="meta",
        batch_size=4, optimize_on_batch=True,
    )
    _ = list(seg(items))

    store = LanceDBDocumentStore(path=path, table_name=table_name, read_consistency_interval=0)
    assert store.count() == 7

