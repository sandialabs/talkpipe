"""Module for embedding text using different models"""

from typing import Optional, Annotated, Iterator, Any, List
import logging

from talkpipe.pipe.core import AbstractFieldSegment, is_metadata
from talkpipe.chatterlang.registry import register_segment
from talkpipe.util.data_manipulation import extract_property, assign_property
from .config import getEmbeddingAdapter, getEmbeddingSources
from talkpipe.util.config import get_config
from talkpipe.util.constants import TALKPIPE_EMBEDDING_MODEL_NAME, TALKPIPE_EMBEDDING_MODEL_SOURCE

logger = logging.getLogger(__name__)


@register_segment("llmEmbed")
class LLMEmbed(AbstractFieldSegment):
    """Create embeddings from text using an embedding model.

    Accepts one stream item at a time and yields one output per item (a vector, or
    the original item with ``set_as`` updated). ``field`` and ``set_as`` follow
    :class:`~talkpipe.pipe.core.AbstractFieldSegment`. Batching is internal only
    (``batch_size``); use ``makeLists`` upstream only if another segment needs grouped
    items—not as direct input to ``llmEmbed``.
    """

    def __init__(
        self,
        model: Annotated[Optional[str], "The name of the embedding model to use"] = None,
        source: Annotated[Optional[str], "The source of the embedding model (e.g., 'ollama')"] = None,
        field: Annotated[Optional[str], "If provided, extract text from this field in the input items"] = None,
        set_as: Annotated[Optional[str], "If provided, append embeddings to input items under this field name"] = None,
        fail_on_error: Annotated[bool, "Whether to raise an error on failure or to silently ignore it"] = True,
        batch_size: Annotated[int, "Number of stream items to embed per provider API call"] = 1,
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
        self.embedder = getEmbeddingAdapter(source)(model=model)
        self.fail_on_error = fail_on_error
        self.batch_size = batch_size

    def process_value(self, value: Any) -> List[float]:
        """Embed one extracted field value (AbstractFieldSegment hook)."""
        return self.embedder.execute_one(str(value))

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

    def _yield_results(self, item: Any, results: List[Any]) -> Iterator[Any]:
        """Emit results using AbstractFieldSegment assign/yield semantics."""
        for result in results:
            if self.set_as:
                assign_property(item, self.set_as, result)
                yield item
            else:
                yield result

    def _vectors_for_texts(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        if len(texts) == 1:
            return [self.process_value(texts[0])]
        return self.embedder.execute_batch(texts)

    def _embed_buffered(self, items: List[Any], texts: List[str]) -> Iterator[Any]:
        if not items or not texts:
            return
        logger.debug(f"Embedding batch of {len(texts)} texts")
        try:
            vectors = self._vectors_for_texts(texts)
            for item, vector in zip(items, vectors):
                yield from self._yield_results(item, [vector])
        except Exception as e:
            logger.error(f"Error during batch embedding: {e}")
            if self.fail_on_error:
                raise
            if len(texts) == 1:
                return
            logger.warning(
                "Batch embedding failed; falling back to per-item embedding"
            )
            for item, text in zip(items, texts):
                try:
                    vector = self.process_value(text)
                except Exception as item_error:
                    logger.error(f"Error during embedding: {item_error}")
                    continue
                yield from self._yield_results(item, [vector])

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
            text = str(self._input_value(item))
            logging.debug(f"Embedding text: {text}")

            if self.batch_size <= 1:
                yield from self._embed_buffered([item], [text])
            else:
                buffer_items.append(item)
                buffer_texts.append(text)
                if len(buffer_items) >= self.batch_size:
                    yield from flush_buffer()

        yield from flush_buffer()
