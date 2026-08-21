"""Draining segments: gather the whole stream into one list or DataFrame."""

from collections.abc import Iterable, Iterator
from typing import Any

import pandas as pd

import talkpipe.chatterlang.registry as registry
from talkpipe.pipe.core import (
    AbstractSegment,
)


@registry.register_segment(name="toDataFrame")
class ToDataFrame(AbstractSegment[Any, Any]):
    """Drain all items from the input stream and emit a single DataFrame.

    The input data stream should be composed of dictionaries, where each
    dictionary represents a row in the DataFrame.
    """

    def transform(self, input_iter: Iterable[Any]) -> Iterator[Any]:
        """Create a DataFrame from the input data.

        This segment empties the generator before creating the DataFrame.

        Args:
            input_iter (Iterable): The input data
        """
        data = list(input_iter)
        if len(data) > 0 and isinstance(data[0], dict):
            yield pd.DataFrame(data)


@registry.register_segment(name="toList")
class ToList(AbstractSegment[Any, Any]):
    """Drains the input stream and emits a list of all items."""

    def transform(self, input_iter: Iterable[Any]) -> Iterator[Any]:
        yield list(input_iter)
