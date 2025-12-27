# Metadata Stream Design Alternatives

## The Problem

Interleaving metadata with transformed items at exact positions requires either:
1. **Buffering all items** (breaks streaming)
2. **Draining the transform iterator for each item** (breaks efficiency)

This is a fundamental trade-off: precise interleaving cannot be achieved with true streaming.

## Current Design (Implemented)

When `process_metadata=False` (default):
- **If segment has downstream segments** (part of a pipeline):
  - Uses `bypass()` function with predicate `lambda x: is_metadata(x)`
  - Metadata items (`is_metadata(item) == True`) are bypassed (passed through directly)
  - Regular items (`is_metadata(item) == False`) are sent to `transform()` for processing
  - The `bypass()` function uses greenlets to interleave items according to their original stream position
  - **Streaming preserved**: Items are yielded as they are processed, maintaining relative position
- **If segment has no downstream** (terminal segment):
  - Uses `filter_out_metadata()` to completely remove metadata
  - Only regular items are processed and yielded
  - Metadata does not appear in final output

When `process_metadata=True`:
- All items (including metadata) pass to `transform()`
- Segments handle metadata positioning themselves if needed
- Segments can implement their own interleaving logic if required

## Alternative Design Options

### Option 1: Greenlet-Based Interleaving (Current Implementation)

**Pros:**
- Fully backward compatible
- Preserves streaming for regular items - no buffering
- Maintains relative position of metadata in the stream using greenlet-based interleaving
- Metadata still flows through for segments that need it
- Terminal segments can filter out metadata when not needed

**Cons:**
- Requires greenlet library for interleaving logic
- More complex implementation than simple filtering
- Segments that need explicit metadata handling must opt-in with `process_metadata=True`

**Implementation:**
- Uses `bypass()` function from `talkpipe.util.iterators` which leverages greenlets
- Metadata items are bypassed (passed through) while regular items go to `transform()`
- Items are interleaved according to original stream position
- Terminal segments (no downstream) filter metadata completely using `filter_out_metadata()`

**Use Case:** Works for flush signals, inline control signals, and any metadata that needs to maintain position in the stream. Segments that need explicit control can opt-in.

### Option 2: Metadata Attached to Items

Metadata could be attached as a property to regular items:

```python
class ItemWithMetadata:
    def __init__(self, item, metadata=None):
        self.item = item
        self.metadata = metadata  # List of metadata items "attached"
```

**Pros:**
- Maintains relative position naturally
- No separate interleaving logic needed

**Cons:**
- Breaks backward compatibility (changes item structure)
- Segments need to unwrap items
- More complex API

### Option 3: Explicit Metadata Handling Only

Remove automatic passthrough entirely. Segments that need metadata must explicitly handle it:

```python
class MetadataAwareSegment(AbstractSegment):
    def __init__(self):
        super().__init__(process_metadata=True)
    
    def transform(self, input_iter):
        for item in input_iter:
            if is_metadata(item):
                # Handle metadata
                self.handle_metadata(item)
            else:
                yield self.process(item)
```

**Pros:**
- No automatic passthrough complexity
- Segments have full control
- Streaming preserved

**Cons:**
- Metadata won't flow through segments that don't opt-in
- Less convenient for common cases (like flush signals)
- Not backward compatible (metadata would stop at segments that don't handle it)

### Option 4: Two-Stream Approach

Separate metadata into a parallel stream that segments can access:

```python
class SegmentContext:
    def __init__(self):
        self.metadata_stream = []  # Parallel metadata stream
```

**Pros:**
- Clear separation of concerns
- Can maintain position information

**Cons:**
- Complex API changes
- Segments need to coordinate two streams
- Not backward compatible

## Recommended Approach

**Current implemented design (Option 1 with greenlet-based interleaving)** was chosen because:

1. **Backward Compatible**: Existing segments work unchanged
2. **Streaming Preserved**: No buffering of transformed results - items are processed and yielded as they arrive
3. **Position Preserved**: The `bypass()` function maintains the relative position of metadata in the stream using greenlet-based interleaving
4. **Practical**: Works for common use cases (flush signals, end markers, inline control signals)
5. **Opt-in Precision**: Segments that need explicit metadata handling can opt-in with `process_metadata=True`

Implementation details:
- Uses `talkpipe.util.iterators.bypass()` function which leverages greenlets for cooperative multitasking
- Metadata items are identified by the predicate `lambda x: is_metadata(x)` 
- Items where predicate returns `True` (metadata) are bypassed (passed through)
- Items where predicate returns `False` (regular data) are sent to the handler (`transform()`)
- Output is interleaved according to original stream order, preserving position

For the common use case of flush signals:
- Metadata with flush action can be placed anywhere in the stream
- Segments that need flush can opt-in to process metadata with `process_metadata=True`
- Metadata maintains its relative position when passing through segments with `process_metadata=False`

If explicit metadata handling is needed:
- Segments set `process_metadata=True`
- They receive both metadata and regular items in their original order
- They can implement custom interleaving logic if required
- They can yield metadata at precise positions in their output

## Example: Buffer with Flush

```python
class BufferedSegment(AbstractSegment):
    def __init__(self, buffer_size=10):
        super().__init__(process_metadata=True)  # Opt-in for metadata
        self.buffer = []
        self.buffer_size = buffer_size
    
    def transform(self, input_iter):
        for item in input_iter:
            if is_metadata(item) and hasattr(item, 'action') and item.action == "flush":
                # Flush buffer
                for buffered in self.buffer:
                    yield buffered
                self.buffer = []
            elif not is_metadata(item):
                # Regular item
                self.buffer.append(item)
                if len(self.buffer) >= self.buffer_size:
                    yield self.buffer.pop(0)
        
        # Flush remaining
        for item in self.buffer:
            yield item
```

This segment receives metadata in order and can handle it appropriately without requiring framework-level interleaving.


