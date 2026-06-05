"""Module for embedding text using different models"""

import logging
import re
from typing import Optional, Annotated, Iterator, Any, List, Literal

import numpy as np

from talkpipe.pipe.core import AbstractFieldSegment, is_metadata
from talkpipe.chatterlang.registry import register_segment
from talkpipe.util.data_manipulation import extract_property, assign_property
from .config import getEmbeddingAdapter, getEmbeddingSources
from .embedding_errors import is_token_overflow_error
from talkpipe.util.config import get_config
from talkpipe.util.constants import TALKPIPE_EMBEDDING_MODEL_NAME, TALKPIPE_EMBEDDING_MODEL_SOURCE

logger = logging.getLogger(__name__)

# on_token_overflow mode strings (compare via _OVERFLOW_* constants to avoid Bandit B105/B107)
_ON_TOKEN_OVERFLOW_CHOICES = ("error", "truncate", "chunk_pool")
_OVERFLOW_ERROR, _OVERFLOW_TRUNCATE, _OVERFLOW_CHUNK_POOL = _ON_TOKEN_OVERFLOW_CHOICES
_TRUNCATE_SIDE_CHOICES = ("head", "tail", "middle")

# Truncate retry tuning (not exposed on the segment in v1).
_SHRINK_RATIO = 0.2
_MIN_TRUNCATE_CHARS = 1
_MAX_TRUNCATE_ATTEMPTS = 8


def _encoded_ascii_token_floor(text: str) -> float:
    if len(text) < 80:
        return 0.0

    letters = [char for char in text if char.isascii() and char.isalpha()]
    if len(letters) < len(text) * 0.55:
        return 0.0

    vowels = sum(1 for char in letters if char in "aeiouAEIOU")
    uppercase = sum(1 for char in letters if char.isupper())
    vowel_ratio = vowels / len(letters)
    uppercase_ratio = uppercase / len(letters)
    suspicious_chars = sum(1 for char in text if char in "\\+^~[]{}|")
    suspicious_ratio = suspicious_chars / len(text)

    if suspicious_ratio >= 0.01 and uppercase_ratio >= 0.35 and vowel_ratio <= 0.30:
        return len(text) * 0.75
    return 0.0


def estimate_tokens(text: str) -> int:
    """Estimate token count without using a provider-specific tokenizer."""
    chars = len(text)
    words = len(re.findall(r"\S+", text))
    non_ascii_chars = sum(1 for char in text if not char.isascii())
    non_ascii_weighted_chars = non_ascii_chars + ((chars - non_ascii_chars) / 4)
    non_ascii_ratio = non_ascii_chars / chars if chars else 0
    non_ascii_floor = chars * 1.5 if non_ascii_ratio >= 0.05 else non_ascii_weighted_chars
    return int(
        max(
            words * 1.3,
            chars / 4,
            non_ascii_floor,
            _encoded_ascii_token_floor(text),
        )
    )


class EmbeddingTokenOverflowError(RuntimeError):
    """Raised when embedding fails due to input length and on_token_overflow is error."""


