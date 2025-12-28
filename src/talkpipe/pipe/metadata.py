from typing import Annotated
from .core import Metadata, segment, source, is_metadata
from talkpipe.chatterlang import register_segment, register_source
import time

class Flush(Metadata):
    """A metadata object that indicates a flush operation."""
    pass

@register_segment("flushN")
@segment()
def flushN(items, n: Annotated[int, "Number of items between flush operations."]):
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
def flushT(items, t: Annotated[float, "Time interval in seconds between flush operations."]):
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

@register_source("flushT")
@source()
def FlushTSource(t: Annotated[float, "Time interval in seconds between flush operations."]):
    """Issues a flush operation every t seconds.
        
    """
    while True:
        yield Flush()
        time.sleep(t)

@register_segment("collectMetadata")
@segment(process_metadata=True)
def CollectMetadata(items):
    """Collects metadata objects from the input stream.
    
    Args:
        items: The input stream.
    
    Example:
        collectMetadata(items)  # Collect metadata objects from the input stream
    """
    for item in items:
        if is_metadata(item):
            ans = str(type(item))
            yield ans