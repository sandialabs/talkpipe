"""Enhanced registry system with hybrid decorator + entry point support.

This registry supports three modes of operation:
1. Decorator registration (existing behavior, always works)
2. Entry point discovery (fallback when decorator not registered)
3. Eager import mode (via TALKPIPE_EAGER_IMPORT env var)

The system is designed for progressive migration from eager to lazy loading:
- Phase 1: All imports eager (current), entry points added
- Phase 2: Remove some imports, rely on entry points
- Phase 3: Fully lazy, minimal imports
"""

from typing import Dict, Type, TypeVar, Generic, Optional, Set
import importlib
import logging
import os
import sys

logger = logging.getLogger(__name__)

# Check for eager import mode
EAGER_IMPORT_MODE = os.environ.get('TALKPIPE_EAGER_IMPORT', '').lower() in ('1', 'true', 'yes')

T = TypeVar('T')


class HybridRegistry(Generic[T]):
    """
    Registry supporting both decorator registration and entry point discovery.
    
    Workflow:
    1. When get() is called, check if component is registered (decorator ran)
    2. If not, try to load from entry points
    3. Entry point import triggers decorator, which registers component
    4. Return registered component
    
    This allows gradual migration from eager to lazy loading without breaking changes.
    """
    
    def __init__(self, 
                 entry_point_group: Optional[str] = None,
                 eager_import: Optional[bool] = None):
        """
        Initialize the hybrid registry.
        
        Args:
            entry_point_group: Entry point group name (e.g., 'talkpipe.segments').
                             If None, only decorator registration is supported.
            eager_import: Force eager import mode. If None, respects environment variable.
        """
        self._registry: Dict[str, Type[T]] = {}
        self._entry_point_group = entry_point_group
        self._entry_points_cache: Optional[Dict] = None
        self._attempted_loads: Set[str] = set()
        self._loaded_modules: Set[str] = set()
        
        # Determine if we should do eager imports
        if eager_import is not None:
            self._eager_import = eager_import
        else:
            self._eager_import = EAGER_IMPORT_MODE
        
        if self._eager_import:
            logger.info(
                f"Registry '{entry_point_group}' in EAGER import mode "
                f"(TALKPIPE_EAGER_IMPORT={os.environ.get('TALKPIPE_EAGER_IMPORT', 'not set')})"
            )
    
    def register(self, cls: Type[T], name: str) -> None:
        """
        Register a component (called by decorators when modules are imported).
        
        Args:
            cls: The class to register
            name: The registration name
        """
        if name in self._registry:
            existing = self._registry[name]
            if existing is not cls:
                logger.warning(
                    f"Component '{name}' already registered as {existing}. "
                    f"Overwriting with {cls}."
                )
        
        self._registry[name] = cls
        logger.debug(f"Registered '{name}' → {cls.__module__}.{cls.__name__}")
    
    def get(self, name: str) -> Type[T]:
        """
        Get a component by name, using entry points as fallback.
        
        Args:
            name: Component name
            
        Returns:
            The component class
            
        Raises:
            KeyError: If component not found in registry or entry points
        """
        # Fast path: already registered via decorator
        if name in self._registry:
            return self._registry[name]
        
        # Avoid retry loops for known failures
        if name in self._attempted_loads:
            raise KeyError(
                f"Component '{name}' not found and previous load attempt failed"
            )
        
        # Try to load from entry points
        if self._entry_point_group:
            if self._try_load_from_entry_point(name):
                return self._registry[name]
        
        # Component not found anywhere
        self._attempted_loads.add(name)
        available = sorted(self._registry.keys())
        
        raise KeyError(
            f"Component '{name}' not found in registry. "
            f"Available components: {', '.join(available[:10])}"
            f"{', ...' if len(available) > 10 else ''}"
        )
    
    def _discover_entry_points(self):
        """Lazy discovery of entry points."""
        if self._entry_points_cache is not None:
            return
        
        if not self._entry_point_group:
            self._entry_points_cache = {}
            return
        
        try:
            # Try Python 3.10+ API first
            from importlib.metadata import entry_points
            
            # Python 3.10+ returns EntryPoints object with select() method
            if hasattr(entry_points, '__call__'):
                eps = entry_points()
                if hasattr(eps, 'select'):
                    # Python 3.10+
                    self._entry_points_cache = {
                        ep.name: ep 
                        for ep in eps.select(group=self._entry_point_group)
                    }
                else:
                    # Python 3.9
                    self._entry_points_cache = {
                        ep.name: ep
                        for ep in eps.get(self._entry_point_group, [])
                    }
            else:
                # Shouldn't happen, but handle it
                self._entry_points_cache = {}
                
        except ImportError:
            # Python < 3.8, try backport
            try:
                from importlib_metadata import entry_points
                eps = entry_points()
                self._entry_points_cache = {
                    ep.name: ep
                    for ep in eps.get(self._entry_point_group, [])
                }
            except ImportError:
                logger.warning(
                    "Cannot discover entry points: importlib.metadata not available. "
                    "Install importlib_metadata for Python < 3.8"
                )
                self._entry_points_cache = {}
        
        logger.debug(
            f"Discovered {len(self._entry_points_cache)} entry points "
            f"in group '{self._entry_point_group}'"
        )
    
    def _try_load_from_entry_point(self, name: str) -> bool:
        """
        Attempt to load a component from entry points.
        
        Args:
            name: Component name
            
        Returns:
            True if component was successfully loaded and registered
        """
        # Discover entry points if needed
        self._discover_entry_points()
        
        if name not in self._entry_points_cache:
            logger.debug(f"Component '{name}' not found in entry points")
            return False
        
        ep = self._entry_points_cache[name]
        
        try:
            logger.info(
                f"Loading '{name}' from entry point: {ep.value} "
                f"(group: {self._entry_point_group})"
            )
            
            # Load the entry point - this imports the module
            # The import will execute decorators, which call register()
            cls = ep.load()
            
            # Track which module we loaded
            if hasattr(cls, '__module__'):
                self._loaded_modules.add(cls.__module__)
            
            # Check if decorator registered it with the same name
            if name in self._registry:
                logger.info(f"Successfully loaded and registered '{name}'")
                return True
            else:
                # Class loaded but didn't register with expected name
                # This could happen if decorator uses different name
                logger.warning(
                    f"Entry point '{name}' loaded class {cls} but it was not "
                    f"registered under that name. Registering manually."
                )
                # Register it manually with the entry point name
                self.register(cls, name)
                return True
                
        except Exception as e:
            logger.error(
                f"Failed to load '{name}' from entry point {ep.value}: {e}",
                exc_info=True
            )
            self._attempted_loads.add(name)
            return False
    
    @property
    def all(self) -> Dict[str, Type[T]]:
        """
        Get all registered components, loading from entry points if needed.
        
        This will trigger imports of all modules with entry points.
        
        Returns:
            Dictionary mapping component names to classes
        """
        # If in eager mode, everything should already be loaded
        if self._eager_import:
            return self._registry.copy()
        
        # Discover and try to load all entry points
        self._discover_entry_points()
        
        for name in list(self._entry_points_cache.keys()):
            if name not in self._registry and name not in self._attempted_loads:
                self._try_load_from_entry_point(name)
        
        return self._registry.copy()
    
    def list_entry_points(self) -> Dict[str, str]:
        """
        Get a mapping of entry point names to their module:object strings.
        
        This does NOT trigger imports.
        
        Returns:
            Dictionary mapping names to "module:object" strings
        """
        self._discover_entry_points()
        return {
            name: ep.value 
            for name, ep in self._entry_points_cache.items()
        }
    
    def invalidate_cache(self):
        """
        Clear caches (useful for testing).
        """
        self._entry_points_cache = None
        self._attempted_loads.clear()
    
    def stats(self) -> Dict[str, int]:
        """
        Get statistics about registry usage.
        
        Returns:
            Dictionary with counts of registered components, entry points, etc.
        """
        self._discover_entry_points()
        
        return {
            'registered': len(self._registry),
            'entry_points': len(self._entry_points_cache),
            'loaded_modules': len(self._loaded_modules),
            'failed_loads': len(self._attempted_loads),
        }


