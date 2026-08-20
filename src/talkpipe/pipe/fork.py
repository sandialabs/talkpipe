"""Fork segments: split a stream into parallel branches.

ForkSegment distributes items across multiple downstream pipelines using
threads and queues. Supports round-robin (one item per branch) or broadcast
(all items to all branches).
"""

import logging
import threading
from collections.abc import Iterable, Iterator
from concurrent.futures import ThreadPoolExecutor
from enum import Enum
from queue import Empty, Full, Queue
from typing import Any

from .core import AbstractSegment, AbstractSource

logger = logging.getLogger(__name__)

# Sentinel to signal end of stream to branch consumers
_poison_pill = object()


class ForkMode(Enum):
    """Distribution modes for fork segments."""

    ROUND_ROBIN = "round_robin"  # Distribute items across branches
    BROADCAST = "broadcast"  # Send all items to all branches


_POLL_SECONDS = 0.5


def _put(queue: Queue[Any], item: Any, stop: threading.Event) -> bool:
    """Put ``item`` on a bounded queue, giving up once ``stop`` is set.

    Returns True if the item was enqueued. Blocking indefinitely on a full
    queue would keep a worker thread alive after the consumer has abandoned
    the fork, so the wait is polled against the stop event instead.
    """
    while not stop.is_set():
        try:
            queue.put(item, timeout=_POLL_SECONDS)
            return True
        except Full:
            continue
    return False


def _poison_filter(queue: Queue[Any], stop: threading.Event) -> Iterator[Any]:
    """Iterator over queue items until _poison_pill is seen or ``stop`` is set."""
    while True:
        try:
            item = queue.get(timeout=_POLL_SECONDS)
        except Empty:
            if stop.is_set():
                break
            continue
        if item is _poison_pill:
            break
        yield item


class ForkSegment(AbstractSegment[Any, Any]):
    """Forks the input stream into multiple downstream pipelines in parallel."""

    def __init__(
        self,
        branches: list[AbstractSegment[Any, Any] | AbstractSource[Any]],
        mode: ForkMode = ForkMode.BROADCAST,
        max_queue_size: int = 100,
        num_threads: int | None = None,
    ):
        super().__init__(process_metadata=True)  # Metadata flows into branches
        self.branches = branches
        self.mode = mode
        self.max_queue_size = max_queue_size
        self.num_threads = num_threads or len(branches)

    def process_branch(
        self,
        branch_id: int,
        branch: AbstractSegment[Any, Any] | AbstractSource[Any],
        input_queue: Queue[Any],
        output_queue: Queue[Any],
        stop: threading.Event,
    ) -> None:
        """Run one branch: consume from input_queue, emit (branch_id, item) to output_queue."""
        try:
            if isinstance(branch, AbstractSegment):
                iter = branch(_poison_filter(input_queue, stop))
            else:
                iter = branch()

            for item in iter:
                if not _put(output_queue, (branch_id, item), stop):
                    break  # consumer went away; stop producing

        except Exception as e:
            logger.error(f"Error in fork branch {branch_id}: {e}")
            raise
        finally:
            _put(output_queue, (branch_id, None), stop)  # Sentinel: branch finished

    def _feed(
        self,
        input_iter: Iterable[Any] | None,
        input_queues: list[Queue[Any]],
        stop: threading.Event,
        errors: list[BaseException],
    ) -> None:
        """Feed input to the branches according to the selected mode.

        Runs on its own thread so that feeding and draining can interleave; with
        bounded queues, doing both sequentially on one thread would deadlock.
        """
        try:
            if self.mode == ForkMode.BROADCAST:
                for item in input_iter or []:
                    for queue in input_queues:
                        if not _put(queue, item, stop):
                            return
            else:  # ROUND_ROBIN
                for i, item in enumerate(input_iter or []):
                    branch_idx = i % len(self.branches)
                    if not _put(input_queues[branch_idx], item, stop):
                        return
        except BaseException as e:
            errors.append(e)
        finally:
            # Always try to signal completion so branches waiting on input can
            # finish; once stop is set they poll and exit on their own.
            for queue in input_queues:
                _put(queue, _poison_pill, stop)

    def transform(self, input_iter: Iterable[Any]) -> Iterator[Any]:
        """Distribute input to branches, collect results as they complete."""
        input_queues: list[Queue[Any]] = [
            Queue(maxsize=self.max_queue_size) for _ in self.branches
        ]
        # Bounded like the inputs, so a slow consumer applies back-pressure to
        # the branches instead of letting their output pile up in memory.
        output_queue: Queue[Any] = Queue(maxsize=self.max_queue_size)
        stop = threading.Event()
        feed_errors: list[BaseException] = []

        with ThreadPoolExecutor(max_workers=self.num_threads) as executor:
            # Submit branch processing tasks
            futures = [
                executor.submit(
                    self.process_branch, idx, branch, input_queue, output_queue, stop
                )
                for idx, (branch, input_queue) in enumerate(
                    zip(self.branches, input_queues, strict=False)
                )
            ]
            feeder = threading.Thread(
                target=self._feed,
                args=(input_iter, input_queues, stop, feed_errors),
                name="fork-feeder",
                daemon=True,
            )
            feeder.start()

            try:
                # Drain output_queue; result=None is branch completion sentinel
                active_branches = len(self.branches)
                while active_branches > 0:
                    _branch_id, result = output_queue.get()
                    if result is None:
                        active_branches -= 1
                    else:
                        yield result

                feeder.join()
                if feed_errors:
                    raise feed_errors[0]

                # Every branch has emitted its sentinel; surface the first
                # branch failure instead of letting a crashed branch look
                # like an empty one.
                for future in futures:
                    future.result()

            except Exception as e:
                logger.error(f"Error in fork main thread: {e}")
                raise
            finally:
                # Release any thread blocked on a full/empty queue; the
                # executor's exit then joins them promptly.
                stop.set()
                for future in futures:
                    future.cancel()


def fork(
    *branches: AbstractSegment[Any, Any],
    mode: ForkMode = ForkMode.ROUND_ROBIN,
    max_queue_size: int = 100,
    num_threads: int | None = None,
) -> ForkSegment:
    """Create a ForkSegment with the given branches."""
    return ForkSegment(list(branches), mode, max_queue_size, num_threads)
