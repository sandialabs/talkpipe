import threading
import time

import pytest

from talkpipe.chatterlang.compiler import compile
from talkpipe.operations.thread_ops import ThreadedQueue, threadedSegment
from talkpipe.pipe import core


def test_single_producer_single_consumer():
    queue_system = ThreadedQueue()

    def producer():
        yield from range(5)

    queue_system.register_producer(producer())
    consumer = queue_system.register_consumer()

    queue_system.start()

    consumed_items = list(consumer)

    assert consumed_items == [0, 1, 2, 3, 4]
    assert not queue_system.has_active_producers()

    queue_system.shutdown()


def test_multiple_producers_single_consumer():
    queue_system = ThreadedQueue()

    def producer_1():
        for i in range(3):
            yield f"P1-{i}"

    def producer_2():
        for i in range(3):
            yield f"P2-{i}"

    queue_system.register_producer(producer_1())
    queue_system.register_producer(producer_2())

    consumer = queue_system.register_consumer()

    queue_system.start()

    consumed_items = set()
    for item in consumer:
        consumed_items.add(item)

    assert consumed_items == {"P1-0", "P1-1", "P1-2", "P2-0", "P2-1", "P2-2"}
    assert not queue_system.has_active_producers()

    queue_system.shutdown()


def test_multiple_consumers():
    queue_system = ThreadedQueue()

    def producer():
        yield from range(5)

    queue_system.register_producer(producer())

    consumer_1 = queue_system.register_consumer()
    consumer_2 = queue_system.register_consumer()

    queue_system.start()

    consumed_items_1 = list(consumer_1)
    consumed_items_2 = list(consumer_2)

    assert consumed_items_1 == [0, 1, 2, 3, 4]
    assert consumed_items_2 == [0, 1, 2, 3, 4]
    assert not queue_system.has_active_producers()

    queue_system.shutdown()


def test_consumer_blocks_until_producer_finishes():
    queue_system = ThreadedQueue()

    def delayed_producer():
        time.sleep(1)
        yield from range(3)

    queue_system.register_producer(delayed_producer())
    consumer = queue_system.register_consumer()

    queue_system.start()

    consumed_items = list(consumer)

    assert consumed_items == [0, 1, 2]
    assert not queue_system.has_active_producers()

    queue_system.shutdown()


def test_shutdown_ends_consumers():
    queue_system = ThreadedQueue()

    def producer():
        for i in range(5):
            yield i
            time.sleep(0.1)

    queue_system.register_producer(producer())
    consumer = queue_system.register_consumer()

    queue_system.start()

    consumed_items = []

    consumer_thread = threading.Thread(
        target=lambda: consumed_items.extend(iter(consumer))
    )
    consumer_thread.start()

    time.sleep(0.3)  # Allow some consumption
    queue_system.shutdown()
    consumer_thread.join()

    assert set(consumed_items).issubset(
        {0, 1, 2, 3, 4}
    )  # Ensure it consumed some values


def test_no_producers_means_no_consumption():
    queue_system = ThreadedQueue()
    consumer = queue_system.register_consumer()

    queue_system.start()

    with pytest.raises(StopIteration):
        next(iter(consumer))  # Consumer should stop immediately

    queue_system.shutdown()


def test_multiple_producers_and_consumers():
    queue_system = ThreadedQueue()

    def producer_1():
        for i in range(3):
            yield f"P1-{i}"

    def producer_2():
        for i in range(3):
            yield f"P2-{i}"

    queue_system.register_producer(producer_1())
    queue_system.register_producer(producer_2())

    consumer_1 = queue_system.register_consumer()
    consumer_2 = queue_system.register_consumer()

    queue_system.start()

    consumed_items_1 = set()
    consumed_items_2 = set()

    for item in consumer_1:
        consumed_items_1.add(item)

    for item in consumer_2:
        consumed_items_2.add(item)

    expected_items = {"P1-0", "P1-1", "P1-2", "P2-0", "P2-1", "P2-2"}
    assert consumed_items_1 == expected_items
    assert consumed_items_2 == expected_items
    assert not queue_system.has_active_producers()

    queue_system.shutdown()


def test_threadedSegment():
    ts = threadedSegment()
    out = list(ts([1, 2, 3]))
    assert out == [1, 2, 3]

    f = compile("threaded")
    out = list(f([1, 2, 3]))
    assert out == [1, 2, 3]


@core.source()
def slowSource():
    for i in range(5):
        time.sleep(0.1)
        yield i


def test_threadedSegment_with_delay():
    noThreading = slowSource()
    threaded = slowSource() | threadedSegment()

    it = iter(noThreading())
    next(it)
    time.sleep(2)
    start = time.time()
    ans = list(it)
    end = time.time()
    assert end - start > 0.4
    assert ans == [1, 2, 3, 4]

    it = iter(threaded())
    next(it)
    time.sleep(2)
    start = time.time()
    ans = list(it)
    end = time.time()
    assert end - start < 0.1
    assert ans == [1, 2, 3, 4]

    it = iter(threaded())
    next(it)
    time.sleep(2)
    start = time.time()
    ans = list(it)
    end = time.time()
    assert end - start < 0.1
    assert ans == [1, 2, 3, 4]


def test_threaded_queue_is_bounded_and_producer_stops_on_shutdown():
    """A slow consumer applies back-pressure; shutdown releases the producer."""
    produced = []

    def producer():
        for i in range(10_000):
            produced.append(i)
            yield i

    queue_system = ThreadedQueue(maxsize=5)
    queue_system.register_producer(producer())
    consumer = queue_system.register_consumer()
    queue_system.start()

    assert next(iter(consumer)) == 0
    time.sleep(0.3)  # Producer should now be blocked on the full queue.
    # 1 consumed + 5 buffered + at most one item in flight.
    assert len(produced) <= 7
    queue_system.shutdown()
    time.sleep(0.2)
    stopped_at = len(produced)
    time.sleep(0.2)
    assert len(produced) == stopped_at  # producer thread really stopped


def test_threadedSegment_stops_producer_when_consumer_abandons():
    produced = []

    @core.source()
    def counting_source():
        for i in range(10_000):
            produced.append(i)
            yield i

    pipeline = counting_source() | threadedSegment(maxsize=5)
    it = iter(pipeline())
    assert next(it) == 0
    it.close()  # abandon early, like firstN would
    time.sleep(0.3)
    stopped_at = len(produced)
    time.sleep(0.2)
    assert len(produced) == stopped_at
    assert stopped_at < 100
