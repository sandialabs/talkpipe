"""Tests for ChatterLang entry point configuration.

These tests verify that the package entry points are correctly configured.
They require the package to be installed (e.g., via 'pip install -e .') to run.
"""
import pytest
from talkpipe.chatterlang import compiler


class TestChatterLangEntryPoints:
    """Test that ChatterLang entry points are configured correctly."""

    def test_basic_cast_segment_loads(self, requires_package_installed):
        """Test that the cast segment can be loaded from entry points."""
        # This will fail if entry points have incorrect module paths
        script = 'INPUT FROM echo[data="1,2,3"] | cast[cast_type="int"] | print'
        pipeline = compiler.compile(script).as_function()
        result = pipeline()

        # Verify we got integers back
        assert result == [1, 2, 3]

    def test_llm_segments_load(self, requires_package_installed):
        """Test that LLM-related segments can be discovered (even if not executable)."""
        # We don't need to execute these, just verify they can be loaded from entry points
        from talkpipe.chatterlang import registry

        # Force lazy loading if enabled
        llm_segments = ['llmPrompt', 'llmScore', 'llmBinaryAnswer']

        for segment_name in llm_segments:
            # This will raise KeyError if the entry point can't be loaded
            # It should load successfully even if we can't execute it (e.g., no API keys)
            segment = registry.segment_registry.get(segment_name)
            assert segment is not None, f"Segment '{segment_name}' should be loadable"

    def test_multiple_segments_in_pipeline(self, requires_package_installed):
        """Test a pipeline with multiple segments to verify entry points work."""
        script = '''
        INPUT FROM echo[data="1,2,3"]
        | cast[cast_type="int"]
        | firstN[n=2]
        | print
        '''
        pipeline = compiler.compile(script).as_function()
        result = pipeline()

        # Verify the pipeline worked (cast to int, then take first 2)
        assert len(result) == 2
        assert result == [1, 2]
