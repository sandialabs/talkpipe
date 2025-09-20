import pytest
import tempfile
import os
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from talkpipe.app.chatterlang_reference_generator import (
    AnalyzedItem,
    sanitize_id,
    analyze_registered_items,
    generate_html,
    generate_text,
    main,
    go
)
from talkpipe.util.doc_extraction import ParamSpec, extract_function_info


class TestParamSpec:
    """Test the ParamSpec dataclass."""
    
    def test_init_default_values(self):
        """Test ParamSpec with default values."""
        param = ParamSpec(name="test_param")
        assert param.name == "test_param"
        assert param.annotation == ""
        assert param.default == ""
    
    def test_init_with_values(self):
        """Test ParamSpec with all values provided."""
        param = ParamSpec(
            name="test_param",
            annotation="str",
            default='"default_value"'
        )
        assert param.name == "test_param"
        assert param.annotation == "str"
        assert param.default == '"default_value"'


class TestAnalyzedItem:
    """Test the AnalyzedItem dataclass."""
    
    def test_init_source(self):
        """Test AnalyzedItem for a source."""
        item = AnalyzedItem(
            type="Source",
            name="TestSource",
            docstring="Test docstring",
            parameters=[ParamSpec("param1")],
            chatterlang_name="testSource",
            decorator_type="source",
            is_source=True
        )
        
        assert item.type == "Source"
        assert item.name == "TestSource"
        assert item.decorator_type == "source"
        assert not item.is_segment
        assert item.is_source
        assert not item.is_field_segment
    
    def test_init_segment(self):
        """Test AnalyzedItem for a segment."""
        item = AnalyzedItem(
            type="Segment",
            name="test_segment",
            docstring="Test docstring",
            parameters=[],
            is_segment=True,
            decorator_type="segment"
        )
        
        assert item.type == "Segment"
        assert item.name == "test_segment"
        assert item.is_segment
        assert not item.is_source
        assert not item.is_field_segment


class TestUtilityFunctions:
    """Test utility functions."""
    
    def test_sanitize_id(self):
        """Test ID sanitization for HTML."""
        assert sanitize_id("test.package") == "test-package"
        assert sanitize_id("test/path") == "test-path"
        assert sanitize_id("test package") == "test-package"
    
    def test_extract_function_info(self):
        """Test extracting function information."""
        def sample_func(param1: str, param2: int = 42):
            """Sample function docstring."""
            pass
        
        result = extract_function_info(sample_func)
        
        assert result['docstring'] == "Sample function docstring."
        assert len(result['parameters']) == 2
        assert result['parameters'][0].name == 'param1'
        assert result['parameters'][0].annotation == "<class 'str'>"
        assert result['parameters'][1].name == 'param2'
        assert result['parameters'][1].default == '42'


class TestAnalyzeFunctions:
    """Test function and class analysis."""
    
    @patch('talkpipe.app.chatterlang_reference_generator.load_plugins')
    @patch('talkpipe.app.chatterlang_reference_generator.input_registry')
    @patch('talkpipe.app.chatterlang_reference_generator.segment_registry')
    def test_analyze_registered_items(self, mock_segment_registry, mock_input_registry, mock_load_plugins):
        """Test analyzing registered items."""
        # Mock a source class
        mock_source_class = type('MockSource', (), {
            '__module__': 'test.module',
            '__doc__': 'Mock source docstring',
            '__bases__': (object,),
            '__init__': lambda self: None
        })
        
        # Mock a segment class
        mock_segment_class = type('MockSegment', (), {
            '__module__': 'test.module',
            '__doc__': 'Mock segment docstring',
            '__bases__': (object,),
            '__init__': lambda self, param1: None
        })
        
        mock_input_registry.all.items.return_value = [('mockSource', mock_source_class)]
        mock_segment_registry.all.items.return_value = [('mockSegment', mock_segment_class)]
        
        result = analyze_registered_items()
        
        assert len(result) == 2
        
        # Check source
        source_item = next((item for item in result if item.type == 'Source'), None)
        assert source_item is not None
        assert source_item.chatterlang_name == 'mockSource'
        assert source_item.is_source
        
        # Check segment
        segment_item = next((item for item in result if item.type == 'Segment'), None)
        assert segment_item is not None
        assert segment_item.chatterlang_name == 'mockSegment'
        assert segment_item.is_segment
    
    def test_shared_extraction_integration(self):
        """Test that the shared extraction logic works with real components."""
        # This tests the integration with the shared doc_extraction module
        from talkpipe.util.doc_extraction import extract_component_info
        
        # Create a mock class similar to what we'd find in the registry
        class TestClass:
            """Test class docstring."""
            __module__ = 'test.module'
            __bases__ = (object,)
            def __init__(self, param1: str = "default"):
                pass
        
        result = extract_component_info("testClass", TestClass, "Source")
        
        assert result is not None
        assert result.name == "TestClass"
        assert result.chatterlang_name == "testClass"
        assert result.docstring == "Test class docstring."
        assert result.component_type == "Source"


