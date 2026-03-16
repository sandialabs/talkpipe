---
name: doc-example-formatting
description: Format code examples in markdown documentation for TalkPipe. Use when writing or editing doc examples. Covers unindented fences, standalone vs fragment intent, and skip-extract. Complements run-documentation-examples which runs the examples.
---

# Doc Example Formatting

Format code blocks in markdown so they render correctly and can be extracted for testing. See [docs/architecture/documentation-formatting.md](docs/architecture/documentation-formatting.md) for full guidelines.

## When to Use

- Writing new documentation with code examples
- Editing existing doc examples
- Adding snippets to README, guides, or API docs

## Code Block Formatting

### Prefer unindented fences

Place the opening fence at the start of the line (no leading spaces):

```markdown
```python
from talkpipe.pipe import io
pipeline = io.echo(data="hello") | io.Print()
result = pipeline.as_function(single_out=False)()
```
```

**Why**: Unindented blocks are easier for extractors to parse. Indented fences (e.g. inside lists) are supported but unindented is preferred.

### Language tag

Always include the language: ` ```python ` for Python, ` ```chatterlang ` or ` ``` ` for ChatterLang. Enables syntax highlighting and lets extractors identify example types.

## Example Intent

Make it clear whether an example is:

- **Standalone runnable**: Complete code users can copy and run. Include all imports, sources, and output.
- **Explanatory fragment**: Partial code illustrating a concept. Add context like "Part of the pipeline above..." or a comment.

## Skip Extraction

Add `# skip-extract` as the first line of a block to exclude it from the doc examples runner:

```python
# skip-extract
from setuptools import setup
setup(name="myproject", ...)
```

**Use skip-extract when:**
- Block invokes distutils/setuptools or requires a package layout
- Block uses relative imports that fail when run in isolation
- Block is an illustrative fragment, not runnable
- Block requires external services (LLM, DB) and is covered elsewhere

## Good vs Bad

**Good (standalone, unindented):**
````markdown
```python
from talkpipe.pipe import io
pipeline = io.echo(data="hello") | io.Print()
pipeline.as_function(single_out=False)()
```
````

**Bad (no language tag):**
````markdown
```
code here
```
````

**Bad (nested backticks inside block):** Avoid triple backticks within the code content; they can break extraction.

## Avoid

- Nested triple backticks inside a code block (can break extraction)
- Code blocks without a language tag when the content is code
- Mixing Python and ChatterLang in the same block without clear separation

## Validation

After editing docs, run the doc examples to verify they execute:

```bash
pytest tests/test_doc_examples.py -v
```

Or use the run-documentation-examples skill. Skip LLM examples when Ollama unavailable: `pytest tests/test_doc_examples.py -m "not requires_ollama" -v`
