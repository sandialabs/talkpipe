import pytest
from unittest.mock import Mock, patch, MagicMock
from importlib import metadata

from talkpipe.util.plugin_loader import (
    PluginLoader,
    get_plugin_loader, 
    load_plugins,
    list_loaded_plugins,
    list_failed_plugins
)


class TestPluginLoader:
    """Test cases for the PluginLoader class."""
    
    def test_init(self):
        """Test PluginLoader initialization."""
        loader = PluginLoader()
        assert loader.loaded_plugins == {}
        assert loader.failed_plugins == []
    
    @patch('talkpipe.util.plugin_loader.metadata.entry_points')
    def test_discover_and_load_plugins(self, mock_entry_points):
        """Test plugin discovery and loading."""
        # Mock entry points
        mock_entry_point = Mock()
        mock_entry_point.name = 'test_plugin'
        mock_entry_point.load.return_value = Mock()
        
        mock_entry_points.return_value = [mock_entry_point]
        
        loader = PluginLoader()
        loader.discover_and_load_plugins()
        
        mock_entry_points.assert_called_once_with(group='talkpipe.plugins')
        assert 'test_plugin' in loader.loaded_plugins
        assert len(loader.failed_plugins) == 0
    
    @patch('talkpipe.util.plugin_loader.metadata.entry_points')
    def test_discover_and_load_plugins_with_initialization(self, mock_entry_points):
        """Test plugin loading with initialization function."""
        # Mock entry points
        mock_plugin_module = Mock()
        mock_plugin_module.initialize_plugin = Mock()
        
        mock_entry_point = Mock()
        mock_entry_point.name = 'test_plugin'
        mock_entry_point.load.return_value = mock_plugin_module
        
        mock_entry_points.return_value = [mock_entry_point]
        
        loader = PluginLoader()
        loader.discover_and_load_plugins()
        
        # Verify initialization was called
        mock_plugin_module.initialize_plugin.assert_called_once()
        assert loader.loaded_plugins['test_plugin'] == mock_plugin_module
    
    @patch('talkpipe.util.plugin_loader.metadata.entry_points')
    def test_discover_and_load_plugins_without_initialization(self, mock_entry_points):
        """Test plugin loading without initialization function."""
        # Mock entry points
        mock_plugin_module = Mock(spec=[])  # No initialize_plugin method
        
        mock_entry_point = Mock()
        mock_entry_point.name = 'test_plugin'
        mock_entry_point.load.return_value = mock_plugin_module
        
        mock_entry_points.return_value = [mock_entry_point]
        
        loader = PluginLoader()
        loader.discover_and_load_plugins()
        
        # Plugin should still be loaded even without initialization
        assert loader.loaded_plugins['test_plugin'] == mock_plugin_module
    
    @patch('talkpipe.util.plugin_loader.metadata.entry_points')
    def test_load_plugin_failure(self, mock_entry_points):
        """Test handling of plugin loading failure."""
        # Mock entry points
        mock_entry_point = Mock()
        mock_entry_point.name = 'failing_plugin'
        mock_entry_point.load.side_effect = ImportError("Module not found")
        
        mock_entry_points.return_value = [mock_entry_point]
        
        loader = PluginLoader()
        loader.discover_and_load_plugins()
        
        # Plugin should be in failed list
        assert 'failing_plugin' in loader.failed_plugins
        assert 'failing_plugin' not in loader.loaded_plugins
    
    @patch('talkpipe.util.plugin_loader.metadata.entry_points')
    def test_discover_and_load_plugins_exception(self, mock_entry_points):
        """Test handling of exception during plugin discovery."""
        mock_entry_points.side_effect = Exception("Discovery failed")
        
        loader = PluginLoader()
        # Should not raise exception
        loader.discover_and_load_plugins()
        
        # Lists should remain empty
        assert len(loader.loaded_plugins) == 0
        assert len(loader.failed_plugins) == 0
    
    def test_get_loaded_plugins(self):
        """Test getting loaded plugins dictionary."""
        loader = PluginLoader()
        mock_plugin = Mock()
        loader.loaded_plugins['test_plugin'] = mock_plugin
        
        result = loader.get_loaded_plugins()
        
        # Should return a copy
        assert result == {'test_plugin': mock_plugin}
        assert result is not loader.loaded_plugins
    
    def test_get_failed_plugins(self):
        """Test getting failed plugins list."""
        loader = PluginLoader()
        loader.failed_plugins.append('failed_plugin')
        
        result = loader.get_failed_plugins()
        
        # Should return a copy
        assert result == ['failed_plugin']
        assert result is not loader.failed_plugins
    
    @patch('talkpipe.util.plugin_loader.importlib.reload')
    @patch('talkpipe.util.plugin_loader.sys.modules', {'test.module': Mock()})
    @patch('talkpipe.util.plugin_loader.metadata.entry_points')
    def test_reload_plugin_success(self, mock_entry_points, mock_reload):
        """Test successful plugin reload."""
        # Setup existing loaded plugin
        loader = PluginLoader()
        loader.loaded_plugins['test_plugin'] = Mock()
        
        # Mock entry points for reload
        mock_plugin_module = Mock()
        mock_entry_point = Mock()
        mock_entry_point.name = 'test_plugin'
        mock_entry_point.value = 'test.module:plugin_function'
        mock_entry_point.load.return_value = mock_plugin_module
        
        mock_entry_points.return_value = [mock_entry_point]
        
        result = loader.reload_plugin('test_plugin')
        
        assert result is True
        mock_reload.assert_called_once()
        assert loader.loaded_plugins['test_plugin'] == mock_plugin_module
    
    @patch('talkpipe.util.plugin_loader.metadata.entry_points')
    def test_reload_plugin_not_found(self, mock_entry_points):
        """Test plugin reload when plugin not found."""
        mock_entry_points.return_value = []
        
        loader = PluginLoader()
        result = loader.reload_plugin('nonexistent_plugin')
        
        assert result is False
    
    @patch('talkpipe.util.plugin_loader.metadata.entry_points')
    def test_reload_plugin_exception(self, mock_entry_points):
        """Test plugin reload with exception."""
        mock_entry_points.side_effect = Exception("Reload failed")
        
        loader = PluginLoader()
        result = loader.reload_plugin('test_plugin')
        
        assert result is False


