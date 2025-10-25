#!/usr/bin/env python3
"""
Script to scan source tree for @register_source and @register_segment decorators
and generate pyproject.toml entry points section.

Usage:
    python generate_entry_points.py <source_directory> [--package-name talkpipe]
"""

import ast
import argparse
from pathlib import Path
from typing import List, Dict, Tuple, Optional
import sys


class DecoratorFinder(ast.NodeVisitor):
    """AST visitor to find decorator usage in Python files."""

    def __init__(self, module_path: str):
        self.module_path = module_path
        self.sources: List[Tuple[str, str]] = []  # [(name, class_name)]
        self.segments: List[Tuple[str, str]] = []  # [(name, class_name)]

    def _process_decorators(self, node):
        """Process decorators on a class or function definition."""
        for decorator in node.decorator_list:
            # Handle @register_source("name") or @register_segment("name")
            # Now also handles multiple names: @register_source("name1", "name2")
            if isinstance(decorator, ast.Call):
                decorator_name = self._get_decorator_name(decorator.func)
                registration_names = self._get_registration_names(decorator)

                if decorator_name == 'register_source' and registration_names:
                    for reg_name in registration_names:
                        self.sources.append((reg_name, node.name))
                elif decorator_name == 'register_segment' and registration_names:
                    for reg_name in registration_names:
                        self.segments.append((reg_name, node.name))

    def visit_ClassDef(self, node: ast.ClassDef):
        """Visit class definitions and check for our decorators."""
        self._process_decorators(node)
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef):
        """Visit function definitions and check for our decorators."""
        self._process_decorators(node)
        self.generic_visit(node)
    
    def _get_decorator_name(self, func_node) -> Optional[str]:
        """Extract decorator function name from AST node."""
        if isinstance(func_node, ast.Name):
            return func_node.id
        elif isinstance(func_node, ast.Attribute):
            return func_node.attr
        return None
    
    def _get_registration_names(self, call_node: ast.Call) -> List[str]:
        """
        Extract all registration names from decorator call arguments.
        
        Handles:
        - @register_source("name1", "name2", "name3")  # Multiple positional
        - @register_source("name1")                     # Single positional
        - @register_source(name="name1")                # Keyword argument
        
        Returns:
            List of registration names found
        """
        names = []
        
        # Check all positional arguments
        for arg in call_node.args:
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                names.append(arg.value)
        
        # Check keyword argument 'name='
        for keyword in call_node.keywords:
            if keyword.arg == 'name' and isinstance(keyword.value, ast.Constant):
                if isinstance(keyword.value.value, str):
                    names.append(keyword.value.value)
        
        return names


