import pytest

from talkpipe.pipe import core, fork


def test_fork_1_branch():
    @core.segment()
    def branch1(iterable):
        for item in iterable:
            yield item * 2

    pipeline = fork.ForkSegment([branch1()])
    results = list(pipeline(range(5)))
    assert results == [0, 2, 4, 6, 8]


def test_fork_2_branches():
    # Define a simple pipeline with two branches
    @core.segment()
    def branch1(iterable):
        for item in iterable:
            yield item * 2

    @core.segment()
    def branch2(iterable):
        for item in iterable:
            yield item + 10

    pipeline = fork.ForkSegment([branch1(), branch2()])

    # Test broadcast mode
    pipeline.mode = fork.ForkMode.BROADCAST
    results = list(pipeline(range(5)))
    assert set(results) == {0, 2, 4, 6, 8, 10, 11, 12, 13, 14}

    # Test round-robin mode
    pipeline.mode = fork.ForkMode.ROUND_ROBIN
    results = list(pipeline(range(5)))
    assert set(results) == {0, 11, 4, 13, 8}


def test_complex_fork():
    @core.segment()
    def branch1(iterable):
        for item in iterable:
            yield item * 2

    @core.segment()
    def branch2(iterable):
        for item in iterable:
            yield item + 10

    @core.segment()
    def branch3(iterable):
        for item in iterable:
            yield item - 5

    @core.segment()
    def branch4(iterable):
        for item in iterable:
            yield item**2

    forkSegment = fork.ForkSegment([branch1(), branch2()])
    forkSegment.mode = fork.ForkMode.ROUND_ROBIN

    pipeline = branch3() | forkSegment | branch4()

    results = list(pipeline(range(5)))
    assert set(results) == {
        ((0 - 5) * 2) ** 2,
        ((1 - 5) + 10) ** 2,
        ((2 - 5) * 2) ** 2,
        ((3 - 5) + 10) ** 2,
        ((4 - 5) * 2) ** 2,
    }


def test_fork_branch_exception_propagates():
    @core.segment()
    def healthy(iterable):
        yield from iterable

    @core.segment()
    def broken(iterable):
        for item in iterable:
            if item == 2:
                raise ValueError("branch exploded")
            yield item

    pipeline = fork.ForkSegment([healthy(), broken()], mode=fork.ForkMode.BROADCAST)
    with pytest.raises(ValueError, match="branch exploded"):
        list(pipeline(range(5)))


def test_fork_output_queue_is_bounded_and_does_not_deadlock():
    """Branches producing more than the queue bound must still complete."""

    @core.segment()
    def to_str(items):
        for item in items:
            yield str(item)

    branches = [to_str(), to_str()]
    forked = fork.fork(*branches, mode=fork.ForkMode.BROADCAST, max_queue_size=2)
    results = list(forked(range(500)))
    assert len(results) == 1000
    assert sorted(results, key=int) == sorted([str(i) for i in range(500)] * 2, key=int)


def test_fork_input_error_propagates():
    @core.segment()
    def to_str(items):
        for item in items:
            yield str(item)

    def bad_input():
        yield 1
        raise ValueError("upstream failed")

    forked = fork.fork(to_str(), max_queue_size=2)
    with pytest.raises(ValueError, match="upstream failed"):
        list(forked(bad_input()))
