# Extending TalkPipe

Comprehensive guide to extending TalkPipe with custom functionality.

## Overview

TalkPipe is designed to be highly extensible, allowing developers to create custom data sources, processing segments, and complete pipeline components. The framework provides multiple extension mechanisms that integrate seamlessly with the existing pipeline architecture.

## Creating Custom Sources and Segments

### Understanding the Core Abstractions

TalkPipe defines two primary building blocks for pipelines:

- **AbstractSource** - Data generators that start pipelines without requiring input
- **AbstractSegment** - Data processors that transform input streams into output streams

Both follow the streaming, generator-based architecture for memory efficiency and lazy evaluation.

### Custom Sources

Sources generate data for pipeline consumption. They implement the `AbstractSource` base class:

#### Class-Based Sources

```python
from talkpipe.pipe.core import AbstractSource
from typing import Iterator

class DatabaseSource(AbstractSource[dict]):
    """Custom source that reads from a database."""
    
    def __init__(self, connection_string: str, query: str):
        super().__init__()
        self.connection_string = connection_string
        self.query = query
    
    def generate(self) -> Iterator[dict]:
        """Generate records from database query."""
        # Connect to database
        with get_connection(self.connection_string) as conn:
            for row in conn.execute(self.query):
                yield dict(row)  # Convert to dictionary

# Usage
db_source = DatabaseSource("sqlite:///data.db", "SELECT * FROM users")
pipeline = db_source | some_processor | output_segment
```

#### Function-Based Sources with Decorators

The `@source` decorator converts functions into source classes:

```python
from talkpipe.pipe.core import source

# Simple function source
@source
def count_source():
    """Generate counting numbers."""
    for i in range(100):
        yield i

# Parameterized function source  
@source()
def file_lines_source(filename: str):
    """Read lines from a file."""
    with open(filename, 'r') as f:
        for line_num, line in enumerate(f, 1):
            yield {
                'line_number': line_num,
                'content': line.strip()
            }

# Usage
numbers = count_source()
file_data = file_lines_source(filename="data.txt")
```

### Custom Segments

Segments process data flowing through pipelines. They implement the `AbstractSegment` base class:

#### Class-Based Segments

```python
from talkpipe.pipe.core import AbstractSegment
from typing import Iterable, Iterator

class JsonParseSegment(AbstractSegment[str, dict]):
    """Parse JSON strings into dictionaries."""
    
    def __init__(self, fail_on_invalid: bool = True):
        super().__init__()
        self.fail_on_invalid = fail_on_invalid
    
    def transform(self, input_iter: Iterable[str]) -> Iterator[dict]:
        """Transform JSON strings to dictionaries."""
        import json
        
        for json_str in input_iter:
            try:
                yield json.loads(json_str)
            except json.JSONDecodeError as e:
                if self.fail_on_invalid:
                    raise ValueError(f"Invalid JSON: {json_str}") from e
                else:
                    # Skip invalid JSON and continue
                    continue

# Usage
json_parser = JsonParseSegment(fail_on_invalid=False)
pipeline = json_source | json_parser | data_processor
```

#### Function-Based Segments with Decorators

The `@segment` decorator converts functions into segment classes:

```python
from talkpipe.pipe.core import segment

# Simple segment function
@segment
def uppercase_segment(items):
    """Convert strings to uppercase."""
    for item in items:
        yield item.upper()

# Parameterized segment function
@segment()
def filter_by_field(items, field: str, value: str):
    """Filter items where field equals value."""
    for item in items:
        if item.get(field) == value:
            yield item

# Field-specific segment
@field_segment()
def extract_domain(email: str):
    """Extract domain from email address."""
    return email.split('@')[1] if '@' in email else None

# Usage
uppercase = uppercase_segment()
active_users = filter_by_field(field="status", value="active")
get_domain = extract_domain(field="email", append_as="domain")
```

#### Advanced Segment Patterns

**Error Handling Segments:**

```python
@segment()
def safe_process(items, processor_func, default_value=None):
    """Apply processor with error handling."""
    for item in items:
        try:
            yield processor_func(item)
        except Exception as e:
            if default_value is not None:
                yield default_value
            else:
                logger.warning(f"Processing failed for {item}: {e}")
                continue
```

**Stateful Segments:**

```python
class WindowSegment(AbstractSegment):
    """Collect items into sliding windows."""
    
    def __init__(self, window_size: int, step_size: int = 1):
        super().__init__()
        self.window_size = window_size
        self.step_size = step_size
    
    def transform(self, input_iter: Iterable) -> Iterator[list]:
        window = []
        step_count = 0
        
        for item in input_iter:
            window.append(item)
            
            if len(window) == self.window_size:
                yield list(window)  # Emit window copy
                
                # Slide window by step_size
                window = window[self.step_size:]
                
        # Emit final partial window if exists
        if window:
            yield window
```

## Plugin Architecture

### Registry System

TalkPipe uses a registry system to manage and discover components:

#### Component Registration

```python
import talkpipe.chatterlang.registry as registry

# Register segments for ChatterLang DSL
@registry.register_segment("customParser")
class CustomParserSegment(AbstractSegment):
    # Implementation here
    pass

# Register sources  
@registry.register_source("apiData")
class APIDataSource(AbstractSource):
    # Implementation here
    pass
```

#### Registry Usage

The registry enables dynamic component loading in ChatterLang scripts:

```chatterlang
// ChatterLang can now use registered components
input apiData(url="https://api.example.com/data")
| customParser(format="json")
| print
```

