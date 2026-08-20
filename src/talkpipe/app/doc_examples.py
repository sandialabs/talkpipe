"""Extract and run Python code examples from markdown documentation."""

import re
import subprocess  # nosec B404 - Required to run extracted doc examples script
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

# Directories to skip when scanning markdown files
SKIP_DIRS = {".github", ".pytest_cache", ".claude", ".venv", "venv", "__pycache__"}

# Requirement tags an example may declare. Everything else runs unconditionally,
# so an example that needs an external service and is not tagged fails in CI
# instead of being silently skipped.
KNOWN_REQUIREMENTS = frozenset({"ollama", "openai", "anthropic"})

# ``<!-- doc-example: requires-ollama -->`` on the line before a fence declares
# a requirement; ``<!-- doc-example: skip -->`` excludes the block (like a
# ``# skip-extract`` first line, but invisible in rendered docs).
_DIRECTIVE_RE = re.compile(r"<!--\s*doc-example:\s*([a-z0-9,\s-]+?)\s*-->\s*$")


def find_markdown_files(root: Path) -> list[Path]:
    """Find all markdown files, excluding skip directories."""
    md_files = []
    for path in root.rglob("*.md"):
        if any(part in path.parts for part in SKIP_DIRS):
            continue
        md_files.append(path)
    return sorted(md_files)


def _parse_directive(preceding: str) -> tuple[bool, frozenset[str]]:
    """Parse the ``doc-example`` HTML comment on the line before a fence.

    Returns ``(skip, requirements)``. Unknown requirement names raise so a
    typo cannot silently turn a gated example into an ungated one.
    """
    lines = preceding.rstrip("\n").split("\n")
    if not lines:
        return False, frozenset()
    match = _DIRECTIVE_RE.search(lines[-1].strip())
    if match is None:
        return False, frozenset()
    tokens = {t.strip() for t in match.group(1).split(",") if t.strip()}
    skip = "skip" in tokens
    tokens.discard("skip")
    requirements = set()
    for token in tokens:
        if not token.startswith("requires-"):
            raise ValueError(f"Unknown doc-example directive: {token!r}")
        name = token[len("requires-") :]
        if name not in KNOWN_REQUIREMENTS:
            raise ValueError(f"Unknown doc-example requirement: {name!r}")
        requirements.add(name)
    return skip, frozenset(requirements)


def extract_python_blocks_with_requirements(
    content: str,
) -> list[tuple[int, str, frozenset[str]]]:
    """
    Extract Python code blocks from markdown content.
    Returns list of (line_number, code, requirements) tuples, where
    requirements is the set of services the example declares it needs.
    """
    pattern = re.compile(
        r"^\s*```\s*python\s*\n(.*?)^\s*```\s*$",
        re.DOTALL | re.MULTILINE | re.IGNORECASE,
    )
    blocks = []
    for match in pattern.finditer(content):
        code = match.group(1)
        line_num = content[: match.start()].count("\n") + 1
        code = _normalize_indentation(code)
        if code.strip().startswith("# skip-extract"):
            continue
        skip, requirements = _parse_directive(content[: match.start()])
        if skip:
            continue
        if code.strip():
            blocks.append((line_num, code, requirements))
    return blocks


def extract_python_blocks(content: str) -> list[tuple[int, str]]:
    """
    Extract Python code blocks from markdown content.
    Returns list of (line_number, code) tuples.
    """
    return [
        (line_num, code)
        for line_num, code, _ in extract_python_blocks_with_requirements(content)
    ]


def _normalize_indentation(code: str) -> str:
    """Strip common leading indentation while preserving relative indentation."""
    lines = code.split("\n")
    if not lines:
        return code
    min_indent = None
    for line in lines:
        if line.strip():
            indent = len(line) - len(line.lstrip())
            if min_indent is None or indent < min_indent:
                min_indent = indent
    if min_indent is None or min_indent == 0:
        return code.rstrip()
    result = []
    for line in lines:
        if line.strip() and len(line) >= min_indent:
            result.append(line[min_indent:])
        else:
            result.append(line)
    return "\n".join(result).rstrip()


