# Extending TalkPipe

This guide explains how to add custom **sources** (pipeline starters) and **segments** (stream processors), register them for the ChatterLang DSL, and ship them in packages. Read the [Data Protocol](protocol.md) first so stream conventions (especially dictionary-shaped data in higher-level pipelines) stay consistent.

## A minimal registered segment

You usually implement a segment as a small function and attach two decorators: `@segment()` turns the function into a segment class factory, and `@register_segment("nameInChatterLang")` adds that class to the global registry under one or more ChatterLang names.

> **Import note:** `talkpipe` re-exports `segment`, `register_segment`, `compile`, and friends at the top level as convenience shortcuts. `from talkpipe import segment, register_segment` and `from talkpipe.chatterlang import registry, compiler` (used in the README) are equivalent — pick one style and use it consistently. This guide uses the top-level shortcuts.

```python
from typing import Iterator, Any

from talkpipe import segment, register_segment
from talkpipe.chatterlang import compile
from talkpipe.pipe import io


@register_segment("doubleEach")
@segment()
def double_each(items: Iterator[Any], factor: int = 2) -> Iterator[Any]:
    """Multiply each numeric item by factor (strings are parsed as integers)."""
    for item in items:
        yield int(item) * factor


# Pipe API: build and run in the same Python process where the decorators ran.
pipeline = io.echo(data="1,2,3") | double_each(factor=10)
print(list(pipeline()))

# ChatterLang: the name matches @register_segment; parameters map to the segment.
# Add "| print" when you want each item on stdout while developing.
fn = compile('INPUT FROM echo[data="1,2,3"] | doubleEach[factor=10]')
print(list(fn()))
```

**Why this pattern fits many workflows**

