# TalkPipe Plugin Manager

Command-line tool for managing and inspecting TalkPipe plugins.

## Overview

The `talkpipe_plugins` command provides utilities to list, reload, and debug TalkPipe plugins that are installed via Python entry points.

## Installation

The plugin manager is included with TalkPipe:

```bash
pip install talkpipe
```

## Usage

### List All Plugins

Display all discovered plugins and their status:

```bash
talkpipe_plugins --list
```

**Example output:**
```
=== TalkPipe Plugins ===
Loaded plugins (2):
  ✓ my-data-plugin
  ✓ custom-llm-plugin

Failed plugins (1):
  ✗ broken-plugin
```

### Reload a Plugin

Reload a specific plugin by name (useful during development):

```bash
talkpipe_plugins --reload my-data-plugin
```

### Verbose Output

Show detailed information:

```bash
talkpipe_plugins --list --verbose
```

## Plugin Discovery

The plugin manager discovers plugins through Python entry points in the `talkpipe.plugins` group. Plugins are automatically loaded when TalkPipe is imported.

### Entry Point Configuration

Plugins should define entry points in their `setup.py` or `pyproject.toml`:

**setup.py:**
```python
setup(
    name="my-talkpipe-plugin",
    entry_points={
        "talkpipe.plugins": [
            "my_plugin = my_plugin.plugin",
        ]
    }
)
```

**pyproject.toml:**
```toml
[project.entry-points."talkpipe.plugins"]
my_plugin = "my_plugin.plugin"
```

The entry point should reference the **module** that contains your plugin code. Component registration happens automatically through decorators when the module is imported.

## How Plugin Loading Works

When TalkPipe discovers a plugin, it performs the following steps:

1. **Load the entry point**: The plugin loader loads whatever the entry point references (typically a module or function)
2. **Automatic registration**: During import, any sources and segments defined or imported by the module are automatically registered with TalkPipe's registry system through decorators like `@registry.register_segment()`
3. **Optional initialization**: If the loaded object has an `initialize_plugin` function attribute, it will be called for additional setup

The key insight is that **simply importing the plugin module triggers component registration**. This happens through TalkPipe's decorator-based registry system.

**Important**: The entry point should reference either:
- A **module** (e.g., `my_plugin.plugin`) that can have a module-level `initialize_plugin()` function
- A **function** directly (e.g., `my_plugin.plugin:setup_plugin`)

Entry points pointing to classes will have the `initialize_plugin` called on the **class itself** (not an instance), so it would need to be a static method or classmethod if using a class.

### Example Plugin Structure

**Recommended: Module-level pattern**

```python
# my_plugin/plugin.py
from talkpipe.chatterlang import registry
from talkpipe.pipe.core import AbstractSource, AbstractSegment

@registry.register_source("httpGet")
class HttpGetSource(AbstractSource):
    """HTTP GET request source - registered automatically on import."""
    pass

@registry.register_segment("jsonParse")
class JsonParseSegment(AbstractSegment):
    """JSON parsing segment - registered automatically on import."""
    pass

def initialize_plugin():
    """Optional: Called after module import for additional setup."""
    print("Network plugin initialized!")
    # Additional setup if needed
```

**Entry point configuration** (points to the module):
```toml
[project.entry-points."talkpipe.plugins"]
network_plugin = "my_plugin.plugin"
```

When this module is loaded:
1. The `@registry.register_source("httpGet")` decorator runs, registering the `HttpGetSource`
2. The `@registry.register_segment("jsonParse")` decorator runs, registering the `JsonParseSegment`
3. The module-level `initialize_plugin()` function is called for any additional setup

### Alternative: Module-Level Registration

You can also register components at the module level:

```python
# my_plugin/__init__.py
from talkpipe.chatterlang import registry
from .sources import MySource
from .segments import MySegment

# Registration happens on import
registry.input_registry.register(MySource, "mySource")
registry.segment_registry.register(MySegment, "mySegment")

def initialize_plugin():
    """Optional additional setup."""
    print("Plugin loaded!")
```

## Plugin Status

### Loaded Plugins
Plugins that were successfully imported and initialized. These plugins are available for use in TalkPipe pipelines.

### Failed Plugins
Plugins that encountered errors during loading. Common causes:
- Missing dependencies
- Import errors
- Registration failures

Check the plugin's documentation and requirements if loading fails.

## Development Workflow

During plugin development, you can reload plugins without restarting Python:

```bash
# Make changes to your plugin code
# Then reload it
talkpipe_plugins --reload my-plugin

# Verify it loaded successfully
talkpipe_plugins --list
```

## Integration with TalkPipe

Plugins are automatically loaded when you import TalkPipe:

```python
import talkpipe  # Plugins loaded automatically

# Use plugin components
from talkpipe.chatterlang import compiler

# Plugin components available in ChatterLang scripts
script = "| httpGet[url='https://api.example.com'] | jsonParse | print"
pipeline = compiler.compile(script)
```

## Troubleshooting

### Plugin Not Found
- Verify the plugin package is installed: `pip list | grep plugin-name`
- Check entry point configuration in plugin's setup files
- Ensure entry point group is `talkpipe.plugins`

### Plugin Load Failure
- Check plugin dependencies are installed
- Review Python import paths
- Verify component registration decorators are working
- Use `--verbose` flag for detailed error information

### Development Issues
- Use `--reload` to refresh plugin code during development
- Check TalkPipe logs for detailed error messages
- Verify plugin follows TalkPipe's component interface requirements

## See Also

- [Extending TalkPipe](../architecture/extending-talkpipe.md) - Creating custom components and plugins
- [Plugin Architecture](../architecture/extending-talkpipe.md#plugin-architecture) - Technical details on the plugin system
- [ChatterLang Registry](../architecture/chatterlang.md) - Component registration system

---

Last Reviewed: 20250831