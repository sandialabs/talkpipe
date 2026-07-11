"""Tests for batch embedding adapters and hybrid llmEmbed batching."""

import numpy as np
import pytest
from unittest.mock import MagicMock, Mock

from dataclasses import dataclass
from typing import Callable, Optional

from talkpipe.llm.embedding import LLMEmbed
from talkpipe.llm.embedding_adapters import AbstractEmbeddingAdapter, OllamaEmbedderAdapter
from talkpipe.llm.embedding_adapters_openai import OpenAIEmbeddingAdapter
from talkpipe.llm.embedding_adapters_model2vec import Model2VecEmbeddingAdapter


def _patch_openai_embedding_client_batch(monkeypatch, embeddings=None):
    if embeddings is None:
        embeddings = [[0.1, 0.2], [0.3, 0.4]]

    class DummyEmbeddings:
        @staticmethod
        def create(*, model, input):
            assert model == "text-embedding-3-small"
            if isinstance(input, str):
                inputs = [input]
            else:
                inputs = list(input)
            response = MagicMock()
            response.data = []
            for i, text in enumerate(inputs):
                assert text in ("Hello", "World", "a", "b")
                data_item = MagicMock()
                data_item.embedding = embeddings[i] if i < len(embeddings) else embeddings[-1]
                response.data.append(data_item)
            return response

    class DummyClient:
        embeddings = DummyEmbeddings()

    class DummyOpenAI:
        class OpenAI:
            def __new__(cls):
                return DummyClient()

    monkeypatch.setattr(
        "talkpipe.llm.embedding_adapters_openai._require_openai",
        lambda: DummyOpenAI,
    )


def test_openai_execute_batch_mocked(monkeypatch):
    _patch_openai_embedding_client_batch(monkeypatch)
    model = OpenAIEmbeddingAdapter("text-embedding-3-small")
    result = model.execute_batch(["Hello", "World"])
    assert result == [[0.1, 0.2], [0.3, 0.4]]


def test_openai_call_list_dispatch_mocked(monkeypatch):
    _patch_openai_embedding_client_batch(monkeypatch)
    model = OpenAIEmbeddingAdapter("text-embedding-3-small")
    result = model(["a", "b"])
    assert len(result) == 2
    assert all(isinstance(row, list) for row in result)


def test_openai_execute_one_mocked(monkeypatch):
    _patch_openai_embedding_client_batch(monkeypatch, embeddings=[[0.1, 0.2, 0.3]])
    model = OpenAIEmbeddingAdapter("text-embedding-3-small")
    result = model.execute_one("Hello")
    assert result == [0.1, 0.2, 0.3]
    assert all(isinstance(x, float) for x in result)


def test_execute_deprecated_warns_and_delegates_to_execute_one(monkeypatch):
    _patch_openai_embedding_client_batch(monkeypatch, embeddings=[[0.1, 0.2, 0.3]])
    model = OpenAIEmbeddingAdapter("text-embedding-3-small")
    with pytest.warns(DeprecationWarning, match="execute_one\\(\\) or execute_batch\\(\\)"):
        result = model.execute("Hello")
    assert result == [0.1, 0.2, 0.3]


def test_ollama_execute_batch_mocked(monkeypatch):
    embed_calls = []

    class DummyClient:
        def embed(self, *, model, input):
            embed_calls.append((model, list(input) if not isinstance(input, str) else [input]))
            if isinstance(input, str):
                texts = [input]
            else:
                texts = list(input)
            return {
                "embeddings": [
                    [float(i), float(i + 1)] for i, _ in enumerate(texts)
                ]
            }

    model = OllamaEmbedderAdapter("test-model")
    monkeypatch.setattr(model, "_client", lambda: DummyClient())
    result = model.execute_batch(["Hello", "World"])
    assert result == [[0.0, 1.0], [1.0, 2.0]]
    assert embed_calls[0][1] == ["Hello", "World"]


