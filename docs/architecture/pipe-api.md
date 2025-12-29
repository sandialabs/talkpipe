# Pipe API Architecture

## Overview

The TalkPipe framework provides a powerful, composable API for building data processing pipelines. The Pipe API is built on a foundation of abstract base classes that define the core contract for data sources and transformations, enabling users to create complex workflows through simple composition patterns.

## Core Concepts

### Pipeline Philosophy

TalkPipe follows a Unix-like pipeline philosophy where data flows through a series of connected processing stages. Each stage:
- Receives data from the previous stage
- Performs some transformation or operation
- Passes the result to the next stage
- Supports lazy evaluation through Python iterators

### Key Components

The Pipe API consists of three main components:

1. **Sources** (`AbstractSource`) - Generate data without requiring input
2. **Segments** (`AbstractSegment`) - Transform data from input to output  
3. **Pipelines** (`Pipeline`) - Chain sources and segments together

## Abstract Base Classes

### AbstractSource

**File**: `src/talkpipe/pipe/core.py`

Sources are the entry points for data pipelines. They generate data without requiring upstream input.

```python
class AbstractSource(ABC, HasRuntimeComponent, Generic[U]):
    @abstractmethod
    def generate(self) -> Iterator[U]:
        """Generate data items for the pipeline."""
        pass
```

**Key Characteristics**:
- No input required (unlike segments)
- Can be chained with segments using the `|` operator
- Must implement the `generate()` method
- Support lazy evaluation through iterators

**Common Source Types**:
- File readers (CSV, JSON, text files)
- Database queries
- API endpoints
- Random data generators
- User input prompts

### AbstractSegment

**File**: `src/talkpipe/pipe/core.py`

Segments are operations that transform data flowing through the pipeline.

```python
class AbstractSegment(ABC, HasRuntimeComponent, Generic[T, U]):
    @abstractmethod
    def transform(self, input_iter: Iterable[T]) -> Iterator[U]:
        """Transform input items into output items."""
        pass
```

**Key Characteristics**:
- Input and output types can be different (T → U)
- Number of input items may differ from output items
- Can be chained together using the `|` operator
- Supports lazy evaluation through iterators

**Transformation Patterns**:
- **1:1 transformation**: Each input produces one output
- **Filtering**: Some inputs are excluded (reducing items)
- **Expanding**: Each input produces multiple outputs (increasing items)
- **Aggregating**: Multiple inputs produce fewer outputs

### Pipeline

**File**: `src/talkpipe/pipe/core.py`

Pipelines chain sources and segments together into executable workflows.

```python
class Pipeline(AbstractSegment):
    def __init__(self, *operations: Union[AbstractSource, AbstractSegment]):
        self.operations = list(operations)
```

**Execution Model**:
- Operations execute in sequence
- Each operation draws from the output of the previous operation
- Supports both sources and segments in the chain
- Lazy evaluation - items flow through the pipeline on-demand

## Composition Patterns

### Basic Chaining

Use the `|` operator to chain components:

```python
# Source | Segment | Segment
pipeline = data_source | transform1 | transform2
```

### Execution

```python
# Execute pipeline and collect results
results = list(pipeline())

# Or iterate through results
for item in pipeline():
    process(item)
```

## Decorator-Based DSL

The Pipe API provides decorators to easily convert functions into sources and segments.

### @source Decorator

**File**: `src/talkpipe/pipe/core.py`

Converts a function into a source class:

```python
@source()
def my_data_source():
    yield "item1"
    yield "item2"

# Usage
pipeline = my_data_source() | some_transform
```

**With Parameters**:
```python
@source(count=10, prefix="item")
def parameterized_source(count, prefix):
    for i in range(count):
        yield f"{prefix}_{i}"

# Usage
source_instance = parameterized_source(count=5, prefix="data")
```

### @segment Decorator

**File**: `src/talkpipe/pipe/core.py`

Converts a function into a segment class:

```python
@segment()
def uppercase(items):
    for item in items:
        yield item.upper()

# Usage
pipeline = data_source | uppercase()
```

**With Parameters**:
```python
@segment(multiplier=2)
def scale(items, multiplier):
    for item in items:
        yield item * multiplier

# Usage
pipeline = data_source | scale(multiplier=3)
```

### @field_segment Decorator

**File**: `src/talkpipe/pipe/core.py`

Creates segments that process specific fields and optionally append results:

```python
@field_segment(field="text", set_as="word_count")
def count_words(text):
    return len(text.split())

# Usage - appends word_count field to each item
pipeline = data_source | count_words()
```

## Runtime Components

### RuntimeComponent

**File**: `src/talkpipe/pipe/core.py`

Provides shared state for pipeline execution:

```python
class RuntimeComponent:
    def __init__(self):
        self._variable_store = {}  # Mutable runtime variables
        self._const_store = {}     # Immutable constants
    
    def add_constants(self, constants: dict, override: bool = True):
        """Add constants to the const_store."""
        # Implementation details...
```

### HasRuntimeComponent Mixin

**File**: `src/talkpipe/pipe/core.py`

Adds runtime component access to sources and segments:

```python
class HasRuntimeComponent:
    @property
    def runtime(self):
        return self._runtime
```

This enables segments to:
- Share state across pipeline execution
- Access configuration constants
- Store intermediate results

## Advanced Pipeline Constructs

### Script

**File**: `src/talkpipe/pipe/core.py`

Executes segments sequentially, fully resolving each before the next:

```python
class Script(AbstractSegment):
    def __init__(self, segments: List[AbstractSegment]):
        self.segments = segments
```

**Difference from Pipeline**:
- Pipeline: Lazy evaluation, items flow through on-demand
- Script: Eager evaluation, each segment completes before the next starts

### Loop

**File**: `src/talkpipe/pipe/core.py`

Repeats a script multiple times:

```python
class Loop(AbstractSegment):
    def __init__(self, times: int, script: Script):
        self.times = times
        self.script = script
```

### ForkSegment

**File**: `src/talkpipe/pipe/fork.py`

Parallel processing with multiple branches:

```python
class ForkSegment(AbstractSegment):
    def __init__(self, branches: List[AbstractSegment], 
                 mode: ForkMode = ForkMode.BROADCAST):
        self.branches = branches
        self.mode = mode
```

**Fork Modes**:
- `BROADCAST`: Send all items to all branches
- `ROUND_ROBIN`: Distribute items across branches


## Registry System

**File**: `src/talkpipe/chatterlang/registry.py`

Components can be registered for use in ChatterLang DSL:

```python
@registry.register_segment("my_transform")
class MyTransform(AbstractSegment):
    pass

@registry.register_source("my_source") 
class MySource(AbstractSource):
    pass
```

The registry enables:
- Dynamic component discovery
- ChatterLang script compilation
- Plugin architecture for custom components

## Utility Functions

### as_function()

**File**: `src/talkpipe/pipe/core.py`

Converts segments to callable functions:

```python
# Convert segment to function
func = my_segment.as_function(single_in=True, single_out=True)
result = func(input_item)
```

**Parameters**:
- `single_in`: Expect single input instead of iterable
- `single_out`: Return single output instead of list

## Best Practices

> **See Also**: The [Data Protocol](protocol.md) documentation covers conventions for data flowing through pipelines, including the dictionary convention and field access patterns.

### 1. Lazy Evaluation

Use `yield` in transform methods for memory efficiency:

```python
def transform(self, input_iter):
    for item in input_iter:
        yield process(item)  # Lazy - processes on demand
```

### 2. Error Handling

Handle errors gracefully in segments:

```python
def transform(self, input_iter):
    for item in input_iter:
        try:
            yield process(item)
        except ProcessingError:
            # Log error, skip item, or raise
            pass
```

### 3. Resource Management

Use context managers for resources:

```python
def generate(self):
    with open(self.filename) as f:
        for line in f:
            yield line.strip()
```

## End-to-End Examples

### Example 1: Text Processing Pipeline

This example demonstrates a complete text processing pipeline that reads a file, processes the content, and outputs results.

```python
from talkpipe.pipe.core import source, segment
from talkpipe.pipe.basic import *
from talkpipe.pipe.io import *

# Create a source that reads lines from a file
@segment()
def read_text_file(items):
    for filename in items:
        with open(filename, 'r') as f:
            for line in f:
                yield line.strip()

# Create segments for text processing
@segment()
def filter_non_empty(lines):
    """Filter out empty lines"""
    for line in lines:
        if line.strip():
            yield line

@segment()
def add_word_count(lines):
    """Add word count to each line"""
    for line in lines:
        word_count = len(line.split())
        yield {
            'text': line,
            'word_count': word_count,
            'length': len(line)
        }

@segment()
def filter_long_lines(items, min_words=5):
    """Filter lines with at least min_words"""
    for item in items:
        if item['word_count'] >= min_words:
            yield item

# Build and execute the pipeline
def text_processing_example():
    # Compose the pipeline
    pipeline = (
        read_text_file() |
        filter_non_empty() |
        add_word_count() |
        filter_long_lines(min_words=3) 
        #ToList()  # Collect all results into a single list
    )
    
    # Execute the pipeline
    results = list(pipeline(["sample.txt"]))

    print(results)

# Usage
# results = text_processing_example([text_file_path1, text_file_path2,...])
```

