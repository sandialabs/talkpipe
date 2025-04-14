"""Module for embedding text using different models"""

from typing import Optional
import logging
from talkpipe.llm.embedding_adapters import OllamaEmbedderAdapter
from talkpipe.pipe.core import AbstractSegment
from talkpipe.chatterlang.registry import register_segment
from talkpipe.util.data_manipulation import extract_property
from .config import getEmbeddingAdapter, getEmbeddingSources
from talkpipe.util.config import get_config

logger = logging.getLogger(__name__)

@register_segment("llmEmbed")
class LLMEmbed(AbstractSegment):
    """Read strings from the input stream and emit an embedding for each string using a language model.
    
    This segment creates vector embeddings from text using the specified embedding model.
    It can extract text from a specific field in structured data or process the input directly.
    
    Attributes:
        embedder: The embedding adapter instance that performs the actual embedding.
        field: Optional field name to extract text from structured input.
        append_as: Optional field name to append embeddings to the original item.
    """
    def __init__(
            self, 
            model: str = None, 
            source: str = None,
            field: Optional[str] = None,
            append_as: Optional[str] = None,
            ):
        """Initialize the embedding segment with the specified parameters.
        
        Args:
            model: The name of the embedding model to use. If None, uses the default from config.
            source: The source of the embedding model (e.g., 'ollama'). If None, uses the default from config.
            field: If provided, extract text from this field in the input items.
            append_as: If provided, append embeddings to input items under this field name.
        
        Raises:
            ValueError: If the specified source is not supported.
        """
        super().__init__()
        cfg = get_config()
        model = model or cfg.get("default_embedding_model_name", None)
        source = source or cfg.get("default_embedding_source", None)
        if source not in getEmbeddingSources():
            logger.error(f"Source '{source}' is not supported. Supported sources are: {getEmbeddingSources()}")
            raise ValueError(f"Source '{source}' is not supported. Supported sources are: {getEmbeddingSources()}")
        self.embedder = getEmbeddingAdapter(source)(model_name=model)
        self.field = field
        self.append_as = append_as

    def transform(self, input_iter):
        """Transform input items by creating embeddings.
        
        Args:
            input_iter: Iterator of input items to process.
            
        Yields:
            If append_as is specified, yields the original items with embeddings added.
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
            ans = self.embedder.execute(str(text))
            logger.debug(f"Received embedding: {ans}")

            if self.append_as is not None:
                logger.debug(f"Appending embedding to field {self.append_as}")
                item[self.append_as] = ans
                yield item
            else:
                logger.debug("Yielding embedding directly")
                yield ans
