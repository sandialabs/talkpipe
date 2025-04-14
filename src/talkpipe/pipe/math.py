"""Math operations for pipe."""

from typing import Iterable, Union
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
    """Generate a range of integers between lower and upper"""
    yield from list(range(lower, upper))

@registry.register_segment("gt")
@core.segment(field=None, n=None)
def gt(items, field, n):
    """Filter items where a specified field's value is greater than a number.

    Takes an iterable of items and yields only those where the value of the specified field
    is greater than the given number n.

    Args:
        items: Iterable of items to filter
        field: String representing the field/property to compare
        n: Number to compare against

    Yields:
        Items where the specified field's value is greater than n

    Raises:
        AttributeError: If the specified field is missing from any item

    Example:
        >>> list(gt([{'value': 5}, {'value': 2}, {'value': 8}], 'value', 4))
        [{'value': 5}, {'value': 8}]
    """
    for item in items:
        if extract_property(item, field, fail_on_missing=True)>n:
            yield item

@registry.register_segment("lt")
@core.segment(field=None, n=None)
def lt(items, field, n):
    """
    Filters items based on a field value being less than a specified number.

    Yields items where the specified field value is less than the given number n.

    Args:
        items (iterable): An iterable of items to filter
        field (str): The field/property name to check against
        n (numeric): The number to compare against

    Yields:
        item: Items where the specified field value is less than n

    Raises:
        AttributeError: If the specified field does not exist on an item (due to fail_on_missing=True)

    Example:
        >>> items = [{'val': 1}, {'val': 5}, {'val': 3}]
        >>> list(lt(items, 'val', 4))
        [{'val': 1}, {'val': 3}]
    """
    for item in items:
        if extract_property(item, field, fail_on_missing=True)<n:
            yield item
