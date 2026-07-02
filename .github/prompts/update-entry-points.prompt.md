---
mode: agent
description: Regenerate and apply talkpipe.sources and talkpipe.segments entry points from @register_source/@register_segment decorators. Use after adding new sources or segments, or when pyproject.toml entry points are out of sync.
---

Regenerate entry points from `@register_source` and `@register_segment` decorators and update `pyproject.toml`.

Run from the project root:

```bash
source .venv/bin/activate
python .cursor/skills/update-entry-points/scripts/update_entry_points.py
```

The script:
1. Scans `src/talkpipe/` for `@register_source` and `@register_segment` decorators
2. Generates updated entry-point TOML
3. Replaces `[project.entry-points."talkpipe.sources"]` and `[project.entry-points."talkpipe.segments"]` in `pyproject.toml`
4. Preserves all other `pyproject.toml` content

**Dry run** (preview without writing):
```bash
python .cursor/skills/update-entry-points/scripts/update_entry_points.py --dry-run
```

After running, verify the expected entry appears in `pyproject.toml`.
