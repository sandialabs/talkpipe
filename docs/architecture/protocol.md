# TalkPipe Data Protocol

This document describes the data protocol used for communication between sources and segments in TalkPipe pipelines.

## Core Principles

### 1. Generators and Streams

At its foundation, TalkPipe operates on **generators** and **streams of independent objects**:

- **Sources** are generators that yield objects (`Iterator[U]`)
- **Segments** are transformers that consume an iterable and yield objects (`Iterable[T] -> Iterator[U]`)
- Each object in the stream is **independent** - segments process items one at a time without requiring knowledge of other items
- Processing is **lazy** - items flow through the pipeline on-demand, not all at once

```python
# Source: generates items
def generate(self) -> Iterator[U]:
    yield item1
    yield item2

# Segment: transforms items
def transform(self, input_iter: Iterable[T]) -> Iterator[U]:
    for item in input_iter:
        yield process(item)
```

### 2. Arbitrary Object Types

The core pipe API places **no restrictions** on the types of objects that flow through pipelines:

- Objects can be strings, numbers, lists, dictionaries, custom classes, or any Python object
- Input type (`T`) and output type (`U`) can differ between segments
- A segment may change the type of objects it emits compared to what it receives

```python
# Valid: strings in, dictionaries out
@segment()
def parse_json(items):
    for json_str in items:
        yield json.loads(json_str)  # str -> dict

# Valid: any object in, same object out (pass-through)
@segment()
def log_items(items):
    for item in items:
        logger.info(f"Processing: {item}")
        yield item
```

### 3. Cardinality Flexibility

Segments can change the number of items in the stream:

| Pattern | Description | Example |
|---------|-------------|---------|
| **1:1** | Each input produces one output | `uppercase()` |
| **1:N** | Each input produces multiple outputs | `split_lines()`, `readFile()` with CSV |
| **N:1** | Multiple inputs produce one output | `collect()`, `aggregate()` |
| **1:0/1** | Filter - some inputs produce no output | `filter()`, `skip_file()` |

```python
# 1:N (multi-emit): One file yields multiple lines
@field_segment(multi_emit=True)
def read_lines(file_path):
    with open(file_path) as f:
        for line in f:
            yield line.strip()

# 1:0/1 (filter): Only yield items matching criteria
@segment()
def filter_positive(items):
    for item in items:
        if item > 0:
            yield item
```

## Conventions

While the core API accepts arbitrary objects, TalkPipe establishes conventions for consistency and interoperability, particularly at the `talkpipe/pipelines` level.

### The Dictionary Convention

**Convention**: Higher-level pipelines (in `talkpipe/pipelines`) expect items to be **dictionaries** or **Pydantic models**.

This convention enables:
- Consistent field access across segments
- Field extraction and assignment patterns
- Composability between segments from different authors
- Clear data contracts between pipeline stages

#### Using Dictionaries

```python
# Conventional item structure using a dictionary
item = {
    "text": "Hello, world!",
    "source": "user_input",
    "timestamp": "2025-01-15T10:30:00Z",
    "metadata": {
        "language": "en",
        "length": 13
    }
}
```

#### Using Pydantic Models

For stronger type safety and clearer documentation of required fields, you can use **Pydantic models** with `extra="allow"`. This enforces required fields while still allowing segments to add additional fields dynamically.

```python
from pydantic import BaseModel, ConfigDict

class DocumentItem(BaseModel):
    """Item representing a document in the pipeline."""
    model_config = ConfigDict(extra="allow")  # Allow additional fields to be added

    # Required fields - enforced by Pydantic
    text: str
    source: str

    # Optional fields with defaults
    language: str = "en"

# Create an item with required fields
item = DocumentItem(text="Hello, world!", source="user_input")

# Segments can add additional fields dynamically
item.word_count = 2  # Works because extra="allow"
item.processed = True
```

**Benefits of Pydantic models:**
- **Required fields are enforced** - Missing fields raise validation errors
- **Type hints are validated** - Wrong types raise errors
- **Self-documenting** - The model definition shows what fields are expected
- **IDE support** - Autocomplete for defined fields
- **Flexible** - `extra="allow"` permits segments to add new fields

The `field` and `set_as` parameters in `AbstractFieldSegment` and `@field_segment` work with both dictionaries and Pydantic models.

### Field Access Utilities

TalkPipe provides utilities for working with dictionary items:

```python
from talkpipe.util.data_manipulation import extract_property, assign_property

# Extract nested fields using dot notation
text = extract_property(item, "text")           # "Hello, world!"
lang = extract_property(item, "metadata.language")  # "en"

# Assign values to fields
assign_property(item, "word_count", 2)
assign_property(item, "metadata.processed", True)
```

