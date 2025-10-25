"""Tests for talkpipe.chatterlang.registry module."""
import os
import pytest
from unittest.mock import patch, MagicMock
from talkpipe.chatterlang import registry


class TestLazyImportConfiguration:
    """Test cases for LAZY_IMPORT configuration."""

    def test_lazy_import_from_config_true(self):
        """Test that LAZY_IMPORT=true from config enables lazy loading."""
        with patch('talkpipe.util.config.get_config') as mock_get_config:
            mock_get_config.return_value = {'LAZY_IMPORT': 'true'}

            # Test the function directly
            result = registry._get_lazy_import_setting()

            assert result is True

    def test_lazy_import_from_config_false(self):
        """Test that LAZY_IMPORT=false from config disables lazy loading."""
        with patch('talkpipe.util.config.get_config') as mock_get_config:
            mock_get_config.return_value = {'LAZY_IMPORT': 'false'}

            result = registry._get_lazy_import_setting()

            assert result is False

    def test_lazy_import_from_env_var(self):
        """Test that TALKPIPE_LAZY_IMPORT environment variable works."""
        # This test relies on get_config() automatically picking up TALKPIPE_* env vars
        with patch.dict(os.environ, {'TALKPIPE_LAZY_IMPORT': 'true'}, clear=False):
            # Reset config to force reload
            from talkpipe.util.config import reset_config
            reset_config()

            result = registry._get_lazy_import_setting()

            assert result is True

    def test_lazy_import_default_false(self):
        """Test that lazy import defaults to false when not configured."""
        with patch('talkpipe.util.config.get_config') as mock_get_config:
            mock_get_config.return_value = {}

            result = registry._get_lazy_import_setting()

            assert result is False


class TestHybridRegistryLazyMode:
    """Test HybridRegistry behavior with lazy import mode."""

    def test_registry_respects_lazy_import_parameter_true(self):
        """Test that registry respects lazy_import=True parameter."""
        test_registry = registry.HybridRegistry(
            entry_point_group='test.group',
            lazy_import=True
        )

        assert test_registry._lazy_import is True

    def test_registry_respects_lazy_import_parameter_false(self):
        """Test that registry respects lazy_import=False parameter."""
        test_registry = registry.HybridRegistry(
            entry_point_group='test.group',
            lazy_import=False
        )

        assert test_registry._lazy_import is False

    def test_registry_uses_global_lazy_mode_when_not_specified(self):
        """Test that registry uses global LAZY_IMPORT_MODE when parameter not specified."""
        # Save original value
        original_mode = registry.LAZY_IMPORT_MODE

        try:
            # Test with lazy mode enabled
            registry.LAZY_IMPORT_MODE = True
            test_registry = registry.HybridRegistry(entry_point_group='test.group')
            assert test_registry._lazy_import is True

            # Test with lazy mode disabled
            registry.LAZY_IMPORT_MODE = False
            test_registry = registry.HybridRegistry(entry_point_group='test.group')
            assert test_registry._lazy_import is False
        finally:
            # Restore original value
            registry.LAZY_IMPORT_MODE = original_mode

    def test_enable_lazy_imports_function(self):
        """Test that enable_lazy_imports() function works."""
        # Save original values
        original_mode = registry.LAZY_IMPORT_MODE
        original_input = registry.input_registry._lazy_import
        original_segment = registry.segment_registry._lazy_import

        try:
            registry.enable_lazy_imports()

            assert registry.LAZY_IMPORT_MODE is True
            assert registry.input_registry._lazy_import is True
            assert registry.segment_registry._lazy_import is True
        finally:
            # Restore original values
            registry.LAZY_IMPORT_MODE = original_mode
            registry.input_registry._lazy_import = original_input
            registry.segment_registry._lazy_import = original_segment

    def test_disable_lazy_imports_function(self):
        """Test that disable_lazy_imports() function works."""
        # Save original values
        original_mode = registry.LAZY_IMPORT_MODE
        original_input = registry.input_registry._lazy_import
        original_segment = registry.segment_registry._lazy_import

        try:
            registry.disable_lazy_imports()

            assert registry.LAZY_IMPORT_MODE is False
            assert registry.input_registry._lazy_import is False
            assert registry.segment_registry._lazy_import is False
        finally:
            # Restore original values
            registry.LAZY_IMPORT_MODE = original_mode
            registry.input_registry._lazy_import = original_input
            registry.segment_registry._lazy_import = original_segment

    def test_get_registry_stats_includes_lazy_mode(self):
        """Test that get_registry_stats() includes lazy_mode."""
        stats = registry.get_registry_stats()

        assert 'lazy_mode' in stats
        assert isinstance(stats['lazy_mode'], bool)