- **Notebooks and ad hoc scripts**: Define the function in a cell or file and run it. Decorators run at import time, so the segment is registered in that interpreter session. Use the pipe API (`source | segment() | …`) immediately, or call `compile(...)` on ChatterLang text in the same process.
- **Application code**: Keep segments in a project module and import that module early (for example from your `main`). Registration is a side effect of import, so ChatterLang and any tooling that resolves names through the registry see your segment without extra wiring.
- **Installable libraries**: Publish a package whose modules use `@register_segment` / `@register_source`, and declare **`talkpipe.segments`** / **`talkpipe.sources`** entry points in `pyproject.toml` so the hybrid registry can import the defining module on demand (see [Registry, ChatterLang names, and entry points](#registry-chatterlang-names-and-entry-points)). Optional **`talkpipe.plugins`** entry points load whole plugin modules when `talkpipe` is imported—useful for one-time setup or side-effect imports across many components.

The same streaming model applies everywhere: sources `yield` items, segments consume an iterable and `yield` outputs, so pipelines stay lazy and memory-friendly from a notebook through to production services.

---

## Core building blocks

TalkPipe pipelines are built from:

- **`AbstractSource`** — starts a pipeline; implements `generate()` and yields items.
- **`AbstractSegment`** — transforms a stream; implements `transform(input_iter)` and yields items.

Both are iterator-based so work is done on demand, which matters for large data or slow IO.

### Custom sources

**Class-based** sources subclass `AbstractSource` and implement `generate()`. Use this when you hold connection state, configuration, or other resources tied to the source instance.

**Function-based** sources use `@source` or `@source(...)`. The decorator wraps a generator function in a small `AbstractSource` subclass, which keeps simple cases short and readable.

The examples below use stubs where a real integration would open databases or files.

#### Class-based source (sketch)

```python
from contextlib import contextmanager
from typing import Iterator

from talkpipe.pipe import io
from talkpipe.pipe.core import AbstractSource


@contextmanager
def get_connection(connection_string: str):
    """Replace with a real connection (e.g. DB driver)."""
    class Conn:
        def execute(self, query):
            return []  # Stub: yield no rows

    yield Conn()


class DatabaseSource(AbstractSource[dict]):
    """Example source that reads rows from a database."""

    def __init__(self, connection_string: str, query: str):
        super().__init__()
        self.connection_string = connection_string
        self.query = query

    def generate(self) -> Iterator[dict]:
        with get_connection(self.connection_string) as conn:
            for row in conn.execute(self.query):
                yield dict(row)


db_source = DatabaseSource("sqlite:///data.db", "SELECT * FROM users")
pipeline = db_source | io.Print()
list(pipeline())
```

#### Function-based source with `@source`

```python
from talkpipe.pipe.core import source


@source
def count_source():
    """Emit counting numbers."""
    for i in range(100):
        yield i


@source()
def file_lines_source(filename: str):
    """Emit one dict per line from a file."""
    with open(filename, encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            yield {"line_number": line_num, "content": line.strip()}


numbers = count_source()
file_data = file_lines_source(filename="data.txt")
```

### Custom segments

**Class-based** segments subclass `AbstractSegment` and implement `transform(self, input_iter)`.

**Function-based** segments use `@segment` or `@segment(...)`. The function receives the upstream iterable as the first argument; additional arguments become constructor parameters on the generated class (for example `filter_by_field(field="status", value="active")`).

**Field helpers**: `@field_segment()` builds a segment that reads one field per item, applies your function, and can write results to another field—useful for record-shaped dicts (see the protocol doc for metadata and field conventions).

#### Class-based segment

```python
from typing import Iterable, Iterator

from talkpipe.pipe import io
from talkpipe.pipe.core import AbstractSegment


class JsonParseSegment(AbstractSegment[str, dict]):
    """Parse JSON strings into dicts."""

    def __init__(self, fail_on_invalid: bool = True):
        super().__init__()
        self.fail_on_invalid = fail_on_invalid

    def transform(self, input_iter: Iterable[str]) -> Iterator[dict]:
        import json

        for json_str in input_iter:
            try:
                yield json.loads(json_str)
            except json.JSONDecodeError as e:
                if self.fail_on_invalid:
                    raise ValueError(f"Invalid JSON: {json_str}") from e


json_parser = JsonParseSegment(fail_on_invalid=False)
json_source = io.echo(data='{"a":1}|{"b":2}', delimiter="|")
pipeline = json_source | json_parser | io.Print()
list(pipeline())
```

#### Function-based segments

```python
from talkpipe.pipe.core import segment, field_segment


@segment
def uppercase_segment(items):
    for item in items:
        yield str(item).upper()


@segment()
def filter_by_field(items, field: str, value: str):
    for item in items:
        if isinstance(item, dict) and item.get(field) == value:
            yield item


@field_segment()
def extract_domain(email: str):
    return email.split("@", 1)[1] if "@" in email else None


uppercase = uppercase_segment()
active_users = filter_by_field(field="status", value="active")
get_domain = extract_domain(field="email", set_as="domain")
```

#### Patterns: errors and state

**Resilient per-item processing** — catch only what you intend to handle; either yield a fallback or skip and log.

```python
from logging import getLogger

from talkpipe.pipe.core import segment

logger = getLogger(__name__)


@segment()
def safe_process(items, default=None):
    for item in items:
        try:
            yield expensive_step(item)
        except Exception as e:
            if default is not None:
                yield default
            else:
                logger.warning("skip item after error: %s", e)
```

**Stateful logic** — when you need instance state across items (windows, running totals), a small `AbstractSegment` subclass is often clearer than closing over mutable globals.

```python
from typing import Any, Iterable, Iterator, List

from talkpipe.pipe.core import AbstractSegment


class WindowSegment(AbstractSegment[Any, List[Any]]):
    """Emit sliding windows of `window_size` items."""

    def __init__(self, window_size: int, step_size: int = 1):
        super().__init__()
        self.window_size = window_size
        self.step_size = step_size

    def transform(self, input_iter: Iterable[Any]) -> Iterator[List[Any]]:
        window: list[Any] = []
        for item in input_iter:
            window.append(item)
            if len(window) == self.window_size:
                yield list(window)
                window = window[self.step_size :]
        if window:
            yield list(window)
```

---

## Registry, ChatterLang names, and entry points

### Why a registry exists

ChatterLang resolves segment and source names at compile time. The **hybrid registry** (`talkpipe.chatterlang.registry`) stores classes registered by decorators and, if a name is missing, loads **`talkpipe.segments`** / **`talkpipe.sources`** entry points so the defining module is imported (which runs the decorators). That gives you:

- **Fast startup** when you only use the pipe API and never touch unknown ChatterLang names.
- **Discoverability** for tools and IDEs that list `segment_registry.all` / `input_registry.all`.
- **Packaging** — third-party packages can expose components without forking TalkPipe.

### Registering with decorators

```python
import talkpipe.chatterlang.registry as registry
from talkpipe.pipe.core import AbstractSegment, AbstractSource


@registry.register_segment("customParser")
class CustomParserSegment(AbstractSegment):
    ...


@registry.register_source("apiData")
class APIDataSource(AbstractSource):
    ...
```

`register_segment` and `register_source` are also re-exported from the top-level `talkpipe` package; use whichever import style matches your project.

ChatterLang uses the names you pass to the decorators (multiple names are allowed in one decorator). Example script shape:

```chatterlang
INPUT FROM apiData(url="https://api.example.com/data")
| customParser(format="json")
| print
```

### Entry points for distributable components

Segments and sources are discovered through the **`talkpipe.segments`** and **`talkpipe.sources`** entry point groups. How you keep those aligned with your decorators depends on whether you are writing a third-party package or contributing to the TalkPipe repository itself.

#### For third-party plugin authors

In your **own** package, declare the same groups in your `pyproject.toml`, pointing each name at `module:ClassName` (the class your decorators attach to). This is all a distributable plugin needs — you do **not** need any TalkPipe repo tooling.

#### For TalkPipe repo contributors (this repository only)

When working inside the TalkPipe source checkout, after adding or renaming `@register_segment` / `@register_source` classes, regenerate `pyproject.toml` entry points with the repo-internal script (not shipped with the installed package):

`python .cursor/skills/update-entry-points/scripts/update_entry_points.py`

(from the project root; see [protocol.md](protocol.md)). That keeps **`talkpipe.segments`** and **`talkpipe.sources`** aligned with decorators so installs and lazy loading resolve the right modules.

### `talkpipe.plugins` (optional)

The `talkpipe.plugins` entry point group is separate from per-segment registration. Importing `talkpipe` runs `load_plugins()`, which loads each plugin entry point. Prefer pointing the entry point at a **module** so importing it runs your `@register_*` decorators; optionally define a module-level `initialize_plugin()` for extra setup. See [TalkPipe Plugin Manager](../api-reference/talkpipe-plugin-manager.md) for CLI (`talkpipe_plugins`) and configuration details.

**Example `pyproject.toml` snippet:**

```toml
[project.entry-points."talkpipe.plugins"]
network_plugin = "my_plugin.plugin"
```

**Example plugin module** (`my_plugin/plugin.py`):

```python
# plugin.py (module referenced by the `talkpipe.plugins` entry point)
try:
    # Normal plugin behavior: importing this module triggers decorator side effects
    # in sibling modules that register segments/sources.
    from my_plugin import components as _components  # noqa: F401
except ImportError:
    # Allows this file to run standalone (for docs/tests) without package layout.
    _components = None


def initialize_plugin() -> None:
    """Optional setup hook called by the plugin loader."""
    print("my_plugin initialized")


if __name__ == "__main__":
    initialize_plugin()
```

```python
# skip-extract
# setup.py alternative (legacy packaging)
from setuptools import setup

setup(
    name="my-talkpipe-plugin",
    entry_points={
        "talkpipe.plugins": [
            "network_plugin = my_plugin.plugin",
        ],
    },
)
```

### Manual registration

Rarely, you may register a class without decorators:

```python
from talkpipe.chatterlang import registry
from talkpipe.pipe.core import AbstractSegment, AbstractSource


class MySegment(AbstractSegment):
    def transform(self, input_iter):
        yield from input_iter


class MySource(AbstractSource):
    def generate(self):
        yield "example"


registry.segment_registry.register(MySegment, name="mySegment")
registry.input_registry.register(MySource, name="mySource")

names = sorted(registry.segment_registry.all.keys())
```

`HybridRegistry.all` returns a mapping of registered names to classes and may trigger loading of entry-point modules the first time you access it.

---

## What runs on import

`talkpipe/__init__.py` loads optional **`talkpipe.plugins`** entry points and re-exports `segment`, `source`, `register_segment`, and `register_source`. It does **not** import every built-in segment module up front.

Many built-in components live in subpackages (`talkpipe.pipe.basic`, `talkpipe.llm.chat`, …). Those modules register names when imported. ChatterLang compilation uses `HybridRegistry.get(name)`, which imports the module listed in **`talkpipe.segments`** / **`talkpipe.sources`** if the name is not yet registered. So a “minimal” `import talkpipe` stays light; pulling in a specific name pulls in its module.

---

## Implementation guidelines

### `AbstractSource`

- Implement `generate(self) -> Iterator[OutputType]` and **yield** items (do not return a big list unless you truly need batching).
- Manage resources with context managers or careful cleanup in `generate`.

### `AbstractSegment`

- Implement `transform(self, input_iter: Iterable[T]) -> Iterator[U]` and **yield** results.
- You may filter (fewer outputs), expand (more outputs), or change types between segments.

### Streaming and memory

Prefer streaming one item at a time:

```python
def transform(self, input_iter):
    for item in input_iter:
        yield self.process(item)
```

Avoid `all_items = list(input_iter)` unless the algorithm genuinely needs the full sequence.

### Errors

Let exceptions propagate when they represent programmer or data errors; catch and log only when you have a defined recovery path (skip item, substitute value, etc.).

### Types and compatibility

Use generics (`AbstractSegment[Input, Output]`) when it helps readers and type checkers. Preserve backwards compatibility for public call signatures when possible; use `warnings.warn` for deprecations.

### Testing

Unit-test `transform`/`generate` with small iterables. For integration tests, build a short pipeline with `compile(...)` or the pipe API and assert on `list(pipeline())`.

```python
import unittest

from talkpipe.pipe.core import AbstractSegment


class DoubleSegment(AbstractSegment):
    def __init__(self, fail_on_error=False):
        super().__init__()
        self.fail_on_error = fail_on_error

    def transform(self, input_iter):
        for item in input_iter:
            if self.fail_on_error and item == "invalid_input":
                raise ValueError("invalid")
            yield item * 2


class TestDoubleSegment(unittest.TestCase):
    def test_basic(self):
        seg = DoubleSegment()
        self.assertEqual(list(seg.transform([1, 2, 3])), [2, 4, 6])

    def test_empty(self):
        seg = DoubleSegment()
        self.assertEqual(list(seg.transform([])), [])

    def test_error(self):
        seg = DoubleSegment(fail_on_error=True)
        with self.assertRaises(ValueError):
            list(seg.transform(["invalid_input"]))
```

---

Last reviewed: 2026-04-15
