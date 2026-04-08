---
name: run-documentation-examples
description: Extract Python examples from markdown docs and run them (including LLM examples). Use when validating documentation, after doc changes, or to verify all doc examples execute correctly.
---

# Run Documentation Examples

Extracts Python code blocks from markdown files and runs each example. LLM examples (llmPrompt, LLMPrompt, etc.) run as-is—they make real API calls when Ollama/OpenAI/Anthropic are configured.

## When to Use

- After editing documentation
- Validating that doc examples execute correctly
- CI-style doc checks

## Environment

Use `.venv`. Run via `.venv/bin/python` or activate with `source .venv/bin/activate`.

## Workflow

**Recommended (pytest):** Run from the project root:

```bash
pytest tests/test_doc_examples.py -v
```

**Alternative (CLI):**

```bash
run_doc_examples
```

Or via the skill script:

```bash
.venv/bin/python .cursor/skills/run-documentation-examples/scripts/run_documentation_examples.py
```

**When running via the agent**: Request `full_network` permissions so the sandbox allows connections to localhost (Ollama) and external APIs (OpenAI, Anthropic).

The pytest approach gives standard test output; `run-doc-examples` extracts examples, generates `extracted_examples.py`, and runs it (supports resume via `.extracted_examples_fail_index`).

## Manual Two-Step Workflow

```bash
.venv/bin/python scripts/extract_documentation_examples.py
.venv/bin/python extracted_examples.py
```

## CI Without Ollama

To skip doc examples when Ollama is unavailable: `pytest tests/ -m "not requires_ollama"`

## Prerequisites for LLM Examples

- **Ollama**: `ollama serve` running; `ollama pull llama3.2` (and `mxbai-embed-large` for embedding examples)
- **OpenAI**: `TALKPIPE_openai_api_key` or config
- **Anthropic**: Similar env/config
- **Extras**: `pip install talkpipe[ollama]` (or `[openai]`, `[anthropic]`, `[all]`)

## Failure Handling

The runner exits on first failure and writes `.extracted_examples_fail_index` with the failed example index. Run again to retry from that point. Delete the file to start from the beginning.
