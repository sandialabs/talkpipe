"""Tests for llmEmbed on_token_overflow (reactive token limit handling)."""

import pytest
from unittest.mock import Mock

from talkpipe.llm.embedding import LLMEmbed, EmbeddingTokenOverflowError
from talkpipe.llm.embedding_errors import is_token_overflow_error

TOKEN_OVERFLOW = RuntimeError("maximum context length exceeded")


def test_is_token_overflow_error_recognizes_common_messages():
    assert is_token_overflow_error(TOKEN_OVERFLOW)
    assert is_token_overflow_error(RuntimeError("input is too long for model"))
    assert not is_token_overflow_error(RuntimeError("connection reset"))


def _overflow_if_long(max_len: int = 10):
    """Embed succeeds when len(text) <= max_len; otherwise token overflow."""

    def execute_one(text: str):
        if len(text) > max_len:
            raise TOKEN_OVERFLOW
        return [float(len(text))]

    def execute_batch(texts):
        for t in texts:
            if len(t) > max_len:
                raise TOKEN_OVERFLOW
        return [[float(len(t))] for t in texts]

    mock = Mock()
    mock.execute_one = Mock(side_effect=execute_one)
    mock.execute_batch = Mock(side_effect=execute_batch)
    return mock


# --- Individual (batch_size=1) ---


def test_on_token_overflow_error_single_item():
    mock = _overflow_if_long(max_len=10)
    embedder = LLMEmbed(
        model="test-model",
        source="ollama",
        on_token_overflow="error",
    )
    embedder.embedder = mock
    long_text = "x" * 15
    with pytest.raises(EmbeddingTokenOverflowError, match="too long"):
        list(embedder([long_text]))
    assert mock.execute_one.call_count == 1


def test_on_token_overflow_error_single_item_with_field():
    mock = _overflow_if_long(max_len=10)
    embedder = LLMEmbed(
        model="test-model",
        source="ollama",
        field="text",
        set_as="vector",
        on_token_overflow="error",
    )
    embedder.embedder = mock
    item = {"id": "doc-b", "text": "y" * 20}
    with pytest.raises(EmbeddingTokenOverflowError, match="doc-b"):
        list(embedder([item]))


def test_on_token_overflow_truncate_single_item():
    mock = _overflow_if_long(max_len=10)
    embedder = LLMEmbed(
        model="test-model",
        source="ollama",
        on_token_overflow="truncate",
        truncate_side="tail",
    )
    embedder.embedder = mock
    long_text = "START" + "x" * 12  # 17 chars
    result = list(embedder([long_text]))
    assert len(result) == 1
    # 17 -> 13 -> 10 (each step keeps 80% by char count)
    assert result[0] == [10.0]
    assert mock.execute_one.call_count >= 2
    last_call = mock.execute_one.call_args_list[-1][0][0]
    assert len(last_call) == 10
    assert last_call == long_text[-10:]
    assert not last_call.startswith("START")


def test_on_token_overflow_chunk_pool_single_item():
    batch_calls = []

    def execute_one(text: str):
        if len(text) > 10:
            raise TOKEN_OVERFLOW
        return [float(len(text))]

    def execute_batch(texts):
        batch_calls.append(list(texts))
        for t in texts:
            if len(t) > 10:
                raise TOKEN_OVERFLOW
        return [[float(len(t))] for t in texts]

    mock = Mock()
    mock.execute_one = Mock(side_effect=execute_one)
    mock.execute_batch = Mock(side_effect=execute_batch)

    embedder = LLMEmbed(
        model="test-model",
        source="ollama",
        on_token_overflow="chunk_pool",
        num_chunks=2,
    )
    embedder.embedder = mock
    long_text = "a" * 20  # num_chunks=2 -> two segments of 10 (max_len=10 is ok)
    result = list(embedder([long_text]))
    assert len(result) == 1
    assert len(result[0]) == 1
    assert batch_calls == [["a" * 10, "a" * 10]]
    mock.execute_one.assert_called_once_with(long_text)


# --- Batch (batch_size > 1) ---


def test_on_token_overflow_error_batch_identifies_bad_item():
    mock = _overflow_if_long(max_len=10)
    embedder = LLMEmbed(
        model="test-model",
        source="ollama",
        batch_size=3,
        on_token_overflow="error",
    )
    embedder.embedder = mock
    items = ["short", "m" * 15, "tiny"]
    with pytest.raises(EmbeddingTokenOverflowError, match="text_length=15"):
        list(embedder(items))
    mock.execute_batch.assert_called_once()
    assert mock.execute_one.call_count >= 1


def test_on_token_overflow_truncate_batch_recovers_middle_item():
    mock = _overflow_if_long(max_len=10)
    embedder = LLMEmbed(
        model="test-model",
        source="ollama",
        batch_size=3,
        on_token_overflow="truncate",
        truncate_side="tail",
    )
    embedder.embedder = mock
    items = ["aaa", "b" * 14, "ccc"]
    result = list(embedder(items))
    # 14 chars -> 11 (still too long) -> 8 (ok)
    assert result == [[3.0], [8.0], [3.0]]
    mock.execute_batch.assert_called_once()


def test_on_token_overflow_chunk_pool_batch_recovers_middle_item():
    batch_calls = []

    def execute_one(text: str):
        if len(text) > 10:
            raise TOKEN_OVERFLOW
        return [float(len(text))]

    def execute_batch(texts):
        texts = list(texts)
        batch_calls.append(texts)
        if len(texts) == 3 and any(len(t) > 10 for t in texts):
            raise TOKEN_OVERFLOW
        return [[float(len(t))] for t in texts]

    mock = Mock()
    mock.execute_one = Mock(side_effect=execute_one)
    mock.execute_batch = Mock(side_effect=execute_batch)

    embedder = LLMEmbed(
        model="test-model",
        source="ollama",
        batch_size=3,
        on_token_overflow="chunk_pool",
        num_chunks=2,
    )
    embedder.embedder = mock
    items = ["ok", "z" * 16, "ok2"]
    result = list(embedder(items))
    assert len(result) == 3
    assert all(isinstance(row, list) and len(row) == 1 for row in result)
    assert batch_calls[0] == items
    assert batch_calls[-1] == ["z" * 8, "z" * 8]
    assert "".join(batch_calls[-1]) == "z" * 16


def test_num_chunks_must_be_at_least_two():
    with pytest.raises(ValueError, match="num_chunks"):
        LLMEmbed(model="test-model", source="ollama", num_chunks=1)
