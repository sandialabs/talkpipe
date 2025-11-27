# Lazy Loading

TalkPipe's lazy loading feature provides significant performance improvements by loading components on-demand rather than importing all sources and segments at startup.

## Overview

The hybrid registry system supports two modes:

- **Eager mode** (default): Components are loaded when first accessed, maintaining backward compatibility
- **Lazy mode**: Entry point discovery is deferred until components are explicitly requested, providing up to **18x faster startup times** (from ~2.9s to ~0.16s)

This is particularly beneficial for command-line tools, documentation generators, and applications that only use a subset of TalkPipe's 72+ built-in components.

## Benefits

- **Faster startup**: Dramatically reduced import time when lazy loading is enabled
- **Reduced memory footprint**: Only load components that are actually used
- **Backward compatible**: Existing code works without changes
- **Flexible configuration**: Enable via environment variable, config file, or programmatically
- **Graceful degradation**: Handles missing components cleanly

## Enabling Lazy Loading

### Method 1: Environment Variable (Recommended)

Set the `TALKPIPE_LAZY_IMPORT` environment variable:

```bash
export TALKPIPE_LAZY_IMPORT=true
python your_script.py
```

Accepted values: `'1'`, `'true'`, `'yes'` (case-insensitive)

### Method 2: Configuration File

Add to `~/.talkpipe.toml`:

```toml
LAZY_IMPORT = true
```

### Method 3: Programmatic Control

Control lazy loading from within your Python code:

```python
from talkpipe.chatterlang.registry import enable_lazy_imports, disable_lazy_imports

# Enable lazy loading
enable_lazy_imports()

# Your TalkPipe code here
from talkpipe import compile
pipeline = compile("range[start=0, stop=100] | print")

# Disable lazy loading if needed
disable_lazy_imports()
```

## How It Works

### Component Registration

TalkPipe uses a hybrid registry that combines decorator-based registration with entry point discovery:

1. **Decorator registration**: Components decorated with `@register_source()` or `@register_segment()` are registered immediately when their module is imported
2. **Entry point discovery**: Components declared in `pyproject.toml` entry points are discovered without importing
3. **On-demand loading**: When a component is requested, its module is imported (triggering all decorators in that module), registering all components from that module at once

### Registry Lookup Process

When you request a component by name:

```python
segment_registry.get("print")
```

The registry follows this process:

1. Check if already registered via decorators (fast path)
2. Check if this component failed to load before (avoid retry loops)
3. Try loading from entry points if available
4. Raise `KeyError` with list of available components if not found

**Important**: When a component's module is imported to load that component, **all components in that module** are registered at once. This is because importing the module executes all decorators in the file. For example, requesting the `print` segment will load and register all segments defined in the `talkpipe/pipe/io.py` module.

### Loading All Components

When you access all components:

```python
all_segments = segment_registry.all
```

In lazy mode, this triggers one-time loading of all entry points. Subsequent accesses use cached results.

## Performance Characteristics

### Lazy Mode (`TALKPIPE_LAZY_IMPORT=true`)

- **Initial import**: ~0.16 seconds
- **First `.all` access**: ~3 seconds (loads all 72 components)
- **Subsequent accesses**: Very fast (cached)
- **Individual component access**: Loads the component's module (registering all components in that module)

### Eager Mode (default)

- **Initial import**: Slightly slower than lazy mode
- **Component access**: Same on-demand loading behavior
- **Backward compatible** with existing code

## Usage Examples

### Basic Usage with ChatterLang

Lazy loading works automatically with ChatterLang scripts:

```python
from talkpipe import compile

# With lazy loading enabled, this starts fast
pipeline = compile("""
    range[start=0, stop=100]
    | scale[factor=2]
    | print
""")

# Only the modules containing 'range', 'scale', and 'print' are loaded
# All components in those modules are registered when their module is imported
```

### Direct Registry Access

```python
from talkpipe.chatterlang.registry import segment_registry, input_registry

# Get a specific segment (loads that component's module in lazy mode)
# Note: All components in the same module are registered when the module is imported
PrintSegment = segment_registry.get("print")

# List available components without loading them
entry_points = segment_registry.list_entry_points()
print(f"Available segments: {', '.join(entry_points)}")

# Get all segments (triggers loading of all modules in lazy mode)
all_segments = segment_registry.all
```

