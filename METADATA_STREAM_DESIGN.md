# Metadata Stream Design Summary

## Overview

This document summarizes the design and implementation of the metadata stream feature for TalkPipe pipelines. This feature enables pipelines to carry control signals and metadata alongside regular data items, enabling use cases such as buffer flushing, end-of-stream signals, and configuration updates.

## Design Goals

1. ✅ **No API Breaking Changes**: Existing pipelines continue to work unchanged
2. ✅ **Opt-in by Default**: Metadata is ignored by default and passes through automatically
3. ✅ **Differentiable**: Metadata objects are easily identifiable in the stream
4. ✅ **Flexible**: Sources and segments can emit or process metadata as needed

## Implementation Summary

### Core Components Added

#### 1. Metadata Class (Pydantic BaseModel)

Located in `src/talkpipe/pipe/core.py`:

```python
from pydantic import BaseModel, ConfigDict

class Metadata(BaseModel):
    """Metadata objects flowing through pipelines."""
    model_config = ConfigDict(extra="allow")  # Allow arbitrary fields
```

Metadata inherits from Pydantic BaseModel, allowing arbitrary fields to be added dynamically. This makes it easy to create metadata with specific attributes while maintaining type safety and validation.

#### 2. Utility Functions

- `is_metadata(obj) -> bool`: Check if an object is a Metadata instance (uses `isinstance(obj, Metadata)`)
- `create_metadata(**kwargs) -> Metadata`: Convenience function to create metadata with fields
- `filter_out_metadata(input_iter) -> Iterator`: Filter iterator to exclude metadata items (used when segment has no downstream)

#### 3. API Extensions

**AbstractSegment:**
- New parameter: `process_metadata: bool = False` (default)
- When `False`: Metadata automatically passes through without being seen by `transform()`
- When `True`: Metadata is passed to `transform()` for explicit handling

**AbstractSource:**
- New parameter: `process_metadata: bool = False` (for API consistency)
- Sources can emit metadata in `generate()` regardless of this flag

**Pipeline:**
- Defaults to `process_metadata=True` to ensure metadata flows to operations
- Each operation handles metadata according to its own flag

### Default Behavior (process_metadata=False)

When a segment has `process_metadata=False` (the default):
1. The `__call__()` method intercepts metadata before calling `transform()`
2. **If the segment has downstream segments** (is part of a pipeline chain):
   - Uses the `bypass()` function to interleave metadata with transformed items
   - Items where `is_metadata(item) == True` are bypassed (passed through directly)
   - Items where `is_metadata(item) == False` are sent to `transform()` for processing
   - The `bypass()` function uses greenlets to interleave items according to their original position in the stream
   - This preserves streaming behavior - items are yielded as they are processed
3. **If the segment has no downstream segments** (is the last segment):
   - Uses `filter_out_metadata()` to completely remove metadata items
   - Only regular items are passed to `transform()`
   - Metadata does not appear in the final output
4. Transformed items are yielded immediately as they are processed (streaming preserved)

### Explicit Processing (process_metadata=True)

When a segment has `process_metadata=True`:
1. All items (including metadata) are passed to `transform()`
2. The segment's `transform()` method receives metadata objects
3. The segment must check for metadata using `is_metadata()` and handle it explicitly
4. The segment controls whether to propagate metadata downstream

## Usage Examples

### Example 1: Buffer Flushing

```python
from talkpipe.pipe.core import AbstractSegment, Metadata, is_metadata

class BufferedSegment(AbstractSegment):
    def __init__(self, buffer_size=10):
        super().__init__(process_metadata=True)  # Enable metadata processing
        self.buffer_size = buffer_size
        self.buffer = []
    
    def transform(self, input_iter):
        for item in input_iter:
            # Metadata is easily identifiable - no need to unwrap
            if is_metadata(item):
                # Access fields directly as attributes
                if hasattr(item, 'action') and item.action == "flush":
                    # Flush buffer
                    for buffered_item in self.buffer:
                        yield buffered_item
                    self.buffer = []
                    continue
            
            self.buffer.append(item)
            if len(self.buffer) >= self.buffer_size:
                yield self.buffer.pop(0)
        
        # Flush remaining items
        for item in self.buffer:
            yield item
```

