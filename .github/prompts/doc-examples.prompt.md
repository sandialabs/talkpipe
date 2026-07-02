---
mode: agent
description: Validate and fix documentation code examples. Use after editing docs, before committing doc changes, or when examples may be broken. Runs examples via pytest and fixes formatting issues.
---

Validate documentation code examples following TalkPipe conventions. See [docs/architecture/documentation-formatting.md](../../docs/architecture/documentation-formatting.md) for full formatting rules.

## Run examples via pytest

```bash
source .venv/bin/activate
pytest tests/test_doc_examples.py -v
```

Skip Ollama-dependent examples when Ollama is unavailable:
```bash
pytest tests/test_doc_examples.py -v -m "not requires_ollama"
```

## Formatting rules (fix any violations found)

- Use **unindented** ` ```python ` fences (no leading spaces before the triple backtick)
- Always include a language tag (` ```python ` or ` ```chatterlang `)
- Standalone examples must include all imports and be runnable in isolation
- Add `# skip-extract` as the first line of blocks that are intentionally non-runnable (fragments, setup code, external-service-only)

## Scope

$input
