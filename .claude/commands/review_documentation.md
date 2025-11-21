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
- For ChatterLang examples: Verify syntax is valid (but don't run LLM-dependent ones)
- Flag examples that reference deprecated or renamed components

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
- Focus on factual accuracy, not style or formatting
- Be thorough but efficient - use search tools to verify claims
- For ambiguous cases, note the uncertainty rather than assuming an error
- Consider that some documentation may describe planned features - flag these for clarification
