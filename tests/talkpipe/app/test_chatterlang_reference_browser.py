import pytest
from unittest.mock import Mock, patch, MagicMock
from talkpipe.app.chatterlang_reference_browser import (
    TalkPipeDoc,
    TalkPipeBrowser,
    main
)


class TestTalkPipeDoc:
    """Test the TalkPipeDoc class."""
    
    def test_init(self):
        """Test TalkPipeDoc initialization."""
        doc = TalkPipeDoc(
            name="TestClass",
            chatterlang_name="testClass",
            doc_type="Segment",
            module="test.module",
            base_classes=["BaseClass"],
            docstring="Test docstring",
            parameters={"param1": "default1"}
        )
        
        assert doc.name == "TestClass"
        assert doc.chatterlang_name == "testClass"
        assert doc.doc_type == "Segment"
        assert doc.module == "test.module"
        assert doc.base_classes == ["BaseClass"]
        assert doc.docstring == "Test docstring"
        assert doc.parameters == {"param1": "default1"}


class TestTalkPipeBrowser:
    """Test the TalkPipeBrowser class."""
    
    @patch('talkpipe.app.chatterlang_reference_browser.load_plugins')
    @patch('talkpipe.app.chatterlang_reference_browser.input_registry')
    @patch('talkpipe.app.chatterlang_reference_browser.segment_registry')
    def test_init(self, mock_segment_registry, mock_input_registry, mock_load_plugins):
        """Test browser initialization with plugin introspection."""
        # Mock empty registries
        mock_input_registry.all.items.return_value = []
        mock_segment_registry.all.items.return_value = []
        
        browser = TalkPipeBrowser()
        
        # Verify plugins were loaded
        mock_load_plugins.assert_called_once()
        assert browser.components == {}
        assert browser.modules == {}
    
    @patch('talkpipe.app.chatterlang_reference_browser.load_plugins')
    @patch('talkpipe.app.chatterlang_reference_browser.input_registry')
    @patch('talkpipe.app.chatterlang_reference_browser.segment_registry')
    @patch('talkpipe.app.chatterlang_reference_browser.extract_component_info')
    def test_load_components_with_mock_data(self, mock_extract, mock_segment_registry, 
                                          mock_input_registry, mock_load_plugins):
        """Test loading components with mocked registry data."""
        # Create mock class
        mock_class = Mock()
        mock_class.__name__ = "TestClass"
        mock_class.__module__ = "test.module"
        
        # Mock registries with test data
        mock_input_registry.all.items.return_value = [("testSource", mock_class)]
        mock_segment_registry.all.items.return_value = [("testSegment", mock_class)]
        
        # Mock extract_component_info to return ComponentInfo objects
        mock_component_info = Mock()
        mock_component_info.name = "TestClass"
        mock_component_info.chatterlang_name = "testSource"
        mock_component_info.component_type = "Source"
        mock_component_info.module = "test.module"
        mock_component_info.base_classes = []
        mock_component_info.docstring = "Test docstring"
        mock_component_info.parameters = []
        
        mock_extract.return_value = mock_component_info
        
        browser = TalkPipeBrowser()
        
        # Check that components were loaded
        assert "testSource" in browser.components
        assert browser.components["testSource"].name == "TestClass"
        assert browser.components["testSource"].doc_type == "Source"
        assert "test.module" in browser.modules
    
    @patch('talkpipe.app.chatterlang_reference_browser.load_plugins')
    @patch('talkpipe.app.chatterlang_reference_browser.input_registry')
    @patch('talkpipe.app.chatterlang_reference_browser.segment_registry')
    @patch('builtins.input')
    def test_run_list_modules(self, mock_input, mock_segment_registry, 
                            mock_input_registry, mock_load_plugins):
        """Test the run method with list command."""
        # Setup empty registries
        mock_input_registry.all.items.return_value = []
        mock_segment_registry.all.items.return_value = []
        
        browser = TalkPipeBrowser()
        
        # Add test data directly
        test_doc = TalkPipeDoc("TestClass", "testComp", "Segment", "test.module", 
                              [], "Test docstring", {})
        browser.components["testComp"] = test_doc
        browser.modules["test.module"] = ["testComp"]
        
        # Simulate user input: list, then quit
        mock_input.side_effect = ['list', 'quit']
        
        with patch('builtins.print') as mock_print:
            browser.run()
            
            # Check that modules were listed
            print_calls = [call[0][0] for call in mock_print.call_args_list if call[0]]
            modules_listed = any("Available Modules" in call for call in print_calls)
            assert modules_listed
    
    @patch('talkpipe.app.chatterlang_reference_browser.load_plugins')
    @patch('talkpipe.app.chatterlang_reference_browser.input_registry')
    @patch('talkpipe.app.chatterlang_reference_browser.segment_registry')
    @patch('builtins.input')
    def test_run_show_component(self, mock_input, mock_segment_registry, 
                               mock_input_registry, mock_load_plugins):
        """Test the run method with show component command."""
        # Setup empty registries
        mock_input_registry.all.items.return_value = []
        mock_segment_registry.all.items.return_value = []
        
        browser = TalkPipeBrowser()
        
        # Add test component
        test_doc = TalkPipeDoc("TestClass", "testComp", "Segment", "test.module", 
                              [], "Test docstring", {"param1": "value1"})
        browser.components["testComp"] = test_doc
        
        # Simulate user input: show testComp, then quit
        mock_input.side_effect = ['show testComp', 'quit']
        
        with patch('builtins.print') as mock_print:
            browser.run()
            
            # Check that component details were shown
            print_calls = [call[0][0] for call in mock_print.call_args_list if call[0]]
            component_shown = any("testComp" in call for call in print_calls)
            assert component_shown
    
    @patch('talkpipe.app.chatterlang_reference_browser.load_plugins')
    @patch('talkpipe.app.chatterlang_reference_browser.input_registry')
    @patch('talkpipe.app.chatterlang_reference_browser.segment_registry')
    @patch('builtins.input')
    def test_run_search_components(self, mock_input, mock_segment_registry, 
                                  mock_input_registry, mock_load_plugins):
        """Test the run method with search command."""
        # Setup empty registries
        mock_input_registry.all.items.return_value = []
        mock_segment_registry.all.items.return_value = []
        
        browser = TalkPipeBrowser()
        
        # Add test component with searchable content
        test_doc = TalkPipeDoc("EmailClass", "emailComp", "Source", "email.module", 
                              [], "Handle email operations", {})
        browser.components["emailComp"] = test_doc
        
        # Simulate user input: search email, then quit
        mock_input.side_effect = ['search email', 'quit']
        
        with patch('builtins.print') as mock_print:
            browser.run()
            
            # Check that search results were shown
            print_calls = [call[0][0] for call in mock_print.call_args_list if call[0]]
            search_results_found = any("Search Results" in call for call in print_calls)
            assert search_results_found
    
    @patch('talkpipe.app.chatterlang_reference_browser.load_plugins')
    @patch('talkpipe.app.chatterlang_reference_browser.input_registry')
    @patch('talkpipe.app.chatterlang_reference_browser.segment_registry')
    @patch('builtins.input')
    def test_run_keyboard_interrupt(self, mock_input, mock_segment_registry, 
                                   mock_input_registry, mock_load_plugins):
        """Test handling of KeyboardInterrupt during run."""
        # Setup empty registries
        mock_input_registry.all.items.return_value = []
        mock_segment_registry.all.items.return_value = []
        
        browser = TalkPipeBrowser()
        
        # Simulate KeyboardInterrupt
        mock_input.side_effect = KeyboardInterrupt()
        
        with patch('builtins.print') as mock_print:
            browser.run()
            
            # Check that goodbye message was printed
            print_calls = [call[0][0] for call in mock_print.call_args_list if call[0]]
            goodbye_found = any("Goodbye" in call for call in print_calls)
            assert goodbye_found
    
    @patch('talkpipe.app.chatterlang_reference_browser.load_plugins')
    @patch('talkpipe.app.chatterlang_reference_browser.input_registry')
    @patch('talkpipe.app.chatterlang_reference_browser.segment_registry')
    def test_show_component_not_found(self, mock_segment_registry, 
                                     mock_input_registry, mock_load_plugins):
        """Test showing a component that doesn't exist."""
        # Setup empty registries
        mock_input_registry.all.items.return_value = []
        mock_segment_registry.all.items.return_value = []
        
        browser = TalkPipeBrowser()
        
        with patch('builtins.print') as mock_print:
            browser._show_component("nonexistent")
            
            print_calls = [call[0][0] for call in mock_print.call_args_list if call[0]]
            not_found = any("not found" in call for call in print_calls)
            assert not_found
    
    @patch('talkpipe.app.chatterlang_reference_browser.load_plugins')
    @patch('talkpipe.app.chatterlang_reference_browser.input_registry')
    @patch('talkpipe.app.chatterlang_reference_browser.segment_registry')
    def test_show_component_case_insensitive(self, mock_segment_registry, 
                                            mock_input_registry, mock_load_plugins):
        """Test showing a component with case-insensitive matching."""
        # Setup empty registries
        mock_input_registry.all.items.return_value = []
        mock_segment_registry.all.items.return_value = []
        
        browser = TalkPipeBrowser()
        
        # Add test component
        test_doc = TalkPipeDoc("ReadEmail", "readEmail", "Source", "email.module", 
                              [], "Read emails", {})
        browser.components["readEmail"] = test_doc
        
        with patch('builtins.print') as mock_print:
            browser._show_component("READEMAIL")  # uppercase
            
            print_calls = [call[0][0] for call in mock_print.call_args_list if call[0]]
            component_shown = any("readEmail" in call for call in print_calls)
            assert component_shown
    
    @patch('talkpipe.app.chatterlang_reference_browser.load_plugins')
    @patch('talkpipe.app.chatterlang_reference_browser.input_registry')
    @patch('talkpipe.app.chatterlang_reference_browser.segment_registry')
    def test_search_no_matches(self, mock_segment_registry, 
                              mock_input_registry, mock_load_plugins):
        """Test search with no matches."""
        # Setup empty registries
        mock_input_registry.all.items.return_value = []
        mock_segment_registry.all.items.return_value = []
        
        browser = TalkPipeBrowser()
        
        with patch('builtins.print') as mock_print:
            browser._search_components("nonexistent_term")
            
            print_calls = [call[0][0] for call in mock_print.call_args_list if call[0]]
            no_matches = any("No components found" in call for call in print_calls)
            assert no_matches


