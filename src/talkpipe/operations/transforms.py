from typing import Optional
import re

import numpy as np

from talkpipe import AbstractSegment, register_segment
from talkpipe.util.data_manipulation import extract_property
from talkpipe.pipe import core
from talkpipe.chatterlang import registry


@registry.register_segment("regexReplace")
@core.segment()
def regex_replace(items, pattern, replacement, field="_"):
    """Transform items by applying regex pattern replacement.

    This segment transforms items by applying a regex pattern replacement to either
    the entire item (if field="_") or a specific field of the item.

    Args:
        items (Iterable): Input items to transform.
        pattern (str): Regular expression pattern to match.
        replacement (str): Replacement string for matched patterns.
        field (str, optional): Field to apply transformation to. Use "_" for entire item. Defaults to "_".

    Yields:
        Union[str, dict]: Transformed items. Returns string if field="_", otherwise returns modified item dict.

    Raises:
        TypeError: If extracted value is not a string or if item is not subscriptable when field != "_".

    Examples:
        >>> list(regex_replace(["hello world"], r"world", "everyone"))
        ['hello everyone']
        
        >>> list(regex_replace([{"text": "hello world"}], r"world", "everyone", field="text"))
        [{'text': 'hello everyone'}]
    """
    for item in items:
        if "." in field:
            raise ValueError("Nested fields are not supported for regex_replace because it cannot re-insert the changed value with a nested field.")
        extracted = extract_property(item, field)
        if not isinstance(extracted, str):
            raise TypeError(f"Expected a string, but got {type(extracted)} instead.")
        modified = re.sub(pattern, replacement, extracted)
        if field == "_":
            yield modified
        else:
            try:
                item[field] = modified
                yield item
            except TypeError:
                raise TypeError(f"Expected something assignable using square brackets, but got {type(item)} instead.")

@registry.register_segment("fillNull")
@core.segment()
def fill_null(items, default='', **kwargs):
    """
    Fills null (None) values in a sequence of dictionaries with specified defaults.

    This generator function processes dictionaries by replacing None values with either
    a general default value or specific values for named fields.

    Args:
        items: An iterable of dictionaries to process.
        default (str, optional): The default value to use for any None values not 
            specified in kwargs. Defaults to ''.
        **kwargs: Field-specific default values. Each keyword argument specifies a
            field name and the default value to use for that field.

    Yields:
        dict: The processed dictionary with None values replaced by defaults.

    Raises:
        AssertionError: If any item in the input is not a dictionary.
        TypeError: If any item doesn't support item assignment using square brackets.

    Examples:
        >>> data = [{'a': None, 'b': 1}, {'a': 2, 'b': None}]
        >>> list(fill_null(data, default='N/A'))
        [{'a': 'N/A', 'b': 1}, {'a': 2, 'b': 'N/A'}]
        
        >>> list(fill_null(data, b='EMPTY'))
        [{'a': None, 'b': 1}, {'a': 2, 'b': 'EMPTY'}]
    """
    for item in items:
        assert isinstance(item, dict), f"Expected a dictionary, but got {type(item)} instead"
        for k in item:
            if item[k] is None and k not in kwargs:
                item[k] = default
        for field, value in kwargs.items():
            try:
                if field not in item or item[field] is None:
                    item[field] = value
            except TypeError:
                raise TypeError(f"Expected something assignable using square brackets, but got {type(item)} instead.")
        yield item


@register_segment("makeLists")
class MakeLists(AbstractSegment):

    def __init__(self, num_items:Optional[int]=None, cumulative:bool = False, field:str = "_", ignoreNone:bool = False):
        super().__init__()
        self.num_items = num_items
        self.cumulative = cumulative
        self.field = field
        self.ignoreNone = ignoreNone

    def transform(self, input_iter):
        """Create a matrix from the input iterator.  

        Each item in the input iterator is a vector. The matrix is created by stacking 
        the vectors vertically.  num_vectors is not None, then the matrix will be emitted
        after all items have been received.  If it is an integer, then the matrix will be emitted
        after num_vectors icreateMatrixtems have been received.  If cumulative is False, the matrix will be
        reset after it is emitted.  If True, the matrix will be cumulative and will not be reset.
        Note that cumulative has no effect if num_vectors is None. 
        """

        assert self.num_items is None or self.num_items > 0, "num_vectors must be None or a positive integer"
        accumulated = []
        for datum in input_iter:
            item = extract_property(datum, self.field)
            if item is None and self.ignoreNone:
                continue
            accumulated.append(item)

            if self.num_items is not None and len(accumulated)>0 and len(accumulated) % self.num_items == 0:
                ans = accumulated.copy()
                if not self.cumulative:
                    accumulated = []
                yield ans
        if len(accumulated)>0:
            yield accumulated.copy()
