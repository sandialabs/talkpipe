import pytest
from talkpipe.util.iterators import bypass


def test_bypass():
    """Test the bypass function with various scenarios."""
    predicate = lambda x: (x % 2 == 0)

    def handler(stream):
        for x in stream:
            if x == 7:
                continue  # skip 7 entirely
            yield 10 * x
            yield 100 * x

    # Test case 1: Mixed bypassed and failed items
    data = [2, 3, 7, 5, 4]
    result = list(bypass(data, predicate, handler))
    assert result == [2, 30, 300, 50, 500, 4]

    # Test case 2: Multiple bypassed items with failed items in between
    data = [2, 3, 2, 7, 5, 4]
    result = list(bypass(data, predicate, handler))
    assert result == [2, 30, 300, 2, 50, 500, 4]

    # Test case 3: All items bypassed (predicate always True)
    data = [2, 4, 6]
    result = list(bypass(data, predicate, handler))
    assert result == [2, 4, 6]

    # Test case 4: All items failed (predicate always False)
    data = [3, 5, 7]
    result = list(bypass(data, predicate, handler))
    assert result == [30, 300, 50, 500]
    # Note: 7 is skipped by the handler, so no output for it

    data = [7,7,7]
    result = list(bypass(data, predicate, handler))
    assert result == []

    data = [3, 5, 9]
    result = list(bypass(data, predicate, handler))
    assert result == [30, 300, 50, 500, 90, 900]

