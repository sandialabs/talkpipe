# TalkPipe AI Coding Instructions

## Project Overview

TalkPipe is a Python toolkit for building AI workflows that combine LLMs, data processing, and search. It provides two complementary ways to build pipelines:

1. **Pipe API** (internal DSL) - Python classes chained with `|` operator for programmatic control
2. **ChatterLang** (external DSL) - Human-readable text scripts compiled to callable functions

## Architecture & Key Components

### Three-Layer Architecture

```
Layer 3: Application Components (app/) - CLI/web interfaces, plugins
Layer 2: AI & Data Primitives (llm/, search/, data/) - LLM wrappers, vector DB, full-text search
Layer 1: Pipe Foundation (pipe/) + ChatterLang (chatterlang/) - DSL and core abstractions
```

### Core Modules

- **`pipe/core.py`** - Base classes: `AbstractSource`, `AbstractSegment`, `AbstractFieldSegment`, `Pipeline`, `Script`
- **`pipe/basic.py`** - 70+ standard segments (DiagPrint, Filter, Cast, etc.) using decorators
- **`chatterlang/compiler.py`** - Compiles ChatterLang text scripts to callable `Pipeline`/`Script` objects
- **`chatterlang/registry.py`** - `HybridRegistry` for decorator + entry-point discovery of segments/sources
- **`pipe/io.py`** - I/O sources (Prompt, ReadCSV) and segments (Print, Log)
- **`search/`** - Vector DB (lancedb) and full-text search (whoosh) wrappers

## Critical Workflows

**Prerequisite**: Use `.venv` virtual environment (described below in Environment Setup). Alert user if `.venv` doesn't exist and offer to create it.

### Run Tests
```bash
pytest                                    # All tests
pytest tests/talkpipe/pipe/test_basic.py # Specific file
pytest --cov=talkpipe --cov-report=html  # With coverage (configured in tasks.json)
```

### Build & Package
```bash
python -m build  # Creates wheel and sdist
```

### Component Registration
New segments/sources must be:
1. Decorated with `@segment()` or `@source()`
2. Added to `pyproject.toml` entry-points (under `[project.entry-points."talkpipe.segments"]` or `"talkpipe.sources"`)
3. Registered in registry via decorator: `@registry.register_segment("name")`

## Design Patterns

### Segment/Source Decorators

All `pipe/` modules use decorators to define segments and sources. Understand the difference:

```python
# Simple segment - operates on iterables
@segment()
def mySegment(items: Iterator[T]) -> Iterator[U]:
    for item in items:
        yield process(item)

# Field segment - extracts field, applies function, reassigns result
@field_segment()
def myFieldSegment(value, field: str = "text"):
    return value.upper()  # Operates on single field value

# Multi-emit field segment - produces multiple outputs per input
@field_segment(multi_emit=True)
def myMultiSegment(items_list):
    for item in items_list:
        yield item
```

**Key insight**: `@field_segment` is convenience for extracting item[field], calling function, assigning back to item[new_field].

### Data Protocol

Arbitrary Python objects flow through pipes, but `talkpipe/pipelines` layer enforces a convention:

**Items are dictionaries or Pydantic models with `extra="allow"`**

```python
# Preferred - Pydantic for type safety
from pydantic import BaseModel, ConfigDict

class DocumentItem(BaseModel):
    model_config = ConfigDict(extra="allow")
    text: str
    source: str
    
# Segments add fields dynamically
item.word_count = 10  # Works because extra="allow"
```

Utilities for safe field access:
```python
from talkpipe.util.data_manipulation import extract_property, assign_property
text = extract_property(item, "nested.field.path")  # Supports dot notation
assign_property(item, "nested.field", value)
```

### ChatterLang Script Compilation

Understanding the compile pipeline is essential:

1. **Text script** → `parsers.script_parser()` → ParsedScript (AST)
2. **ParsedScript** → `compile()` dispatches on type (singledispatch)
3. **Each ParsedPipeline** gets recursively compiled to `Pipeline` object
4. **Segments/sources** resolved from registry with parameters substituted
5. **Runtime constants** passed through `RuntimeComponent` to enable variable access

