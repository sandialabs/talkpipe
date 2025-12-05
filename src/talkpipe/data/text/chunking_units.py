from typing import Annotated, Iterator, Union, Callable
import logging
from talkpipe.data.text.operations import shingle_generator
from talkpipe.pipe.core import field_segment, AbstractSegment
from talkpipe.chatterlang import register_segment
from talkpipe.util.data_manipulation import assign_property

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
        emit_detail: If True, emits a dictionary with text and paragraph numbers (default False)
    """
    def __init__(self,
                 field: Annotated[str, "Field containing string.  If not, use entire item"] = None,
                 set_as: Annotated[str, "Field name to set/append the result as (optional)"] = None,
                 key: Annotated[str, "Key to identify the segment (optional)"] = None,
                 delimiter: Annotated[str, "Delimiter to join chunks (default is a single space)"] = " ",
                 shingle_size: Annotated[int, "Size threshold - number of chunks (count) or min char length (length)"] = 3,
                 overlap: Annotated[int, "Number of chunks that overlap between consecutive shingles (default 0)"] = 0,
                 size_mode: Annotated[str, "Either 'count' (count chunks) or 'length' (measure char length)"] = "count",
                 emit_detail: Annotated[bool, "If True, emits dict with text (called 'text') and paragraph numbers (called 'first_paragraph' and 'last_paragraph') (default False)"] = False):
        super().__init__()
        self.shingle_size = shingle_size
        self.overlap = overlap
        self.key = key
        self.field = field
        self.set_as = set_as
        self.delimiter = delimiter
        self.size_mode = size_mode
        self.emit_detail = emit_detail

    def transform(self, input_iter):
        """Transforms the input iterator by segmenting text into shingles."""

        for result in shingle_generator(
            input_iter,
            self.field,
            self.key,
            self.shingle_size,
            self.overlap,
            self.delimiter,
            self.size_mode,
            include_paragraph_numbers=self.emit_detail
        ):
            if self.emit_detail:
                item, shingle_text, first_para, last_para = result
                output = {
                    "text": shingle_text,
                    "first_paragraph": first_para,
                    "last_paragraph": last_para
                }
            else:
                item, shingle_text = result
                output = shingle_text

            if self.set_as:
                new_item = item.copy() if item else {}
                assign_property(new_item, self.set_as, output)
                yield new_item
            else:
                yield output