def scan_file(file_path: Path, package_root: Path, package_name: str) -> Dict[str, List[Tuple[str, str, str]]]:
    """
    Scan a single Python file for decorator usage.
    
    Args:
        file_path: Path to the Python file
        package_root: Root directory of the package
        package_name: Name of the package (e.g., 'talkpipe')
    
    Returns:
        Dictionary with 'sources' and 'segments' keys, each containing
        list of tuples: (registration_name, class_name, module_path)
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        tree = ast.parse(content, filename=str(file_path))
        
        # Calculate module path relative to package root
        relative_path = file_path.relative_to(package_root)
        module_parts = list(relative_path.parts[:-1]) + [relative_path.stem]
        
        # Remove __init__ from the end if present
        if module_parts[-1] == '__init__':
            module_parts = module_parts[:-1]
        
        module_path = '.'.join([package_name] + module_parts)
        
        finder = DecoratorFinder(module_path)
        finder.visit(tree)
        
        sources = [(name, cls, module_path) for name, cls in finder.sources]
        segments = [(name, cls, module_path) for name, cls in finder.segments]
        
        return {
            'sources': sources,
            'segments': segments
        }
    
    except SyntaxError as e:
        print(f"Syntax error in {file_path}: {e}", file=sys.stderr)
        return {'sources': [], 'segments': []}
    except Exception as e:
        print(f"Error scanning {file_path}: {e}", file=sys.stderr)
        return {'sources': [], 'segments': []}


def scan_directory(directory: Path, package_name: str) -> Dict[str, List[Tuple[str, str, str]]]:
    """
    Recursively scan directory for Python files with decorators.
    
    Args:
        directory: Root directory to scan
        package_name: Name of the package
    
    Returns:
        Dictionary with 'sources' and 'segments' lists
    """
    all_sources = []
    all_segments = []
    
    # Find all Python files
    python_files = list(directory.rglob('*.py'))
    
    print(f"Scanning {len(python_files)} Python files in {directory}...")
    
    for py_file in python_files:
        # Skip test files and certain directories if needed
        if '__pycache__' in py_file.parts or 'test' in py_file.parts:
            continue
        
        results = scan_file(py_file, directory, package_name)
        all_sources.extend(results['sources'])
        all_segments.extend(results['segments'])
        
        if results['sources'] or results['segments']:
            print(f"  Found in {py_file.relative_to(directory)}:")
            for name, cls, _ in results['sources']:
                print(f"    @register_source('{name}') → {cls}")
            for name, cls, _ in results['segments']:
                print(f"    @register_segment('{name}') → {cls}")
    
    return {
        'sources': all_sources,
        'segments': all_segments
    }


def generate_toml_section(sources: List[Tuple[str, str, str]], 
                          segments: List[Tuple[str, str, str]]) -> str:
    """
    Generate the pyproject.toml entry points section.
    
    Args:
        sources: List of (registration_name, class_name, module_path)
        segments: List of (registration_name, class_name, module_path)
    
    Returns:
        String containing the TOML configuration
    """
    lines = []
    
    # Sort for consistent output
    sources = sorted(sources, key=lambda x: x[0])
    segments = sorted(segments, key=lambda x: x[0])
    
    if sources:
        lines.append('[project.entry-points."talkpipe.sources"]')
        for reg_name, class_name, module_path in sources:
            lines.append(f'{reg_name} = "{module_path}:{class_name}"')
        lines.append('')
    
    if segments:
        lines.append('[project.entry-points."talkpipe.segments"]')
        for reg_name, class_name, module_path in segments:
            lines.append(f'{reg_name} = "{module_path}:{class_name}"')
        lines.append('')
    
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(
        description='Generate pyproject.toml entry points from decorator usage'
    )
    parser.add_argument(
        'source_dir',
        type=Path,
        help='Source directory to scan (e.g., ./src/talkpipe or ./talkpipe)'
    )
    parser.add_argument(
        '--package-name',
        type=str,
        default='talkpipe',
        help='Package name for module paths (default: talkpipe)'
    )
    parser.add_argument(
        '--output',
        type=Path,
        help='Output file (default: print to stdout)'
    )
    
    args = parser.parse_args()
    
    if not args.source_dir.exists():
        print(f"Error: Directory {args.source_dir} does not exist", file=sys.stderr)
        sys.exit(1)
    
    if not args.source_dir.is_dir():
        print(f"Error: {args.source_dir} is not a directory", file=sys.stderr)
        sys.exit(1)
    
    # Scan the directory
    results = scan_directory(args.source_dir, args.package_name)
    
    print(f"\n{'='*60}")
    print(f"Summary:")
    print(f"  Found {len(results['sources'])} source registrations")
    print(f"  Found {len(results['segments'])} segment registrations")
    print(f"{'='*60}\n")
    
    # Generate TOML section
    toml_content = generate_toml_section(results['sources'], results['segments'])
    
    if args.output:
        with open(args.output, 'w') as f:
            f.write(toml_content)
        print(f"Entry points written to {args.output}")
    else:
        print("Generated pyproject.toml section:")
        print("="*60)
        print(toml_content)
        print("="*60)
    
    # Check for duplicates
    source_names = [name for name, _, _ in results['sources']]
    segment_names = [name for name, _, _ in results['segments']]
    
    source_dupes = [name for name in source_names if source_names.count(name) > 1]
    segment_dupes = [name for name in segment_names if segment_names.count(name) > 1]
    
    if source_dupes or segment_dupes:
        print("\n⚠️  WARNING: Duplicate registrations found!", file=sys.stderr)
        if source_dupes:
            print(f"  Duplicate sources: {set(source_dupes)}", file=sys.stderr)
        if segment_dupes:
            print(f"  Duplicate segments: {set(segment_dupes)}", file=sys.stderr)


if __name__ == '__main__':
    main()
