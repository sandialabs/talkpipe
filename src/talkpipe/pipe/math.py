"""Math operations for pipe."""

from typing import Iterable, Union, Callable, Any
from numpy import random
from talkpipe.pipe import core
from talkpipe.chatterlang import registry
from talkpipe.util.data_manipulation import extract_property

@registry.register_source(name="randomInts")
@core.source(n=10, lower=0, upper=100)
def randomInts(n: int, lower, upper) -> Iterable[int]:
    """Generate n random integers between lower and upper."""
    yield from random.randint(lower, upper, n)

@registry.register_segment(name="scale")
@core.segment(multiplier=2)
def scale(items: Iterable[Union[int, float]], multiplier: Union[int, float]) -> Iterable[Union[int, float]]:
    """Scale each item in the input stream by the multiplier."""
    for x in items:
        yield x * multiplier

@registry.register_source(name="range")
@core.source(lower=0,  upper=10)
def arange(lower, upper):
    """Generate a range of integers between lower (inclusive) and upper (exclusive)

    This segment wraps the built-in range function, allowing you to specify
    the lower and upper bounds of the range. The range is inclusive of the
    lower bound and exclusive of the upper bound.

    Args:
        lower (int): Lower bound of the range (inclusive)
        upper (int): Upper bound of the range (exclusive)

    """
    yield from list(range(lower, upper))


class AbstractComparisonFilter(core.AbstractSegment):
    """Abstract base class for comparison segments."""

    def __init__(self, field: str, n: Any, comparator: Callable[[Any, Any], bool]):
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


#TODO: rename class to EQ in 0.5.0
@registry.register_segment(name="eq")
class eq(AbstractComparisonFilter):
    """Filter items where a specified field's value equals a number.

    For each item passed in, this segment yields only those where the value of the specified field
    is equal to the given number n.  

    Args:
        items: Iterable of items to filter
        field: String representing the field/property to compare.  Note that
          an underscore "_" can be used to refer to the item itself.
        n: Item to compare against

    Yields:
        Items where the specified field's value equals n

    Raises:
        AttributeError: If the specified field is missing from any item

    """

    def __init__(self, field: str, n: Any):
        super().__init__(field, n, lambda x, y: x == y)

#TODO: rename class to NEQ in 0.5.0
@registry.register_segment(name="neq")
class neq(AbstractComparisonFilter):
    """Filter items where a specified field's value does not equal a number.

    For each item passed in, this segment yields only those where the value of the specified field
    is not equal to the given number n.

    Args:
        items: Iterable of items to filter
        field: String representing the field/property to compare.  Note that
          an underscore "_" can be used to refer to the item itself.
        n: Item to compare against

    Yields:
        Items where the specified field's value does not equal n

    Raises:
        AttributeError: If the specified field is missing from any item

    """
    def __init__(self, field: str, n: Any):
        super().__init__(field, n, lambda x, y: x != y)

#TODO: rename class to GT in 0.5.0
@registry.register_segment("gt")
class gt(AbstractComparisonFilter):    
    """Filter items where a specified field's value is greater than a number.

    For each item passed in, this segment yields only those where the value of the specified field
    is greater than the given number n.

    Args:
        items: Iterable of items to filter
        field: String representing the field/property to compare.  Note that
          an underscore "_" can be used to refer to the item itself.
        n: Number to compare against

    Yields:
        Items where the specified field's value is greater than n

    Raises:
        AttributeError: If the specified field is missing from any item

    """
    def __init__(self, field: str, n: Any):
        super().__init__(field, n, lambda x, y: x > y)

#TODO: rename class to GTE in 0.5.0
@registry.register_segment(name="gte")
class gte(AbstractComparisonFilter):
    """Filter items where a specified field's value is greater than or equal to a number.

    For each item passed in, this segment yields only those where the value of the specified field
    is greater than or equal to the given number n.

    Args:
        items: Iterable of items to filter
        field: String representing the field/property to compare.  Note that
          an underscore "_" can be used to refer to the item itself.
        n: Number to compare against

    Yields:
        Items where the specified field's value is greater than or equal to n

    Raises:
        AttributeError: If the specified field is missing from any item

    """
    def __init__(self, field: str, n: Any):
        super().__init__(field, n, lambda x, y: x >= y)

#TODO: rename class to LT in 0.5.0
@registry.register_segment("lt")
class lt(AbstractComparisonFilter):
    """
    Filters items based on a field value being less than a specified number.

    For each item passed in, this segment yields items where the 
    specified field value is less than the given number n.

    Args:
        items (iterable): An iterable of items to filter
        field: String representing the field/property to compare.  Note that
          an underscore "_" can be used to refer to the item itself.
        n (numeric): The number to compare against

    Yields:
        item: Items where the specified field value is less than n

    Raises:
        AttributeError: If the specified field does not exist on an item (due to fail_on_missing=True)

    """
    def __init__(self, field: str, n: Any):
        super().__init__(field, n, lambda x, y: x < y)


#TODO: rename class to LTE in 0.5.0
@registry.register_segment(name="lte")
class lte(AbstractComparisonFilter):
    """Filter items where a specified field's value is less than or equal to a number.

    For each item passed in, this segment yields only those where the value of the specified field
    is less than or equal to the given number n.

    Args:
        items: Iterable of items to filter
        field: String representing the field/property to compare.  Note that
          an underscore "_" can be used to refer to the item itself.
        n: Number to compare against

    Yields:
        Items where the specified field's value is less than or equal to n

    Raises:
        AttributeError: If the specified field is missing from any item

    """
    def __init__(self, field: str, n: Any):
        super().__init__(field, n, lambda x, y: x <= y)