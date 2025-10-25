"""Enhanced registry system with hybrid decorator + entry point support.

This registry supports three modes of operation:
1. Decorator registration (existing behavior, always works)
2. Entry point discovery (fallback when decorator not registered)
3. Lazy import mode (via LAZY_IMPORT config or TALKPIPE_LAZY_IMPORT env var)

Lazy import behavior:
- The `.all` property always returns all available segments/sources (72 total)
- Entry points are loaded on-demand when `.all` is first accessed (~3s load time)
- LAZY_IMPORT=true: Fast module import (~0.17s) - entry points loaded when needed
- LAZY_IMPORT=false (default): Same behavior currently, but reserved for future use

This ensures tools like chatterlang_reference_browser can discover all components
while maintaining fast import times for applications that use lazy mode.
"""

from typing import Dict, Type, TypeVar, Generic, Optional, Set
import logging

logger = logging.getLogger(__name__)

# Check for lazy import mode from configuration
def _get_lazy_import_setting() -> bool:
    """Get the LAZY_IMPORT setting from configuration.

    Returns True if lazy loading is enabled, False for eager loading.
    Supports both configuration file and TALKPIPE_LAZY_IMPORT env var.
    """
    try:
        from talkpipe.util.config import get_config
        config = get_config()
        value = config.get('LAZY_IMPORT', 'false')
        return str(value).lower() in ('1', 'true', 'yes')
    except Exception as e:
        logger.warning(f"Could not load LAZY_IMPORT from config: {e}. Defaulting to eager loading.")
        return False

LAZY_IMPORT_MODE = _get_lazy_import_setting()

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
                 lazy_import: Optional[bool] = None):
        """
        Initialize the hybrid registry.

        Args:
            entry_point_group: Entry point group name (e.g., 'talkpipe.segments').
                             If None, only decorator registration is supported.
            lazy_import: Force lazy import mode. If None, respects configuration setting.
                        True = lazy loading, False = eager loading.
        """
        self._registry: Dict[str, Type[T]] = {}
        self._entry_point_group = entry_point_group
        self._entry_points_cache: Optional[Dict] = None
        self._attempted_loads: Set[str] = set()
        self._loaded_modules: Set[str] = set()

        # Determine if we should do lazy imports
        if lazy_import is not None:
            self._lazy_import = lazy_import
        else:
            self._lazy_import = LAZY_IMPORT_MODE

        if self._lazy_import:
            # Using lazy loading (fast startup, load on demand)
            logger.debug(
                f"Registry '{entry_point_group}' in LAZY import mode "
                f"(will delay loading until needed)"
            )
        else:
            # Not using lazy loading (will load on demand but not delay)
            logger.debug(
                f"Registry '{entry_point_group}' in EAGER import mode "
                f"(will load all entry points when accessed)"
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
        """Lazy discovery of entry points with collision detection."""
        if self._entry_points_cache is not None:
            return

        if not self._entry_point_group:
            self._entry_points_cache = {}
            return

        try:
            # Try Python 3.10+ API first
            from importlib.metadata import entry_points

            # Get entry points list
            ep_list = []
            if hasattr(entry_points, '__call__'):
                eps = entry_points()
                if hasattr(eps, 'select'):
                    # Python 3.10+
                    ep_list = list(eps.select(group=self._entry_point_group))
                else:
                    # Python 3.9
                    ep_list = list(eps.get(self._entry_point_group, []))
            else:
                # Shouldn't happen, but handle it
                ep_list = []

        except ImportError:
            # Python < 3.8, try backport
            try:
                from importlib_metadata import entry_points
                eps = entry_points()
                ep_list = list(eps.get(self._entry_point_group, []))
            except ImportError:
                logger.warning(
                    "Cannot discover entry points: importlib.metadata not available. "
                    "Install importlib_metadata for Python < 3.8"
                )
                ep_list = []

        # Detect name collisions before creating cache
        seen = {}
        conflicts = []

        for ep in ep_list:
            if ep.name in seen:
                # Get package names for better error messages
                existing_pkg = 'unknown'
                new_pkg = 'unknown'

                try:
                    if hasattr(seen[ep.name], 'dist') and hasattr(seen[ep.name].dist, 'name'):
                        existing_pkg = seen[ep.name].dist.name
                except Exception as e:
                    logger.debug(f"Could not get package name for existing entry point '{ep.name}': {e}")

                try:
                    if hasattr(ep, 'dist') and hasattr(ep.dist, 'name'):
                        new_pkg = ep.dist.name
                except Exception as e:
                    logger.debug(f"Could not get package name for new entry point '{ep.name}': {e}")

                conflicts.append(
                    f"  - Component '{ep.name}' defined by:\n"
                    f"      • {seen[ep.name].value} (from package '{existing_pkg}')\n"
                    f"      • {ep.value} (from package '{new_pkg}')"
                )
            else:
                seen[ep.name] = ep

        if conflicts:
            error_msg = (
                f"Entry point name collision detected in group '{self._entry_point_group}'.\n"
                f"Multiple packages are trying to register components with the same name:\n"
                + "\n".join(conflicts) + "\n\n"
                f"To resolve this conflict:\n"
                f"  1. Use unique prefixes for plugin components (e.g., 'myplugin_transform')\n"
                f"  2. Uninstall conflicting packages\n"
                f"  3. Contact the plugin authors to coordinate naming"
            )
            raise ValueError(error_msg)

        self._entry_points_cache = seen

        logger.debug(
            f"Discovered {len(self._entry_points_cache)} entry points "
            f"in group '{self._entry_point_group}'"
        )
    
    def _load_all_entry_points(self):
        """
        Discover and load all entry points.

        This is called during __init__ in eager mode, or on first .all access in lazy mode.
        """
        self._discover_entry_points()

        for name in list(self._entry_points_cache.keys()):
            if name not in self._registry and name not in self._attempted_loads:
                self._try_load_from_entry_point(name)

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

        This always returns all available components. In lazy mode, entry points
        are loaded on first access to this property. In eager mode, they were
        already loaded during __init__.

        Returns:
            Dictionary mapping component names to classes
        """
        # Ensure all entry points are loaded
        self._load_all_entry_points()

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
        'lazy_mode': LAZY_IMPORT_MODE,
    }


def enable_lazy_imports():
    """Enable lazy import mode programmatically."""
    global LAZY_IMPORT_MODE
    LAZY_IMPORT_MODE = True
    input_registry._lazy_import = True
    segment_registry._lazy_import = True
    logger.info("Enabled lazy import mode")


def disable_lazy_imports():
    """Disable lazy import mode (use eager loading) programmatically."""
    global LAZY_IMPORT_MODE
    LAZY_IMPORT_MODE = False
    input_registry._lazy_import = False
    segment_registry._lazy_import = False
    logger.info("Disabled lazy import mode (eager loading enabled)")
