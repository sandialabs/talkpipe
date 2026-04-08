---
name: update-entry-points
description: Generate talkpipe.sources and talkpipe.segments entry points from @register_source/@register_segment decorators and update pyproject.toml. Use when adding new sources or segments to TalkPipe, or when entry points are out of sync with the codebase.
---

# Update Entry Points in pyproject.toml

Generates entry points from `@register_source` and `@register_segment` decorators and replaces the relevant sections in pyproject.toml.

## When to Use

- After adding a new source or segment to TalkPipe
- When entry points in pyproject.toml are out of sync with decorator usage
- When chatterlang_generate_entry_points output needs to be applied to pyproject.toml

## Workflow

Run the bundled script from the project root:

```bash
.venv/bin/python .cursor/skills/update-entry-points/scripts/update_entry_points.py
```

Or with the venv activated:

```bash
python .cursor/skills/update-entry-points/scripts/update_entry_points.py
```

The script:
1. Scans `src/talkpipe` for `@register_source` and `@register_segment` decorators
2. Generates the entry points TOML (same logic as chatterlang_generate_entry_points)
3. Replaces `[project.entry-points."talkpipe.sources"]` and `[project.entry-points."talkpipe.segments"]` in pyproject.toml
4. Preserves all other pyproject.toml content

## Options

| Option | Description |
|--------|-------------|
| `--dry-run` | Print generated content and show diff without modifying pyproject.toml |
| `--source-dir PATH` | Override source directory (default: `src/talkpipe`) |
| `--pyproject PATH` | Override pyproject.toml path (default: `pyproject.toml`) |

## Manual Fallback

If the script fails, you can:

1. Run `chatterlang_generate_entry_points src/talkpipe --output /tmp/entry_points.toml`
2. Open pyproject.toml and replace the entry point sections (from `[project.entry-points."talkpipe.sources"]` to end of file) with the contents of /tmp/entry_points.toml