# Create the global registries with entry point groups
input_registry = HybridRegistry(entry_point_group='talkpipe.sources')
segment_registry = HybridRegistry(entry_point_group='talkpipe.segments')


def register_source(*names: str, name: str = None):
    """
    Decorator to register a source module with one or more names in the registry.
    
    Usage:
        @register_source("mySource")
        class MySource(AbstractSource):
            ...
        
        # Register with multiple names
        @register_source("source1", "source2", "source3")
        class MultiNameSource(AbstractSource):
            ...
        
        # Backward compatible keyword argument
        @register_source(name="mySource")
        class KeywordSource(AbstractSource):
            ...
    
    Args:
        *names: One or more names to register the source under (positional)
        name: Single name to register the source under (keyword, for backward compatibility)
    """
    # Handle backward compatibility with name= keyword argument
    if name is not None:
        if names:
            raise ValueError("Cannot specify both positional names and 'name' keyword argument")
        names = (name,)
    
    if not names:
        raise ValueError("At least one name must be provided")
    
    def wrap(cls):
        for source_name in names:
            input_registry.register(cls, name=source_name)
        return cls
    return wrap


def register_segment(*names: str, name: str = None):
    """
    Decorator to register a segment module with one or more names in the registry.
    
    Usage:
        @register_segment("mySegment")
        class MySegment(AbstractSegment):
            ...
        
        # Register with multiple names
        @register_segment("segment1", "segment2", "segment3")
        class MultiNameSegment(AbstractSegment):
            ...
        
        # Backward compatible keyword argument
        @register_segment(name="mySegment")
        class KeywordSegment(AbstractSegment):
            ...
    
    Args:
        *names: One or more names to register the segment under (positional)
        name: Single name to register the segment under (keyword, for backward compatibility)
    """
    # Handle backward compatibility with name= keyword argument
    if name is not None:
        if names:
            raise ValueError("Cannot specify both positional names and 'name' keyword argument")
        names = (name,)
    
    if not names:
        raise ValueError("At least one name must be provided")
    
    def wrap(cls):
        for segment_name in names:
            segment_registry.register(cls, name=segment_name)
        return cls
    return wrap


def get_registry_stats():
    """
    Get statistics about both registries.
    
    Returns:
        Dictionary with stats for both registries
    """
    return {
        'sources': input_registry.stats(),
        'segments': segment_registry.stats(),
        'eager_mode': EAGER_IMPORT_MODE,
    }


def enable_eager_imports():
    """Enable eager import mode programmatically."""
    global EAGER_IMPORT_MODE
    EAGER_IMPORT_MODE = True
    input_registry._eager_import = True
    segment_registry._eager_import = True
    logger.info("Enabled eager import mode")


def disable_eager_imports():
    """Disable eager import mode programmatically."""
    global EAGER_IMPORT_MODE
    EAGER_IMPORT_MODE = False
    input_registry._eager_import = False
    segment_registry._eager_import = False
    logger.info("Disabled eager import mode (lazy loading enabled)")
