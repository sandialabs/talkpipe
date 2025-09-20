import sys
from importlib import metadata
import importlib
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

class PluginLoader:
    """Manages loading of TalkPipe plugins via entry points."""
    
    def __init__(self):
        self.loaded_plugins: Dict[str, any] = {}
        self.failed_plugins: List[str] = []
    
    def discover_and_load_plugins(self) -> None:
        """Discover and load all TalkPipe plugins from installed packages."""
        try:
            # Get all entry points for the 'talkpipe.plugins' group
            entry_points = metadata.entry_points(group='talkpipe.plugins')
            
            logger.info(f"Found {len(entry_points)} TalkPipe plugin(s)")
            
            for entry_point in entry_points:
                self._load_plugin(entry_point)
                
        except Exception as e:
            logger.error(f"Error during plugin discovery: {e}")
    
    def _load_plugin(self, entry_point) -> None:
        """Load a single plugin from an entry point."""
        try:
            logger.debug(f"Loading plugin: {entry_point.name}")
            
            # Load the plugin module
            plugin_module = entry_point.load()
            
            # Call initialization function if it exists
            if hasattr(plugin_module, 'initialize_plugin'):
                plugin_module.initialize_plugin()
            
            # Store reference to loaded plugin
            self.loaded_plugins[entry_point.name] = plugin_module
            
            logger.info(f"Successfully loaded plugin: {entry_point.name}")
            
        except Exception as e:
            logger.error(f"Failed to load plugin {entry_point.name}: {e}")
            self.failed_plugins.append(entry_point.name)
    
    def get_loaded_plugins(self) -> Dict[str, any]:
        """Get dictionary of successfully loaded plugins."""
        return self.loaded_plugins.copy()
    
    def get_failed_plugins(self) -> List[str]:
        """Get list of plugins that failed to load."""
        return self.failed_plugins.copy()
    
    def reload_plugin(self, plugin_name: str) -> bool:
        """Reload a specific plugin by name."""
        try:
            entry_points = metadata.entry_points(group='talkpipe.plugins')
            
            for entry_point in entry_points:
                if entry_point.name == plugin_name:
                    # Remove from loaded plugins if it exists
                    if plugin_name in self.loaded_plugins:
                        del self.loaded_plugins[plugin_name]
                    
                    # Reload the module
                    module_name = entry_point.value.split(':')[0]
                    if module_name in sys.modules:
                        importlib.reload(sys.modules[module_name])
                    
                    # Load the plugin again
                    self._load_plugin(entry_point)
                    return True
            
            logger.warning(f"Plugin {plugin_name} not found for reload")
            return False
            
        except Exception as e:
            logger.error(f"Failed to reload plugin {plugin_name}: {e}")
            return False

# Global plugin loader instance
_plugin_loader: Optional[PluginLoader] = None

def get_plugin_loader() -> PluginLoader:
    """Get the global plugin loader instance."""
    global _plugin_loader
    if _plugin_loader is None:
        _plugin_loader = PluginLoader()
    return _plugin_loader

def load_plugins() -> None:
    """Convenience function to load all plugins."""
    loader = get_plugin_loader()
    loader.discover_and_load_plugins()

def list_loaded_plugins() -> List[str]:
    """Get list of successfully loaded plugin names."""
    loader = get_plugin_loader()
    return list(loader.get_loaded_plugins().keys())

def list_failed_plugins() -> List[str]:
    """Get list of plugins that failed to load."""
    loader = get_plugin_loader()
    return loader.get_failed_plugins()