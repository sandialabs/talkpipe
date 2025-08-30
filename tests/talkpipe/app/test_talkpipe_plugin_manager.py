import pytest
from unittest.mock import Mock, patch, call
from io import StringIO
import sys

from talkpipe.app.talkpipe_plugin_manager import main


class TestTalkpipePluginManager:
    """Test cases for the talkpipe_plugin_manager main function."""
    
    @patch('talkpipe.app.talkpipe_plugin_manager.list_loaded_plugins')
    @patch('talkpipe.app.talkpipe_plugin_manager.list_failed_plugins')
    @patch('sys.stdout', new_callable=StringIO)
    @patch('sys.argv', ['talkpipe_plugin_manager', '--list'])
    def test_list_plugins_success_only(self, mock_stdout, mock_list_failed, mock_list_loaded):
        """Test listing plugins when all plugins loaded successfully."""
        mock_list_loaded.return_value = ['plugin1', 'plugin2', 'plugin3']
        mock_list_failed.return_value = []
        
        main()
        
        output = mock_stdout.getvalue()
        assert "=== TalkPipe Plugins ===" in output
        assert "Loaded plugins (3):" in output
        assert "✓ plugin1" in output
        assert "✓ plugin2" in output
        assert "✓ plugin3" in output
        assert "Failed plugins" not in output
    
    @patch('talkpipe.app.talkpipe_plugin_manager.list_loaded_plugins')
    @patch('talkpipe.app.talkpipe_plugin_manager.list_failed_plugins')
    @patch('sys.stdout', new_callable=StringIO)
    @patch('sys.argv', ['talkpipe_plugin_manager', '--list'])
    def test_list_plugins_with_failures(self, mock_stdout, mock_list_failed, mock_list_loaded):
        """Test listing plugins when some plugins failed to load."""
        mock_list_loaded.return_value = ['plugin1', 'plugin2']
        mock_list_failed.return_value = ['bad_plugin1', 'bad_plugin2']
        
        main()
        
        output = mock_stdout.getvalue()
        assert "=== TalkPipe Plugins ===" in output
        assert "Loaded plugins (2):" in output
        assert "✓ plugin1" in output
        assert "✓ plugin2" in output
        assert "Failed plugins (2):" in output
        assert "✗ bad_plugin1" in output
        assert "✗ bad_plugin2" in output
    
    @patch('talkpipe.app.talkpipe_plugin_manager.list_loaded_plugins')
    @patch('talkpipe.app.talkpipe_plugin_manager.list_failed_plugins')
    @patch('sys.stdout', new_callable=StringIO)
    @patch('sys.argv', ['talkpipe_plugin_manager', '--list'])
    def test_list_plugins_no_plugins(self, mock_stdout, mock_list_failed, mock_list_loaded):
        """Test listing plugins when no plugins are available."""
        mock_list_loaded.return_value = []
        mock_list_failed.return_value = []
        
        main()
        
        output = mock_stdout.getvalue()
        assert "=== TalkPipe Plugins ===" in output
        assert "Loaded plugins (0):" in output
        assert "Failed plugins" not in output
    
    @patch('talkpipe.app.talkpipe_plugin_manager.get_plugin_loader')
    @patch('sys.stdout', new_callable=StringIO)
    @patch('sys.argv', ['talkpipe_plugin_manager', '--reload', 'test_plugin'])
    def test_reload_plugin_success(self, mock_stdout, mock_get_plugin_loader):
        """Test successful plugin reload."""
        mock_loader = Mock()
        mock_loader.reload_plugin.return_value = True
        mock_get_plugin_loader.return_value = mock_loader
        
        main()
        
        mock_loader.reload_plugin.assert_called_once_with('test_plugin')
        output = mock_stdout.getvalue()
        assert "Successfully reloaded plugin: test_plugin" in output
    
    @patch('talkpipe.app.talkpipe_plugin_manager.get_plugin_loader')
    @patch('sys.stdout', new_callable=StringIO)
    @patch('sys.argv', ['talkpipe_plugin_manager', '--reload', 'test_plugin'])
    def test_reload_plugin_failure(self, mock_stdout, mock_get_plugin_loader):
        """Test failed plugin reload."""
        mock_loader = Mock()
        mock_loader.reload_plugin.return_value = False
        mock_get_plugin_loader.return_value = mock_loader
        
        main()
        
        mock_loader.reload_plugin.assert_called_once_with('test_plugin')
        output = mock_stdout.getvalue()
        assert "Failed to reload plugin: test_plugin" in output
    
    @patch('talkpipe.app.talkpipe_plugin_manager.list_loaded_plugins')
    @patch('talkpipe.app.talkpipe_plugin_manager.list_failed_plugins')
    @patch('talkpipe.app.talkpipe_plugin_manager.get_plugin_loader')
    @patch('sys.stdout', new_callable=StringIO)
    @patch('sys.argv', ['talkpipe_plugin_manager', '--list', '--reload', 'test_plugin'])
    def test_list_and_reload_combined(self, mock_stdout, mock_get_plugin_loader, 
                                    mock_list_failed, mock_list_loaded):
        """Test combining list and reload operations."""
        # Setup mocks
        mock_list_loaded.return_value = ['plugin1']
        mock_list_failed.return_value = ['bad_plugin']
        mock_loader = Mock()
        mock_loader.reload_plugin.return_value = True
        mock_get_plugin_loader.return_value = mock_loader
        
        main()
        
        output = mock_stdout.getvalue()
        # Should contain both list and reload output
        assert "=== TalkPipe Plugins ===" in output
        assert "✓ plugin1" in output
        assert "✗ bad_plugin" in output
        assert "Successfully reloaded plugin: test_plugin" in output
        mock_loader.reload_plugin.assert_called_once_with('test_plugin')
    
    @patch('sys.stdout', new_callable=StringIO)
    @patch('sys.argv', ['talkpipe_plugin_manager'])
    def test_no_arguments(self, mock_stdout):
        """Test running with no arguments."""
        main()
        
        # Should run without error but produce no output
        output = mock_stdout.getvalue()
        assert output == ""
    
    @patch('sys.stdout', new_callable=StringIO)
    @patch('sys.argv', ['talkpipe_plugin_manager', '--verbose'])
    def test_verbose_flag(self, mock_stdout):
        """Test that verbose flag is parsed but doesn't affect current functionality."""
        main()
        
        # Should run without error
        output = mock_stdout.getvalue()
        assert output == ""
    
    @patch('talkpipe.app.talkpipe_plugin_manager.list_loaded_plugins')
    @patch('talkpipe.app.talkpipe_plugin_manager.list_failed_plugins')
    @patch('sys.stdout', new_callable=StringIO)
    @patch('sys.argv', ['talkpipe_plugin_manager', '--list', '--verbose'])
    def test_list_with_verbose(self, mock_stdout, mock_list_failed, mock_list_loaded):
        """Test listing plugins with verbose flag."""
        mock_list_loaded.return_value = ['plugin1']
        mock_list_failed.return_value = []
        
        main()
        
        output = mock_stdout.getvalue()
        assert "=== TalkPipe Plugins ===" in output
        assert "✓ plugin1" in output


class TestArgumentParsing:
    """Test argument parsing edge cases."""
    
    @patch('sys.argv', ['talkpipe_plugin_manager', '--help'])
    def test_help_argument(self):
        """Test that help argument works."""
        with pytest.raises(SystemExit) as exc_info:
            main()
        
        # argparse exits with code 0 for help
        assert exc_info.value.code == 0
    
    @patch('sys.argv', ['talkpipe_plugin_manager', '--invalid'])
    @patch('sys.stderr', new_callable=StringIO)
    def test_invalid_argument(self, mock_stderr):
        """Test handling of invalid arguments."""
        with pytest.raises(SystemExit) as exc_info:
            main()
        
        # argparse exits with code 2 for invalid arguments
        assert exc_info.value.code == 2