import json
from unittest.mock import patch

import numpy as np
import pytest

from talkpipe.chatterlang import compile
from talkpipe.llm.embedding import LLMEmbed
from talkpipe.llm.model2vec_embeddings import DEFAULT_MODEL, Model2VecEmbedder, precache_model


def _mock_static_model(monkeypatch, *, dimension=256, embedding=None):
    if embedding is None:
        embedding = np.array([0.1, 0.2, 0.3], dtype=np.float32)

    class DummyModel:
        dim = dimension
        normalize = True

        def __init__(self, *args, **kwargs):
            pass

        @classmethod
        def from_pretrained(cls, *args, **kwargs):
            return cls()

        def encode(self, text, **kwargs):
            if isinstance(text, str):
                return embedding
            return np.stack([embedding for _ in text])

    monkeypatch.setattr(
        "talkpipe.llm.model2vec_embeddings._require_model2vec",
        lambda: DummyModel,
    )
    return embedding


def test_model2vec_embedding_execute_mocked(monkeypatch):
    from talkpipe.llm.embedding_adapters_model2vec import Model2VecEmbeddingAdapter

    _mock_static_model(monkeypatch)
    model = Model2VecEmbeddingAdapter("minishlab/potion-base-8M")
    assert model.model_name == "minishlab/potion-base-8M"
    assert model.source == "model2vec"
    ans = model("Hello")
    assert ans == pytest.approx([0.1, 0.2, 0.3])
    assert all(isinstance(x, float) for x in ans)


def test_model2vec_default_model_when_none(monkeypatch):
    from talkpipe.llm.embedding_adapters_model2vec import Model2VecEmbeddingAdapter

    _mock_static_model(monkeypatch)
    model = Model2VecEmbeddingAdapter(None)
    assert model.model_name == DEFAULT_MODEL


def test_create_model2vec_embedder_mocked(monkeypatch):
    from talkpipe.llm.embedding_adapters_model2vec import Model2VecEmbeddingAdapter

    _mock_static_model(monkeypatch)
    cmd = LLMEmbed(model="minishlab/potion-base-8M", source="model2vec")
    assert isinstance(cmd.embedder, Model2VecEmbeddingAdapter)
    response = list(cmd(["Hello"]))
    assert len(response) == 1
    assert response[0] == pytest.approx([0.1, 0.2, 0.3])


def test_execute_returns_list_not_ndarray(monkeypatch):
    from talkpipe.llm.embedding_adapters_model2vec import Model2VecEmbeddingAdapter

    _mock_static_model(monkeypatch)
    model = Model2VecEmbeddingAdapter("minishlab/potion-base-8M")
    ans = model("Hello")
    assert isinstance(ans, list)
    assert not isinstance(ans, np.ndarray)

    f = compile(
        "| llmEmbed[model='minishlab/potion-base-8M', source='model2vec', "
        "field='example', set_as='vector'] | toDict[field_list='example']"
    )
    f = f.as_function(single_in=True, single_out=False)
    response = list(f({"example": "Hello"}))
    json.dumps(response)


def test_model2vec_embedder_embed_one_returns_list(monkeypatch):
    _mock_static_model(monkeypatch)
    embedder = Model2VecEmbedder("test-model")
    result = embedder.embed_one("Hello")
    assert result == pytest.approx([0.1, 0.2, 0.3])
    assert all(isinstance(x, float) for x in result)


def test_embedder_without_revision_loads_by_model_name(monkeypatch):
    """When no revision/cache_folder is set, StaticModel.from_pretrained is called
    with the bare model name (not unsupported revision/cache_folder kwargs)."""
    captured = {}

    class DummyModel:
        dim = 3
        normalize = True

        @classmethod
        def from_pretrained(cls, path, **kwargs):
            captured["path"] = path
            captured["kwargs"] = kwargs
            return cls()

        def encode(self, text, **_):
            return np.array([0.1, 0.2, 0.3])

    monkeypatch.setattr(
        "talkpipe.llm.model2vec_embeddings._require_model2vec",
        lambda: DummyModel,
    )
    Model2VecEmbedder("minishlab/potion-base-8M")
    assert captured["path"] == "minishlab/potion-base-8M"
    assert captured["kwargs"] == {}


