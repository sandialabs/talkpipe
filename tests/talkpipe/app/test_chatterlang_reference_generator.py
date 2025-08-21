import pytest
import ast
import tempfile
import os
from pathlib import Path
from unittest.mock import Mock, patch
from talkpipe.app.chatterlang_reference_generator import (
    ParamSpec,
    AnalyzedItem,
    _extract_chatterlang_name,
    build_param_specs,
    sanitize_id,
    analyze_function,
    analyze_class,
    compute_package_name,
    find_python_files,
    analyze_file,
    generate_html,
    generate_text,
    main,
    go,
    safe_unparse
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


class TestAnalyzedItem:
    """Test the AnalyzedItem dataclass."""
    
    def test_init_class(self):
        """Test AnalyzedItem for a class."""
        item = AnalyzedItem(
            type="Class",
            name="TestClass",
            docstring="Test docstring",
            parameters=[ParamSpec("param1")],
            package_name="test.package",
            decorator_type="segment"
        )
        
        assert item.type == "Class"
        assert item.name == "TestClass"
        assert item.decorator_type == "segment"
        assert not item.is_segment
        assert not item.is_source
        assert not item.is_field_segment
    
    def test_init_function(self):
        """Test AnalyzedItem for a function."""
        item = AnalyzedItem(
            type="Function",
            name="test_function",
            docstring="Test docstring",
            parameters=[],
            is_segment=True
        )
        
        assert item.type == "Function"
        assert item.name == "test_function"
        assert item.is_segment
        assert not item.is_source
        assert not item.is_field_segment


class TestUtilityFunctions:
    """Test utility functions."""
    
    def test_extract_chatterlang_name_positional(self):
        """Test extracting chatterlang name from positional argument."""
        # Create AST for @register_segment("test_name")
        call_node = ast.Call(
            func=ast.Name(id='register_segment'),
            args=[ast.Constant(value='test_name')],
            keywords=[]
        )
        
        result = _extract_chatterlang_name(call_node)
        assert result == 'test_name'
    
    def test_extract_chatterlang_name_keyword(self):
        """Test extracting chatterlang name from keyword argument."""
        # Create AST for @register_segment(name="test_name")
        call_node = ast.Call(
            func=ast.Name(id='register_segment'),
            args=[],
            keywords=[ast.keyword(arg='name', value=ast.Constant(value='test_name'))]
        )
        
        result = _extract_chatterlang_name(call_node)
        assert result == 'test_name'
    
    def test_extract_chatterlang_name_none(self):
        """Test extracting chatterlang name when none exists."""
        call_node = ast.Call(
            func=ast.Name(id='register_segment'),
            args=[],
            keywords=[]
        )
        
        result = _extract_chatterlang_name(call_node)
        assert result is None
    
    def test_build_param_specs_no_defaults(self):
        """Test building parameter specs without defaults."""
        # Create AST args for function(param1: str, param2: int)
        args = [
            ast.arg(arg='param1', annotation=ast.Name(id='str')),
            ast.arg(arg='param2', annotation=ast.Name(id='int'))
        ]
        defaults = []
        
        result = build_param_specs(args, defaults)
        
        assert len(result) == 2
        assert result[0].name == 'param1'
        assert result[1].name == 'param2'
        assert result[0].default == ""
        assert result[1].default == ""
    
    def test_build_param_specs_with_defaults(self):
        """Test building parameter specs with defaults."""
        # Create AST args for function(param1: str, param2: int = 42)
        args = [
            ast.arg(arg='param1', annotation=ast.Name(id='str')),
            ast.arg(arg='param2', annotation=ast.Name(id='int'))
        ]
        defaults = [ast.Constant(value=42)]
        
        result = build_param_specs(args, defaults)
        
        assert len(result) == 2
        assert result[0].name == 'param1'
        assert result[1].name == 'param2'
        assert result[0].default == ""
        # Default value depends on Python version and AST unparsing
        assert result[1].default != ""
    
    def test_sanitize_id(self):
        """Test ID sanitization for HTML."""
        assert sanitize_id("test.package") == "test-package"
        assert sanitize_id("test/path") == "test-path"
        assert sanitize_id("test package") == "test-package"
    
    def test_safe_unparse(self):
        """Test safe AST unparsing."""
        node = ast.Name(id='test_name')
        result = safe_unparse(node)
        
        # Result depends on Python version
        assert result != ""
    
    def test_safe_unparse_none(self):
        """Test safe AST unparsing with None."""
        result = safe_unparse(None)
        assert result == ""


class TestAnalyzeFunctions:
    """Test function and class analysis."""
    
    def test_analyze_function_segment(self):
        """Test analyzing a segment function."""
        # Create AST for @register_segment("test_segment") function
        func_node = ast.FunctionDef(
            name='test_func',
            args=ast.arguments(
                args=[ast.arg(arg='items', annotation=None)],
                defaults=[],
                vararg=None,
                kwonlyargs=[],
                kw_defaults=[],
                kwarg=None
            ),
            body=[ast.Pass()],
            decorator_list=[
                ast.Call(
                    func=ast.Name(id='register_segment'),
                    args=[ast.Constant(value='test_segment')],
                    keywords=[]
                )
            ]
        )
        
        result = analyze_function(func_node, "test.py", "test.package")
        
        assert result is not None
        assert result.name == 'test_func'
        assert result.chatterlang_name == 'test_segment'
        assert result.is_segment
        assert not result.is_source
        assert not result.is_field_segment
    
    def test_analyze_function_source(self):
        """Test analyzing a source function."""
        func_node = ast.FunctionDef(
            name='test_source',
            args=ast.arguments(
                args=[],
                defaults=[],
                vararg=None,
                kwonlyargs=[],
                kw_defaults=[],
                kwarg=None
            ),
            body=[ast.Pass()],
            decorator_list=[
                ast.Name(id='source')
            ]
        )
        
        result = analyze_function(func_node, "test.py", "test.package")
        
        assert result is not None
        assert result.name == 'test_source'
        assert not result.is_segment
        assert result.is_source
        assert not result.is_field_segment
    
    def test_analyze_function_field_segment(self):
        """Test analyzing a field_segment function."""
        func_node = ast.FunctionDef(
            name='test_field_segment',
            args=ast.arguments(
                args=[ast.arg(arg='item', annotation=None)],
                defaults=[],
                vararg=None,
                kwonlyargs=[],
                kw_defaults=[],
                kwarg=None
            ),
            body=[ast.Pass()],
            decorator_list=[
                ast.Name(id='field_segment')
            ]
        )
        
        result = analyze_function(func_node, "test.py", "test.package")
        
        assert result is not None
        assert result.name == 'test_field_segment'
        assert not result.is_segment
        assert not result.is_source
        assert result.is_field_segment
    
    def test_analyze_function_no_decorators(self):
        """Test analyzing a function with no relevant decorators."""
        func_node = ast.FunctionDef(
            name='regular_func',
            args=ast.arguments(
                args=[],
                defaults=[],
                vararg=None,
                kwonlyargs=[],
                kw_defaults=[],
                kwarg=None
            ),
            body=[ast.Pass()],
            decorator_list=[]
        )
        
        result = analyze_function(func_node, "test.py", "test.package")
        assert result is None
    
    def test_analyze_class_segment(self):
        """Test analyzing a segment class."""
        class_node = ast.ClassDef(
            name='TestSegment',
            bases=[ast.Name(id='BaseClass')],
            keywords=[],
            body=[
                ast.FunctionDef(
                    name='__init__',
                    args=ast.arguments(
                        args=[
                            ast.arg(arg='self', annotation=None),
                            ast.arg(arg='param1', annotation=None)
                        ],
                        defaults=[],
                        vararg=None,
                        kwonlyargs=[],
                        kw_defaults=[],
                        kwarg=None
                    ),
                    body=[ast.Pass()],
                    decorator_list=[]
                )
            ],
            decorator_list=[
                ast.Call(
                    func=ast.Name(id='register_segment'),
                    args=[ast.Constant(value='testSegment')],
                    keywords=[]
                )
            ]
        )
        
        result = analyze_class(class_node, "test.py", "test.package")
        
        assert result is not None
        assert result.name == 'TestSegment'
        assert result.chatterlang_name == 'testSegment'
        assert result.decorator_type == 'segment'
        assert result.base_classes == ['BaseClass']
        assert len(result.parameters) == 2  # self + param1
    
    def test_analyze_class_no_decorators(self):
        """Test analyzing a class with no relevant decorators."""
        class_node = ast.ClassDef(
            name='RegularClass',
            bases=[],
            keywords=[],
            body=[ast.Pass()],
            decorator_list=[]
        )
        
        result = analyze_class(class_node, "test.py", "test.package")
        assert result is None


class TestFileOperations:
    """Test file-related operations."""
    
    def test_compute_package_name(self):
        """Test computing package name from file path."""
        # Test Unix-like paths
        root_dir = "/projects/myapp"
        file_path = "/projects/myapp/mypkg/subpkg/module.py"
        expected = "mypkg.subpkg.module"
        
        result = compute_package_name(file_path, root_dir)
        assert result == expected
    
    def test_compute_package_name_windows(self):
        """Test computing package name from Windows file path."""
        # Mock os.path.relpath and os.path.splitext for Windows behavior
        with patch('os.path.relpath') as mock_relpath, \
             patch('os.path.splitext') as mock_splitext, \
             patch('os.path.sep', '\\'):
            
            mock_relpath.return_value = "mypkg\\subpkg\\module.py"
            mock_splitext.return_value = ("mypkg\\subpkg\\module", ".py")
            
            root_dir = "C:\\projects\\myapp"
            file_path = "C:\\projects\\myapp\\mypkg\\subpkg\\module.py"
            expected = "mypkg.subpkg.module"
            
            result = compute_package_name(file_path, root_dir)
            assert result == expected
    
    def test_find_python_files(self):
        """Test finding Python files in directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create test files
            py_file1 = Path(temp_dir) / "test1.py"
            py_file2 = Path(temp_dir) / "subdir" / "test2.py"
            txt_file = Path(temp_dir) / "readme.txt"
            
            py_file1.touch()
            py_file2.parent.mkdir()
            py_file2.touch()
            txt_file.touch()
            
            result = find_python_files(temp_dir)
            
            # Should find 2 Python files, not the txt file
            assert len(result) == 2
            assert any("test1.py" in path for path in result)
            assert any("test2.py" in path for path in result)
            assert not any("readme.txt" in path for path in result)
    
    def test_analyze_file(self):
        """Test analyzing a Python file."""
        python_code = '''
"""Module docstring."""

from talkpipe.pipe import core
from talkpipe.chatterlang import registry

@registry.register_segment("testSegment")
@core.segment()
def test_function(items):
    """Test function docstring."""
    return items

@core.source()
def test_source():
    """Test source docstring."""
    yield 1
'''
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(python_code)
            temp_file = f.name
        
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                result = analyze_file(temp_file, temp_dir)
                
                # Should find 2 items: segment and source
                assert len(result) == 2
                
                segment_item = next((item for item in result if item.is_segment), None)
                source_item = next((item for item in result if item.is_source), None)
                
                assert segment_item is not None
                assert segment_item.chatterlang_name == "testSegment"
                
                assert source_item is not None
                assert source_item.name == "test_source"
        finally:
            os.unlink(temp_file)


class TestGeneration:
    """Test HTML and text generation."""
    
    @pytest.fixture
    def sample_items(self):
        """Sample analyzed items for testing generation."""
        return [
            AnalyzedItem(
                type="Class",
                name="TestClass",
                docstring="Test class docstring",
                parameters=[
                    ParamSpec("self"),
                    ParamSpec("param1", "str", '"default"')
                ],
                package_name="test.package",
                chatterlang_name="testClass",
                decorator_type="segment"
            ),
            AnalyzedItem(
                type="Function",
                name="test_function",
                docstring="Test function docstring",
                parameters=[
                    ParamSpec("items"),
                    ParamSpec("param1", "int", "42")
                ],
                package_name="test.package",
                is_segment=True,
                chatterlang_name="testFunction"
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
            assert "testClass" in content
            assert "testFunction" in content
            assert "Segment Class" in content
            assert "Segment Function" in content
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
            assert "Class and Function Documentation" in content
            assert "PACKAGE: test.package" in content
            assert "Segment Class: TestClass" in content
            assert "Segment Function: test_function" in content
            assert "Chatterlang Name: testClass" in content
        finally:
            os.unlink(temp_file)


class TestMainFunctions:
    """Test main entry points."""
    
    @patch('talkpipe.app.chatterlang_reference_generator.find_python_files')
    @patch('talkpipe.app.chatterlang_reference_generator.analyze_file')
    @patch('talkpipe.app.chatterlang_reference_generator.generate_html')
    @patch('talkpipe.app.chatterlang_reference_generator.generate_text')
    def test_main(self, mock_gen_text, mock_gen_html, mock_analyze, mock_find):
        """Test main function."""
        # Mock file finding and analysis
        mock_find.return_value = ["test.py"]
        mock_analyze.return_value = []
        
        with patch('builtins.print'):
            main("/test/root", "output.html", "output.txt")
        
        mock_find.assert_called_once_with("/test/root")
        mock_analyze.assert_called_once_with("test.py", "/test/root")
        mock_gen_html.assert_called_once_with([], "output.html")
        mock_gen_text.assert_called_once_with([], "output.txt")
    
    @patch('sys.argv', ['script.py'])
    @patch('talkpipe.app.chatterlang_reference_generator.main')
    @patch('importlib.util.find_spec')
    def test_go_default_args(self, mock_find_spec, mock_main):
        """Test go function with default arguments."""
        # Mock finding the talkpipe package
        mock_spec = Mock()
        mock_spec.submodule_search_locations = ["/path/to/talkpipe"]
        mock_find_spec.return_value = mock_spec
        
        with patch('builtins.print'):
            go()
        
        mock_main.assert_called_once_with(
            "/path/to/talkpipe",
            "./talkpipe_ref.html",
            "./talkpipe_ref.txt"
        )
    
    @patch('sys.argv', ['script.py', 'custom_package', 'custom.html', 'custom.txt'])
    @patch('talkpipe.app.chatterlang_reference_generator.main')
    @patch('importlib.util.find_spec')
    def test_go_custom_args(self, mock_find_spec, mock_main):
        """Test go function with custom arguments."""
        mock_spec = Mock()
        mock_spec.submodule_search_locations = ["/path/to/custom"]
        mock_find_spec.return_value = mock_spec
        
        go()
        
        mock_main.assert_called_once_with(
            "/path/to/custom",
            "custom.html",
            "custom.txt"
        )
    
    @patch('sys.argv', ['script.py', 'invalid_package'])
    @patch('importlib.util.find_spec')
    def test_go_invalid_package(self, mock_find_spec):
        """Test go function with invalid package."""
        mock_find_spec.return_value = None
        
        with patch('os.path.isdir', return_value=False):
            with pytest.raises(SystemExit):
                go()
    
    @patch('sys.argv', ['script.py', 'wrong', 'number'])
    def test_go_wrong_arg_count(self):
        """Test go function with wrong number of arguments."""
        with patch('builtins.print'):
            with pytest.raises(SystemExit):
                go()