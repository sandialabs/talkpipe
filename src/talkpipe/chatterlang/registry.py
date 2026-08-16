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

import logging
from collections.abc import Callable
from typing import Any, Generic, TypeVar

logger = logging.getLogger(__name__)

# Misspelled legacy names kept registered as functional aliases (so existing scripts
# that use them keep working) but excluded from discovery listings — error-message
# suggestions and `talkpipe_plugins --list` — since showing both spellings with no
# indication of which is canonical only confuses newcomers.
DEPRECATED_ALIASES = {"addToLancDB", "searchLancDB"}


# Check for lazy import mode from configuration
def _get_lazy_import_setting() -> bool:
    """Get the LAZY_IMPORT setting from configuration.

    Returns True if lazy loading is enabled, False for eager loading.
    Supports both configuration file and TALKPIPE_LAZY_IMPORT env var.
    """
    try:
        from talkpipe.util.config import get_config

        config = get_config()
        value = config.get("LAZY_IMPORT", "false")
        return str(value).lower() in ("1", "true", "yes")
    except Exception as e:
        logger.warning(
            f"Could not load LAZY_IMPORT from config: {e}. Defaulting to eager loading."
        )
        return False


LAZY_IMPORT_MODE = _get_lazy_import_setting()

T = TypeVar("T")


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

    def __init__(
        self, entry_point_group: str | None = None, lazy_import: bool | None = None
    ):
        """
        Initialize the hybrid registry.

        Args:
            entry_point_group: Entry point group name (e.g., 'talkpipe.segments').
                             If None, only decorator registration is supported.
            lazy_import: Force lazy import mode. If None, respects configuration setting.
                        True = lazy loading, False = eager loading.
        """
        self._registry: dict[str, type[T]] = {}
        self._entry_point_group = entry_point_group
        self._entry_points_cache: dict | None = None
        self._attempted_loads: set[str] = set()
        self._loaded_modules: set[str] = set()
        self._load_errors: dict[str, str] = {}

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

    def register(self, cls: type[T], name: str) -> None:
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

    def get(self, name: str) -> type[T]:
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
        if self._entry_point_group and self._try_load_from_entry_point(name):
            return self._registry[name]

        # Component not found anywhere
        self._attempted_loads.add(name)
        available = sorted(self._registry.keys())

        raise KeyError(
            f"Component '{name}' not found in registry. "
            f"Available components: {', '.join(available[:10])}"
            f"{', ...' if len(available) > 10 else ''}"
        )

    def _discover_entry_points(self) -> dict[str, Any]:
        """Lazy discovery of entry points with collision detection.

        Returns the (possibly freshly built) name -> entry point cache.
        """
        if self._entry_points_cache is not None:
            return self._entry_points_cache

        if not self._entry_point_group:
            self._entry_points_cache = {}
            return self._entry_points_cache

        # A package installed (e.g. via `pip install -e .`) earlier in this same
        # process can leave stale negative lookups in the import machinery's path
        # caches, which makes freshly-declared entry points intermittently
        # invisible until some later cache-busting import happens. Invalidating
        # here is cheap and ensures discovery sees on-disk metadata as it is now.
        import importlib

        importlib.invalidate_caches()

        from importlib.metadata import entry_points

        ep_list = list(entry_points().select(group=self._entry_point_group))

        # Detect name collisions before creating cache
        seen: dict[str, Any] = {}
        conflicts: list[str] = []

        for ep in ep_list:
            if ep.name in seen:
                # Get package names for better error messages
                existing_pkg = "unknown"
                new_pkg = "unknown"

                try:
                    if hasattr(seen[ep.name], "dist") and hasattr(
                        seen[ep.name].dist, "name"
                    ):
                        existing_pkg = seen[ep.name].dist.name
                except Exception as e:
                    logger.debug(
                        f"Could not get package name for existing entry point '{ep.name}': {e}"
                    )

                try:
                    if ep.dist is not None and hasattr(ep.dist, "name"):
                        new_pkg = ep.dist.name
                except Exception as e:
                    logger.debug(
                        f"Could not get package name for new entry point '{ep.name}': {e}"
                    )

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
                + "\n".join(conflicts)
                + "\n\n"
                "To resolve this conflict:\n"
                "  1. Use unique prefixes for plugin components (e.g., 'myplugin_transform')\n"
                "  2. Uninstall conflicting packages\n"
                "  3. Contact the plugin authors to coordinate naming"
            )
            raise ValueError(error_msg)

        self._entry_points_cache = seen

        logger.debug(
            f"Discovered {len(self._entry_points_cache)} entry points "
            f"in group '{self._entry_point_group}'"
        )
        return self._entry_points_cache

    def _load_all_entry_points(self):
        """
        Discover and load all entry points.

        This is called during __init__ in eager mode, or on first .all access in lazy mode.
        """
        entry_points_cache = self._discover_entry_points()

        for name in list(entry_points_cache.keys()):
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
        entry_points_cache = self._discover_entry_points()

        if name not in entry_points_cache:
            logger.debug(f"Component '{name}' not found in entry points")
            return False

        ep = entry_points_cache[name]

        try:
            logger.info(
                f"Loading '{name}' from entry point: {ep.value} "
                f"(group: {self._entry_point_group})"
            )

            # Load the entry point - this imports the module
            # The import will execute decorators, which call register()
            cls = ep.load()

            # Track which module we loaded
            if hasattr(cls, "__module__"):
                self._loaded_modules.add(cls.__module__)

            # Check if decorator registered it with the same name
            if name in self._registry:
                logger.info(f"Successfully loaded and registered '{name}'")
                return True
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
            logger.exception(
                f"Failed to load '{name}' from entry point {ep.value}: {e}"
            )
            self._attempted_loads.add(name)
            self._load_errors[name] = f"{ep.value}: {e}"
            return False

    def load_error(self, name: str) -> str | None:
        """
        Get the captured error for a name whose entry point failed to load.

        Returns:
            The "module:object: exception" string from the failed load attempt,
            or None if no load was attempted or it succeeded.
        """
        return self._load_errors.get(name)

    @property
    def all(self) -> dict[str, type[T]]:
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

    def list_entry_points(self) -> dict[str, str]:
        """
        Get a mapping of entry point names to their module:object strings.

        This does NOT trigger imports.

        Returns:
            Dictionary mapping names to "module:object" strings
        """
        entry_points_cache = self._discover_entry_points()
        return {name: ep.value for name, ep in entry_points_cache.items()}

    @property
    def available_names(self) -> list[str]:
        """
        Sorted names of every component known without importing them.

        Combines decorator-registered names with declared entry point names.
        Unlike :pyattr:`all`, this does NOT trigger entry point imports, so it
        is cheap enough to use when building "component not found" error
        messages.

        Returns:
            Sorted list of component names
        """
        names = set(self._registry.keys())
        try:
            names.update(self.list_entry_points().keys())
        except Exception as e:
            # Discovering entry points must never block an error message.
            logger.debug(
                f"Failed to discover entry points while collecting available names: {e}",
                exc_info=True,
            )
        names -= DEPRECATED_ALIASES
        return sorted(names)

    def invalidate_cache(self):
        """
        Clear caches (useful for testing).
        """
        self._entry_points_cache = None
        self._attempted_loads.clear()

    def stats(self) -> dict[str, int]:
        """
        Get statistics about registry usage.

        Returns:
            Dictionary with counts of registered components, entry points, etc.
        """
        entry_points_cache = self._discover_entry_points()

        return {
            "registered": len(self._registry),
            "entry_points": len(entry_points_cache),
            "loaded_modules": len(self._loaded_modules),
            "failed_loads": len(self._attempted_loads),
        }


# Create the global registries with entry point groups
input_registry: HybridRegistry[Any] = HybridRegistry(
    entry_point_group="talkpipe.sources"
)
segment_registry: HybridRegistry[Any] = HybridRegistry(
    entry_point_group="talkpipe.segments"
)


def register_source(
    *names: str, name: str | None = None
) -> Callable[[type[T]], type[T]]:
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
            raise ValueError(
                "Cannot specify both positional names and 'name' keyword argument"
            )
        names = (name,)

    if not names:
        raise ValueError("At least one name must be provided")

    def wrap(cls: type[T]) -> type[T]:
        for source_name in names:
            input_registry.register(cls, name=source_name)
        return cls

    return wrap


def register_segment(
    *names: str, name: str | None = None
) -> Callable[[type[T]], type[T]]:
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
            raise ValueError(
                "Cannot specify both positional names and 'name' keyword argument"
            )
        names = (name,)

    if not names:
        raise ValueError("At least one name must be provided")

    def wrap(cls: type[T]) -> type[T]:
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
        "sources": input_registry.stats(),
        "segments": segment_registry.stats(),
        "lazy_mode": LAZY_IMPORT_MODE,
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
