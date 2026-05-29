import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from talkpipe.chatterlang import compile
from talkpipe.llm.embedding import LLMEmbed
from talkpipe.llm.local_embeddings import DEFAULT_MODEL, LocalEmbedder, precache_model


def _mock_sentence_transformer(monkeypatch, *, dimension=768, embedding=None):
    if embedding is None:
        embedding = np.array([0.1, 0.2, 0.3], dtype=np.float32)

    class DummyModel:
        def __init__(self, *args, **kwargs):
            pass

        def get_embedding_dimension(self):
            return dimension

        @property
        def max_seq_length(self):
            return 8192

        def encode(self, texts, **kwargs):
            if isinstance(texts, str):
                texts = [texts]
            rows = [embedding for _ in texts]
            return np.stack(rows)

    monkeypatch.setattr(
        "talkpipe.llm.local_embeddings._require_sentence_transformers",
        lambda: DummyModel,
    )
    return embedding


def test_local_embedding_execute_mocked(monkeypatch):
    from talkpipe.llm.embedding_adapters_local import LocalEmbeddingAdapter

    _mock_sentence_transformer(monkeypatch)
    model = LocalEmbeddingAdapter("jinaai/jina-embeddings-v2-base-en")
    assert model.model_name == "jinaai/jina-embeddings-v2-base-en"
    assert model.source == "local"
    ans = model("Hello")
    assert ans == pytest.approx([0.1, 0.2, 0.3])
    assert all(isinstance(x, float) for x in ans)


def test_local_embedding_default_model_when_none(monkeypatch):
    from talkpipe.llm.embedding_adapters_local import LocalEmbeddingAdapter

    _mock_sentence_transformer(monkeypatch)
    model = LocalEmbeddingAdapter(None)
    assert model.model_name == DEFAULT_MODEL


def test_create_local_embedder_mocked(monkeypatch):
    from talkpipe.llm.embedding_adapters_local import LocalEmbeddingAdapter

    _mock_sentence_transformer(monkeypatch)
    cmd = LLMEmbed(model="jinaai/jina-embeddings-v2-base-en", source="local")
    assert isinstance(cmd.embedder, LocalEmbeddingAdapter)
    response = list(cmd(["Hello"]))
    assert len(response) == 1
    assert response[0] == pytest.approx([0.1, 0.2, 0.3])


def test_execute_returns_list_not_ndarray(monkeypatch):
    from talkpipe.llm.embedding_adapters_local import LocalEmbeddingAdapter

    _mock_sentence_transformer(monkeypatch)
    model = LocalEmbeddingAdapter("jinaai/jina-embeddings-v2-base-en")
    ans = model("Hello")
    assert isinstance(ans, list)
    assert not isinstance(ans, np.ndarray)

    f = compile(
        "| llmEmbed[model='jinaai/jina-embeddings-v2-base-en', source='local', "
        "field='example', set_as='vector'] | toDict[field_list='example']"
    )
    f = f.as_function(single_in=True, single_out=False)
    response = list(f({"example": "Hello"}))
    json.dumps(response)


def test_local_embedder_embed_one_returns_list(monkeypatch):
    _mock_sentence_transformer(monkeypatch)
    embedder = LocalEmbedder("test-model")
    result = embedder.embed_one("Hello")
    assert result == pytest.approx([0.1, 0.2, 0.3])
    assert all(isinstance(x, float) for x in result)


def test_precache_model_smoke(tmp_path):
    snapshot_dir = tmp_path / "snapshot"
    snapshot_dir.mkdir()
    tokenizer_json = snapshot_dir / "tokenizer.json"
    tokenizer_json.write_text('{"version":"1.0","truncation":null,"padding":null,"added_tokens":[],"normalizer":null,"pre_tokenizer":null,"post_processor":null,"decoder":null,"model":{"type":"WordLevel","vocab":{"<unk>":0,"hello":1},"unk_token":"<unk>"}}')

    mock_tok = MagicMock()
    mock_tok.encode.return_value.ids = [1, 2, 3]

    mock_hub = MagicMock()
    mock_hub.snapshot_download.return_value = str(snapshot_dir)
    mock_tokenizers = MagicMock()
    mock_tokenizers.Tokenizer.from_file.return_value = mock_tok

    with patch.dict(
        "sys.modules",
        {"huggingface_hub": mock_hub, "tokenizers": mock_tokenizers},
    ):
        result = precache_model(
            "jinaai/jina-embeddings-v2-base-en",
            revision="abc123",
            cache_dir=tmp_path / "cache",
        )

    assert result["model"] == "jinaai/jina-embeddings-v2-base-en"
    assert result["revision"] == "abc123"
    assert result["snapshot_dir"] == str(snapshot_dir)
    assert result["tokenizer_only"] is False
    assert result["smoke_test_tokens"] == 3


def test_precache_model_skips_tokenizer_smoke_without_tokenizer_json(tmp_path):
    snapshot_dir = tmp_path / "snapshot"
    snapshot_dir.mkdir()

    mock_hub = MagicMock()
    mock_hub.snapshot_download.return_value = str(snapshot_dir)

    with patch.dict("sys.modules", {"huggingface_hub": mock_hub, "tokenizers": MagicMock()}):
        result = precache_model("some/model")

    assert result["smoke_test_tokens"] is None


def test_precache_model_raises_on_empty_tokenizer_output(tmp_path):
    snapshot_dir = tmp_path / "snapshot"
    snapshot_dir.mkdir()
    (snapshot_dir / "tokenizer.json").write_text("{}")

    mock_tok = MagicMock()
    mock_tok.encode.return_value.ids = []

    mock_hub = MagicMock()
    mock_hub.snapshot_download.return_value = str(snapshot_dir)
    mock_tokenizers = MagicMock()
    mock_tokenizers.Tokenizer.from_file.return_value = mock_tok

    with patch.dict(
        "sys.modules",
        {"huggingface_hub": mock_hub, "tokenizers": mock_tokenizers},
    ):
        with pytest.raises(RuntimeError, match="produced empty output"):
            precache_model("broken/model")


def test_require_local_embeddings_import_error():
    from talkpipe.llm import local_embeddings

    with patch.dict("sys.modules", {"sentence_transformers": None}):
        with pytest.raises(ImportError, match="local-embeddings"):
            local_embeddings._require_sentence_transformers()
