"""Module for embedding text using different models"""

from typing import Optional, Annotated, Iterator, Any, List
import logging
from talkpipe.pipe.core import AbstractSegment
from talkpipe.chatterlang.registry import register_segment
from talkpipe.util.data_manipulation import extract_property, assign_property
from .config import getEmbeddingAdapter, getEmbeddingSources
from talkpipe.util.config import get_config
from talkpipe.util.constants import TALKPIPE_EMBEDDING_MODEL_NAME, TALKPIPE_EMBEDDING_MODEL_SOURCE

logger = logging.getLogger(__name__)

@register_segment("llmEmbed")
class LLMEmbed(AbstractSegment):
    """Create embeddings from text using an embedding model.

    Scalar stream items produce one output per item (a vector, or the item with
    ``set_as`` updated). List-shaped stream items (e.g. from ``makeLists``) produce
    one list-shaped output: a list of vectors, or the same list with ``set_as`` set
    on each element.
    
    Attributes:
        embedder: The embedding adapter instance that performs the actual embedding.
        field: Optional field name to extract text from structured input.
        set_as: Optional field name to append embeddings to the original item.
    """
    def __init__(
            self, 
            model: Annotated[Optional[str], "The name of the embedding model to use"] = None, 
            source: Annotated[Optional[str], "The source of the embedding model (e.g., 'ollama')"] = None,
            field: Annotated[Optional[str], "If provided, extract text from this field in the input items"] = None,
            set_as: Annotated[Optional[str], "If provided, append embeddings to input items under this field name"] = None,
            fail_on_error: Annotated[bool, "Whether to raise an error on failure or to silently ignore it"] = True,
            batch_size: Annotated[int, "Number of texts to embed per provider call when items are scalars"] = 1,
            ):
        """Initialize the embedding segment with the specified parameters.
        
        Raises:
            ValueError: If the specified source is not supported.
        """
        super().__init__()
        cfg = get_config()
        model = model or cfg.get(TALKPIPE_EMBEDDING_MODEL_NAME, None)
        source = source or cfg.get(TALKPIPE_EMBEDDING_MODEL_SOURCE, None)
        if source not in getEmbeddingSources():
            logger.error(f"Source '{source}' is not supported. Supported sources are: {getEmbeddingSources()}")
            raise ValueError(f"Source '{source}' is not supported. Supported sources are: {getEmbeddingSources()}")
        if batch_size < 1:
            raise ValueError("batch_size must be a positive integer")
        self.embedder = getEmbeddingAdapter(source)(model=model)
        self.field = field
        self.set_as = set_as
        self.fail_on_error = fail_on_error
        self.batch_size = batch_size

    def _text_from_item(self, item: Any, *, fail_on_missing: bool = False) -> str:
        if self.field is not None:
            return str(
                extract_property(item, self.field, fail_on_missing=fail_on_missing)
            )
        return str(item)

    def _yield_embedded(
        self, items: List[Any], vectors: List[List[float]]
    ) -> Iterator[Any]:
        for item, ans in zip(items, vectors):
            logger.debug(f"Received embedding: {ans}")
            if self.set_as is not None:
                logger.debug(f"Appending embedding to field {self.set_as}")
                assign_property(item, self.set_as, ans)
                yield item
            else:
                logger.debug("Yielding embedding directly")
                yield ans

    def _yield_list_output(
        self, items: List[Any], vectors: List[List[float]]
    ) -> Iterator[Any]:
        if self.set_as is not None:
            for item, vec in zip(items, vectors):
                logger.debug(f"Appending embedding to field {self.set_as}")
                assign_property(item, self.set_as, vec)
            yield items
        else:
            yield vectors

    def _vectors_for_texts(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        if len(texts) == 1:
            return [self.embedder.execute_one(texts[0])]
        return self.embedder.execute_batch(texts)

    def _embed_and_emit(self, items: List[Any], texts: List[str]) -> Iterator[Any]:
        if not items or not texts:
            return
        logger.debug(f"Embedding batch of {len(texts)} texts")
        try:
            vectors = self._vectors_for_texts(texts)
            yield from self._yield_embedded(items, vectors)
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
                    ans = self.embedder.execute_one(text)
                except Exception as item_error:
                    logger.error(f"Error during embedding: {item_error}")
                    continue
                yield from self._yield_embedded([item], [ans])

    def _embed_list_item(self, list_item: list) -> Iterator[Any]:
        if self.field is not None:
            raise ValueError(
                "llmEmbed 'field' cannot be used when the stream item is a list; "
                "the list object has no such property. Use makeLists to collect text "
                "into a list of strings and omit 'field', or pass scalar items with "
                "'field' set on each item."
            )
        items = list(list_item)
        if not items:
            yield []
            return
        texts = [self._text_from_item(item) for item in items]
        logger.debug(f"Embedding list input of {len(texts)} texts")
        try:
            vectors = self._vectors_for_texts(texts)
            yield from self._yield_list_output(items, vectors)
        except Exception as e:
            logger.error(f"Error during list batch embedding: {e}")
            if self.fail_on_error:
                raise
            logger.warning(
                "List batch embedding failed; falling back to per-item embedding"
            )
            succeeded_items: List[Any] = []
            succeeded_vectors: List[List[float]] = []
            for item, text in zip(items, texts):
                try:
                    succeeded_vectors.append(self.embedder.execute_one(text))
                    succeeded_items.append(item)
                except Exception as item_error:
                    logger.error(f"Error during embedding: {item_error}")
            if not succeeded_items:
                yield []
                return
            yield from self._yield_list_output(succeeded_items, succeeded_vectors)

    def transform(self, input_iter):
        """Transform input items by creating embeddings.
        
        Args:
            input_iter: Iterator of input items to process.
            
        Yields:
            For scalar items: one embedding (or item with ``set_as``) per input.
            For list items: one list of embeddings (or one list of updated items).
        """
        buffer_items: List[Any] = []
        buffer_texts: List[str] = []

        def flush_buffer() -> Iterator[Any]:
            if not buffer_items:
                return
            yield from self._embed_and_emit(buffer_items, buffer_texts)
            buffer_items.clear()
            buffer_texts.clear()

        for item in input_iter:
            logging.debug(f"Processing input item: {item}")
            if isinstance(item, list):
                yield from flush_buffer()
                yield from self._embed_list_item(item)
                continue

            text = self._text_from_item(item)
            logging.debug(f"Embedding text: {text}")

            if self.batch_size <= 1:
                yield from self._embed_and_emit([item], [text])
            else:
                buffer_items.append(item)
                buffer_texts.append(text)
                if len(buffer_items) >= self.batch_size:
                    yield from flush_buffer()

        yield from flush_buffer()
