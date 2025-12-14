"""Module for embedding text using different models"""

from typing import Optional, Annotated
import logging
from talkpipe.llm.embedding_adapters import OllamaEmbedderAdapter
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
            fail_on_error: Annotated[bool, "Whether to raise an error on failure or to silently ignore it"] = True
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
        self.embedder = getEmbeddingAdapter(source)(model=model)
        self.field = field
        self.set_as = set_as
        self.fail_on_error = fail_on_error

    def transform(self, input_iter):
        """Transform input items by creating embeddings.
        
        Args:
            input_iter: Iterator of input items to process.
            
        Yields:
            If set_as is specified, yields the original items with embeddings added.
            Otherwise, yields the embeddings directly.
        """
        for item in input_iter:
            logging.debug(f"Processing input item: {item}")
            if self.field is not None:
                text = extract_property(item, self.field)
                logging.debug(f"Extracted text from field {self.field}: {text}")
            else:
                text = item
                logging.debug(f"Using item as text: {text}")

            logger.debug(f"Embedding text: {text}")
            try:
                ans = self.embedder.execute(str(text))
            except Exception as e:
                logger.error(f"Error during embedding: {e}")
                if self.fail_on_error:
                    raise e
                else:
                    continue
            logger.debug(f"Received embedding: {ans}")

            if self.set_as is not None:
                logger.debug(f"Appending embedding to field {self.set_as}")
                assign_property(item, self.set_as, ans)
                yield item
            else:
                logger.debug("Yielding embedding directly")
                yield ans
