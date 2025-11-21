Test all standalone ChatterLang examples in the markdown documentation using chatterlang_script.
Assume that the environment is configured so that LLM examples will work.

## Identifying Testable Examples

ChatterLang examples appear in code blocks, often marked with ` ```chatterlang ` or ` ``` `.
A **standalone** example is one that:
- Starts with `INPUT FROM`, `NEW FROM`, or `|` (for interactive pipelines)
- Does NOT depend on external data files created by other steps (e.g., `stories.json` from a previous tutorial)
- Is NOT embedded inside Python code (e.g., `script = '...'` or `compiler.compile("...")`)

Examples that are just syntax demonstrations or fragments (like `| print` alone) should be skipped.

## Directories to Skip

Skip markdown files in these directories:
- `.pytest_cache/`
- `.github/`
- `.claude/`

## Steps

**IMPORTANT: Run tests automatically without asking for permission before each test.**

1. Find every markdown file in the repository (excluding skip directories).
2. For each markdown file:
    1. Identify each standalone ChatterLang script example (see criteria above)
    2. For each standalone example:
        1. Write the example to a temporary file (e.g., `/tmp/test_example.chatterlang`)
        2. Run using: `chatterlang_script --script /tmp/test_example.chatterlang`
        3. If the test passes, continue to the next example.
        4. If there's an error:
            1. Report the file location, line number, and error.
            2. Suggest a fix.
            3. Ask the user if they want to apply the fix, skip, or stop.
            4. If user wants the fix, apply it and re-run the test.
            5. Repeat until the script works or the user says to skip.

## Summary Format

At the end, provide a summary:
- Number of files checked
- Number of examples tested
- Number of examples passed
- Number of examples failed (with file locations)
- Number of examples skipped (with reasons: depends on external files, embedded in Python, etc.)