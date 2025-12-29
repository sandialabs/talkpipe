# Metadata Stream Design

## Overview

The metadata stream feature enables pipelines to carry control signals and metadata alongside regular data items. This is particularly useful for implementing features like flushing buffers, sending end-of-stream signals, or passing configuration updates through pipelines.

## Key Design Principles

1. **Ignored by Default**: Metadata objects pass through segments without processing unless explicitly enabled
2. **Opt-in Processing**: Segments can enable metadata processing by setting `process_metadata=True`
3. **Stream Integration**: Metadata flows through pipelines like regular objects but is differentiable
4. **Backward Compatible**: Existing pipelines continue to work unchanged

## Core Components

### Metadata Class

The `Metadata` class is a Pydantic BaseModel that allows arbitrary fields to be added dynamically. This makes it easy to create metadata with specific attributes while maintaining type safety:

```python
from talkpipe.pipe.core import Metadata, create_metadata, is_metadata

# Create metadata with specific fields
flush_signal = Metadata(action="flush", buffer_id="main")
# Or using convenience function
flush_signal = create_metadata(action="flush", buffer_id="main")

# Create from dictionary
data = {"action": "flush", "timestamp": "2025-01-15"}
flush_signal = Metadata(**data)

# Check if an item is metadata and access fields directly
if is_metadata(item):
    if item.action == "flush":
        # Handle flush
        pass
    # Access any field directly
    buffer_id = item.buffer_id
```

### API Changes

#### AbstractSegment

- **New parameter**: `process_metadata: bool = False`
  - When `False` (default): Metadata objects are automatically passed through without calling `transform()`
  - When `True`: Metadata objects are passed to `transform()` for explicit handling

#### AbstractSource

- **New parameter**: `process_metadata: bool = False` (for API consistency)
  - Sources can emit metadata in their `generate()` method regardless of this flag

## Usage Patterns

### Basic Usage: Flushing Buffers

A common use case is flushing buffers at the end of a stream:

```python
from talkpipe.pipe.core import AbstractSegment, Metadata, is_metadata

class BufferedSegment(AbstractSegment):
    """Segment that buffers items and flushes on metadata signal."""
    
    def __init__(self, buffer_size=10):
        super().__init__(process_metadata=True)  # Enable metadata processing
        self.buffer_size = buffer_size
        self.buffer = []
    
    def transform(self, input_iter):
        for item in input_iter:
            # Check if this is a flush signal - metadata is easily identifiable
            if is_metadata(item):
                if hasattr(item, 'action') and item.action == "flush":
                    # Flush buffer
                    for buffered_item in self.buffer:
                        yield buffered_item
                    self.buffer = []
                    continue
            
            # Regular item processing
            self.buffer.append(item)
            if len(self.buffer) >= self.buffer_size:
                yield self.buffer.pop(0)
        
        # Flush remaining items
        for item in self.buffer:
            yield item

# Usage
@source()
def data_source():
    for i in range(25):
        yield {"id": i, "data": f"item_{i}"}
    # Send flush signal with arbitrary fields
    yield Metadata(action="flush", buffer_id="main")

pipeline = data_source() | BufferedSegment(buffer_size=10, process_metadata=True)
```

### Emitting Metadata from Sources

Sources can emit metadata to signal downstream segments:

```python
@source()
def file_reader(filename: str):
    with open(filename) as f:
        for line in f:
            yield line.strip()
    # Signal end of file with arbitrary fields
    yield Metadata(event="eof", filename=filename)
```

### Segments That Ignore Metadata (Default Behavior)

By default, segments automatically pass metadata through:

```python
@segment()
def simple_transform(items):
    """This segment doesn't need to handle metadata - it passes through automatically."""
    for item in items:
        # Metadata items are automatically filtered out before transform() is called
        # when process_metadata=False (the default)
        yield process_item(item)

# Metadata will still flow through the pipeline but won't be seen by transform()
```

### Explicit Metadata Handling

When a segment needs to process metadata:

