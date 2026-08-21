"""Stream-control segments: limit, sample, pace, and debounce the flow of items."""

import itertools
import threading
import time
from collections.abc import Iterable, Iterator
from queue import Queue
from typing import Annotated, Any

import talkpipe.chatterlang.registry as registry
from talkpipe.pipe.core import (
    segment,
)


@registry.register_segment("sleep")
@segment()
def sleep(
    items: Iterable[Any],
    seconds: Annotated[int, "The number of seconds to sleep after processing n items"],
    n: Annotated[int, "The number of items to process before sleeping"] = 1,
) -> Iterator[Any]:
    """Sleep for a specified number of seconds after each n items.

    This segment introduces a delay between processing each item in the pipeline.
    Useful for rate limiting, testing timing-sensitive code, or simulating slow operations.

    Yields:
        Any: Each input item unchanged after the sleep delay.
    """
    for count, item in enumerate(items, start=1):
        yield item  # Pass through the item unchanged
        if count % n == 0:
            time.sleep(seconds)  # Sleep after yielding to maintain pipeline flow


@registry.register_segment(name="firstN")
@segment()
def firstN(
    items: Iterable[Any], n: Annotated[int, "The number of items to yield."] = 1
) -> Iterator[Any]:
    """Yields the first n items from the input stream.

    Useful for sampling data, testing pipelines with limited data, or implementing
    pagination-like functionality.

    ChatterLang Usage:
        firstN[n=5]

    Args:
        items (Iterable): An iterable of items to process.
        n (int): The number of items to yield. Defaults to 1.

    Yields:
        Any: The first n items from the input stream."""
    yield from itertools.islice(items, n)


@registry.register_segment("everyN")
@segment()
def everyN(
    items: Iterable[Any],
    n: Annotated[int, "Number of items to skip between each yield"],
) -> Iterator[Any]:
    """Yield every nth item from the input stream, creating a sampling effect.

    This segment yields only items at positions that are multiples of n, effectively
    sampling every nth item from the stream. Useful for reducing data volume, creating
    summaries, or testing with subset of large datasets.

    For example, with n=5: yields items 5, 10, 15, 20, etc. (items at positions 5, 10, 15...).
    With n=1: yields all items. With n=2: yields every other item.

    Yields:
        Every nth item from the input stream.
    """
    for i, item in enumerate(items):
        if (i + 1) % n == 0:
            yield item


@registry.register_segment("debounce")
@segment()
def Debounce(
    items: Any,
    key_field: Annotated[str, "Field name to use as the debounce key"] = "path",
    debounce_seconds: Annotated[
        float, "Seconds to wait for stability before yielding"
    ] = 1.0,
) -> Iterator[Any]:
    """
    Segment that debounces events by a key field, waiting for stability before yielding.

    Expects input items as dicts with a field to use as the debounce key (default: "path").
    When multiple events arrive for the same key, only the last event is yielded after
    no new events have arrived for that key within the debounce period.

    This is useful for handling race conditions where files are created and then
    immediately modified (e.g., create with 0 bytes, then write content). The debounce
    ensures processing only happens after the file has stabilized.

    Yields the most recent event for each key after the debounce period expires.
    """
    pending: dict[Any, tuple[Any, float]] = {}  # key -> (item, timestamp)
    lock = threading.Lock()
    output_queue: Queue[Any] = Queue()
    stop_event = threading.Event()
    input_done = threading.Event()

    def add_pending(item: Any) -> None:
        key = item.get(key_field) if isinstance(item, dict) else None
        if key is None:
            output_queue.put(item)
            return
        with lock:
            pending[key] = (item, time.time())

    def input_consumer() -> None:
        try:
            for item in items:
                if stop_event.is_set():
                    break
                add_pending(item)
        finally:
            input_done.set()

    def checker() -> None:
        while not stop_event.is_set():
            time.sleep(0.1)
            now = time.time()
            with lock:
                stable_keys = [
                    k
                    for k, (item, ts) in pending.items()
                    if now - ts >= debounce_seconds
                ]
                for k in stable_keys:
                    item, _ = pending.pop(k)
                    output_queue.put(item)

            # Signal completion when input is done and no pending items
            if input_done.is_set():
                with lock:
                    if not pending:
                        output_queue.put(None)  # Sentinel to signal done
                        break

    input_thread = threading.Thread(target=input_consumer, daemon=True)
    checker_thread = threading.Thread(target=checker, daemon=True)
    input_thread.start()
    checker_thread.start()

    try:
        while True:
            item = output_queue.get()
            if item is None:  # Sentinel
                break
            yield item
    finally:
        stop_event.set()
        input_thread.join(timeout=1.0)
        checker_thread.join(timeout=1.0)