def test_ollama_embed_connection_error_names_url_and_env_var(monkeypatch):
    class DummyClient:
        def embed(self, *, model, input):
            raise ConnectionError("Failed to connect to Ollama.")

    model = OllamaEmbedderAdapter("test-model", server_url="http://custom:11434")
    monkeypatch.setattr(model, "_client", lambda: DummyClient())
    with pytest.raises(ConnectionError) as excinfo:
        model.execute_batch(["Hello"])
    message = str(excinfo.value)
    assert "http://custom:11434" in message
    assert "TALKPIPE_OLLAMA_SERVER_URL" in message
    # The example must stay paste-safe: an angle-bracket placeholder like
    # <host> is parsed as a shell redirection when copied into a terminal.
    assert "http://your-ollama-host:11434" in message
    assert "<host>" not in message


def test_ollama_embed_connection_error_defaults_to_localhost_url(monkeypatch):
    class DummyClient:
        def embed(self, *, model, input):
            raise ConnectionError("Failed to connect to Ollama.")

    model = OllamaEmbedderAdapter("test-model")
    monkeypatch.setattr(model, "_client", lambda: DummyClient())
    monkeypatch.setattr(model, "_resolve_server_url", lambda: None)
    with pytest.raises(ConnectionError) as excinfo:
        model.execute_batch(["Hello"])
    assert "http://localhost:11434" in str(excinfo.value)


def test_ollama_execute_one_returns_list_not_ndarray(monkeypatch):
    class DummyClient:
        def embed(self, *, model, input):
            return {"embeddings": [[0.1, 0.2, 0.3]]}

    model = OllamaEmbedderAdapter("test-model")
    monkeypatch.setattr(model, "_client", lambda: DummyClient())
    result = model.execute_one("Hello")
    assert isinstance(result, list)
    assert not isinstance(result, np.ndarray)
    assert result == pytest.approx([0.1, 0.2, 0.3])


def test_model2vec_execute_batch_mocked(monkeypatch):
    embedding = np.array([0.1, 0.2, 0.3], dtype=np.float32)

    class DummyModel:
        dim = 3
        normalize = True

        @classmethod
        def from_pretrained(cls, *args, **kwargs):
            return cls()

        def encode(self, text, **kwargs):
            if isinstance(text, str):
                return embedding
            return np.stack([embedding, embedding * 2])

    monkeypatch.setattr(
        "talkpipe.llm.model2vec_embeddings._require_model2vec",
        lambda: DummyModel,
    )
    model = Model2VecEmbeddingAdapter("minishlab/potion-base-8M")
    result = model.execute_batch(["first", "second"])
    assert len(result) == 2
    assert result[0] == pytest.approx([0.1, 0.2, 0.3])
    assert result[1] == pytest.approx([0.2, 0.4, 0.6])


def test_custom_adapter_default_execute_batch_loop():
    class SimpleAdapter(AbstractEmbeddingAdapter):
        def __init__(self):
            super().__init__("m", "custom")

        def execute_one(self, text: str):
            return [float(len(text))]

    adapter = SimpleAdapter()
    assert adapter.execute_batch(["ab", "cde"]) == [[2.0], [3.0]]


def test_llmembed_batch_size_calls_execute_batch():
    batch_calls = []

    def record_batch(texts):
        batch_calls.append(list(texts))
        if len(texts) == 3:
            return [[1.0], [2.0], [3.0]]
        return [[4.0], [5.0]]

    mock_embedder = Mock()
    mock_embedder.execute_batch = Mock(side_effect=record_batch)
    embedder = LLMEmbed(model="test-model", source="ollama", batch_size=3)
    embedder.embedder = mock_embedder
    result = list(embedder(["a", "b", "c", "d", "e"]))
    assert result == [[1.0], [2.0], [3.0], [4.0], [5.0]]
    assert batch_calls == [["a", "b", "c"], ["d", "e"]]


@pytest.mark.parametrize(
    "stream_input",
    [
        [["one", "two"]],
        [[]],
        [[{"text": "a"}, {"text": "b"}]],
    ],
)
def test_llmembed_rejects_list_shaped_stream_items(stream_input):
    mock_embedder = Mock()
    embedder = LLMEmbed(model="test-model", source="ollama", field="text", set_as="vector")
    embedder.embedder = mock_embedder
    with pytest.raises(TypeError, match="list-shaped"):
        list(embedder(stream_input))
    mock_embedder.execute_batch.assert_not_called()
    mock_embedder.execute_one.assert_not_called()