### Creating Plugin Packages

```python
# my_plugin/registry.py
import talkpipe.chatterlang.registry as registry
from .sources import MyCustomSource
from .segments import MyCustomSegment

def register_all_components():
    """Register all plugin components."""
    registry.input_registry.register(MyCustomSource, "mySource")
    registry.segment_registry.register(MyCustomSegment, "mySegment")
```

#### Plugin Installation and Usage

```python
# Install plugin
pip install my-talkpipe-plugin

# Use in Python
import talkpipe
import my_plugin  # Auto-registers components

# Components are now available
source = my_plugin.MyCustomSource()
segment = my_plugin.MyCustomSegment()
```

## Module Loading and Registration

### Automatic Discovery

TalkPipe automatically loads components from several locations:

#### Core Module Loading

The main `__init__.py` imports all built-in components:

```python
# talkpipe/__init__.py
from talkpipe.pipe.basic import *
from talkpipe.pipe.math import *
from talkpipe.pipe.io import *
from talkpipe.data.email import *
from talkpipe.data.rss import *
# ... other modules
```

#### Dynamic Registration Pattern

Components register themselves when their modules are imported:

```python
# In any module
@registry.register_segment("myComponent")
class MyComponent(AbstractSegment):
    pass

# Registration happens at import time
```

### Manual Registration

For fine-grained control, components can be registered manually:

```python
from talkpipe.chatterlang import registry

# Manual registration
registry.segment_registry.register(MySegment, name="mySegment")
registry.input_registry.register(MySource, name="mySource")

# Verify registration
all_segments = registry.segment_registry.all
all_sources = registry.input_registry.all
```

## API Compatibility Guidelines

### Interface Contracts

#### AbstractSource Requirements

Custom sources must implement:

```python
class CustomSource(AbstractSource[OutputType]):
    def generate(self) -> Iterator[OutputType]:
        """REQUIRED: Generate data items."""
        # Must yield items, not return a list
        # Should handle resource cleanup
        # May generate infinite sequences
```

#### AbstractSegment Requirements

Custom segments must implement:

```python
class CustomSegment(AbstractSegment[InputType, OutputType]):
    def transform(self, input_iter: Iterable[InputType]) -> Iterator[OutputType]:
        """REQUIRED: Transform input stream to output stream."""
        # Must consume input_iter completely if processing all items
        # Must yield results, not return a list
        # Should handle errors gracefully
        # May produce different number of outputs than inputs
```

### Memory Efficiency Guidelines

**Streaming Requirements:**
- Always use `yield` instead of collecting results in lists
- Process items one at a time when possible
- Avoid loading entire datasets into memory

```python
# GOOD: Streaming approach
def transform(self, input_iter):
    for item in input_iter:
        processed = self.process_item(item)
        yield processed

# BAD: Memory-intensive approach  
def transform(self, input_iter):
    all_items = list(input_iter)  # Loads everything into memory
    results = [self.process_item(item) for item in all_items]
    return iter(results)
```

### Error Handling Standards

**Exception Propagation:**
- Let exceptions bubble up unless specifically handling them
- Provide meaningful error messages with context
- Support optional graceful degradation

```python
def transform(self, input_iter):
    for item in input_iter:
        try:
            yield self.risky_operation(item)
        except SpecificError as e:
            if self.fail_silently:
                logger.warning(f"Skipping item {item}: {e}")
                continue
            else:
                raise ProcessingError(f"Failed processing {item}") from e
```

### Type Safety

**Generic Type Parameters:**
- Use appropriate type hints for input and output types
- Leverage generic type parameters for type safety

```python
from typing import TypeVar, Generic, Iterator, Iterable

T = TypeVar('T')
U = TypeVar('U')

class TypedSegment(AbstractSegment[T, U], Generic[T, U]):
    def transform(self, input_iter: Iterable[T]) -> Iterator[U]:
        # Type checker can verify correctness
        pass
```

### Backwards Compatibility

**API Stability:**
- Avoid breaking changes in public interfaces
- Use deprecation warnings for API changes
- Provide migration paths for major changes

```python
import warnings

class LegacySegment(AbstractSegment):
    def __init__(self, old_param=None, new_param=None):
        if old_param is not None:
            warnings.warn(
                "old_param is deprecated, use new_param instead",
                DeprecationWarning,
                stacklevel=2
            )
            new_param = old_param
        
        self.param = new_param
```

### Testing Extensions

**Unit Testing Pattern:**

```python
import unittest
from your_extension import CustomSegment

class TestCustomSegment(unittest.TestCase):
    def test_basic_functionality(self):
        segment = CustomSegment()
        input_data = [1, 2, 3]
        results = list(segment.transform(input_data))
        self.assertEqual(results, [2, 4, 6])  # Expected output
    
    def test_empty_input(self):
        segment = CustomSegment()
        results = list(segment.transform([]))
        self.assertEqual(results, [])
    
    def test_error_handling(self):
        segment = CustomSegment(fail_on_error=True)
        with self.assertRaises(ValueError):
            list(segment.transform(["invalid_input"]))
```

**Integration Testing:**

```python
def test_pipeline_integration(self):
    """Test segment works in pipeline context."""
    pipeline = source() | CustomSegment() | output_segment()
    results = list(pipeline())
    # Verify end-to-end functionality
```

This extension system enables TalkPipe to grow organically while maintaining consistent interfaces and performance characteristics across all components.

---

Last Reviewed: 20250818