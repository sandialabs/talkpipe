from typing import Annotated
import logging
from typing import Annotated, Iterator, Union
from talkpipe.pipe.core import field_segment, AbstractSegment
from talkpipe.chatterlang import register_segment
from talkpipe.util.data_manipulation import extract_property

logger = logging.getLogger(__name__)


@register_segment("splitText")
@field_segment(multi_emit=True)
def splitText(text: Annotated[str, "Text to split into sentences"], 
    criteria: Annotated[
        Union[str, int], 
        "Criteria for splitting text. If string, split by this string. "
        "If int, split by this many characters."
    ]
) -> Iterator[str]:
    """Splits the input text into a list of text chunks.

    Returns:
        iterator[str]: A list of text chunks extracted from the input text.
    """
    if isinstance(criteria, str):
        logger.debug(f"Splitting text by string: {criteria}")
        yield from text.split(criteria)
    elif isinstance(criteria, int):
        logger.debug(f"Splitting text into chunks of size: {criteria}")
        yield from (text[i:i + criteria] for i in range(0, len(text), criteria))
    else:
        raise ValueError("Criteria must be either a string or an integer.")

@register_segment("shingleText")
class ShingleText(AbstractSegment):
    """Segments text into overlapping shingles of a specified size.

    Args:
        field: The field to extract from each item (optional)
        set_as: The field name to set/append the result as (optional)
        shingle_size: The size of each shingle (number of words)
        overlap: The number of words that overlap between consecutive shingles
    """
    def __init__(self, 
                 field: Annotated[str, "Field containing string.  If not, use entire item"] = None, 
                 set_as: Annotated[str, "Field name to set/append the result as (optional)"] = None, 
                 key: Annotated[str, "Key to identify the segment (optional)"] = None,
                 delimiter: Annotated[str, "Delimiter to join chunks (default is a single space)"] = " ",
                 shingle_size: Annotated[int, "Size of each shingle (number of words)"] = 3, 
                 overlap: Annotated[int, "Number of words that overlap between consecutive shingles (default 0)"] = 0):
        super().__init__()
        self.shingle_size = shingle_size
        self.overlap = overlap
        self.key = key
        self.field = field
        self.set_as = set_as
        self.delimiter = delimiter

    def transform(self, input_iter):
        """Transforms the input iterator by segmenting text into shingles."""
        shingles = []
        current_key = None
        last_item = None
        
        for item in input_iter:
            text = extract_property(item, self.field) if self.field else item
            
            # Reset shingles for a new key
            if self.key:
                item_key = extract_property(item, self.key)
                if current_key is not None and item_key != current_key:
                    if shingles and (len(shingles) == self.shingle_size or self.overlap == 0):
                        yield self._create_result(shingles, last_item)
                    shingles = []
                current_key = item_key
            
            last_item = item
            shingles.append(text)
            
            # Emit complete shingle
            if len(shingles) == self.shingle_size:
                yield self._create_result(shingles, last_item)
                shingles = shingles[-self.overlap:] if self.overlap > 0 else []
        
        # Emit final shingle if appropriate
        if shingles and (len(shingles) == self.shingle_size or self.overlap == 0):
            yield self._create_result(shingles, last_item)

    def _create_result(self, shingles, item):
        """Helper to create the result from shingles."""
        result = self.delimiter.join(shingles)
        if self.set_as:
            new_item = item.copy() if item else {}
            new_item[self.set_as] = result
            return new_item
        return result