class TestMain:
    """Test the main function."""
    
    @patch('talkpipe.app.chatterlang_reference_browser.TalkPipeBrowser')
    @patch('argparse.ArgumentParser.parse_args')
    def test_main_default_mode(self, mock_args, mock_browser_class):
        """Test main function in default (introspection) mode."""
        # Mock arguments - no legacy flag
        mock_namespace = Mock()
        mock_namespace.legacy = False
        mock_args.return_value = mock_namespace
        
        # Mock browser instance
        mock_browser = Mock()
        mock_browser.components = {"test": Mock()}  # Non-empty to avoid exit
        mock_browser.modules = {"test.module": ["test"]}  # Proper dict structure
        mock_browser_class.return_value = mock_browser
        
        main()
        
        mock_browser_class.assert_called_once()
        mock_browser.run.assert_called_once()
    
    @patch('argparse.ArgumentParser.parse_args')
    def test_main_legacy_mode_not_supported(self, mock_args):
        """Test main function rejects legacy mode."""
        mock_namespace = Mock()
        mock_namespace.legacy = True
        mock_args.return_value = mock_namespace
        
        with pytest.raises(SystemExit):
            main()
    
    @patch('talkpipe.app.chatterlang_reference_browser.TalkPipeBrowser')
    @patch('argparse.ArgumentParser.parse_args')
    def test_main_no_components_found(self, mock_args, mock_browser_class):
        """Test main function when no components are found."""
        mock_namespace = Mock()
        mock_namespace.legacy = False
        mock_args.return_value = mock_namespace
        
        # Mock browser with no components
        mock_browser = Mock()
        mock_browser.components = {}
        mock_browser_class.return_value = mock_browser
        
        with pytest.raises(SystemExit):
            main()
    
    @patch('talkpipe.app.chatterlang_reference_browser.TalkPipeBrowser')
    @patch('argparse.ArgumentParser.parse_args')
    def test_main_initialization_error(self, mock_args, mock_browser_class):
        """Test main function handles initialization errors."""
        mock_namespace = Mock()
        mock_namespace.legacy = False
        mock_args.return_value = mock_namespace
        
        # Mock browser initialization error
        mock_browser_class.side_effect = Exception("Test error")
        
        with pytest.raises(SystemExit):
            main()