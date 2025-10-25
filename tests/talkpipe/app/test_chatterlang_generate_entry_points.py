#!/usr/bin/env python3
"""
Tests for chatterlang_generate_entry_points.py script.
"""
import tempfile
from pathlib import Path
import pytest

from talkpipe.app.chatterlang_generate_entry_points import (
    DecoratorFinder,
    scan_file,
    scan_directory,
)


def test_decorator_finder_finds_function_based_sources_and_segments():
    """Test that DecoratorFinder can find @register_source and @register_segment on functions."""

    # Create a temporary Python file with function-based decorators
    test_code = '''
from talkpipe.chatterlang.registry import register_source, register_segment
from talkpipe.pipe.core import source, segment

@register_source('test_echo')
@source()
def echo_func(data: str):
    """A test echo function."""
    yield data

@register_segment('test_transform')
@segment()
def transform_func(items):
    """A test transform function."""
    for item in items:
        yield item.upper()
'''

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        test_file = tmpdir_path / "test_module.py"
        test_file.write_text(test_code)

        # Scan the file
        results = scan_file(test_file, tmpdir_path, "testpackage")

        # Verify that both the function-based source and segment were found
        assert len(results['sources']) == 1, f"Expected 1 source, found {len(results['sources'])}"
        assert len(results['segments']) == 1, f"Expected 1 segment, found {len(results['segments'])}"

        # Check the source details
        source_name, source_class, source_module = results['sources'][0]
        assert source_name == 'test_echo'
        assert source_class == 'echo_func'
        assert source_module == 'testpackage.test_module'

        # Check the segment details
        segment_name, segment_class, segment_module = results['segments'][0]
        assert segment_name == 'test_transform'
        assert segment_class == 'transform_func'
        assert segment_module == 'testpackage.test_module'


def test_decorator_finder_finds_class_based_sources_and_segments():
    """Test that DecoratorFinder can still find @register_source and @register_segment on classes."""

    # Create a temporary Python file with class-based decorators
    test_code = '''
from talkpipe.chatterlang.registry import register_source, register_segment
from talkpipe.pipe.core import AbstractSource, AbstractSegment

@register_source('test_prompt')
class Prompt(AbstractSource):
    """A test prompt class."""
    def generate(self):
        yield "test"

@register_segment('test_print')
class Print(AbstractSegment):
    """A test print class."""
    def transform(self, input_iter):
        for item in input_iter:
            yield item
'''

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        test_file = tmpdir_path / "test_module.py"
        test_file.write_text(test_code)

        # Scan the file
        results = scan_file(test_file, tmpdir_path, "testpackage")

        # Verify that both the class-based source and segment were found
        assert len(results['sources']) == 1, f"Expected 1 source, found {len(results['sources'])}"
        assert len(results['segments']) == 1, f"Expected 1 segment, found {len(results['segments'])}"

        # Check the source details
        source_name, source_class, source_module = results['sources'][0]
        assert source_name == 'test_prompt'
        assert source_class == 'Prompt'
        assert source_module == 'testpackage.test_module'

        # Check the segment details
        segment_name, segment_class, segment_module = results['segments'][0]
        assert segment_name == 'test_print'
        assert segment_class == 'Print'
        assert segment_module == 'testpackage.test_module'


def test_decorator_finder_handles_both_functions_and_classes():
    """Test that DecoratorFinder can find decorators on both functions and classes in the same file."""

    test_code = '''
from talkpipe.chatterlang.registry import register_source, register_segment
from talkpipe.pipe.core import AbstractSource, AbstractSegment, source, segment

@register_source('class_source')
class ClassSource(AbstractSource):
    def generate(self):
        yield "class"

@register_source('func_source')
@source()
def func_source(data: str):
    yield data

@register_segment('class_segment')
class ClassSegment(AbstractSegment):
    def transform(self, input_iter):
        for item in input_iter:
            yield item

@register_segment('func_segment')
@segment()
def func_segment(items):
    for item in items:
        yield item
'''

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        test_file = tmpdir_path / "test_module.py"
        test_file.write_text(test_code)

        # Scan the file
        results = scan_file(test_file, tmpdir_path, "testpackage")

        # Should find 2 sources (1 class, 1 function) and 2 segments (1 class, 1 function)
        assert len(results['sources']) == 2, f"Expected 2 sources, found {len(results['sources'])}"
        assert len(results['segments']) == 2, f"Expected 2 segments, found {len(results['segments'])}"

        # Check that we have the right mix
        source_names = {name for name, _, _ in results['sources']}
        assert source_names == {'class_source', 'func_source'}

        segment_names = {name for name, _, _ in results['segments']}
        assert segment_names == {'class_segment', 'func_segment'}
