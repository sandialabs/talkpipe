import pytest
import tempfile
import os
from pathlib import Path
from unittest.mock import Mock, patch, mock_open
from talkpipe.app.chatterlang_reference_browser import (
    TalkPipeDoc,
    TalkPipeBrowser,
    main
)


@pytest.fixture
def sample_doc_content():
    """Sample documentation content for testing."""
    return """Class and Function Documentation (Text Version)
================================================

PACKAGE: talkpipe.data.email
----------------------------

Segment Class: ReadEmail
  Chatterlang Name: readEmail
  Base Classes: EmailSource
  Docstring:
    Read emails from an email source.
    Supports IMAP and POP3 protocols.
  Parameters:
    host: str = "localhost"
    port: int = 993
    username: str

Source Class: EmailConnection
  Chatterlang Name: emailConn
  Docstring:
    Connect to an email server.
  Parameters:
    ssl: bool = True

PACKAGE: talkpipe.operations.transforms
--------------------------------------

Segment Function: transform_text
  Chatterlang Name: transformText
  Docstring:
    Transform text using various operations.
  Parameters:
    operation: str = "uppercase"
    preserve_whitespace: bool = True
"""


@pytest.fixture
def temp_doc_file(sample_doc_content):
    """Create a temporary documentation file."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write(sample_doc_content)
        temp_path = f.name
    
    yield temp_path
    
    # Cleanup - check if file exists before trying to delete
    if os.path.exists(temp_path):
        os.unlink(temp_path)


class TestTalkPipeDoc:
    """Test the TalkPipeDoc class."""
    
    def test_init(self):
        """Test TalkPipeDoc initialization."""
        doc = TalkPipeDoc(
            name="TestClass",
            chatterlang_name="testClass",
            doc_type="Segment Class",
            package="test.package",
            base_classes=["BaseClass"],
            docstring="Test docstring",
            parameters={"param1": "default1"}
        )
        
        assert doc.name == "TestClass"
        assert doc.chatterlang_name == "testClass"
        assert doc.doc_type == "Segment Class"
        assert doc.package == "test.package"
        assert doc.base_classes == ["BaseClass"]
        assert doc.docstring == "Test docstring"
        assert doc.parameters == {"param1": "default1"}


class TestTalkPipeBrowser:
    """Test the TalkPipeBrowser class."""
    
    def test_init_with_existing_file(self, temp_doc_file):
        """Test browser initialization with existing documentation file."""
        doc_dir = Path(temp_doc_file).parent
        # Rename to expected filename
        expected_file = doc_dir / "talkpipe_ref.txt"
        os.rename(temp_doc_file, expected_file)
        
        try:
            browser = TalkPipeBrowser(doc_dir)
            
            assert len(browser.components) > 0
            assert len(browser.packages) > 0
            assert "talkpipe.data.email" in browser.packages
            assert "talkpipe.operations.transforms" in browser.packages
        finally:
            if expected_file.exists():
                os.unlink(expected_file)
    
    def test_init_with_missing_file(self):
        """Test browser initialization with missing documentation file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            with pytest.raises(SystemExit):
                TalkPipeBrowser(temp_dir)
    
    def test_parse_component_segment_class(self):
        """Test parsing a segment class component."""
        browser = TalkPipeBrowser.__new__(TalkPipeBrowser)  # Create without calling __init__
        browser.components = {}
        browser.packages = {}
        
        component_text = """Segment Class: ReadEmail
  Chatterlang Name: readEmail
  Base Classes: EmailSource
  Docstring:
    Read emails from an email source.
    Supports IMAP and POP3 protocols.
  Parameters:
    host: str = "localhost"
    port: int = 993
    username: str"""
        
        component = browser._parse_component("test.package", component_text)
        
        assert component is not None
        assert component.name == "ReadEmail"
        assert component.chatterlang_name == "readEmail"
        assert component.doc_type == "Segment Class"
        assert component.package == "test.package"
        assert component.base_classes == ["EmailSource"]
        assert "Read emails from an email source." in component.docstring
        assert "host" in component.parameters
        assert component.parameters["host"] == '"localhost"'
    
    def test_parse_component_segment_function(self):
        """Test parsing a segment function component."""
        browser = TalkPipeBrowser.__new__(TalkPipeBrowser)
        browser.components = {}
        browser.packages = {}
        
        component_text = """Segment Function: transform_text
  Chatterlang Name: transformText
  Docstring:
    Transform text using various operations.
  Parameters:
    operation: str = "uppercase"
    preserve_whitespace: bool = True"""
        
        component = browser._parse_component("test.package", component_text)
        
        assert component is not None
        assert component.name == "transform_text"
        assert component.chatterlang_name == "transformText"
        assert component.doc_type == "Segment Function"
        assert "Transform text using various operations." in component.docstring
        assert "operation" in component.parameters
    
    def test_parse_component_invalid_header(self):
        """Test parsing component with invalid header."""
        browser = TalkPipeBrowser.__new__(TalkPipeBrowser)
        browser.components = {}
        browser.packages = {}
        
        component_text = """Invalid Header: SomeClass
  Chatterlang Name: someClass"""
        
        component = browser._parse_component("test.package", component_text)
        assert component is None
    
    @patch('builtins.input')
    def test_run_list_packages(self, mock_input, temp_doc_file):
        """Test the run method with list packages command."""
        doc_dir = Path(temp_doc_file).parent
        expected_file = doc_dir / "talkpipe_ref.txt"
        os.rename(temp_doc_file, expected_file)
        
        try:
            browser = TalkPipeBrowser(doc_dir)
            
            # Simulate user input: list, then quit
            mock_input.side_effect = ['list', 'quit']
            
            with patch('builtins.print') as mock_print:
                browser.run()
                
                # Check that packages were listed
                print_calls = [call[0][0] for call in mock_print.call_args_list if call[0]]
                package_list_found = any("Available Packages" in call for call in print_calls)
                assert package_list_found
        finally:
            if expected_file.exists():
                os.unlink(expected_file)
    
    @patch('builtins.input')
    def test_run_show_component(self, mock_input, temp_doc_file):
        """Test the run method with show component command."""
        doc_dir = Path(temp_doc_file).parent
        expected_file = doc_dir / "talkpipe_ref.txt"
        os.rename(temp_doc_file, expected_file)
        
        try:
            browser = TalkPipeBrowser(doc_dir)
            
            # Simulate user input: show readEmail, then quit
            mock_input.side_effect = ['show readEmail', 'quit']
            
            with patch('builtins.print') as mock_print:
                browser.run()
                
                # Check that component details were shown
                print_calls = [call[0][0] for call in mock_print.call_args_list if call[0]]
                component_shown = any("readEmail" in call for call in print_calls)
                assert component_shown
        finally:
            if expected_file.exists():
                os.unlink(expected_file)
    
    @patch('builtins.input')
    def test_run_search_components(self, mock_input, temp_doc_file):
        """Test the run method with search command."""
        doc_dir = Path(temp_doc_file).parent
        expected_file = doc_dir / "talkpipe_ref.txt"
        os.rename(temp_doc_file, expected_file)
        
        try:
            browser = TalkPipeBrowser(doc_dir)
            
            # Simulate user input: search email, then quit
            mock_input.side_effect = ['search email', 'quit']
            
            with patch('builtins.print') as mock_print:
                browser.run()
                
                # Check that search results were shown
                print_calls = [call[0][0] for call in mock_print.call_args_list if call[0]]
                search_results_found = any("Search Results" in call for call in print_calls)
                assert search_results_found
        finally:
            if expected_file.exists():
                os.unlink(expected_file)
    
    @patch('builtins.input')
    def test_run_keyboard_interrupt(self, mock_input, temp_doc_file):
        """Test handling of KeyboardInterrupt during run."""
        doc_dir = Path(temp_doc_file).parent
        expected_file = doc_dir / "talkpipe_ref.txt"
        os.rename(temp_doc_file, expected_file)
        
        try:
            browser = TalkPipeBrowser(doc_dir)
            
            # Simulate KeyboardInterrupt
            mock_input.side_effect = KeyboardInterrupt()
            
            with patch('builtins.print') as mock_print:
                browser.run()
                
                # Check that goodbye message was printed
                print_calls = [call[0][0] for call in mock_print.call_args_list if call[0]]
                goodbye_found = any("Goodbye" in call for call in print_calls)
                assert goodbye_found
        finally:
            if expected_file.exists():
                os.unlink(expected_file)
    
    def test_show_component_not_found(self, temp_doc_file):
        """Test showing a component that doesn't exist."""
        doc_dir = Path(temp_doc_file).parent
        expected_file = doc_dir / "talkpipe_ref.txt"
        os.rename(temp_doc_file, expected_file)
        
        try:
            browser = TalkPipeBrowser(doc_dir)
            
            with patch('builtins.print') as mock_print:
                browser._show_component("nonexistent")
                
                print_calls = [call[0][0] for call in mock_print.call_args_list if call[0]]
                not_found = any("not found" in call for call in print_calls)
                assert not_found
        finally:
            if expected_file.exists():
                os.unlink(expected_file)
    
    def test_show_component_case_insensitive(self, temp_doc_file):
        """Test showing a component with case-insensitive matching."""
        doc_dir = Path(temp_doc_file).parent
        expected_file = doc_dir / "talkpipe_ref.txt"
        os.rename(temp_doc_file, expected_file)
        
        try:
            browser = TalkPipeBrowser(doc_dir)
            
            with patch('builtins.print') as mock_print:
                browser._show_component("READEMAIL")  # uppercase
                
                print_calls = [call[0][0] for call in mock_print.call_args_list if call[0]]
                component_shown = any("readEmail" in call for call in print_calls)
                assert component_shown
        finally:
            if expected_file.exists():
                os.unlink(expected_file)
    
    def test_search_no_matches(self, temp_doc_file):
        """Test search with no matches."""
        doc_dir = Path(temp_doc_file).parent
        expected_file = doc_dir / "talkpipe_ref.txt"
        os.rename(temp_doc_file, expected_file)
        
        try:
            browser = TalkPipeBrowser(doc_dir)
            
            with patch('builtins.print') as mock_print:
                browser._search_components("nonexistent_term")
                
                print_calls = [call[0][0] for call in mock_print.call_args_list if call[0]]
                no_matches = any("No components found" in call for call in print_calls)
                assert no_matches
        finally:
            if expected_file.exists():
                os.unlink(expected_file)


