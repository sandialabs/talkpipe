---
mode: agent
description: Add a new segment or source to TalkPipe. Use when creating new pipe components. Covers decorator pattern, parameter annotations, entry-point registration, and TDD.
---

Add a new **$input** to TalkPipe following all project conventions:

## Step 1 — Write a failing test

In the appropriate file under `tests/talkpipe/`, write a test that fails without the new component. Run it to confirm failure:

```bash
source .venv/bin/activate && pytest <test-file> -v
```

## Step 2 — Implement the component

Place it in the appropriate module under `src/talkpipe/`:

```python
from typing import Annotated, Iterator, Any
from talkpipe.pipe.core import segment, field_segment
from talkpipe import register_segment  # or register_source

@register_segment("mySegment")          # camelCase name used in ChatterLang
@segment()
def my_segment(
    items: Iterator[Any],
    param: Annotated[str, "Description of this parameter"] = "default",
) -> Iterator[Any]:
    for item in items:
        yield item  # process and yield
```

Rules:
- Use `@segment()` for iterators; `@field_segment()` for per-field transforms
- Use `Annotated[type, "description"]` for every parameter (shown in ChatterLang reference)
- Do NOT add docstrings documenting parameters — use `Annotated` instead
- For `@field_segment`, the first non-items argument is the `field` parameter by convention

## Step 3 — Register entry point

```bash
.venv/bin/python .cursor/skills/update-entry-points/scripts/update_entry_points.py
```

Verify the new entry appears in `pyproject.toml` under `[project.entry-points."talkpipe.segments"]` or `"talkpipe.sources"`.

## Step 4 — Verify test passes

```bash
pytest <test-file> -v
```

## Step 5 — Update CHANGELOG.md

Add a bullet under `## Unreleased` describing the new component.
