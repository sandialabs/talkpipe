from typing import Optional, Annotated
import re

import numpy as np

from talkpipe import AbstractSegment, register_segment
from talkpipe.util.data_manipulation import extract_property
from talkpipe.pipe import core
from talkpipe.chatterlang import registry


@registry.register_segment("regexReplace")
@core.segment()
def regex_replace(items: Annotated[object, "Input items to transform"], pattern: Annotated[str, "Regular expression pattern to match"], replacement: Annotated[str, "Replacement string for matched patterns"], field: Annotated[str, "Field to apply transformation to. Use '_' for entire item"] = "_"):
    """Transform items by applying regex pattern replacement.

    This segment transforms items by applying a regex pattern replacement to either
    the entire item (if field="_") or a specific field of the item.

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
def fill_null(items: Annotated[object, "An iterable of dictionaries to process"], default: Annotated[str, "The default value to use for any None values not specified in kwargs"] = '', **kwargs):
    """
    Fills null (None) values in a sequence of dictionaries with specified defaults.

    This generator function processes dictionaries by replacing None values with either
    a general default value or specific values for named fields.

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
        if not isinstance(item, dict):
            raise TypeError(f"Expected a dictionary, but got {type(item)} instead")
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

    def __init__(self, num_items: Annotated[Optional[int], "Number of items to collect per batch. If None, collect all items"] = None, cumulative: Annotated[bool, "If True, batches are cumulative (growing), if False, batches are fixed-size"] = False, field: Annotated[str, "Field to extract from each item. Use '_' for the entire item"] = "_", ignoreNone: Annotated[bool, "If True, skip items whose extracted value is None"] = False):
        super().__init__()
        self.num_items = num_items
        self.cumulative = cumulative
        self.field = field
        self.ignoreNone = ignoreNone

    def transform(self, input_iter):
        """Collect items (or a field from each item) into lists (batches).

        Behavior:
        - field: If field == "_", each original item is collected. Otherwise the value
          of that field (via extract_property) is collected.
        - ignoreNone: If True, items whose extracted value is None are skipped.
        - num_items is None: All (remaining) collected values are yielded once at the end.
        - num_items is an int:
            * Values are accumulated and a list is yielded every time the count
              reaches a multiple of num_items.
            * cumulative = False: the accumulator is cleared after each yield (fixed-size batches).
            * cumulative = True: the accumulator is NOT cleared, so each yielded list
              grows (sliding cumulative window snapshots).
              (cumulative has no effect when num_items is None.)
        The transform always yields lists (copies) so downstream code can safely mutate.

        Common use: When each extracted item is a numeric vector, the yielded list
        can be turned into a matrix (e.g. np.stack(batch)) by downstream code.

        """

        if self.num_items is not None and self.num_items <= 0:
            raise ValueError("num_items must be None or a positive integer")
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
