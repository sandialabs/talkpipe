from typing import List, Iterator, Iterable, Any
import logging
from queue import Queue
from concurrent.futures import ThreadPoolExecutor
from enum import Enum
from .core import AbstractSegment

logger = logging.getLogger(__name__)

class ForkMode(Enum):
    """Distribution modes for fork segments."""
    ROUND_ROBIN = "round_robin"  # Distribute items across branches
    BROADCAST = "broadcast"      # Send all items to all branches

_poison_pill = object()

def _poison_filter(queue: Queue) -> Iterator[Any]:
    """Filter that adds a poison pill to the end of the input."""
    while True:
        item = queue.get()
        if item is _poison_pill:
            break
        yield item

class ForkSegment(AbstractSegment):
    """A segment that forks the input stream into multiple downstream pipelines,
    processing them in parallel using threads.
    """
    
    def __init__(self, 
                 branches: List[AbstractSegment], 
                 mode: ForkMode = ForkMode.BROADCAST,
                 max_queue_size: int = 100, 
                 num_threads: int = None):
        """Initialize the fork segment."""
        super().__init__()
        self.branches = branches
        self.mode = mode
        self.max_queue_size = max_queue_size
        self.num_threads = num_threads or len(branches)
        
    def process_branch(self, branch_id: int, branch: AbstractSegment, 
                      input_queue: Queue, output_queue: Queue):
        """Process a single branch of the fork."""
        try:
            if isinstance(branch, AbstractSegment):
                iter = branch(_poison_filter(input_queue))
            else:
                iter = branch()

            for item in iter:
                output_queue.put((branch_id, item))
                
        except Exception as e:
            logger.error(f"Error in fork branch {branch_id}: {e}")
            raise
        finally:
            output_queue.put((branch_id, None))  # Signal branch completion
            input_queue.task_done()
            
    def transform(self, input_iter: Iterable[Any]) -> Iterator[Any]:
        """Transform input by distributing it across multiple branches."""
        input_queues = [Queue(maxsize=self.max_queue_size) for _ in self.branches]
        output_queue = Queue()
        
        with ThreadPoolExecutor(max_workers=self.num_threads) as executor:
            # Submit branch processing tasks
            futures = [
                executor.submit(
                    self.process_branch, 
                    idx, branch, input_queue, output_queue
                )
                for idx, (branch, input_queue) in enumerate(zip(self.branches, input_queues))
            ]
            
            try:
                # Feed input to branches according to the selected mode
                if self.mode == ForkMode.BROADCAST:
                    for item in input_iter or []:
                        for queue in input_queues:
                            queue.put(item)
                else:  # ROUND_ROBIN
                    for i, item in enumerate(input_iter or []):
                        branch_idx = i % len(self.branches)
                        input_queues[branch_idx].put(item)
                
                # Send poison pills to signal completion
                for queue in input_queues:
                    queue.put(_poison_pill)
                
                # Yield results as they become available
                active_branches = len(self.branches)
                while active_branches > 0:
                    branch_id, result = output_queue.get()
                    if result is None:
                        active_branches -= 1
                    else:
                        yield result
                
            except Exception as e:
                logger.error(f"Error in fork main thread: {e}")
                raise
            finally:
                for future in futures:
                    future.cancel()
                
# Helper function to create a fork
def fork(*branches: AbstractSegment, 
         mode: ForkMode = ForkMode.ROUND_ROBIN,
         max_queue_size: int = 100, 
         num_threads: int = None) -> ForkSegment:
    """Create a fork segment with the given branches."""
    return ForkSegment(list(branches), mode, max_queue_size, num_threads)
