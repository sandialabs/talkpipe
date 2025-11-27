# Review Documentation for Accuracy

Review all markdown documentation files in the repository for accuracy with respect to the codebase.

## Scope

Review all `.md` files in the repository, excluding:
- `.pytest_cache/`
- `.github/`
- `.claude/`
- `CHANGELOG.md` (version history, not technical docs)

## Review Categories

For each documentation file, check the following:

### 1. Code References
- Verify that referenced file paths exist (e.g., `src/talkpipe/pipe/core.py:166`)
- Check that mentioned classes, functions, and methods exist in the codebase
- Validate import statements shown in examples

### 2. API Accuracy
- Verify function/method signatures match the actual code
- Check that documented parameters exist and have correct types/defaults
- Confirm return types are accurate
- Validate that documented exceptions are actually raised

### 3. Command-Line Tools
- Verify that documented CLI commands exist in `pyproject.toml` entry points
- Check that command-line arguments match the actual argument parsers
- Validate default values mentioned in documentation

### 4. Configuration Options
- Verify documented configuration keys are actually used in the code
- Check environment variable names and prefixes
- Validate default values

### 5. ChatterLang Components
- Verify that documented sources exist in the registry
- Verify that documented segments exist in the registry
- Check parameter names and defaults for registered components

### 6. Code Examples
- For Python examples: Check that imports would work and APIs are correct
- For ChatterLang examples: Verify syntax is valid (including LLM-dependent ones)
- Flag examples that reference deprecated or renamed components
- **Ensure snippet intent is explicit**: Each code snippet should clearly communicate whether it is:
  - **Stand-alone runnable code**: Complete examples that users can copy and execute
  - **Explanatory fragments**: Partial code showing syntax, concepts, or parts of a larger example
- For stand-alone snippets: Verify they are complete and runnable (include all necessary imports, INPUT FROM sources, output destinations, etc.)
- For explanatory fragments: Check that they are properly contextualized through:
  - Introductory text like "This segment...", "Part of the pipeline above...", or "The following step..."
  - Placement within a clear breakdown/explanation section
  - Comments indicating they're part of a larger example
- When snippet intent is unclear, suggest adding context or completing the example to make it obvious to readers whether code is meant to be copied and run or just studied

### 7. Writing Quality
- Check that text is concise and focused, not meandering or unnecessarily verbose
- Identify repetitive content that restates the same ideas multiple times
- Flag sections where the same concept is explained redundantly
- Ensure each paragraph adds new information rather than rephrasing previous content
- Look for overly long explanations that could be condensed without losing clarity

## Output Format

For each issue found, report:
1. **File**: The markdown file path
2. **Line**: Approximate line number or section
3. **Issue Type**: One of the categories above
4. **Description**: What's wrong
5. **Suggestion**: How to fix it

## Process

1. First, gather context about the codebase structure:
   - Read `pyproject.toml` to understand entry points and package structure
   - Scan the registry system to understand available sources and segments
   - Review core API files to understand current signatures

2. Then systematically review each documentation file:
   - Parse the markdown to identify code blocks, references, and technical claims
   - Cross-reference against the actual codebase
   - Note any discrepancies

3. Finally, provide a summary:
   - Total files reviewed
   - Issues found by category
   - Priority recommendations (critical issues vs minor improvements)

## Important Notes

- Do NOT automatically fix issues. Report them for user review.
- Focus on factual accuracy and clarity - check both technical correctness and writing quality
- Be thorough but efficient - use search tools to verify claims
- For ambiguous cases, note the uncertainty rather than assuming an error
- Consider that some documentation may describe planned features - flag these for clarification
