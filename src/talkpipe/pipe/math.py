"""Math operations for pipe."""

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
@core.source(lower=0,  upper=10)
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
    """Abstract base class for comparison segments."""

    def __init__(self, 
                 field: Annotated[str, "Field/property to compare"], 
                 n: Annotated[Any, "Value to compare against"], 
                 comparator: Callable[[Any, Any], bool]):
        super().__init__()
        self.field = field
        self.n = n
        self.comparator = comparator

    def transform(self, items: Iterable) -> Iterable:
        """Filter items based on the comparison."""
        for item in items:
            value = extract_property(item, self.field, fail_on_missing=True)
            if self.comparator(value, self.n):
                yield item


def _make_comparison_segment(name: str, op: Callable[[Any, Any], bool], docstring: str):
    """Factory for comparison segments (eq, neq, gt, gte, lt, lte)."""
    @registry.register_segment(name=name)
    class ComparisonSegment(AbstractComparisonFilter):
        __doc__ = docstring

        def __init__(self, 
                     field: Annotated[str, "Field/property to compare"], 
                     n: Annotated[Any, "Value to compare against"]):
            super().__init__(field, n, op)
    ComparisonSegment.__name__ = name
    return ComparisonSegment


# TODO: rename to EQ in 0.5.0
eq = _make_comparison_segment("eq", lambda x, y: x == y,
    "Filter items where a specified field's value equals a number.")
# TODO: rename to NEQ in 0.5.0
neq = _make_comparison_segment("neq", lambda x, y: x != y,
    "Filter items where a specified field's value does not equal a number.")
# TODO: rename to GT in 0.5.0
gt = _make_comparison_segment("gt", lambda x, y: x > y,
    "Filter items where a specified field's value is greater than a number.")
# TODO: rename to GTE in 0.5.0
gte = _make_comparison_segment("gte", lambda x, y: x >= y,
    "Filter items where a specified field's value is greater than or equal to a number.")
# TODO: rename to LT in 0.5.0
lt = _make_comparison_segment("lt", lambda x, y: x < y,
    "Filters items based on a field value being less than a specified number.")
# TODO: rename to LTE in 0.5.0
lte = _make_comparison_segment("lte", lambda x, y: x <= y,
    "Filter items where a specified field's value is less than or equal to a number.")