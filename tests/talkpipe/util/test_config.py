"""Tests for talkpipe.util.config module."""
import os
import tempfile
import pytest
from pathlib import Path
from unittest.mock import patch, mock_open
from talkpipe.util.config import load_script, reset_config, get_config


class TestLoadScript:
    """Test cases for the load_script function."""
    
    def test_load_script_inline_simple(self):
        """Test loading inline script content."""
        script_content = "not really a script"
        result = load_script(script_content)
        assert result == script_content
    
    def test_load_script_inline_complex(self):
        """Test loading complex inline script content."""
        script_content = """
Not really a script
with multiple lines and special characters like !@#$%^&*()_+.
        """.strip()
        result = load_script(script_content)
        assert result == script_content
    
    def test_load_script_empty_input(self):
        """Test that empty input raises ValueError."""
        with pytest.raises(ValueError, match="script_input cannot be None or empty"):
            load_script("")
    
    def test_load_script_none_input(self):
        """Test that None input raises ValueError."""
        with pytest.raises(ValueError, match="script_input cannot be None or empty"):
            load_script(None)
    
    def test_load_script_whitespace_input(self):
        """Test that whitespace-only input raises ValueError."""
        with pytest.raises(ValueError, match="script_input cannot be None or empty"):
            load_script("   ")
    
    def test_load_script_from_file(self):
        """Test loading script from an existing file."""
        script_content = "not really a script"
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.tp', delete=False) as f:
            f.write(script_content)
            temp_path = f.name
        
        try:
            result = load_script(temp_path)
            assert result == script_content
        finally:
            os.unlink(temp_path)
    
    def test_load_script_from_file_utf8(self):
        """Test loading script with UTF-8 characters from file."""
        script_content = "print('héllo wørld 🌍')"
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.tp', delete=False, encoding='utf-8') as f:
            f.write(script_content)
            temp_path = f.name
        
        try:
            result = load_script(temp_path)
            assert result == script_content
        finally:
            os.unlink(temp_path)
    
    def test_load_script_file_not_readable(self):
        """Test IOError when file exists but cannot be read."""
        # Skip test when running as root (e.g., in Docker builds)
        # Root can bypass file permission restrictions
        if os.getuid() == 0:
            pytest.skip("Test skipped when running as root - root bypasses file permissions")
            
        with tempfile.NamedTemporaryFile(delete=False) as f:
            temp_path = f.name
        
        try:
            # Make file unreadable
            os.chmod(temp_path, 0o000)
            
            with pytest.raises(IOError, match="Failed to read script file"):
                load_script(temp_path)
        finally:
            # Restore permissions and cleanup
            os.chmod(temp_path, 0o644)
            os.unlink(temp_path)
    
    def test_load_script_from_config_file_entry(self):
        """Test loading script from talkpipe configuration file."""
        script_content = "print('from config file')"
        config_content = f'my_script = "{script_content}"'
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.toml', delete=False) as f:
            f.write(config_content)
            config_path = f.name
        
        try:
            # Reset config to force reload
            reset_config()
            
            # Mock get_config to return our test config
            with patch('talkpipe.util.config.get_config') as mock_get_config:
                mock_get_config.return_value = {'my_script': script_content}
                
                result = load_script('my_script')
                assert result == script_content
                mock_get_config.assert_called_once()
        finally:
            os.unlink(config_path)
            reset_config()
    
    def test_load_script_from_environment_variable(self):
        """Test loading script from environment variable via config."""
        script_content = "print('from env var')"
        
        # Reset config to force reload
        reset_config()
        
        with patch('os.environ', {'TALKPIPE_TEST_VAR': script_content}):
            with patch('argparse.ArgumentParser.parse_args') as mock_args:
            
                result = load_script('TEST_VAR')
                assert result == script_content
    
    def test_load_script_config_key_not_found_falls_back_to_inline(self):
        """Test that non-existent config key falls back to inline script."""
        script_content = "nonexistent_key"
        
        # Reset config to force reload
        reset_config()
        
        # Mock get_config to return empty config
        with patch('talkpipe.util.config.get_config') as mock_get_config:
            mock_get_config.return_value = {}
            
            result = load_script(script_content)
            assert result == script_content
            mock_get_config.assert_called_once()
    
    def test_load_script_priority_file_over_config(self):
        """Test that existing file takes priority over config entry."""
        script_from_file = "print('from file')"
        script_from_config = "print('from config')"
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.tp', delete=False) as f:
            f.write(script_from_file)
            temp_path = f.name
        
        try:
            # Reset config to force reload
            reset_config()
            
            # Mock get_config to return config with same key as file path
            with patch('talkpipe.util.config.get_config') as mock_get_config:
                mock_get_config.return_value = {temp_path: script_from_config}
                
                result = load_script(temp_path)
                # Should return content from file, not config
                assert result == script_from_file
        finally:
            os.unlink(temp_path)
            reset_config()
    
    def test_load_script_priority_config_over_inline(self):
        """Test that config entry takes priority over inline interpretation."""
        config_key = "ambiguous_content"
        script_from_config = "print('from config')"
        
        # Reset config to force reload
        reset_config()
        
        # Mock get_config to return config entry
        with patch('talkpipe.util.config.get_config') as mock_get_config:
            mock_get_config.return_value = {config_key: script_from_config}
            
            result = load_script(config_key)
            # Should return content from config, not treat as inline
            assert result == script_from_config
            mock_get_config.assert_called_once()
    
    def test_load_script_file_path_with_spaces(self):
        """Test loading script from file path containing spaces."""
        script_content = "print('file with spaces')"
        
        with tempfile.NamedTemporaryFile(mode='w', suffix=' test file.tp', delete=False) as f:
            f.write(script_content)
            temp_path = f.name
        
        try:
            result = load_script(temp_path)
            assert result == script_content
        finally:
            os.unlink(temp_path)
    
    def test_load_script_multiline_inline(self):
        """Test loading multiline inline script."""
        script_content = """line1
line2
line3"""
        result = load_script(script_content)
        assert result == script_content
    
    def test_load_script_relative_path_not_existing(self):
        """Test that relative path that doesn't exist is treated as inline."""
        script_input = "./nonexistent/script.tp"
        result = load_script(script_input)
        # Should treat as inline since file doesn't exist
        assert result == script_input