class TestMain:
    """Test the main function."""
    
    @patch('talkpipe.app.chatterlang_reference_browser.TalkPipeBrowser')
    @patch('argparse.ArgumentParser.parse_args')
    def test_main_with_doc_path(self, mock_args, mock_browser_class):
        """Test main function with provided doc path."""
        # Mock arguments
        mock_namespace = Mock()
        mock_namespace.doc_path = "/test/path"
        mock_args.return_value = mock_namespace
        
        # Mock browser instance
        mock_browser = Mock()
        mock_browser_class.return_value = mock_browser
        
        with patch('os.path.exists', return_value=True):
            main()
            
            mock_browser_class.assert_called_once_with("/test/path")
            mock_browser.run.assert_called_once()
    
    @patch('talkpipe.app.chatterlang_reference_browser.TalkPipeBrowser')
    @patch('argparse.ArgumentParser.parse_args')
    def test_main_with_invalid_path(self, mock_args, mock_browser_class):
        """Test main function with invalid doc path."""
        mock_namespace = Mock()
        mock_namespace.doc_path = "/invalid/path"
        mock_args.return_value = mock_namespace
        
        with patch('os.path.exists', return_value=False):
            with pytest.raises(SystemExit):
                main()
    
    @patch('talkpipe.app.chatterlang_reference_browser.TalkPipeBrowser')
    @patch('argparse.ArgumentParser.parse_args')
    @patch('subprocess.run')
    def test_main_auto_generate_docs(self, mock_subprocess, mock_args, mock_browser_class):
        """Test main function auto-generating documentation."""
        mock_namespace = Mock()
        mock_namespace.doc_path = None
        mock_args.return_value = mock_namespace
        
        mock_browser = Mock()
        mock_browser_class.return_value = mock_browser
        
        with patch('os.getcwd', return_value='/test/cwd'), \
             patch('pathlib.Path.exists') as mock_exists:
            
            # First call (talkpipe_ref.txt) returns False, second call (after generation) returns True
            mock_exists.side_effect = [False, False, True]
            
            # Mock successful subprocess run
            mock_subprocess.return_value = Mock()
            
            with patch('builtins.print'):
                main()
            
            # Verify subprocess was called to generate docs
            mock_subprocess.assert_called_once_with(
                ['chatterlang_reference_generator'],
                capture_output=True,
                text=True,
                check=True
            )
            
            # Verify browser was created and run
            mock_browser_class.assert_called_once()
            mock_browser.run.assert_called_once()