### Checking Registry Statistics

Monitor what's loaded in the registry:

```python
from talkpipe.chatterlang.registry import segment_registry

stats = segment_registry.stats()
print(stats)
# Output: {'registered': 10, 'entry_points': 71, 'loaded_modules': 5, 'failed_loads': 0}
```

### Get Statistics for All Registries

```python
from talkpipe.chatterlang.registry import get_registry_stats

stats = get_registry_stats()
print(stats)
# Output: {
#   'sources': {'registered': 5, 'entry_points': 8, ...},
#   'segments': {'registered': 35, 'entry_points': 71, ...},
#   'lazy_mode': True
# }
```

## API Reference

### Functions

#### `enable_lazy_imports()`
Enable lazy loading mode for all registries.

```python
from talkpipe.chatterlang.registry import enable_lazy_imports
enable_lazy_imports()
```

#### `disable_lazy_imports()`
Disable lazy loading mode, returning to eager loading.

```python
from talkpipe.chatterlang.registry import disable_lazy_imports
disable_lazy_imports()
```

#### `get_registry_stats()`
Get statistics for all registries including lazy mode status.

**Returns:** Dictionary with keys `'sources'`, `'segments'`, and `'lazy_mode'`

```python
from talkpipe.chatterlang.registry import get_registry_stats
stats = get_registry_stats()
```

### Registry Methods

#### `registry.get(name: str) -> Type`
Get a component by name, loading from entry points if needed.

**Raises:** `KeyError` if component is not found

```python
from talkpipe.chatterlang.registry import segment_registry
component = segment_registry.get("print")
```

#### `registry.all -> Dict[str, Type]`
Get all registered components. In lazy mode, this triggers loading of all entry points.

```python
from talkpipe.chatterlang.registry import segment_registry
all_components = segment_registry.all
```

#### `registry.list_entry_points() -> List[str]`
List names of all components available via entry points without loading them.

```python
from talkpipe.chatterlang.registry import segment_registry
names = segment_registry.list_entry_points()
```

#### `registry.stats() -> Dict`
Get statistics about the registry state.

**Returns:** Dictionary with keys:
- `'registered'`: Number of currently loaded components
- `'entry_points'`: Total number of available entry points
- `'loaded_modules'`: Number of modules that have been imported
- `'failed_loads'`: Number of components that failed to load

```python
from talkpipe.chatterlang.registry import segment_registry
stats = segment_registry.stats()
```

### Module Constants

#### `LAZY_IMPORT_MODE`
Global boolean flag indicating whether lazy loading is enabled.

```python
from talkpipe.chatterlang.registry import LAZY_IMPORT_MODE
print(f"Lazy loading enabled: {LAZY_IMPORT_MODE}")
```

## Supported Components

Lazy loading is fully supported for all TalkPipe components:

- **8 built-in sources**: `chatterlangServer`, `echo`, `exec`, `prompt`, `randomInts`, `range`, `readEmail`, `rss`
- **71 built-in segments**: Including data I/O, transformations, filtering, LLM operations, search, web processing, and more

All components are declared as entry points in `pyproject.toml` and use decorator-based registration for seamless lazy loading.


### Taking Advantage of Lazy Loading

As a developer building TalkPipe applications or creating custom sources and segments, you can structure your code to maximize the benefits of lazy loading.

### Module Organization Best Practices

Since lazy loading works at the **module level** (importing one component loads all components in that module), organize your code strategically:

#### 1. Group Related Components Together

Place components that are often used together in the same module:

```python
# Good: data_io.py - components commonly used together
from talkpipe.chatterlang.registry import register_segment

@register_segment("readJson")
class ReadJson(AbstractSegment):
    """Read JSON files"""
    pass

@register_segment("writeJson")
class WriteJson(AbstractSegment):
    """Write JSON files"""
    pass
```

#### 2. Isolate Heavy Dependencies

Place components with heavy or optional dependencies in separate modules:

```python
# ml_segments.py - isolated because it requires tensorflow
import tensorflow as tf  # Heavy import

@register_segment("tensorflowPredict")
class TensorFlowPredict(AbstractSegment):
    pass

# basic_segments.py - no heavy dependencies
@register_segment("filter")
class Filter(AbstractSegment):
    pass
```

This way, users who don't need TensorFlow won't pay the cost of importing it.

#### 3. Organize by Domain

