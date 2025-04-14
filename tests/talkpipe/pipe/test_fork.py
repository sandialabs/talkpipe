from talkpipe.pipe import fork
from talkpipe.pipe import core

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
    assert set(results) == set([0, 2, 4, 6, 8, 10, 11, 12, 13, 14])

    # Test round-robin mode
    pipeline.mode = fork.ForkMode.ROUND_ROBIN
    results = list(pipeline(range(5)))
    assert set(results) == set([0, 11, 4, 13, 8])

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
            yield item ** 2

    forkSegment = fork.ForkSegment([branch1(), branch2()])
    forkSegment.mode = fork.ForkMode.ROUND_ROBIN

    pipeline = branch3() | forkSegment | branch4()

    results = list(pipeline(range(5)))
    assert set(results) == set([((0-5)*2)**2, ((1-5)+10)**2, ((2-5)*2)**2, ((3-5)+10)**2, ((4-5)*2)**2])    


