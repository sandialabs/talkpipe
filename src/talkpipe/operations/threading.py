from typing import Iterator, Any, Dict
import threading
import queue
import uuid
from talkpipe.pipe import core
from talkpipe.chatterlang import registry

class QueueConsumer:
    """
    An iterable consumer that yields items from its personal queue.
    It blocks waiting for new items; when it receives a termination sentinel,
    iteration stops.
    """
    def __init__(self, parent_queue: 'ThreadedQueue', maxsize: int = 100):
        self.personal_queue = queue.Queue(maxsize=maxsize)
        self.parent = parent_queue
        self.consumer_id = str(uuid.uuid4())
        self.active = True

        # Register with the parent queue.
        self.parent._register_consumer_queue(self.consumer_id, self.personal_queue)

    def __iter__(self):
        return self

    def __next__(self):
        if not self.active:
            raise StopIteration

        item = self.personal_queue.get()
        if item is self.parent._sentinel:
            # Termination sentinel received: unregister and stop iteration.
            self.active = False
            self.parent._unregister_consumer_queue(self.consumer_id)
            raise StopIteration

        self.personal_queue.task_done()
        return item

    def close(self):
        """Stop consuming and unregister from the parent queue."""
        self.active = False
        self.parent._unregister_consumer_queue(self.consumer_id)


class ThreadedQueue:
    """
    A multi-producer, multi-consumer queue system where each producer broadcasts its
    items to all registered consumers. Producers are not started until start() is called.
    This allows all producers and consumers to be registered first.

    **Important:** Once start() is called, no new producers or consumers can be registered.
    When the last producer finishes (or if there are no producers), a termination sentinel
    is broadcast so that consumers stop.
    """
    def __init__(self, maxsize: int = 0):
        self.consumer_queues: Dict[str, queue.Queue] = {}
        self._active_producers: Dict[str, threading.Thread] = {}
        self._pending_producers: Dict[str, Iterator[Any]] = {}
        self._started = False  # Flag indicating that start() has been called.
        self.active = threading.Event()
        self.active.set()
        self._lock = threading.RLock()
        # A unique sentinel object for termination.
        self._sentinel = object()

    def _register_consumer_queue(self, consumer_id: str, consumer_queue: queue.Queue):
        with self._lock:
            self.consumer_queues[consumer_id] = consumer_queue

    def _unregister_consumer_queue(self, consumer_id: str):
        with self._lock:
            self.consumer_queues.pop(consumer_id, None)

    def _broadcast_item(self, item: Any):
        with self._lock:
            for consumer_queue in self.consumer_queues.values():
                consumer_queue.put(item)

    def _broadcast_termination(self):
        with self._lock:
            for consumer_queue in self.consumer_queues.values():
                consumer_queue.put(self._sentinel)

    def register_producer(self, generator: Iterator[Any]) -> str:
        """
        Register a producer that yields items to be broadcast to all consumers.
        **Must be called before start().** If start() has already been called,
        a RuntimeError is raised.
        """
        with self._lock:
            if self._started:
                raise RuntimeError("Cannot register producers after start() is called")
            producer_id = str(uuid.uuid4())
            self._pending_producers[producer_id] = generator
        return producer_id

    def _start_producer(self, producer_id: str, generator: Iterator[Any]):
        """
        Helper to start a producer in its own thread. Each item produced is
        broadcast to all registered consumer queues.
        """
        def producer_worker():
            try:
                for item in generator:
                    if not self.active.is_set():
                        break
                    self._broadcast_item(item)
            finally:
                with self._lock:
                    self._active_producers.pop(producer_id, None)
                    # Only broadcast termination when there are no active or pending producers.
                    if not self._active_producers and not self._pending_producers:
                        self._broadcast_termination()

        thread = threading.Thread(target=producer_worker, daemon=True)
        with self._lock:
            self._active_producers[producer_id] = thread
        thread.start()

    def register_consumer(self) -> QueueConsumer:
        """
        Register a new consumer that will receive all broadcasted items.
        **Must be called before start().** If start() has been called,
        a RuntimeError is raised.
        """
        with self._lock:
            if self._started:
                raise RuntimeError("Cannot register consumers after start() is called")
            consumer = QueueConsumer(self)
        return consumer

    def start(self):
        """
        Start processing all pending producers. This call marks the end of
        the registration phase. Once start() is called, no new producers or
        consumers can be registered.

        **Key change:** If there are no pending producers (i.e. no producers were registered),
        immediately broadcast the termination sentinel so that consumers stop.
        """
        with self._lock:
            self._started = True
            # Copy pending producers.
            pending = list(self._pending_producers.items())
            # Reserve all producer IDs in _active_producers.
            for producer_id, _ in pending:
                self._active_producers[producer_id] = None
            self._pending_producers.clear()
            # If no producers were registered, broadcast termination immediately.
            if not pending:
                self._broadcast_termination()
        # Start all pending producers (if any).
        for producer_id, generator in pending:
            self._start_producer(producer_id, generator)

    def has_active_producers(self) -> bool:
        with self._lock:
            return bool(self._active_producers or self._pending_producers)

    def shutdown(self):
        """
        Gracefully shut down the queue system by clearing the active flag,
        enqueuing the termination sentinel for all consumers, and waiting for
        all producer threads to complete.
        """
        self.active.clear()
        with self._lock:
            for consumer_queue in self.consumer_queues.values():
                consumer_queue.put(self._sentinel)
        for thread in list(self._active_producers.values()):
            if thread is not None:
                thread.join(timeout=1.0)


@registry.register_segment(name="threaded")
@core.segment()
def threadedSegment(items: Iterator):
    """Links the input stream to a threaded queue system.

    This segment takes an input stream and links it to a threaded queue system.
    It starts the queue system and then starts yielding from the queue.  That way
    the upstream units don't have to wait for the downstream segments to draw 
    from them.
    """

    queue_system = ThreadedQueue()
    queue_system.register_producer(items)
    consumer = queue_system.register_consumer()
    queue_system.start()
    yield from consumer