### Example 2: Source Emitting Metadata

```python
from talkpipe.pipe.core import source, Metadata

@source()
def file_reader(filename: str):
    with open(filename) as f:
        for line in f:
            yield line.strip()
    # Signal end of file - arbitrary fields allowed
    yield Metadata(event="eof", filename=filename)
```

### Example 3: Segments That Ignore Metadata (Default)

```python
from talkpipe.pipe.core import segment

@segment()
def simple_transform(items):
    """Metadata automatically passes through - never seen by transform()"""
    for item in items:
        yield process_item(item)
```

## Files Modified

1. **src/talkpipe/pipe/core.py**
   - Added `Metadata` class (Pydantic BaseModel)
   - Added utility functions: `is_metadata()`, `create_metadata()`, `filter_out_metadata()`
   - Extended `AbstractSegment` with `process_metadata` parameter and passthrough logic
   - Extended `AbstractSource` with `process_metadata` parameter (for API consistency)
   - Updated `AbstractFieldSegment` to handle metadata
   - Updated `Pipeline` to default to `process_metadata=True`
   - Updated all decorator-generated classes (`@segment`, `@source`, `@field_segment`) to support `process_metadata` parameter
   - Fixed decorator bug where `process_metadata` value was being lost due to `.pop()` mutating the dictionary

2. **src/talkpipe/util/iterators.py**
   - Uses existing `bypass()` function for interleaving metadata with transformed items
   - The `bypass()` function uses greenlets to coordinate between bypassed items and handler output

2. **docs/architecture/metadata-stream.md**
   - Comprehensive documentation with examples and best practices

## Backward Compatibility

✅ **Fully backward compatible:**
- All existing segments default to `process_metadata=False`
- Existing pipelines continue to work unchanged
- No changes required to existing code
- Metadata support is purely additive

## Testing Recommendations

The following test cases should be added:

1. **Metadata passthrough**: Verify metadata passes through segments with `process_metadata=False`
2. **Metadata processing**: Verify segments with `process_metadata=True` receive metadata
3. **Source metadata emission**: Verify sources can emit metadata
4. **Pipeline metadata flow**: Verify metadata flows correctly through pipelines
5. **Decorator compatibility**: Verify decorator-generated segments handle metadata correctly

## Next Steps

1. Add unit tests for metadata stream functionality
2. Create example segments that use metadata (e.g., BufferedSegment, FlushSegment)
3. Update existing segments that could benefit from metadata (e.g., batching, buffering segments)
4. Consider adding metadata-aware utility functions for common patterns

## Design Decisions

1. **Metadata as Pydantic BaseModel**: Makes metadata easily differentiable while allowing arbitrary fields to be added dynamically. Inherits validation and type safety from Pydantic.
2. **Default passthrough**: Ensures backward compatibility and most segments don't need to care about metadata
3. **Pipeline defaults to True**: Ensures metadata flows through to operations, which then handle it according to their flags
4. **Separation in __call__**: Keeps `transform()` clean - segments don't need to handle metadata separation manually
5. **Streaming behavior**: Items are yielded as they are received and processed using the `bypass()` function, which interleaves metadata with transformed items according to their original position. This maintains lazy evaluation and memory efficiency.
6. **Different handling based on downstream**: Segments with downstream use `bypass()` to preserve metadata in the stream, while terminal segments use `filter_out_metadata()` to remove metadata from final output
7. **Greenlet-based interleaving**: The `bypass()` function uses greenlets to coordinate between bypassed items (metadata) and handler output (transformed items), enabling true streaming interleaving

This design provides a clean, extensible, and backward-compatible way to add metadata streaming to TalkPipe pipelines.

