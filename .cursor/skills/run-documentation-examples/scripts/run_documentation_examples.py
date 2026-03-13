#!/usr/bin/env python3
"""
Extract Python examples from markdown docs and run them.

Thin wrapper that invokes talkpipe.app.doc_examples. Run from the TalkPipe project root.
Use .venv: .venv/bin/python .cursor/skills/run-documentation-examples/scripts/run_documentation_examples.py
"""

import subprocess
import sys
from pathlib import Path

# Project root: .../run-documentation-examples/scripts/ -> .../../../../../ = project root
_project_root = Path(__file__).resolve().parent.parent.parent.parent.parent


def main() -> int:
    result = subprocess.run(
        [sys.executable, "-m", "talkpipe.app.doc_examples"],
        cwd=str(_project_root),
    )
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
