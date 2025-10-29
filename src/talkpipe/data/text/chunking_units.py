from typing import Annotated, Iterator, Union, Callable
import logging
from talkpipe.data.text.operations import shingle_generator
from talkpipe.pipe.core import field_segment, AbstractSegment
from talkpipe.chatterlang import register_segment

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
        key: Key field to identify groups (optional)
        delimiter: Delimiter to join chunks (default is a single space)
        shingle_size: Size threshold - number of chunks (count mode) or minimum character length (length mode)
        overlap: Number of chunks that overlap between consecutive shingles (default 0)
        size_mode: Either 'count' to count chunks or 'length' to measure character length (default 'count')
    """
    def __init__(self,
                 field: Annotated[str, "Field containing string.  If not, use entire item"] = None,
                 set_as: Annotated[str, "Field name to set/append the result as (optional)"] = None,
                 key: Annotated[str, "Key to identify the segment (optional)"] = None,
                 delimiter: Annotated[str, "Delimiter to join chunks (default is a single space)"] = " ",
                 shingle_size: Annotated[int, "Size threshold - number of chunks (count) or min char length (length)"] = 3,
                 overlap: Annotated[int, "Number of chunks that overlap between consecutive shingles (default 0)"] = 0,
                 size_mode: Annotated[str, "Either 'count' (count chunks) or 'length' (measure char length)"] = "count"):
        super().__init__()
        self.shingle_size = shingle_size
        self.overlap = overlap
        self.key = key
        self.field = field
        self.set_as = set_as
        self.delimiter = delimiter
        self.size_mode = size_mode

    def transform(self, input_iter):
        """Transforms the input iterator by segmenting text into shingles."""

        for item, shingle_text in shingle_generator(
            input_iter,
            self.field,
            self.key,
            self.shingle_size,
            self.overlap,
            self.delimiter,
            self.size_mode
        ):
            if self.set_as:
                new_item = item.copy() if item else {}
                new_item[self.set_as] = shingle_text
                yield new_item
            else:
                yield shingle_text