Structure components by domain or functionality:

```python
# Project structure
src/myproject/
    sources/
        database.py      # All database sources
        web.py          # All web-related sources
    segments/
        transform.py    # Data transformation
        llm.py          # LLM-related (may have heavy deps)
```

#### 4. Use Entry Points for Discoverability

Declare your components as entry points in `pyproject.toml`:

```toml
[project.entry-points."talkpipe.sources"]
myDatabaseSource = "myproject.sources.database"

[project.entry-points."talkpipe.segments"]
myTransform = "myproject.segments.transform"
```

This allows TalkPipe to discover and load components on-demand without importing them.

**Important**: Component names must be unique across all installed packages. TalkPipe detects name collisions and raises detailed errors. Use unique prefixes for plugin components (e.g., `myplugin_transform`) to avoid conflicts. See the [Extending TalkPipe](../architecture/extending-talkpipe.md) documentation for details on plugin architecture and collision handling.

### When to Enable Lazy Loading

### When to Enable Lazy Loading

Enable lazy loading in these scenarios:

#### Best Use Cases

1. **Command-line tools**: Fast startup is critical for good UX
   ```bash
   export TALKPIPE_LAZY_IMPORT=true
   python my_cli_tool.py
   ```

2. **Documentation generators**: Need to discover all components but may not use them all
   ```python
   enable_lazy_imports()
   all_segments = segment_registry.list_entry_points()  # Fast discovery
   ```

3. **Development and testing**: Faster feedback loops
   ```bash
   export TALKPIPE_LAZY_IMPORT=true
   pytest tests/
   ```

4. **Large libraries**: Projects with many components where users typically use a small subset
   ```python
   # In your library's __init__.py
   from talkpipe.chatterlang.registry import enable_lazy_imports
   enable_lazy_imports()
   ```

#### When Eager Loading May Be Better

1. **Production services**: Where startup time happens once but runtime performance matters
2. **Small applications**: With few components where lazy loading overhead isn't worth it
3. **Using most components**: If your pipeline uses most available components anyway

### Creating Lazy-Loading-Friendly Plugins

When developing TalkPipe plugins, follow these guidelines:

#### 1. Use Lazy Imports Within Your Code

Avoid importing heavy dependencies at module level:

```python
# Bad: Heavy import at module level
from talkpipe.chatterlang.registry import register_segment
import tensorflow as tf  # Loaded even if segment never used

@register_segment("tfPredict")
class TensorFlowPredict(AbstractSegment):
    def transform(self, input_iter):
        # Use tf here
        pass

# Good: Import only when needed
from talkpipe.chatterlang.registry import register_segment

@register_segment("tfPredict")
class TensorFlowPredict(AbstractSegment):
    def transform(self, input_iter):
        import tensorflow as tf  # Loaded only when segment actually runs
        # Use tf here
        pass
```

#### 2. Provide Multiple Granularity Levels

Offer both bundled and granular entry points:

```toml
# In your plugin's pyproject.toml

[project.entry-points."talkpipe.segments"]
# All-in-one for convenience
all_ml_segments = "myplugin.ml"

# Individual components for lazy loading
mlPredict = "myplugin.ml.predict"
mlTrain = "myplugin.ml.train"
mlEvaluate = "myplugin.ml.evaluate"
```

#### 3. Document Dependency Requirements

Make it clear which components have special requirements:

```python
@register_segment("tfPredict")
class TensorFlowPredict(AbstractSegment):
    """
    Run TensorFlow predictions on input data.

    Requires: tensorflow>=2.0

    This segment will only be loaded if TensorFlow is installed.
    Install with: pip install tensorflow
    """
    pass
```

### Measuring the Impact

Monitor the effectiveness of lazy loading:

```python
import time
from talkpipe.chatterlang.registry import segment_registry, enable_lazy_imports

# Measure startup time
start = time.time()
enable_lazy_imports()
from talkpipe import compile
startup_time = time.time() - start
print(f"Startup time: {startup_time:.3f}s")

# Check what's actually loaded
stats = segment_registry.stats()
print(f"Registered: {stats['registered']}/{stats['entry_points']} segments")
print(f"Modules loaded: {stats['loaded_modules']}")

# Run your pipeline
pipeline = compile("range[start=0, stop=10] | print")

# Check what got loaded
stats_after = segment_registry.stats()
print(f"After pipeline: {stats_after['registered']}/{stats_after['entry_points']} segments")
print(f"Modules loaded: {stats_after['loaded_modules']}")
```

