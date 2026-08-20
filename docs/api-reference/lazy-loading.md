# Lazy Loading

TalkPipe's component registry loads segments and sources **on demand, always**.
There is no switch to flip: `import talkpipe` is fast (well under a second)
because nothing beyond the core is imported until a script or the Pipe API
actually names a component.

## How the registry loads components

The registry (`talkpipe.chatterlang.registry`) resolves a name in this order:

1. **Decorator registrations** — anything already registered with
   `@register_segment` / `@register_source` in a module that has been imported.
2. **Entry points** — the `talkpipe.segments` / `talkpipe.sources` groups
   declared by talkpipe itself and by installed plugins. The entry point for
   *that one name* is imported at that moment; nothing else is touched.
3. Otherwise a `CompileError` / `KeyError` naming the closest matches.

Only operations that need the *whole* catalogue — the `.all` property,
`chatterlang_reference_browser`, the workbench reference pane,
`talkpipe_plugins --list`, and error-message suggestions — import every
declared entry point, once, on first use.

```python
from talkpipe.chatterlang import registry

# Resolving one name imports only that component's module.
seg = registry.segment_registry.get("print")

# .all imports every declared entry point (once) — expected to be slower.
names = sorted(registry.segment_registry.all)
assert "print" in names
```

## `LAZY_IMPORT` — kept for compatibility, no longer changes behaviour

Earlier releases documented a `LAZY_IMPORT` config key
(`TALKPIPE_LAZY_IMPORT=true`) that switched the registry between eager and
lazy loading. On-demand loading became the only behaviour, so the flag now
affects nothing except the `lazy_mode` field of
`registry.segment_registry.stats()` and a debug log line. Setting it is
harmless; leaving it unset is recommended. `enable_lazy_imports()` /
`disable_lazy_imports()` are retained as no-op-equivalent helpers for the same
reason and are scheduled for removal in TalkPipe 2.0.

## Keeping *your* components cheap to load

Lazy resolution only helps if a component's module is itself cheap to import.
Import heavy optional dependencies inside the function or method that needs
them, not at module top level, so a pipeline that never uses that component
never pays for it:

```python
from talkpipe.pipe import core
from talkpipe.chatterlang import registry


@registry.register_segment("myHeavyThing")
@core.segment()
def my_heavy_thing(items):
    import json  # stand-in for a heavy import; resolved only when the segment runs

    for item in items:
        yield json.dumps(item)


assert registry.segment_registry.get("myHeavyThing") is not None
```

This is the pattern talkpipe uses for its own optional providers
(`ollama`, `openai`, `anthropic`, `model2vec`, `pypdf`, `PIL`), each of which
raises an `ImportError` naming the extra to install if it is missing.

## Diagnostics

```python
from talkpipe.chatterlang import registry

stats = registry.segment_registry.stats()
print(sorted(stats))  # decorator-registered, entry-point, loaded, failed counts, lazy_mode
```

`talkpipe_plugins --list` shows which entry points loaded and which failed,
with the error, so a plugin that fails to import does not silently
disappear.