class TestRegistryAllProperty:
    """Test the .all property behavior with lazy loading."""

    def test_all_always_returns_everything_lazy_mode(self):
        """Test that .all returns all components in lazy mode (loads on first access)."""
        test_registry = registry.HybridRegistry(
            entry_point_group='test.group',
            lazy_import=True  # Lazy mode - no loading at init
        )

        # Register a test component
        class TestClass:
            pass

        test_registry.register(TestClass, 'test_component')

        # Mock _load_all_entry_points to track when loading happens
        test_registry._load_all_entry_points = MagicMock(wraps=test_registry._load_all_entry_points)

        # First access to .all should trigger loading
        result = test_registry.all

        # Should have called _load_all_entry_points
        test_registry._load_all_entry_points.assert_called_once()
        assert 'test_component' in result
        assert result['test_component'] is TestClass

    def test_all_always_returns_everything_eager_mode(self):
        """Test that .all returns all components in eager mode (already loaded at init)."""
        # Register a test component before creating registry
        class TestClass:
            pass

        test_registry = registry.HybridRegistry(
            entry_point_group='test.group',
            lazy_import=False  # Eager mode - load at init
        )

        test_registry.register(TestClass, 'test_component')

        # In eager mode, entry points were already loaded at __init__
        # Accessing .all should still work and return everything
        result = test_registry.all

        assert 'test_component' in result
        assert result['test_component'] is TestClass

    def test_neither_mode_loads_at_init(self):
        """Test that neither mode loads entry points during __init__ (avoids circular imports)."""
        # Mock _load_all_entry_points to verify it's NOT called during init in either mode
        with patch.object(registry.HybridRegistry, '_load_all_entry_points') as mock_load:
            # Test eager mode
            test_registry_eager = registry.HybridRegistry(
                entry_point_group='test.group',
                lazy_import=False  # Eager mode
            )
            # Should NOT have been called during __init__ (avoids circular imports)
            mock_load.assert_not_called()

            # Test lazy mode
            test_registry_lazy = registry.HybridRegistry(
                entry_point_group='test.group',
                lazy_import=True  # Lazy mode
            )
            # Should still not have been called
            mock_load.assert_not_called()


class TestEntryPointCollisionDetection:
    """Test entry point name collision detection."""

    def test_collision_detection_raises_error(self):
        """Test that duplicate entry point names from different packages raise an error."""
        # Create mock entry points with the same name but different values
        mock_ep1 = MagicMock()
        mock_ep1.name = 'mySegment'
        mock_ep1.value = 'package1.segments:MySegment'
        mock_ep1.dist.name = 'package1'

        mock_ep2 = MagicMock()
        mock_ep2.name = 'mySegment'  # Same name as ep1 - this is the collision
        mock_ep2.value = 'package2.segments:MySegment'
        mock_ep2.dist.name = 'package2'

        # Mock the entry_points() function to return our conflicting entry points
        mock_eps_result = MagicMock()
        mock_eps_result.select = MagicMock(return_value=[mock_ep1, mock_ep2])

        with patch('importlib.metadata.entry_points', return_value=mock_eps_result):
            test_registry = registry.HybridRegistry(
                entry_point_group='test.segments',
                lazy_import=True
            )

            # Attempting to discover entry points should raise ValueError
            with pytest.raises(ValueError) as exc_info:
                test_registry._discover_entry_points()

            # Check that the error message contains useful information
            error_msg = str(exc_info.value)
            assert 'collision' in error_msg.lower() or 'conflict' in error_msg.lower()
            assert 'mySegment' in error_msg
            assert 'package1' in error_msg
            assert 'package2' in error_msg

    def test_no_collision_with_unique_names(self):
        """Test that unique entry point names work correctly."""
        # Create mock entry points with different names
        mock_ep1 = MagicMock()
        mock_ep1.name = 'segment1'
        mock_ep1.value = 'package1.segments:Segment1'
        mock_ep1.dist.name = 'package1'

        mock_ep2 = MagicMock()
        mock_ep2.name = 'segment2'  # Different name - no collision
        mock_ep2.value = 'package2.segments:Segment2'
        mock_ep2.dist.name = 'package2'

        # Mock the entry_points() function
        mock_eps_result = MagicMock()
        mock_eps_result.select = MagicMock(return_value=[mock_ep1, mock_ep2])

        with patch('importlib.metadata.entry_points', return_value=mock_eps_result):
            test_registry = registry.HybridRegistry(
                entry_point_group='test.segments',
                lazy_import=True
            )

            # Should not raise any error
            test_registry._discover_entry_points()

            # Should have both entry points cached
            assert len(test_registry._entry_points_cache) == 2
            assert 'segment1' in test_registry._entry_points_cache
            assert 'segment2' in test_registry._entry_points_cache

    def test_collision_detection_with_multiple_conflicts(self):
        """Test that multiple collisions are all reported."""
        # Create multiple pairs of colliding entry points
        mock_ep1 = MagicMock()
        mock_ep1.name = 'seg1'
        mock_ep1.value = 'pkg1.seg:Seg1'
        mock_ep1.dist.name = 'pkg1'

        mock_ep2 = MagicMock()
        mock_ep2.name = 'seg1'  # Collision with ep1
        mock_ep2.value = 'pkg2.seg:Seg1'
        mock_ep2.dist.name = 'pkg2'

        mock_ep3 = MagicMock()
        mock_ep3.name = 'seg2'
        mock_ep3.value = 'pkg3.seg:Seg2'
        mock_ep3.dist.name = 'pkg3'

        mock_ep4 = MagicMock()
        mock_ep4.name = 'seg2'  # Collision with ep3
        mock_ep4.value = 'pkg4.seg:Seg2'
        mock_ep4.dist.name = 'pkg4'

        mock_eps_result = MagicMock()
        mock_eps_result.select = MagicMock(return_value=[mock_ep1, mock_ep2, mock_ep3, mock_ep4])

        with patch('importlib.metadata.entry_points', return_value=mock_eps_result):
            test_registry = registry.HybridRegistry(
                entry_point_group='test.segments',
                lazy_import=True
            )

            # Should raise ValueError with both conflicts mentioned
            with pytest.raises(ValueError) as exc_info:
                test_registry._discover_entry_points()

            error_msg = str(exc_info.value)
            # Should mention both colliding names
            assert 'seg1' in error_msg
            assert 'seg2' in error_msg
