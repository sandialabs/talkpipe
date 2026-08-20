"""Shared contract checks every AbstractEmbeddingAdapter implementation must meet.

Import and call ``run_embedding_adapter_contract`` from a provider test module,
passing a factory that returns an adapter whose transport has been replaced by
a deterministic fake. Third-party adapters (plugins) can reuse it the same way.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from talkpipe.llm.embedding_adapters import AbstractEmbeddingAdapter


def run_embedding_adapter_contract(
    make_adapter: Callable[[], AbstractEmbeddingAdapter],
    *,
    expected_source: str,
    expected_model: str,
) -> None:
    adapter = make_adapter()

    # identity
    assert isinstance(adapter, AbstractEmbeddingAdapter)
    assert adapter.source == expected_source
    assert adapter.model_name == expected_model
    assert expected_model in adapter.description()
    assert expected_source in adapter.description()
    assert str(adapter) == adapter.description() == repr(adapter)

    # single vs batch, and __call__ dispatch on type
    one = adapter.execute_one("alpha")
    assert isinstance(one, list)
    assert one, "execute_one must return a non-empty list"
    assert all(isinstance(x, float) for x in one)
    assert adapter("alpha") == one

    batch = adapter.execute_batch(["alpha", "beta"])
    assert isinstance(batch, list)
    assert len(batch) == 2
    assert all(isinstance(v, list) and len(v) == len(one) for v in batch)
    assert adapter(["alpha", "beta"]) == batch
    assert adapter(("alpha", "beta")) == batch  # any Sequence[str]

    # empty batch is a no-op, never a provider call
    assert adapter.execute_batch([]) == []
    assert adapter([]) == []

    # deprecated execute() still works and warns
    with pytest.warns(DeprecationWarning, match="execute_one"):
        assert adapter.execute("alpha") == one