def test_llmembed_batch_failure_fallback_when_fail_on_error_false():
    mock_embedder = Mock()
    mock_embedder.execute_batch = Mock(side_effect=RuntimeError("batch failed"))
    mock_embedder.execute_one = Mock(side_effect=[[1.0], RuntimeError("bad"), [3.0]])
    embedder = LLMEmbed(
        model="test-model",
        source="ollama",
        batch_size=3,
        fail_on_error=False,
    )
    embedder.embedder = mock_embedder
    result = list(embedder(["a", "b", "c"]))
    assert result == [[1.0], [3.0]]
    assert mock_embedder.execute_one.call_count == 3


def _make_tracking_embedder():
    """Return (mock, state) with deterministic vectors keyed by text."""
    state = {"batch": [], "one": []}

    def execute_batch(texts):
        state["batch"].append(list(texts))
        return [[float(10 * (i + 1))] for i in range(len(texts))]

    def execute_one(text):
        state["one"].append(text)
        return [float(100 + ord(text[0]))]

    mock = Mock()
    mock.execute_batch = Mock(side_effect=execute_batch)
    mock.execute_one = Mock(side_effect=execute_one)
    return mock, state


@dataclass(frozen=True)
class LLMEmbedShapeCase:
    """Expected llmEmbed stream shape (or error) for one configuration."""

    id: str
    embedder_kwargs: dict
    stream_input: list
    expected_yields: list
    expected_batch_calls: list
    expected_one_calls: list
    result_checker: Optional[Callable[[list], None]] = None
    expects_exception: bool = False
    exception_type: type = Exception
    exception_match: Optional[str] = None


def _check_dict_vectors(result, field="vector"):
    for row in result:
        assert isinstance(row, dict)
        assert field in row
        assert isinstance(row[field], list)


# Output shape contract (one stream item in, one out; batch_size batches API calls only):
# - batch_size=1: N yields, execute_one per item.
# - batch_size>1: N yields; execute_batch per flush; tail of 1 uses execute_one.
# - list-shaped stream items: TypeError before embedding.
LLM_EMBED_SHAPE_CASES = [
    LLMEmbedShapeCase(
        # handed a stream of three items, one vector per yield
        id="scalar_strings_default_expanded_vectors",
        embedder_kwargs={},
        stream_input=["a", "b", "c"],
        # batch_size=1: one stream yield per scalar, each a vector
        expected_yields=[[197.0], [198.0], [199.0]],
        expected_batch_calls=[],
        expected_one_calls=["a", "b", "c"],
    ),

    LLMEmbedShapeCase(
        # handed a stream of three items, one vector per yield even though batch_size is 3
        # input is three different items, so batching inside the embedder is
        # transpearant to the user.
        id="scalar_strings_batch_size_expanded_vectors",
        embedder_kwargs={"batch_size": 3},
        stream_input=["a", "b", "c"],
        # batch_size=3: API batch of 3, still 3 stream yields (expanded)
        expected_yields=[[10.0], [20.0], [30.0]],
        expected_batch_calls=[["a", "b", "c"]],
        expected_one_calls=[],
    ),
    LLMEmbedShapeCase(
        # handed a stream of three items, one vector per yield even though batch_size is 2
        # input is three different items, so batching inside the embedder is
        # transpearant to the user
        id="scalar_strings_partial_flush_expanded_vectors",
        embedder_kwargs={"batch_size": 2},
        stream_input=["a", "b", "c"],
        # flush [a,b] via batch; remainder [c] uses execute_one (len==1)
        expected_yields=[[10.0], [20.0], [199.0]],
        expected_batch_calls=[["a", "b"]],
        expected_one_calls=["c"],
    ),
    LLMEmbedShapeCase(
        # handed a stream of two dicts, one vector per yield, with the vectors attached to the dicts.
        id="scalar_dicts_set_as_expanded_items",
        embedder_kwargs={"field": "text", "set_as": "vector"},
        stream_input=[{"text": "a"}, {"text": "b"}],
        expected_yields=[
            {"text": "a", "vector": [197.0]},
            {"text": "b", "vector": [198.0]},
        ],
        expected_batch_calls=[],
        expected_one_calls=["a", "b"],
        result_checker=_check_dict_vectors,
    ),
    LLMEmbedShapeCase(
        id="list_shaped_input_raises",
        embedder_kwargs={"field": "text", "set_as": "vector"},
        stream_input=[[{"text": "a"}, {"text": "b"}]],
        expected_yields=[],
        expected_batch_calls=[],
        expected_one_calls=[],
        expects_exception=True,
        exception_type=TypeError,
        exception_match="list-shaped",
    ),
    LLMEmbedShapeCase(
        # fail_on_error=True (default): embedder errors propagate.
        id="scalar_embedder_error_raises",
        embedder_kwargs={},
        stream_input=["bad"],
        expected_yields=[],
        expected_batch_calls=[],
        expected_one_calls=["bad"],
        expects_exception=True,
        exception_type=RuntimeError,
        exception_match="embed failed",
    ),
]


