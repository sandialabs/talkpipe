import pytest
import time
import threading
import time
from queue import Empty
from talkpipe.pipe import core
from talkpipe.operations.thread_ops import ThreadedQueue, QueueConsumer, threadedSegment
from talkpipe.chatterlang.compiler import compile


def test_single_producer_single_consumer():
    queue_system = ThreadedQueue()

    def producer():
        for i in range(5):
            yield i

    producer_id = queue_system.register_producer(producer())
    consumer = queue_system.register_consumer()

    queue_system.start()

    consumed_items = []
    for item in consumer:
        consumed_items.append(item)

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
        for i in range(5):
            yield i

    queue_system.register_producer(producer())

    consumer_1 = queue_system.register_consumer()
    consumer_2 = queue_system.register_consumer()

    queue_system.start()

    consumed_items_1 = []
    consumed_items_2 = []

    for item in consumer_1:
        consumed_items_1.append(item)

    for item in consumer_2:
        consumed_items_2.append(item)

    assert consumed_items_1 == [0, 1, 2, 3, 4]
    assert consumed_items_2 == [0, 1, 2, 3, 4]
    assert not queue_system.has_active_producers()
    
    queue_system.shutdown()


def test_consumer_blocks_until_producer_finishes():
    queue_system = ThreadedQueue()

    def delayed_producer():
        time.sleep(1)
        for i in range(3):
            yield i

    queue_system.register_producer(delayed_producer())
    consumer = queue_system.register_consumer()

    queue_system.start()

    consumed_items = []
    for item in consumer:
        consumed_items.append(item)

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

    consumer_thread = threading.Thread(target=lambda: consumed_items.extend(iter(consumer)))
    consumer_thread.start()

    time.sleep(0.3)  # Allow some consumption
    queue_system.shutdown()
    consumer_thread.join()

    assert set(consumed_items).issubset({0, 1, 2, 3, 4})  # Ensure it consumed some values


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
    out = list(ts([1,2,3]))
    assert out == [1,2,3]

    f = compile("threaded")
    out = list(f([1,2,3]))
    assert out == [1,2,3]

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
    assert ans == [1,2,3,4]

    it = iter(threaded())
    next(it)
    time.sleep(2)
    start = time.time()
    ans = list(it)
    end = time.time()
    assert end - start < 0.1
    assert ans == [1,2,3,4]

    it = iter(threaded())
    next(it)
    time.sleep(2)
    start = time.time()
    ans = list(it)
    end = time.time()
    assert end - start < 0.1
    assert ans == [1,2,3,4]