def extract_all_examples_with_requirements(
    root: Path,
) -> list[tuple[Path, int, str, frozenset[str]]]:
    """
    Extract all Python examples from markdown files.
    Returns list of (file_path, line_number, code, requirements) tuples.
    """
    examples = []
    for md_path in find_markdown_files(root):
        try:
            content = md_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        rel_path = (
            md_path.relative_to(root) if md_path.is_relative_to(root) else md_path
        )
        for line_num, code, requirements in extract_python_blocks_with_requirements(
            content
        ):
            examples.append((rel_path, line_num, code, requirements))
    return examples


def extract_all_examples(root: Path) -> list[tuple[Path, int, str]]:
    """
    Extract all Python examples from markdown files.
    Returns list of (file_path, line_number, code) tuples.
    """
    return [
        (path, line_num, code)
        for path, line_num, code, _ in extract_all_examples_with_requirements(root)
    ]


def run_example(location: str, code: str) -> tuple[bool, BaseException | None]:
    """
    Execute code in a fresh namespace.

    Returns (True, None) if successful, (False, exception) on failure.
    Patches io.Prompt to use echo with default input (avoids blocking on user input).
    """
    io_module: ModuleType | None = None
    original_prompt: Any = None
    try:
        import talkpipe.pipe.io as _io

        io_module = _io
        original_prompt = _io.Prompt
        setattr(  # noqa: B010 - monkeypatch a module attribute
            _io, "Prompt", lambda *args, **kwargs: _io.echo(data="Hello, world!")
        )
    except ImportError:
        pass

    namespace = {"__name__": "__main__", "__package__": None}
    try:
        exec(code, namespace)  # nosec B102 - Code from project's own markdown docs, trusted source
        return (True, None)
    except Exception as e:
        return (False, e)
    finally:
        if io_module is not None and original_prompt is not None:
            setattr(io_module, "Prompt", original_prompt)  # noqa: B010


def generate_runner_script(
    examples: list[tuple[Path, int, str]], output_path: Path
) -> None:
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
        '    namespace = {"__name__": "__main__", "__package__": None}',
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
        escaped = code.replace("\\", "\\\\").replace('"""', r"\"\"\"")
        path_str = str(rel_path).replace("\\", "\\\\")
        lines.append(f'        ("{path_str}", {line_num}, """')
        lines.append(escaped)
        lines.append('"""),')

    fail_index_path = (
        "Path(__file__).resolve().parent / '.extracted_examples_fail_index'"
    )
    lines.extend(
        [
            "    ]",
            "",
            "    from pathlib import Path",
            "",
            f"    fail_index_path = {fail_index_path}",
            "    start_index = 0",
            "    try:",
            "        with open(fail_index_path) as f:",
            "            start_index = int(f.read().strip())",
            "    except (FileNotFoundError, ValueError):",
            "        pass",
            "",
            "    for i in range(start_index, len(examples)):",
            "        path, line_num, code = examples[i]",
            '        print(f"\\n--- {Path(path).name}:{line_num} ---")',
            '        print(f"  {path}")',
            '        if not run_example(f"{path}:{line_num}", code):',
            "            fail_index_path.write_text(str(i))",
            '            print(f"\\nExiting: example {i + 1} failed. Run again to retry from here.", file=sys.stderr)',
            "            sys.exit(1)",
            "",
            "    fail_index_path.unlink(missing_ok=True)",
            '    print(f"\\n--- All {len(examples)} examples passed ---")',
            "",
            "",
            'if __name__ == "__main__":',
            "    main()",
        ]
    )

    output_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    """Extract examples, generate runner script, and run all examples. Returns exit code."""
    root = Path.cwd()
    output_path = root / "extracted_examples.py"

    print(f"Scanning markdown files under {root}...")
    examples = extract_all_examples(root)
    print(f"Found {len(examples)} Python examples")

    generate_runner_script(examples, output_path)
    print(f"Wrote {output_path}")

    result = subprocess.run(  # nosec B603 - output_path is generated by this module, not user input
        [sys.executable, str(output_path)], cwd=str(root)
    )
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
