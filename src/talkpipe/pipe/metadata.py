from .core import Metadata, segment, source
from talkpipe.chatterlang import register_segment, register_source
import time

class Flush(Metadata):
    """A metadata object that indicates a flush operation."""
    pass

@register_segment("flushN")
@segment()
def flushN(items, n: int):
    """Issues a flush operation every n items.
    
    Args:
        n: Number of items between flush operations.
    
    Example:
        flushN(items, n=10)  # Flush every 10 items
    """
    count = 0
    for item in items:
        yield item
        count += 1
        if count % n == 0:
            yield Flush()

@register_segment("flushT")
@segment()
def flushT(items, t: float):
    """Issues a flush operation every t seconds while processing items.
    
    The flush operation checks time after each item is processed and yields
    a Flush() object if the time interval has elapsed. Items are yielded as
    they arrive, and Flush() objects are interleaved at the specified time
    interval. Exits when items are exhausted.
    
    """
    last_flush_time = time.time()
    
    for item in items:
        yield item
        
        # Check if it's time for a flush after processing an item
        now = time.time()
        if now - last_flush_time >= t:
            last_flush_time = now
            yield Flush()
