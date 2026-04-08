#!/usr/bin/env python3
"""
Generate talkpipe.sources and talkpipe.segments entry points from @register_source
and @register_segment decorators, then replace the relevant sections in pyproject.toml.

Usage:
    python update_entry_points.py [--dry-run] [--source-dir PATH] [--pyproject PATH]

Run from the TalkPipe project root.
"""

import argparse
import re
import sys
from pathlib import Path

# Add project src to path so we can import talkpipe
_project_root = Path(__file__).resolve().parent.parent.parent.parent.parent
sys.path.insert(0, str(_project_root / "src"))

from talkpipe.app.chatterlang_generate_entry_points import (
    generate_toml_section,
    scan_directory,
)


def _find_entry_points_start(content: str) -> int:
    """Return the byte index where entry points section begins, or -1 if not found."""
    match = re.search(
        r'\n\[project\.entry-points\.["\']talkpipe\.sources["\']\]',
        content,
    )
    if match:
        return match.start() + 1  # Include the newline before the section
    return -1


def update_pyproject(
    pyproject_path: Path,
    source_dir: Path,
    package_name: str = "talkpipe",
    dry_run: bool = False,
) -> bool:
    """
    Generate entry points from source_dir and replace sections in pyproject.toml.

    Returns True if pyproject.toml was updated (or would be in dry-run), False on error.
    """
    if not pyproject_path.exists():
        print(f"Error: {pyproject_path} does not exist", file=sys.stderr)
        return False

    if not source_dir.exists():
        print(f"Error: Source directory {source_dir} does not exist", file=sys.stderr)
        return False

    # Generate entry points
    results = scan_directory(source_dir, package_name)
    new_toml = generate_toml_section(results["sources"], results["segments"])

    if not new_toml.strip():
        print("Warning: No entry points generated. Check that sources use @register_source/@register_segment.", file=sys.stderr)
        return False

    content = pyproject_path.read_text(encoding="utf-8")
    start = _find_entry_points_start(content)

    if start < 0:
        print("Error: Could not find [project.entry-points.\"talkpipe.sources\"] in pyproject.toml", file=sys.stderr)
        return False

    prefix = content[:start]
    # Ensure generated section ends with newline; strip trailing blanks from prefix
    new_section = new_toml.rstrip() + "\n"
    new_content = prefix.rstrip() + "\n\n" + new_section

    if dry_run:
        print("Generated entry points (dry-run, no file written):")
        print("=" * 60)
        print(new_section)
        print("=" * 60)
        if new_content != content:
            print("pyproject.toml would be updated.")
        else:
            print("No changes needed.")
        return True

    if new_content != content:
        pyproject_path.write_text(new_content, encoding="utf-8")
        print(f"Updated {pyproject_path} with {len(results['sources'])} sources and {len(results['segments'])} segments.")
    else:
        print("No changes needed; pyproject.toml already matches generated entry points.")

    return True


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate entry points and update pyproject.toml",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print generated content without modifying pyproject.toml",
    )
    parser.add_argument(
        "--source-dir",
        type=Path,
        default=_project_root / "src" / "talkpipe",
        help="Directory to scan for decorators (default: src/talkpipe)",
    )
    parser.add_argument(
        "--pyproject",
        type=Path,
        default=_project_root / "pyproject.toml",
        help="Path to pyproject.toml (default: pyproject.toml)",
    )

    args = parser.parse_args()

    ok = update_pyproject(
        pyproject_path=args.pyproject,
        source_dir=args.source_dir,
        dry_run=args.dry_run,
    )
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