### Example 2: Data Analysis with Forking

This example shows a more complex pipeline using forking to perform parallel analysis on numerical data.

```python
from talkpipe.pipe.core import source, segment
from talkpipe.pipe.math import *
from talkpipe.pipe.fork import fork, ForkMode
from talkpipe.pipe.basic import *
import statistics

# Source: Generate sample data
@source()
def generate_sample_data(count=100):
    """Generate sample numerical data"""
    import random
    for i in range(count):
        yield {
            'id': i,
            'value': random.randint(1, 100),
            'category': random.choice(['A', 'B', 'C'])
        }

# Analysis segments
@segment()
def extract_values(items):
    """Extract just the numerical values"""
    for item in items:
        yield item['value']

@segment()
def calculate_statistics(values):
    """Calculate basic statistics from a list of values"""
    value_list = list(values)[0]
    if value_list:
        yield {
            'count': len(value_list),
            'mean': statistics.mean(value_list),
            'median': statistics.median(value_list),
            'stdev': statistics.stdev(value_list) if len(value_list) > 1 else 0
        }

@segment()
def categorize_by_range(items):
    """Categorize items by value ranges"""
    categories = {'low': 0, 'medium': 0, 'high': 0}
    for item in items:
        if item['value'] < 30:
            categories['low'] += 1
        elif item['value'] < 70:
            categories['medium'] += 1
        else:
            categories['high'] += 1
    yield categories

@segment()
def top_values(items, n=10):
    """Find top N values"""
    sorted_items = sorted(items, key=lambda x: x['value'], reverse=True)
    for item in sorted_items[:n]:
        yield item

# Complex pipeline with forking
def data_analysis_example():
    # Create the main data source
    data_source = generate_sample_data(count=200)
    
    # Create analysis branches
    stats_branch = extract_values() | ToList() | calculate_statistics()
    
    category_branch = categorize_by_range()
    
    top_values_branch = top_values(n=5)
    
    # Fork the data stream for parallel analysis
    analysis_fork = fork(
        stats_branch,
        category_branch, 
        top_values_branch,
        mode=ForkMode.BROADCAST  # Send all data to all branches
    )
    
    # Build the complete pipeline
    pipeline = data_source | analysis_fork | ToList()
    
    # Execute and collect results
    results = list(pipeline())
    
    # Process and display results
    if results:
        all_results = results[0]  # ToList() yields a single list
        print("Analysis Results:")
        print("="*50)
        
        for i, result in enumerate(all_results):
            if isinstance(result, dict):
                if 'mean' in result:
                    print(f"Statistics: Mean={result['mean']:.2f}, "
                          f"Median={result['median']:.2f}, "
                          f"Count={result['count']}")
                elif 'low' in result:
                    print(f"Categories: Low={result['low']}, "
                          f"Medium={result['medium']}, "
                          f"High={result['high']}")
                elif 'id' in result and 'value' in result:
                    print(f"Top value: ID={result['id']}, Value={result['value']}")
    
    return results

# Usage
# results = data_analysis_example()
```

### Key Takeaways from Examples

1. **Composability**: Both examples show how simple components can be combined into powerful pipelines using the `|` operator.

1. **Extensibility**: It is easy, even in a jupyter notebook, to extend the components.

2. **Lazy Evaluation**: Data flows through the pipeline on-demand, making it memory efficient even for large datasets.

3. **Reusable Components**: Segments like `filter_non_empty` and `extract_values` can be reused across different pipelines.

5. **Parallel Processing**: The forking example demonstrates how to split data streams for parallel analysis while maintaining pipeline simplicity.


## Conclusion

The Pipe API provides a flexible, composable foundation for building data processing pipelines. Through its abstract base classes, decorator-based DSL, and advanced constructs like forking and looping, it enables both simple data transformations and complex workflow orchestration while maintaining the simplicity of the Unix pipeline philosophy.


---
Last Reviewed: 20250815