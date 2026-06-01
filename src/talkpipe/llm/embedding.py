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
    """Read strings from the input stream and emit an embedding for each string using a language model.
    
    This segment creates vector embeddings from text using the specified embedding model.
    It can extract text from a specific field in structured data or process the input directly.
    
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

    def _text_from_item(self, item: Any) -> str:
        if self.field is not None:
            return str(extract_property(item, self.field))
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
        if not list_item:
            return
        items = list(list_item)
        texts = [self._text_from_item(item) for item in items]
        yield from self._embed_and_emit(items, texts)

    def transform(self, input_iter):
        """Transform input items by creating embeddings.
        
        Args:
            input_iter: Iterator of input items to process.
            
        Yields:
            If set_as is specified, yields the original items with embeddings added.
            Otherwise, yields the embeddings directly.
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