class TestGeneration:
    """Test HTML and text generation."""
    
    @pytest.fixture
    def sample_items(self):
        """Sample analyzed items for testing generation."""
        return [
            AnalyzedItem(
                type="Source",
                name="TestSource",
                docstring="Test source docstring",
                parameters=[
                    ParamSpec("param1", "str", '"default"')
                ],
                chatterlang_name="testSource",
                decorator_type="source",
                is_source=True
            ),
            AnalyzedItem(
                type="Segment",
                name="TestSegment",
                docstring="Test segment docstring",
                parameters=[
                    ParamSpec("param1", "int", "42")
                ],
                chatterlang_name="testSegment",
                decorator_type="segment",
                is_segment=True
            )
        ]
    
    def test_generate_html(self, sample_items):
        """Test HTML generation."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
            temp_file = f.name
        
        try:
            generate_html(sample_items, temp_file)
            
            # Read the generated file
            with open(temp_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Check that HTML contains expected elements
            assert "<!DOCTYPE html>" in content
            assert "Table of Contents" in content
            assert "testSource" in content
            assert "testSegment" in content
            assert "Test source docstring" in content
            assert "Test segment docstring" in content
        finally:
            os.unlink(temp_file)
    
    def test_generate_text(self, sample_items):
        """Test text generation."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            temp_file = f.name
        
        try:
            generate_text(sample_items, temp_file)
            
            # Read the generated file
            with open(temp_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Check that text contains expected elements
            assert "Chatterlang Reference Documentation" in content
            assert "TYPE: Source" in content
            assert "TYPE: Segment" in content
            assert "Chatterlang Name: testSource" in content
            assert "Chatterlang Name: testSegment" in content
        finally:
            os.unlink(temp_file)


class TestMainFunctions:
    """Test main entry points."""
    
    @patch('talkpipe.app.chatterlang_reference_generator.analyze_registered_items')
    @patch('talkpipe.app.chatterlang_reference_generator.generate_html')
    @patch('talkpipe.app.chatterlang_reference_generator.generate_text')
    def test_main(self, mock_gen_text, mock_gen_html, mock_analyze):
        """Test main function."""
        # Mock analysis
        mock_analyze.return_value = []
        
        with patch('builtins.print'):
            main("output.html", "output.txt")
        
        mock_analyze.assert_called_once()
        mock_gen_html.assert_called_once_with([], "output.html")
        mock_gen_text.assert_called_once_with([], "output.txt")
    
    @patch('sys.argv', ['script.py'])
    @patch('talkpipe.app.chatterlang_reference_generator.main')
    def test_go_default_args(self, mock_main):
        """Test go function with default arguments."""
        with patch('builtins.print'):
            go()
        
        mock_main.assert_called_once_with(
            "./chatterlang_ref.html",
            "./chatterlang_ref.txt"
        )
    
    @patch('sys.argv', ['script.py', 'custom.html', 'custom.txt'])
    @patch('talkpipe.app.chatterlang_reference_generator.main')
    def test_go_custom_args(self, mock_main):
        """Test go function with custom arguments."""
        go()
        
        mock_main.assert_called_once_with(
            "custom.html",
            "custom.txt"
        )
    
    @patch('sys.argv', ['script.py', 'wrong', 'number', 'of', 'args'])
    def test_go_wrong_arg_count(self):
        """Test go function with wrong number of arguments."""
        with patch('builtins.print'):
            with pytest.raises(SystemExit):
                go()