```python
class MetadataAwareSegment(AbstractSegment):
    def __init__(self):
        super().__init__(process_metadata=True)  # Enable metadata processing
    
    def transform(self, input_iter):
        for item in input_iter:
            if is_metadata(item):
                # Handle metadata explicitly - access fields directly
                if hasattr(item, 'action') and item.action == "flush":
                    # Perform flush operation
                    self.flush_buffer()
                # Don't yield metadata unless you want to propagate it
            else:
                # Process regular items - easily differentiated from metadata
                yield self.process(item)
```

## Implementation Details

### Default Behavior (process_metadata=False)

When `process_metadata=False`:
1. `__call__()` intercepts metadata objects before calling `transform()`
2. Metadata is separated from regular items
3. Regular items are passed to `transform()` for processing
4. Metadata is automatically yielded after transformed items (preserving metadata signals like flush that typically come at the end)

### Explicit Processing (process_metadata=True)

When `process_metadata=True`:
1. All items (including metadata) are passed to `transform()`
2. The segment's `transform()` method receives metadata objects
3. The segment must explicitly handle metadata (check with `is_metadata()`)
4. Metadata is not automatically yielded - the segment controls whether to propagate it

### Pipeline Behavior

Pipelines default to `process_metadata=True` so metadata flows through to their operations. Each operation handles metadata according to its own `process_metadata` flag.

## Examples

### Example 1: Batched Processing with Flush

```python
from talkpipe.pipe.core import AbstractSegment, Metadata, is_metadata, source, segment

class BatchProcessor(AbstractSegment):
    def __init__(self, batch_size=5):
        super().__init__(process_metadata=True)
        self.batch_size = batch_size
        self.batch = []
    
    def transform(self, input_iter):
        for item in input_iter:
            if is_metadata(item):
                # Easy to identify metadata and access its fields
                if hasattr(item, 'action') and item.action == "flush" and self.batch:
                    # Process and yield remaining batch
                    yield self.process_batch(self.batch)
                    self.batch = []
                continue
            
            self.batch.append(item)
            if len(self.batch) >= self.batch_size:
                yield self.process_batch(self.batch)
                self.batch = []
    
    def process_batch(self, batch):
        return {"batch": batch, "count": len(batch)}

@source()
def data_source():
    for i in range(12):
        yield {"id": i}
    yield Metadata(action="flush")  # Arbitrary fields allowed

pipeline = data_source() | BatchProcessor(batch_size=5)
# Will produce 3 batches: [0-4], [5-9], [10-11] (last on flush)
```

### Example 2: Metadata Passing Through

```python
@source()
def source_with_metadata():
    yield {"data": "item1"}
    yield Metadata(signal="important")  # Metadata with arbitrary fields
    yield {"data": "item2"}

@segment()
def passthrough_transform(items):
    """This automatically passes metadata through without seeing it."""
    for item in items:
        yield item  # Metadata never reaches here when process_metadata=False

pipeline = source_with_metadata() | passthrough_transform()
# Metadata flows through to downstream segments
```

## Best Practices

1. **Use metadata for control signals**: Flush signals, end-of-stream markers, configuration updates
2. **Use clear field names**: Use descriptive field names (e.g., `action="flush"`, `event="eof"`)
3. **Access fields directly**: Metadata is a Pydantic model, so access fields as attributes (e.g., `item.action` not `item["action"]`)
4. **Document metadata handling**: If your segment processes metadata, document what fields it expects
5. **Default to passthrough**: Most segments should leave `process_metadata=False` (default) unless they need to handle metadata
6. **Preserve metadata order**: When emitting metadata from sources, consider when in the stream it should appear
7. **Items are yielded as received**: Metadata passthrough maintains streaming behavior - items flow through as they are processed

## Backward Compatibility

- All existing segments continue to work unchanged (default `process_metadata=False`)
- Existing pipelines that don't use metadata are unaffected
- The API remains backward compatible - metadata support is purely additive