class TestGlobalPluginLoaderFunctions:
    """Test cases for global plugin loader functions."""
    
    @patch('talkpipe.util.plugin_loader._plugin_loader', None)
    def test_get_plugin_loader_singleton(self):
        """Test that get_plugin_loader returns singleton instance."""
        loader1 = get_plugin_loader()
        loader2 = get_plugin_loader()
        
        assert loader1 is loader2
        assert isinstance(loader1, PluginLoader)
    
    @patch('talkpipe.util.plugin_loader.get_plugin_loader')
    def test_load_plugins(self, mock_get_loader):
        """Test load_plugins convenience function."""
        mock_loader = Mock()
        mock_get_loader.return_value = mock_loader
        
        load_plugins()
        
        mock_get_loader.assert_called_once()
        mock_loader.discover_and_load_plugins.assert_called_once()
    
    @patch('talkpipe.util.plugin_loader.get_plugin_loader')
    def test_list_loaded_plugins(self, mock_get_loader):
        """Test list_loaded_plugins convenience function."""
        mock_loader = Mock()
        mock_loader.get_loaded_plugins.return_value = {'plugin1': Mock(), 'plugin2': Mock()}
        mock_get_loader.return_value = mock_loader
        
        result = list_loaded_plugins()
        
        assert result == ['plugin1', 'plugin2']
        mock_loader.get_loaded_plugins.assert_called_once()
    
    @patch('talkpipe.util.plugin_loader.get_plugin_loader')
    def test_list_failed_plugins(self, mock_get_loader):
        """Test list_failed_plugins convenience function."""
        mock_loader = Mock()
        mock_loader.get_failed_plugins.return_value = ['failed1', 'failed2']
        mock_get_loader.return_value = mock_loader
        
        result = list_failed_plugins()
        
        assert result == ['failed1', 'failed2']
        mock_loader.get_failed_plugins.assert_called_once()


class TestEdgeCases:
    """Test edge cases and integration scenarios."""
    
    @patch('talkpipe.util.plugin_loader.metadata.entry_points')
    def test_multiple_plugins_mixed_success_failure(self, mock_entry_points):
        """Test loading multiple plugins with mixed success/failure."""
        # Create mock plugins - one successful, one failing
        good_plugin = Mock()
        good_entry_point = Mock()
        good_entry_point.name = 'good_plugin'
        good_entry_point.load.return_value = good_plugin
        
        bad_entry_point = Mock()
        bad_entry_point.name = 'bad_plugin'
        bad_entry_point.load.side_effect = ImportError("Bad plugin")
        
        mock_entry_points.return_value = [good_entry_point, bad_entry_point]
        
        loader = PluginLoader()
        loader.discover_and_load_plugins()
        
        # Check results
        assert 'good_plugin' in loader.loaded_plugins
        assert 'bad_plugin' not in loader.loaded_plugins
        assert 'bad_plugin' in loader.failed_plugins
        assert len(loader.loaded_plugins) == 1
        assert len(loader.failed_plugins) == 1
    
    @patch('talkpipe.util.plugin_loader.metadata.entry_points')
    def test_empty_entry_points(self, mock_entry_points):
        """Test behavior with no available plugins."""
        mock_entry_points.return_value = []
        
        loader = PluginLoader()
        loader.discover_and_load_plugins()
        
        assert len(loader.loaded_plugins) == 0
        assert len(loader.failed_plugins) == 0