@register_segment("llmEmbed")
class LLMEmbed(AbstractFieldSegment):
    """Create embeddings from text using an embedding model.

    Accepts one stream item at a time and yields one output per item (a vector, or
    the original item with ``set_as`` updated). ``field`` and ``set_as`` follow
    :class:`~talkpipe.pipe.core.AbstractFieldSegment`. Batching is internal only
    (``batch_size``); use ``makeLists`` upstream only if another segment needs grouped
    items—not as direct input to ``llmEmbed``.

    When the provider rejects text as too long, ``on_token_overflow`` controls recovery:
    ``error`` (default), ``truncate`` (shrink and retry), or ``chunk_pool`` (split into
    ``num_chunks`` segments, embed, and mean-pool). Size text before this segment with
    upstream chunking when possible.

    ``max_estimated_tokens`` optionally truncates text before the provider call using
    a lightweight estimate, not a tokenizer. ``truncate_side`` controls both that
    proactive truncation and reactive ``on_token_overflow="truncate"`` retry behavior.
    """

    def __init__(
        self,
        model: Annotated[Optional[str], "The name of the embedding model to use"] = None,
        source: Annotated[Optional[str], "The source of the embedding model (e.g., 'ollama')"] = None,
        field: Annotated[Optional[str], "If provided, extract text from this field in the input items"] = None,
        set_as: Annotated[Optional[str], "If provided, append embeddings to input items under this field name"] = None,
        fail_on_error: Annotated[bool, "Whether to raise an error on failure or to silently ignore it"] = True,
        batch_size: Annotated[int, "Number of stream items to embed per provider API call"] = 1,
        on_token_overflow: Annotated[
            Literal["error", "truncate", "chunk_pool"],
            "When embed fails as too long: error, truncate (shrink and retry), or chunk_pool",
        ] = _OVERFLOW_ERROR,
        truncate_side: Annotated[
            Literal["head", "tail", "middle"],
            "For truncate: which portion of the string to keep when shortening",
        ] = "tail",
        num_chunks: Annotated[
            int,
            "For chunk_pool: number of contiguous segments to split overflow text into",
        ] = 2,
        max_estimated_tokens: Annotated[
            Optional[int],
            "If set, pre-truncate text to this estimated token budget before embedding",
        ] = None,
    ):
        """Initialize the embedding segment with the specified parameters.

        Raises:
            ValueError: If the specified source is not supported.
        """
        super().__init__(field=field, set_as=set_as)
        cfg = get_config()
        model = model or cfg.get(TALKPIPE_EMBEDDING_MODEL_NAME, None)
        source = source or cfg.get(TALKPIPE_EMBEDDING_MODEL_SOURCE, None)
        if source not in getEmbeddingSources():
            logger.error(
                f"Source '{source}' is not supported. Supported sources are: {getEmbeddingSources()}"
            )
            raise ValueError(
                f"Source '{source}' is not supported. Supported sources are: {getEmbeddingSources()}"
            )
        if batch_size < 1:
            raise ValueError("batch_size must be a positive integer")
        if on_token_overflow not in _ON_TOKEN_OVERFLOW_CHOICES:
            raise ValueError(
                f"on_token_overflow must be one of {_ON_TOKEN_OVERFLOW_CHOICES}, "
                f"got {on_token_overflow!r}"
            )
        if truncate_side not in _TRUNCATE_SIDE_CHOICES:
            raise ValueError(
                f"truncate_side must be one of {_TRUNCATE_SIDE_CHOICES}, got {truncate_side!r}"
            )
        if num_chunks < 2:
            raise ValueError("num_chunks must be at least 2")
        if max_estimated_tokens is not None and max_estimated_tokens < 1:
            raise ValueError("max_estimated_tokens must be a positive integer")
        self.embedder = getEmbeddingAdapter(source)(model=model)
        self.fail_on_error = fail_on_error
        self.batch_size = batch_size
        self.on_token_overflow = on_token_overflow
        self.truncate_side = truncate_side
        self.num_chunks = num_chunks
        self.max_estimated_tokens = max_estimated_tokens
        self._embedding_source = source
        self._embedding_model = model

    def process_value(self, value: Any) -> List[float]:
        """Embed one extracted field value (AbstractFieldSegment hook)."""
        text = self._truncate_to_estimated_token_budget(str(value))
        return self._embed_one_with_overflow_policy(None, text)

    def _input_value(self, item: Any) -> Any:
        """Extract the value to embed (same rule as AbstractFieldSegment)."""
        return extract_property(item, self.field) if self.field else item

    @staticmethod
    def _ensure_scalar_item(item: Any) -> None:
        if isinstance(item, list):
            raise TypeError(
                "llmEmbed does not accept list-shaped stream items; pass one item per "
                "document and use batch_size for provider batching, or flatten lists "
                "before this segment."
            )

    @staticmethod
    def _slice_text(text: str, length: int, side: str) -> str:
        if length <= 0:
            return ""
        if side == "head":
            return text[:length]
        if side == "tail":
            return text[-length:]
        if side == "middle":
            if length >= len(text):
                return text
            start = (len(text) - length) // 2
            return text[start : start + length]
        raise ValueError(f"Unknown truncate_side: {side!r}")

    def _truncate_to_estimated_token_budget(self, text: str) -> str:
        if self.max_estimated_tokens is None:
            return text
        if estimate_tokens(text) <= self.max_estimated_tokens:
            return text

        low = 0
        high = len(text)
        while low < high:
            mid = (low + high + 1) // 2
            candidate = self._slice_text(text, mid, self.truncate_side)
            if estimate_tokens(candidate) <= self.max_estimated_tokens:
                low = mid
            else:
                high = mid - 1
        return self._slice_text(text, low, self.truncate_side)

    @staticmethod
    def _split_num_chunks(text: str, num_chunks: int) -> List[str]:
        n = len(text)
        if num_chunks < 2 or n == 0:
            return [text] if text else []
        return [text[i * n // num_chunks : (i + 1) * n // num_chunks] for i in range(num_chunks)]

    @staticmethod
    def _mean_pool(vectors: List[List[float]]) -> List[float]:
        if not vectors:
            raise ValueError("Cannot mean-pool an empty list of vectors")
        arr = np.asarray(vectors, dtype=float)
        pooled = arr.mean(axis=0)
        norm = float(np.linalg.norm(pooled))
        if norm > 0:
            pooled = pooled / norm
        return pooled.tolist()

    def _wrap_token_overflow(
        self,
        exc: BaseException,
        *,
        item: Any,
        text: str,
        detail: Optional[str] = None,
    ) -> EmbeddingTokenOverflowError:
        field_part = f"field={self.field!r}, " if self.field else ""
        item_part = f"item={item!r}, " if item is not None else ""
        text_len = len(text)
        hint = (
            "Use smaller upstream chunks (e.g. splitText), "
            f"on_token_overflow='truncate', or on_token_overflow='chunk_pool' "
            f"(num_chunks={self.num_chunks})."
        )
        extra = f" {detail}" if detail else ""
        message = (
            f"Embedding input too long for {self._embedding_source}/{self._embedding_model}: "
            f"{item_part}{field_part}text_length={text_len}. {hint}{extra} "
            f"Provider error: {exc}"
        )
        return EmbeddingTokenOverflowError(message)

    def _execute_one_raw(self, text: str) -> List[float]:
        return self.embedder.execute_one(text)

    def _embed_truncate(self, item: Any, text: str) -> List[float]:
        current = text
        last_overflow: Optional[BaseException] = None
        for _ in range(_MAX_TRUNCATE_ATTEMPTS):
            try:
                return self._execute_one_raw(current)
            except Exception as exc:
                if not is_token_overflow_error(exc):
                    raise
                last_overflow = exc
                n = len(current)
                n_next = max(_MIN_TRUNCATE_CHARS, int(n * (1 - _SHRINK_RATIO)))
                if n_next >= n:
                    break
                current = self._slice_text(current, n_next, self.truncate_side)
        raise self._wrap_token_overflow(
            last_overflow or RuntimeError("truncate exhausted"),
            item=item,
            text=text,
            detail="Truncate retries exhausted.",
        )

    def _embed_chunk_pool(self, item: Any, text: str) -> List[float]:
        segments = self._split_num_chunks(text, self.num_chunks)
        if not segments:
            raise self._wrap_token_overflow(
                RuntimeError("empty text"),
                item=item,
                text=text,
            )
        try:
            if len(segments) == 1:
                vectors = [self._execute_one_raw(segments[0])]
            else:
                vectors = self.embedder.execute_batch(segments)
        except Exception as exc:
            if is_token_overflow_error(exc):
                raise self._wrap_token_overflow(
                    exc,
                    item=item,
                    text=text,
                    detail=(
                        f"chunk_pool with num_chunks={self.num_chunks} still exceeded the limit; "
                        "try a larger num_chunks or smaller upstream chunks."
                    ),
                ) from exc
            raise
        return self._mean_pool(vectors)

    def _embed_one_with_overflow_policy(self, item: Any, text: str) -> List[float]:
        try:
            return self._execute_one_raw(text)
        except Exception as exc:
            if not is_token_overflow_error(exc):
                raise
            if self.on_token_overflow == _OVERFLOW_ERROR:
                raise self._wrap_token_overflow(exc, item=item, text=text) from exc
            if self.on_token_overflow == _OVERFLOW_TRUNCATE:
                return self._embed_truncate(item, text)
            return self._embed_chunk_pool(item, text)

    def _yield_results(self, item: Any, results: List[Any]) -> Iterator[Any]:
        """Emit results using AbstractFieldSegment assign/yield semantics."""
        for result in results:
            if self.set_as:
                assign_property(item, self.set_as, result)
                yield item
            else:
                yield result

    def _embed_items_pair(self, items: List[Any], texts: List[str]) -> Iterator[Any]:
        for item, text in zip(items, texts):
            try:
                vector = self._embed_one_with_overflow_policy(item, text)
            except EmbeddingTokenOverflowError:
                raise
            except Exception as exc:
                logger.error(f"Error during embedding: {exc}")
                if self.fail_on_error:
                    raise
                continue
            yield from self._yield_results(item, [vector])

    def _embed_buffered(self, items: List[Any], texts: List[str]) -> Iterator[Any]:
        if not items or not texts:
            return
        logger.debug(f"Embedding batch of {len(texts)} texts")
        if len(texts) == 1:
            yield from self._embed_items_pair(items, texts)
            return
        try:
            vectors = self.embedder.execute_batch(texts)
            for item, vector in zip(items, vectors):
                yield from self._yield_results(item, [vector])
        except Exception as e:
            logger.info(f"Error during batch embedding: {e}")
            yield from self._embed_items_pair(items, texts)

    def transform(self, input_iter):
        """Transform one stream item at a time; batching is internal only."""
        buffer_items: List[Any] = []
        buffer_texts: List[str] = []

        def flush_buffer() -> Iterator[Any]:
            if not buffer_items:
                return
            yield from self._embed_buffered(buffer_items, buffer_texts)
            buffer_items.clear()
            buffer_texts.clear()

        for item in input_iter:
            if is_metadata(item):
                yield item
                continue

            self._ensure_scalar_item(item)
            logging.debug(f"Processing input item: {item}")
            text = self._truncate_to_estimated_token_budget(str(self._input_value(item)))
            logging.debug(f"Embedding text: {text}")

            if self.batch_size <= 1:
                yield from self._embed_buffered([item], [text])
            else:
                buffer_items.append(item)
                buffer_texts.append(text)
                if len(buffer_items) >= self.batch_size:
                    yield from flush_buffer()

        yield from flush_buffer()