```python
from talkpipe.chatterlang import compiler
script = '| echo["hello"] | print'
pipeline = compiler.compile(script)  # Returns Script with callable(input) interface
result = list(pipeline.generate())
```

**Critical flow**: `compiler.py` lines 45-100 show parameter resolution with `_resolve_params()` - this handles constants and arrays from the script.

### Registry & Entry Points

The `HybridRegistry` supports discovery via:
- Decorator registration (happens at import time)
- Entry-point discovery (fallback for lazy loading)

**Development workflow**: When adding new segment:
1. Add `@registry.register_segment("mySegment")` decorator
2. Add entry-point in `pyproject.toml`
3. Entry-point = "segment_name" → "module:function_or_class"

See `pyproject.toml` lines 130-200 for all registered segments/sources.

## Environment Setup

**Always use the `.venv` virtual environment in the repository root when running Python code or pytest.**

### Checking & Creating the Environment

Before running any Python commands:
1. **Check if `.venv` exists** - Look for `.venv/bin/activate` at the repo root
2. **If `.venv` doesn't exist**, alert the user and offer to create it:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   pip install -e ".[dev,all]"
   ```
3. **If creating the environment**, use the command above (`pip install -e ".[dev,all]"`) to install dev dependencies + all LLM providers

### Running Commands with .venv

All Python/pytest commands should use the virtual environment:
```bash
source .venv/bin/activate        # Activate the environment
pytest                           # Run tests
python -c "import talkpipe"      # Verify imports
```

This ensures:
- Correct package versions from `pyproject.toml`
- Optional dependencies (openai, ollama, anthropic) are available if installed
- Development tools (pytest, pytest-cov, pytest-mock) are present

## Development Conventions

### Testing Strategy

From CLAUDE.md: "Write unit test that fails without change, verify it fails, implement, verify it passes."

- Tests in `tests/talkpipe/` mirror src structure
- Keep tests concise while covering functionality completely
- Use `pytest.fixture` and `pytest-mock` for dependencies
- Example: tests for DiagPrint patterns in `tests/talkpipe/pipe/test_basic.py`

### CHANGELOG Management

- Update `CHANGELOG.md` after implementing features
- For minor changes to existing features, update existing entry if present
- Use semantic versioning

### Documentation Examples

- Document examples must be runnable standalone code
- Test examples by executing them before committing
- See `docs/architecture/protocol.md` for data convention examples

### Code Quality

- Use type hints (especially in segment/source functions)
- Leverage Pydantic for data validation at boundaries
- Use `talkpipe.util.data_manipulation` for field access (supports dicts and Pydantic models)
- Configure logging: `from talkpipe.util.config import configure_logger`

## Common Editing Patterns

### Adding a New Segment

```python
# In pipe/basic.py or domain-specific module
from talkpipe.pipe.core import segment, field_segment
import talkpipe.chatterlang.registry as registry

@registry.register_segment("myNewSegment")
@segment()
def my_new_segment(items: Iterator[Any], param1: str = "default") -> Iterator[Any]:
    """Docstring with Annotated types for IDE help."""
    for item in items:
        # Process and yield
        yield result

# Add to pyproject.toml:
# myNewSegment = "talkpipe.pipe.basic:my_new_segment"
```

### Modifying Segment Parameters

Segment function parameters are exposed via `@segment()` decorator. Use `Annotated` for descriptions shown in ChatterLang reference:

```python
@segment()
def foo(
    items,
    threshold: Annotated[float, "Cutoff value for filtering (0-1)"] = 0.5
):
    ...
```

### Adding LLM Provider Integration

See `src/talkpipe/llm/chat.py` for pattern:
- Lazy import optional providers (openai, ollama, anthropic)
- Use `CompletionConfig` for unified interface
- Support `multi_turn=True` for conversation state

## Entry Points for Navigation

- **Segment/source definitions** - grep for `@segment()` or `@source()` in `src/talkpipe/*/`
- **Registry resolution** - `chatterlang/registry.py` `.get()` method for loading from decorators or entry-points
- **Compilation logic** - `chatterlang/compiler.py` `compile(ParsedPipeline, ...)` function with singledispatch pattern
- **Data protocol utilities** - `util/data_manipulation.py` for field access and Pydantic integration
- **Field-based operations** - `pipe/basic.py` has numerous `@field_segment` examples