### Example: Optimizing a Large Project

Here's a real-world example of restructuring for lazy loading:

**Before: All components in one file**
```python
# components.py (slow to load)
from talkpipe.chatterlang.registry import register_segment
import pandas as pd
import numpy as np
import tensorflow as tf
import torch
from sklearn import *

# 50+ segments all in one file
@register_segment("pandasFilter")
class PandasFilter(AbstractSegment): pass

@register_segment("tfPredict")
class TFPredict(AbstractSegment): pass

# ... 48 more segments
```

**After: Organized by functionality and dependencies**
```python
# segments/basic.py (fast to load, no heavy deps)
from talkpipe.chatterlang.registry import register_segment

@register_segment("filter")
class Filter(AbstractSegment): pass

@register_segment("map")
class Map(AbstractSegment): pass

# segments/dataframe.py (moderate deps)
from talkpipe.chatterlang.registry import register_segment

@register_segment("pandasFilter")
class PandasFilter(AbstractSegment):
    def transform(self, input_iter):
        import pandas as pd  # Lazy import
        # Use pandas here

# segments/ml_tensorflow.py (heavy deps)
from talkpipe.chatterlang.registry import register_segment

@register_segment("tfPredict")
class TFPredict(AbstractSegment):
    def transform(self, input_iter):
        import tensorflow as tf  # Lazy import
        # Use tensorflow here
```

**Result**: Users who only need basic filtering get **10x faster startup** because TensorFlow and PyTorch are never imported.

## Troubleshooting

### Component Not Found

If a component fails to load, check:

1. Is the component name correct? Use `registry.list_entry_points()` to see available names
2. Are dependencies installed? Some components require optional dependencies
3. Check `registry.stats()` for `'failed_loads'` count

### Performance Not Improved

If you don't see performance improvements:

1. Verify lazy loading is enabled: check `LAZY_IMPORT_MODE` value
2. Ensure environment variable is set before importing TalkPipe
3. Consider if your use case actually benefits (e.g., loading all components negates the benefit)

### Circular Import Issues

The hybrid registry is designed to avoid circular imports by:

- Not loading entry points at `__init__` time
- Loading decorators only when components are requested
- Providing fallback to entry point discovery

If you encounter circular import issues, they're likely from other parts of your code.

### Component Name Conflicts

**Automatic Detection**: As of the current version, TalkPipe automatically detects and reports entry point name collisions when packages are loaded. If you see a `ValueError` about name collisions, it means multiple installed packages are trying to use the same component name.

**What to do when you see a collision error:**

1. **Read the error message carefully** - it lists all conflicting packages and component names:
   ```
   ValueError: Entry point name collision detected in group 'talkpipe.segments'.
   Multiple packages are trying to register components with the same name:
     - Component 'transform' defined by:
         • package1.segments:Transform (from package 'myplugin1')
         • package2.segments:Transform (from package 'myplugin2')
   ```

2. **Choose your resolution strategy:**
   - **Uninstall one of the conflicting packages** if you don't need both
   - **Contact plugin authors** to request they use unique prefixes
   - **Temporarily use a workaround** by forking one plugin and renaming its components

3. **For plugin developers** - prevent conflicts by using unique prefixes:
   ```toml
   [project.entry-points."talkpipe.segments"]
   # Good: unique prefix
   myplugin_transform = "myplugin.segments.transform"

   # Risky: generic name
   transform = "myplugin.segments.transform"
   ```

**Manual collision checking** (if you want to check before installing a package):
```bash
# Show all packages defining talkpipe.segments
python -c "
from importlib.metadata import entry_points
eps = entry_points().select(group='talkpipe.segments')
seen = {}
for ep in eps:
    if ep.name in seen:
        print(f'CONFLICT: {ep.name} defined by both {seen[ep.name]} and {ep.value}')
    else:
        seen[ep.name] = ep.value
print(f'Total: {len(seen)} unique names')
"
```

---

**See Also:**
- [Plugin Manager](talkpipe-plugin-manager.md) for managing external plugins
- [ChatterLang Compiler](../architecture/compiler.md) for how components are resolved during compilation

Last Reviewed: 20251025
