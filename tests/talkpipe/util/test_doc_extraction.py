import pytest
from unittest.mock import Mock
from talkpipe.util.doc_extraction import (
    ParamSpec, ComponentInfo, extract_function_info, extract_component_info,
    detect_component_type, extract_parameters_dict
)


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


class TestExtractFunctionInfo:
    """Test function information extraction."""
    
    def test_simple_function(self):
        """Test extracting info from a simple function."""
        def sample_func(param1: str, param2: int = 42):
            """Sample function docstring."""
            pass
        
        result = extract_function_info(sample_func)
        
        assert result['docstring'] == "Sample function docstring."
        assert len(result['parameters']) == 2
        assert result['parameters'][0].name == 'param1'
        assert result['parameters'][1].name == 'param2'
        assert result['parameters'][1].default == '42'
    
    def test_function_with_excluded_params(self):
        """Test that self, items, item parameters are excluded."""
        def sample_func(self, items, param1: str):
            """Sample function docstring."""
            pass
        
        result = extract_function_info(sample_func)
        
        assert len(result['parameters']) == 1
        assert result['parameters'][0].name == 'param1'


class TestDetectComponentType:
    """Test component type detection."""
    
    def test_source_type(self):
        """Test source type detection."""
        mock_class = type('MockSource', (), {})
        result = detect_component_type(mock_class, "Source")
        assert result == "Source"
    
    def test_regular_segment_type(self):
        """Test regular segment type detection."""
        mock_class = type('MockSegment', (), {})
        result = detect_component_type(mock_class, "Segment")
        assert result == "Segment"
    
    def test_field_segment_type_by_name(self):
        """Test field segment type detection by class name."""
        mock_class = type('MockFieldSegment', (), {})
        result = detect_component_type(mock_class, "Segment")
        assert result == "Field Segment"


class TestExtractComponentInfo:
    """Test comprehensive component information extraction."""
    
    def test_regular_class(self):
        """Test extracting info from a regular class."""
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
        assert result.component_type == "Source"
        assert result.module == "test.module"
        assert result.docstring == "Test class docstring."
        assert len(result.parameters) == 1
        assert result.parameters[0].name == "param1"
    
    def test_field_segment_with_original_func(self):
        """Test extracting info from a field segment with preserved original function."""
        def original_func(file_path: str):
            """Original function docstring."""
            pass
        
        class MockFieldSegment:
            """Generic field segment docstring."""
            __module__ = "test.module"
            __bases__ = (object,)
            _original_func = original_func
            
            def __init__(self):
                pass
        
        result = extract_component_info("testField", MockFieldSegment, "Field Segment")
        
        assert result is not None
        assert result.name == "Mock"  # FieldSegment suffix is cleaned off
        assert result.chatterlang_name == "testField"
        assert result.component_type == "Field Segment"
        assert result.docstring == "Original function docstring."
        # Field segments should include synthetic 'field' and 'set_as' parameters
        assert len(result.parameters) == 3
        assert [p.name for p in result.parameters] == ["field", "file_path", "set_as"]


class TestExtractParametersDict:
    """Test parameter extraction as dictionary."""
    
    def test_regular_class_parameters(self):
        """Test parameter extraction from regular class."""
        class TestClass:
            def __init__(self, param1: str, param2: int = 42):
                pass
        
        result = extract_parameters_dict(TestClass)
        
        assert "param1" in result
        assert "param2" in result
        assert result["param1"] == "param1: <class 'str'>"
        assert result["param2"] == "param2: <class 'int'> = 42"
    
    def test_field_segment_parameters(self):
        """Test parameter extraction from field segment with original function."""
        def original_func(file_path: str, recursive: bool = True):
            pass
        
        class MockFieldSegment:
            _original_func = original_func
        
        result = extract_parameters_dict(MockFieldSegment)
        
        assert "file_path" in result
        assert "recursive" in result
        assert result["file_path"] == "file_path: <class 'str'>"
        assert result["recursive"] == "recursive: <class 'bool'> = True"