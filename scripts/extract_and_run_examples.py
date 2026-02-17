#!/usr/bin/env python3
"""
Extract Python code examples from markdown files and generate a runnable script.

Scans all .md files (excluding .github, .pytest_cache, .claude) for ```python
code blocks, collects them, and writes a single Python file that prints each
example's location before running it.
"""

import re
from pathlib import Path


# Directories to skip when scanning markdown files
SKIP_DIRS = {".github", ".pytest_cache", ".claude", ".venv", "venv", "__pycache__"}


def find_markdown_files(root: Path) -> list[Path]:
    """Find all markdown files, excluding skip directories."""
    md_files = []
    for path in root.rglob("*.md"):
        if any(part in path.parts for part in SKIP_DIRS):
            continue
        md_files.append(path)
    return sorted(md_files)


def extract_python_blocks(content: str) -> list[tuple[int, str]]:
    """
    Extract Python code blocks from markdown content.
    Returns list of (line_number, code) tuples.
    """
    # Match ```python ... ``` (CommonMark allows up to 3 spaces indent on fences)
    pattern = re.compile(
        r"^\s*```\s*python\s*\n(.*?)^\s*```\s*$",
        re.DOTALL | re.MULTILINE | re.IGNORECASE,
    )
    blocks = []
    for match in pattern.finditer(content):
        code = match.group(1)
        # Find the line number of the start of this block
        line_num = content[: match.start()].count("\n") + 1
        # Strip common leading indentation from the code block
        code = _normalize_indentation(code)
        if code.strip():
            blocks.append((line_num, code))
    return blocks


def _normalize_indentation(code: str) -> str:
    """Strip common leading indentation while preserving relative indentation."""
    lines = code.split("\n")
    if not lines:
        return code
    # Find minimum non-empty line indentation
    min_indent = None
    for line in lines:
        if line.strip():
            indent = len(line) - len(line.lstrip())
            if min_indent is None or indent < min_indent:
                min_indent = indent
    if min_indent is None or min_indent == 0:
        return code.rstrip()
    # Strip that much from each line
    result = []
    for line in lines:
        if line.strip() and len(line) >= min_indent:
            result.append(line[min_indent:])
        else:
            result.append(line)
    return "\n".join(result).rstrip()


def extract_all_examples(root: Path) -> list[tuple[Path, int, str]]:
    """
    Extract all Python examples from markdown files.
    Returns list of (file_path, line_number, code) tuples.
    """
    examples = []
    for md_path in find_markdown_files(root):
        try:
            content = md_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line_num, code in extract_python_blocks(content):
            # Use path relative to root for cleaner output
            rel_path = md_path.relative_to(root) if md_path.is_relative_to(root) else md_path
            examples.append((rel_path, line_num, code))
    return examples


def generate_runner_script(examples: list[tuple[Path, int, str]], output_path: Path) -> None:
    """Generate a Python script that runs each example with location printed."""
    lines = [
        '"""',
        "Auto-generated script: runs all Python examples extracted from markdown files.",
        "Each example prints its source location before execution.",
        "Pipelines using the Prompt source are fed 'Hello, world!' instead of waiting for input.",
        "Exits on first failure.",
        '"""',
        "",
        "import sys",
        "",
        "",
        "def run_example(location: str, code: str) -> bool:",
        '    """Execute code in a fresh namespace. Returns True if successful."""',
        "    # Patch io.Prompt to use echo with default input (avoids blocking on user input)",
        "    io_module = None",
        "    original_prompt = None",
        "    try:",
        "        import talkpipe.pipe.io as _io",
        "        io_module = _io",
        "        original_prompt = _io.Prompt",
        "        _io.Prompt = lambda *args, **kwargs: _io.echo(data='Hello, world!')",
        "    except ImportError:",
        "        pass",
        "",
        "    namespace = {}",
        "    try:",
        "        exec(code, namespace)",
        "        return True",
        "    except Exception as e:",
        '        print(f"  ERROR: {e}", file=sys.stderr)',
        "        return False",
        "    finally:",
        "        if io_module is not None and original_prompt is not None:",
        "            io_module.Prompt = original_prompt",
        "",
        "",
        "def main():",
        "    examples = [",
    ]

    for rel_path, line_num, code in examples:
        # Escape for embedding in triple-quoted string: \ and """
        escaped = code.replace("\\", "\\\\").replace('"""', r"\"\"\"")
        location = str(rel_path).replace("\\", "\\\\")
        lines.append(f'        ("{location}:{line_num}", """')
        lines.append(escaped)
        lines.append('"""),')

    lines.extend(
        [
            "    ]",
            "",
            "    for i, (location, code) in enumerate(examples):",
            '        print(f"\\n--- {location} ---")',
            "        if not run_example(location, code):",
            '            print(f"\\nExiting: example {i + 1} failed.", file=sys.stderr)',
            "            sys.exit(1)",
            "",
            '    print(f"\\n--- All {len(examples)} examples passed ---")',
            "",
            "",
            'if __name__ == "__main__":',
            "    main()",
        ]
    )

    output_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    output_path = root / "extracted_examples.py"

    print(f"Scanning markdown files under {root}...")
    examples = extract_all_examples(root)
    print(f"Found {len(examples)} Python examples")

    generate_runner_script(examples, output_path)
    print(f"Wrote {output_path}")


if __name__ == "__main__":
    main()
