# Documentation Formatting Guidelines

Guidelines for formatting code examples in markdown to ensure they render correctly and can be extracted for testing.

## Code Block Formatting

### Prefer unindented fences

Place the opening fence at the start of a line (no leading spaces):

````markdown
```python
from talkpipe.pipe import io
pipeline = io.echo(data="hello") | io.Print()
result = pipeline.as_function(single_out=False)()
```
````

**Why**: Unindented blocks are easier for extractors (e.g. `scripts/extract_documentation_examples.py`) to parse and are rendered consistently across markdown processors. The extractor does support indented fences (e.g. inside numbered lists), but unindented is preferred.

### Inside lists

When a code block follows a list item, you can either:

1. **Use an unindented block** (breaks list nesting but is clearest):

   ```python
   code = "at column 0"
   ```

2. **Use indented blocks** (preserves list structure; extractor handles these):

   ```python
   code = "indented under list item"
   ```

### Language tag

Always include the language: ` ```python ` for Python, ` ```chatterlang ` or ` ``` ` for ChatterLang scripts. This enables syntax highlighting and lets extractors identify example types.

## Example intent

Make it clear whether an example is:

- **Standalone runnable**: Complete code users can copy and run. Include all imports, sources, and output.
- **Explanatory fragment**: Partial code illustrating a concept. Add context like "Part of the pipeline above..." or a comment.

See `.claude/commands/review_documentation.md` for more on snippet intent.

## Skip extraction

Add `# skip-extract` as the first line of a block to exclude it from the extracted examples runner (e.g. `setup()` calls that invoke distutils, or fragments that require a package layout).

## Avoid

- Nested triple backticks inside a code block (can break extraction)
- Code blocks without a language tag when the content is code
- Mixing Python and ChatterLang in the same block without clear separation
