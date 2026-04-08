#!/usr/bin/env python3
"""
Extract Python code examples from markdown files and generate a runnable script.

Scans all .md files (excluding .github, .pytest_cache, .claude) for ```python
code blocks, collects them, and writes extracted_examples.py.

Thin wrapper around talkpipe.app.doc_examples.
"""

import sys
from pathlib import Path

# Add project root for imports when run as script
_script_dir = Path(__file__).resolve().parent
_project_root = _script_dir.parent
sys.path.insert(0, str(_project_root / "src"))

from talkpipe.app.doc_examples import (
    extract_all_examples,
    generate_runner_script,
)


def main() -> None:
    root = _project_root
    output_path = root / "extracted_examples.py"

    print(f"Scanning markdown files under {root}...")
    examples = extract_all_examples(root)
    print(f"Found {len(examples)} Python examples")

    generate_runner_script(examples, output_path)
    print(f"Wrote {output_path}")


if __name__ == "__main__":
    main()