def _embedder_for_case(case: LLMEmbedShapeCase):
    if case.id == "scalar_embedder_error_raises":
        state = {"batch": [], "one": []}

        def execute_one(text):
            state["one"].append(text)
            raise RuntimeError("embed failed")

        def execute_batch(texts):
            state["batch"].append(list(texts))
            raise RuntimeError("embed failed")

        mock = Mock()
        mock.execute_one = Mock(side_effect=execute_one)
        mock.execute_batch = Mock(side_effect=execute_batch)
        return mock, state
    return _make_tracking_embedder()


@pytest.mark.parametrize("case", LLM_EMBED_SHAPE_CASES, ids=[c.id for c in LLM_EMBED_SHAPE_CASES])
def test_llmembed_output_shape_by_configuration(case: LLMEmbedShapeCase):
    """Encode llmEmbed output shape: one item in, one item out; internal batch_size only."""
    mock, state = _embedder_for_case(case)
    embedder = LLMEmbed(model="test-model", source="ollama", **case.embedder_kwargs)
    embedder.embedder = mock

    if case.expects_exception:
        with pytest.raises(case.exception_type, match=case.exception_match):
            list(embedder(case.stream_input))
    else:
        result = list(embedder(case.stream_input))
        assert result == case.expected_yields, (
            f"{case.id}: stream yield count/shape mismatch "
            f"(got {len(result)} yields)"
        )
        if case.result_checker is not None:
            case.result_checker(result)
    assert state["batch"] == case.expected_batch_calls
    assert state["one"] == case.expected_one_calls


def test_llmembed_scalar_set_as_single_item():
    """Scalar + set_as: one dict yield with vector attached (not a list wrapper)."""
    mock, state = _make_tracking_embedder()
    embedder = LLMEmbed(
        model="test-model",
        source="ollama",
        field="text",
        set_as="vector",
    )
    embedder.embedder = mock
    item = {"text": "hello"}
    result = list(embedder([item]))
    assert len(result) == 1
    assert result[0]["text"] == "hello"
    assert result[0]["vector"] == [float(100 + ord("h"))]
    assert state["one"] == ["hello"]
    assert state["batch"] == []


def test_llmembed_dict_with_list_field_scalar_path():
    """Dict whose field is a list: scalar path stringifies it (one vector, not per string)."""
    mock, state = _make_tracking_embedder()
    embedder = LLMEmbed(
        model="test-model",
        source="ollama",
        field="texts",
        set_as="vectors",
    )
    embedder.embedder = mock
    item = {"texts": ["a", "b"]}
    result = list(embedder([item]))
    assert len(result) == 1
    assert "vectors" in result[0]
    assert isinstance(result[0]["vectors"], list)
    assert len(result[0]["vectors"]) == 1
    assert state["one"] == [str(["a", "b"])]
    assert state["batch"] == []