def test_embedder_with_revision_resolves_via_snapshot_download(monkeypatch):
    """When revision/cache_folder is set, the embedder uses huggingface_hub.snapshot_download
    to pin the revision and then loads StaticModel from the resulting local directory."""
    download_calls = []

    def fake_snapshot_download(**kwargs):
        download_calls.append(kwargs)
        return "/cache/snapshots/abc123"

    captured = {}

    class DummyModel:
        dim = 3
        normalize = True

        @classmethod
        def from_pretrained(cls, path, **kwargs):
            captured["path"] = path
            captured["kwargs"] = kwargs
            return cls()

        def encode(self, text, **_):
            return np.array([0.1, 0.2, 0.3])

    monkeypatch.setattr(
        "talkpipe.llm.model2vec_embeddings._require_model2vec",
        lambda: DummyModel,
    )
    monkeypatch.setattr(
        "huggingface_hub.snapshot_download", fake_snapshot_download
    )

    Model2VecEmbedder(
        "minishlab/potion-base-8M",
        revision="abc123",
        cache_folder="/tmp/cache",
    )
    assert download_calls == [
        {
            "repo_id": "minishlab/potion-base-8M",
            "revision": "abc123",
            "cache_dir": "/tmp/cache",
        }
    ]
    assert captured["path"] == "/cache/snapshots/abc123"
    assert captured["kwargs"] == {}


def test_embedder_with_local_dir_loads_from_path(monkeypatch, tmp_path):
    """When model points at an existing local directory, it is loaded directly
    (resolved to an absolute path) without any snapshot_download."""
    captured = {}

    class DummyModel:
        dim = 3
        normalize = True

        @classmethod
        def from_pretrained(cls, path, **kwargs):
            captured["path"] = path
            return cls()

        def encode(self, text, **_):
            return np.array([0.1, 0.2, 0.3])

    def fail_snapshot_download(**kwargs):
        raise AssertionError("snapshot_download should not be called for a local path")

    monkeypatch.setattr(
        "talkpipe.llm.model2vec_embeddings._require_model2vec",
        lambda: DummyModel,
    )
    monkeypatch.setattr("huggingface_hub.snapshot_download", fail_snapshot_download)

    model_dir = tmp_path / "my-model"
    model_dir.mkdir()

    # Even with revision/cache_folder set, a local dir takes precedence.
    Model2VecEmbedder(str(model_dir), revision="abc123", cache_folder="/tmp/cache")
    assert captured["path"] == str(model_dir.resolve())


def test_embedder_expands_user_home_local_path(monkeypatch, tmp_path):
    """A ``~``-prefixed path to a downloaded model is expanded and loaded directly."""
    captured = {}

    class DummyModel:
        dim = 3
        normalize = True

        @classmethod
        def from_pretrained(cls, path, **kwargs):
            captured["path"] = path
            return cls()

        def encode(self, text, **_):
            return np.array([0.1, 0.2, 0.3])

    monkeypatch.setattr(
        "talkpipe.llm.model2vec_embeddings._require_model2vec",
        lambda: DummyModel,
    )
    monkeypatch.setenv("HOME", str(tmp_path))

    model_dir = tmp_path / "my-model"
    model_dir.mkdir()

    Model2VecEmbedder("~/my-model")
    assert captured["path"] == str(model_dir.resolve())


def test_precache_model_smoke(monkeypatch):
    download_calls = []

    def fake_snapshot_download(**kwargs):
        download_calls.append(kwargs)
        return "/cache/snapshots/abc123"

    class DummyModel:
        dim = 3
        normalize = True

        @classmethod
        def from_pretrained(cls, path, **kwargs):
            return cls()

        def encode(self, text, **_):
            return np.array([0.1, 0.2, 0.3])

    monkeypatch.setattr(
        "talkpipe.llm.model2vec_embeddings._require_model2vec",
        lambda: DummyModel,
    )
    monkeypatch.setattr(
        "huggingface_hub.snapshot_download", fake_snapshot_download
    )

    result = precache_model(
        "minishlab/potion-base-8M",
        revision="abc123",
        cache_dir="/tmp/cache",
    )

    assert download_calls == [
        {
            "repo_id": "minishlab/potion-base-8M",
            "revision": "abc123",
            "cache_dir": "/tmp/cache",
        }
    ]
    assert result["model"] == "minishlab/potion-base-8M"
    assert result["revision"] == "abc123"
    assert result["snapshot_dir"] == "/cache/snapshots/abc123"
    assert result["dimension"] == 3
    assert result["smoke_test_length"] == 3


def test_precache_model_raises_on_empty_embedding(monkeypatch):
    class DummyModel:
        dim = 0
        normalize = True

        @classmethod
        def from_pretrained(cls, path, **kwargs):
            return cls()

        def encode(self, text, **_):
            return np.array([])

    monkeypatch.setattr(
        "talkpipe.llm.model2vec_embeddings._require_model2vec",
        lambda: DummyModel,
    )
    monkeypatch.setattr(
        "huggingface_hub.snapshot_download",
        lambda **kwargs: "/cache/snapshots/x",
    )

    with pytest.raises(RuntimeError, match="produced empty output"):
        precache_model("broken/model")


def test_require_model2vec_import_error():
    from talkpipe.llm import model2vec_embeddings

    with patch.dict("sys.modules", {"model2vec": None}):
        with pytest.raises(ImportError, match="model2vec"):
            model2vec_embeddings._require_model2vec()