The special value `"_"` refers to the entire item:
```python
whole_item = extract_property(item, "_")  # Returns the entire item
```

### AbstractFieldSegment

The `AbstractFieldSegment` base class implements the dictionary convention:

```python
class MyProcessor(AbstractFieldSegment):
    def __init__(self, field="text", set_as="processed"):
        super().__init__(field=field, set_as=set_as)

    def process_value(self, value):
        return value.upper()

# Usage:
# Input:  {"text": "hello", "id": 1}
# Output: {"text": "hello", "id": 1, "processed": "HELLO"}
```

Key parameters:
- `field`: Which field to extract from the input item (or `None` to use entire item)
- `set_as`: Which field to store the result in (or `None` to replace entire item with result)
- `multi_emit`: If `True`, `process_value` returns an iterator of results

### The @field_segment Decorator

For function-based segments following the dictionary convention:

```python
@field_segment(field="text", set_as="word_count")
def count_words(text):
    return len(text.split())

# Input:  {"text": "hello world", "id": 1}
# Output: {"text": "hello world", "id": 1, "word_count": 2}
```

Multi-emit field segments:

```python
@field_segment(multi_emit=True)
def split_sentences(text):
    for sentence in text.split(". "):
        yield sentence

# Input:  "First sentence. Second sentence."
# Output: "First sentence", "Second sentence"
```

## Protocol Layers

TalkPipe's protocol operates at multiple layers:

### Layer 1: Core Pipe API (Unrestricted)

- Any Python object can flow through pipelines
- No type enforcement or validation
- Maximum flexibility for custom use cases
- Location: `talkpipe/pipe/core.py`

### Layer 2: Individual Segments and Sources (Mixed)

- Any segment or source can work with arbitrary object types
- Many built-in segments are **convention-aware** and assume dictionary items with specific fields
- Convention-aware segments use `extract_property`/`assign_property` for field access
- Segments document their expected input/output types in docstrings
- Location: `talkpipe/pipe/basic.py`, `talkpipe/operations/`, etc.

```python
# Convention-aware segment: expects dict with 'text' field
@field_segment(field="text", set_as="length")
def text_length(text):
    return len(text)

# Arbitrary object segment: works with any type
@segment()
def double(items):
    for item in items:
        yield item * 2  # Works with numbers, strings, lists...
```

### Layer 3: Pipelines (Dictionary Convention Enforced)

- Pre-built pipelines in `talkpipe/pipelines/` **require** dictionary items
- Field names are documented and consistent
- Segments are composed with known field contracts
- Location: `talkpipe/pipelines/`

```python
# Example: RAG pipeline expects dictionaries with specific fields
# Input: {"query": "What is TalkPipe?", ...}
# Internal fields: "_background", "_ragprompt" (prefixed with _ for internal use)
# Output: {"query": "...", "answer": "TalkPipe is...", ...}
```

## Common Field Names

While field names are flexible, these conventions are used in built-in segments:

| Field | Description | Used By |
|-------|-------------|---------|
| `text` | Primary text content | LLM segments, text processing |
| `content` | Alternative for text content | Document processing |
| `query` | User query or question | RAG pipelines, search |
| `answer` | LLM response | Completion segments |
| `score` | Numeric score or rating | Scoring segments |
| `embedding` | Vector embedding | Embedding segments |
| `source` | Origin of the data | File readers |
| `id` | Unique identifier | Database operations |
| `_*` | Internal/temporary fields | Prefixed with underscore |

## Best Practices

### 1. Document Your Protocol

```python
@segment()
def my_segment(items):
    """Process items in the pipeline.

    Input Protocol:
        Expected: dict with 'text' field (str)
        Optional: 'metadata' field (dict)

    Output Protocol:
        Yields: dict with original fields plus 'processed' (str)
    """
```

### 2. Be Defensive with Field Access

```python
# Good: Handle missing fields gracefully
text = extract_property(item, "text", default="")

# Good: Check before accessing
if "text" in item:
    process(item["text"])
```

### 3. Preserve Unknown Fields

```python
# Good: Keep original fields, add new ones
@segment()
def enrich(items):
    for item in items:
        item["enriched"] = compute_enrichment(item)
        yield item  # Original fields preserved

# Avoid: Replacing the entire item loses fields
@segment()
def bad_enrich(items):
    for item in items:
        yield {"enriched": compute_enrichment(item)}  # Lost original data!
```

### 4. Use Underscore Prefix for Internal Fields

```python
# Internal/temporary fields that shouldn't be exposed
assign_property(item, "_intermediate_result", temp_value)
assign_property(item, "_ragprompt", constructed_prompt)
```

---

Last Reviewed: 20251212
