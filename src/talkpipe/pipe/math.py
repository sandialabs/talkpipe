"""Math operations for pipe: random numbers, ranges, scaling, and comparison filters.

Provides sources (randomInts, range) and segments (scale, eq, neq, gt, gte, lt, lte)
for numeric pipelines.
"""
from typing import Iterable, Union, Callable, Any, Annotated
from numpy import random
from talkpipe.pipe import core
from talkpipe.chatterlang import registry
from talkpipe.util.data_manipulation import extract_property

@registry.register_source(name="randomInts")
@core.source(n=10, lower=0, upper=100)
def randomInts(
    n: Annotated[int, "Number of random integers to generate"], 
    lower: Annotated[int, "Lower bound (inclusive)"], 
    upper: Annotated[int, "Upper bound (exclusive)"]
) -> Iterable[int]:
    """Generate n random integers between lower and upper."""
    yield from random.randint(lower, upper, n)

@registry.register_segment(name="scale")
@core.segment(multiplier=2)
def scale(
    items: Iterable[Union[int, float]], 
    multiplier: Annotated[Union[int, float], "Value to multiply each item by"]
) -> Iterable[Union[int, float]]:
    """Scale each item in the input stream by the multiplier."""
    for x in items:
        yield x * multiplier

@registry.register_source(name="range")
@core.source(lower=0, upper=10)
def arange(
    lower: Annotated[int, "Lower bound of the range (inclusive)"], 
    upper: Annotated[int, "Upper bound of the range (exclusive)"]
):
    """Generate a range of integers between lower (inclusive) and upper (exclusive)

    This segment wraps the built-in range function, allowing you to specify
    the lower and upper bounds of the range. The range is inclusive of the
    lower bound and exclusive of the upper bound.
    """
    yield from list(range(lower, upper))


class AbstractComparisonFilter(core.AbstractSegment):
    """Base for comparison segments: filter items where field value op threshold."""

    def __init__(
        self,
        field: Annotated[str, "Field/property to compare"],
        n: Annotated[Any, "Value to compare against"],
        comparator: Callable[[Any, Any], bool],
    ):
        super().__init__()
        self.field = field
        self.n = n
        self.comparator = comparator

    def transform(self, items: Iterable) -> Iterable:
        """Yield items whose field value satisfies the comparator."""
        for item in items:
            value = extract_property(item, self.field, fail_on_missing=True)
            if self.comparator(value, self.n):
                yield item


def _make_comparison_segment(name: str, op: Callable[[Any, Any], bool], docstring: str):
    """Factory: create a registered comparison segment with given op and docstring."""
    @registry.register_segment(name=name)
    class ComparisonSegment(AbstractComparisonFilter):
        __doc__ = docstring

        def __init__(self, 
                     field: Annotated[str, "Field/property to compare"], 
                     n: Annotated[Any, "Value to compare against"]):
            super().__init__(field, n, op)
    ComparisonSegment.__name__ = name
    return ComparisonSegment


# Comparison segments: filter by field value vs threshold 
EQ = _make_comparison_segment("eq", lambda x, y: x == y,
    "Filter items where a specified field's value equals a number.")
NEQ = _make_comparison_segment("neq", lambda x, y: x != y,
    "Filter items where a specified field's value does not equal a number.")
GT = _make_comparison_segment("gt", lambda x, y: x > y,
    "Filter items where a specified field's value is greater than a number.")
GTE = _make_comparison_segment("gte", lambda x, y: x >= y,
    "Filter items where a specified field's value is greater than or equal to a number.")
LT = _make_comparison_segment("lt", lambda x, y: x < y,
    "Filters items based on a field value being less than a specified number.")
LTE = _make_comparison_segment("lte", lambda x, y: x <= y,
    "Filter items where a specified field's value is less than or equal to a number.")