import json
from unittest.mock import MagicMock, patch

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


def test_precache_model_smoke():
    mock_model = MagicMock()
    mock_model.encode.return_value = np.array([0.1, 0.2, 0.3])
    mock_model.dim = 3

    DummyStaticModel = MagicMock(return_value=mock_model)
    DummyStaticModel.from_pretrained = MagicMock(return_value=mock_model)

    with patch(
        "talkpipe.llm.model2vec_embeddings._require_model2vec",
        return_value=DummyStaticModel,
    ):
        result = precache_model(
            "minishlab/potion-base-8M",
            revision="abc123",
            cache_dir="/tmp/cache",
        )

    DummyStaticModel.from_pretrained.assert_called_once_with(
        "minishlab/potion-base-8M",
        revision="abc123",
        cache_folder="/tmp/cache",
    )
    mock_model.encode.assert_called_once_with("model2vec smoke test")
    assert result["model"] == "minishlab/potion-base-8M"
    assert result["revision"] == "abc123"
    assert result["dimension"] == 3
    assert result["smoke_test_length"] == 3


def test_precache_model_raises_on_empty_embedding():
    mock_model = MagicMock()
    mock_model.encode.return_value = np.array([])
    mock_model.dim = 0

    DummyStaticModel = MagicMock(return_value=mock_model)
    DummyStaticModel.from_pretrained = MagicMock(return_value=mock_model)

    with patch(
        "talkpipe.llm.model2vec_embeddings._require_model2vec",
        return_value=DummyStaticModel,
    ):
        with pytest.raises(RuntimeError, match="produced empty output"):
            precache_model("broken/model")


def test_require_model2vec_import_error():
    from talkpipe.llm import model2vec_embeddings

    with patch.dict("sys.modules", {"model2vec": None}):
        with pytest.raises(ImportError, match="model2vec"):
            model2vec_embeddings._require_model2vec()
