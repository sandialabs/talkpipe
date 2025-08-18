# Streaming Architecture

How TalkPipe processes data efficiently using Python generators.

## Overview

TalkPipe's streaming architecture is built on Python generators and iterators, enabling efficient processing of data streams without loading entire datasets into memory. This approach allows TalkPipe to handle large datasets, infinite streams, and real-time data processing with minimal resource consumption.

## Memory-Efficient Data Processing

### Generator-Based Pipeline

TalkPipe's core architecture uses Python generators throughout the pipeline chain. Each segment in the pipeline:

- Receives an `Iterable[T]` as input
- Returns an `Iterator[U]` as output using `yield` statements
- Processes items one at a time rather than collecting all results

```python
def transform(self, input_iter: Iterable[T]) -> Iterator[U]:
    for item in input_iter:
        # Process item individually
        processed_item = self.process(item)
        yield processed_item  # Stream result immediately
```

This design means that:
- Memory usage remains constant regardless of dataset size
- Processing begins immediately when data becomes available
- Memory footprint scales with pipeline complexity, not data volume

### Streaming Data Sources

Data sources (`AbstractSource`) generate items on-demand:

```python
def generate(self) -> Iterator[U]:
    # File-based streaming
    with open(self.filename) as f:
        for line in f:
            yield line.strip()  # One line at a time
```

This allows TalkPipe to:
- Process files larger than available memory
- Handle real-time data feeds
- Support infinite data sequences

## Lazy Evaluation Principles

### On-Demand Processing

TalkPipe employs lazy evaluation where:

- **No computation occurs until data is consumed** - Pipelines are constructed but don't execute until terminal operations
- **Items flow through the pipeline individually** - Each item is processed through all stages before the next item begins
- **Intermediate results are not stored** - Data flows directly from one segment to the next

### Pipeline Construction vs Execution

```python
# Pipeline construction (no data processing yet)
pipeline = source | transform1 | transform2 | filter_segment

# Execution begins only when consumed
for result in pipeline():  # Now processing starts
    handle(result)
```

### Chaining Behavior

When segments are chained with the `|` operator:

1. **Upstream registration** - Each segment tracks its dependencies
2. **Deferred execution** - No processing occurs during chain construction
3. **Flow-through processing** - Data flows item-by-item through the entire chain

## Backpressure Handling

### Natural Flow Control

Python's iterator protocol provides built-in backpressure handling:

- **Pull-based processing** - Downstream segments request data from upstream segments
- **Automatic throttling** - Slow consumers naturally throttle fast producers
- **Memory bounded** - Only active pipeline segments consume memory

### Iterator Consumption Patterns

Different consumption patterns can be used to provide natural backpressure:

```python
# Immediate consumption - no backpressure
results = list(pipeline())

# Batched consumption - controlled backpressure  
for batch in batched(pipeline(), 100):
    process_batch(batch)

# Single-item consumption - maximum backpressure
for item in pipeline():
    if should_stop():
        break  # Pipeline stops producing
```

### Resource Management

The streaming architecture prevents resource exhaustion:

- **No buffer overflow** - Generators don't pre-compute results
- **Garbage collection friendly** - Items are released as soon as they're processed
- **Interruptible processing** - Pipelines can be stopped mid-stream

## Error Propagation

### Error Handling Strategies

TalkPipe supports multiple error handling approaches:

1. **Fail-fast** - Exceptions terminate the entire pipeline
2. **Graceful degradation** - Error handling segments can catch and transform exceptions
3. **Partial processing** - Some segments support `fail_silently` options

### Context Preservation

When errors occur:
- **Stack traces preserve pipeline context** - Shows which segment failed
- **Item context available** - Current item being processed is accessible
- **Pipeline state maintained** - Upstream/downstream relationships preserved

### Error Recovery Patterns

```python
# Error filtering segment
def transform(self, input_iter):
    for item in input_iter:
        try:
            result = risky_operation(item)
            yield result
        except SpecificError:
            logger.warning(f"Skipping item {item}")
            continue  # Skip failed items
```

## Performance Characteristics

### Memory Efficiency
- **O(1) memory usage** relative to data size
- **O(n) memory usage** relative to pipeline depth
- **Minimal object creation** - generators reuse iteration state

### Processing Latency
- **Low latency** - first results available immediately
- **Consistent throughput** - no batch processing delays
- **Interruptible** - processing can stop at any point

### Scalability
- **Horizontal scaling** - multiple pipeline instances can process partitioned data
- **Vertical scaling** - memory usage doesn't grow with data volume
- **Resource predictability** - memory usage determined by pipeline structure

This streaming architecture makes TalkPipe suitable for processing large datasets, real-time data streams, and building memory-efficient data processing pipelines that can run in resource-constrained environments.

---

Last Reviewed: 20250818