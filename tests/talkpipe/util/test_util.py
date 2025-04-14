import pytest
import logging
import talkpipe.llm.config
import talkpipe.util.config
from  talkpipe.util import data_manipulation
import talkpipe.util.os
from testutils import monkeypatched_env
import subprocess, os, sys
from unittest.mock import patch
from  pydantic import BaseModel
from talkpipe.pipe.core import AbstractSegment

####################################################################
# NOTE: These test cases test functionality in talkpipe.util.*
# That's because they were originally in a single file.    This
# Write future unit tests in files cooresponding to the source
# files and copy these out.
####################################################################

def test_run_command_basic():
    """Test basic command execution."""
    # Use a cross-platform command that's almost guaranteed to exist
    if sys.platform.startswith('win'):
        # Windows-specific command
        command = "echo Hello, World!"
    else:
        # Unix/Linux command
        command = "echo 'Hello, World!'"
    
    # Collect output lines
    output_lines = list(talkpipe.util.os.run_command(command))
    
    # Assertions
    assert len(output_lines) == 1
    assert output_lines[0] == "Hello, World!"

def test_run_command_multiple_lines():
    """Test command that produces multiple lines of output."""
    if sys.platform.startswith('win'):
        # Windows: use dir to list files
        command = "dir"
    else:
        # Unix/Linux: use ls to list files
        command = "ls"
    
    # Collect output lines
    output_lines = list(talkpipe.util.os.run_command(command))
    
    # Assertions
    assert len(output_lines) > 0  # Should have at least one line
    assert all(isinstance(line, str) for line in output_lines)  # All lines should be strings

def test_run_command_error_handling():
    """Test error handling for invalid command."""
    # Use a command that's extremely unlikely to exist
    command = "this_command_definitely_does_not_exist_12345"
    
    # Should raise CalledProcessError or print error message
    with pytest.raises(subprocess.CalledProcessError):
        list(talkpipe.util.os.run_command(command))

def test_run_command_with_arguments():
    """Test command with multiple arguments."""
    if sys.platform.startswith('win'):
        # Windows: use findstr (equivalent to grep)
        command = 'echo "apple\nbanana\ncherry" | findstr "a"'
    else:
        # Unix/Linux: use grep
        command = 'printf "apple\nbanana\ncherry" | grep "a"'
    
    # Collect output lines
    output_lines = list(talkpipe.util.os.run_command(command))
    
    # Assertions
    assert len(output_lines) == 2
    assert "apple" in output_lines
    assert "banana" in output_lines

def test_get_all_attributes():
    class TestClass:
        def __init__(self):
            self.a = 1
            self.b = 2
            self.c = 3
    tc = TestClass()
    assert data_manipulation.get_all_attributes(tc) == ["a", "b", "c"]

    obj = {"key": "value", "key2": {"ka": "va", "kb": "vb"}}
    obj_d = data_manipulation.get_all_attributes(obj)
    assert obj_d == ["key", {"key2": ["ka", "kb"]}]

class TestExtractProperty:
    a_dict = {"key": "value"}
    a_list = ["a", "b", "c"]

    @property
    def a_property(self):
        return "a_value"
    
    def a_func(self):
        return "a_result"
    
    
def test_extract_property():
    x = {"a": 1, "b": 2}
    assert data_manipulation.extract_property(x, "a") == 1

    x = {"a": 1, "b": [6, 7, 8]}
    assert data_manipulation.extract_property(x, "b.1") == 7

    tep = TestExtractProperty()
    assert data_manipulation.extract_property(tep, "a_dict.key") == "value"
    assert data_manipulation.extract_property(tep, "a_list.1") == "b"
    assert data_manipulation.extract_property(tep, "a_property") == "a_value"
    assert data_manipulation.extract_property(tep, "a_func") == "a_result"
    assert data_manipulation.extract_property(tep, "a_dict.key2", False) == None

    with pytest.raises(AttributeError):
        data_manipulation.extract_property(tep, "a_dict.key2", True)


def test_extract_property_with_pydantic():
    class TestModel(BaseModel):
        a: int

    x = TestModel(a=1)
    assert data_manipulation.extract_property(x, "a") == 1

    y = {"v": x}
    assert data_manipulation.extract_property(y, "v.a") == 1

def test_parse_key_value_list():
    assert talkpipe.util.config.parse_key_value_str("a:b,c") == {"a": "b", "c": "c"}
    assert talkpipe.util.config.parse_key_value_str("a:b,c:d") == {"a": "b", "c": "d"}
    assert talkpipe.util.config.parse_key_value_str("a,b,c") == {"a": "a", "b": "b", "c": "c"}
    assert talkpipe.util.config.parse_key_value_str("a,b,c:d") == {"a": "a", "b": "b", "c": "d"}
    assert talkpipe.util.config.parse_key_value_str("a:b,c:d,e:f") == {"a": "b", "c": "d", "e": "f"}
    assert talkpipe.util.config.parse_key_value_str("_") == {"_": "original"}
    assert talkpipe.util.config.parse_key_value_str("a") == {"a": "a"}
    assert talkpipe.util.config.parse_key_value_str("a:b") == {"a": "b"}
    assert talkpipe.util.config.parse_key_value_str("a:b,c") == {"a": "b", "c": "c"}
    assert talkpipe.util.config.parse_key_value_str("a:b,c:d") == {"a": "b", "c": "d"}
    assert talkpipe.util.config.parse_key_value_str("a,b,c") == {"a": "a", "b": "b", "c": "c"}
    assert talkpipe.util.config.parse_key_value_str("a,b,c:d") == {"a": "a", "b": "b", "c": "d"}
    assert talkpipe.util.config.parse_key_value_str("a, b, c: d") == {"a": "a", "b": "b", "c": "d"}

    assert talkpipe.util.config.parse_key_value_str("a:b,c", False) == {"a": "b", "c": "c"}
    with pytest.raises(ValueError):
        assert talkpipe.util.config.parse_key_value_str("a:b,c", True)




def test_get_type_safely():
    t = talkpipe.util.data_manipulation.get_type_safely("int")
    assert t == int

    t = talkpipe.util.data_manipulation.get_type_safely("AbstractSegment", "talkpipe.pipe.core")
    assert t == AbstractSegment

    t = talkpipe.util.data_manipulation.get_type_safely("talkpipe.pipe.core.AbstractSegment")
    assert t == AbstractSegment
    
    
def test_get_config(tmp_path, monkeypatch):
    # Reset the configuration before starting and ensure a clean environment
    talkpipe.util.config.reset_config()
    original_environ = os.environ.copy()
    
    # Create a clean test environment
    monkeypatch.setattr(os, 'environ', {})
    
    try:
        test_path = tmp_path / "test.toml"
        assert talkpipe.util.config._config is None

        # Add environment variables in a controlled way
        monkeypatch.setenv("TALKPIPE_" + talkpipe.llm.config.TALKPIPE_MODEL_NAME, "llama3.1")
        monkeypatch.setenv("TALKPIPE_" + talkpipe.llm.config.TALKPIPE_SOURCE, "ollama")
        
        # When no configuration file exists, get_config will initialize the config.
        cfg = talkpipe.util.config.get_config(path=test_path)
        assert talkpipe.util.config._config is not None
        assert len(cfg) == 2
        assert talkpipe.llm.config.TALKPIPE_MODEL_NAME in cfg
        assert talkpipe.llm.config.TALKPIPE_SOURCE in cfg

        # Write a configuration file with values that differ from the env vars.
        with open(test_path, "w") as file:
            file.write(
                """
                %s = "silly"
                %s = "beans"
                """ % (talkpipe.llm.config.TALKPIPE_MODEL_NAME, talkpipe.llm.config.TALKPIPE_SOURCE)
            )

        # Reload the config: env vars should override the values in the file.
        cfg = talkpipe.util.config.get_config(path=test_path, reload=True)
        assert len(cfg) == 2
        # The environment variable values take precedence over the file.
        assert cfg[talkpipe.llm.config.TALKPIPE_MODEL_NAME] == "llama3.1"
        assert cfg[talkpipe.llm.config.TALKPIPE_SOURCE] == "ollama"

        # Remove environment variables to test file-only mode
        monkeypatch.delenv("TALKPIPE_" + talkpipe.llm.config.TALKPIPE_MODEL_NAME)
        monkeypatch.delenv("TALKPIPE_" + talkpipe.llm.config.TALKPIPE_SOURCE)
        
        talkpipe.util.config.reset_config()
        # Here, ignore_env=True tells get_config to load values directly from the file.
        cfg = talkpipe.util.config.get_config(path=test_path, reload=True, ignore_env=True)
        assert len(cfg) == 2
        assert cfg[talkpipe.llm.config.TALKPIPE_MODEL_NAME] == "silly"
        assert cfg[talkpipe.llm.config.TALKPIPE_SOURCE] == "beans"
    
    finally:
        # Ensure we reset everything at the end
        talkpipe.util.config.reset_config()

    
def test_configure_logging(tmp_path, capsys):

    talkpipe.util.config.configure_logger("talkpipe.test:INFO")
    logger = logging.getLogger("talkpipe.test")
    assert logger.level == logging.INFO
    logger.debug("This is a test debug message")
    logger.info("This is a test info message")
    logger.warning("This is a test warning message")
    logger.error("This is a test error message")
    logger.critical("This is a test critical message")
    captured = capsys.readouterr()
    assert "DEBUG" not in captured.err
    assert "INFO" in captured.err
    assert "WARNING" in captured.err
    assert "ERROR" in captured.err
    assert "CRITICAL" in captured.err

    log_file = tmp_path / "test.log"

    talkpipe.util.config.configure_logger("talkpipe.test:WARNING", logger_files=f"talkpipe.test:{log_file}")
    logger = logging.getLogger("talkpipe.test")
    assert logger.level == logging.WARNING
    logger.debug("This is a test debug message")
    logger.info("This is a test info message")
    logger.warning("This is a test warning message")
    logger.error("This is a test error message")
    logger.critical("This is a test critical message")
    captured = capsys.readouterr()
    assert "DEBUG" not in captured.err
    assert "INFO" not in captured.err
    assert "WARNING" in captured.err
    assert "ERROR" in captured.err
    assert "CRITICAL" in captured.err

    log_file = next(tmp_path.glob('*.log'))
    assert log_file.exists()
    with open(log_file, "r") as file:
        log_data = file.read()
        assert "DEBUG" not in log_data
        assert "INFO" not in log_data
        assert "WARNING" in log_data
        assert "ERROR" in log_data
        assert "CRITICAL" in log_data

def test_get_config_nofile(monkeypatch, monkeypatched_env):
    monkeypatched_env({
        "TALKPIPE_FUNNY_ITEM": "silly",
        "X": "Y"
    })

    monkeypatch.setattr(os.path, "exists", lambda path: False)

    talkpipe.util.config.reset_config()

    cfg = talkpipe.util.config.get_config()
    assert len(cfg) == 1
    assert "funny_item" in cfg
    assert cfg["funny_item"] == "silly"


def test_extract_field_names_basic():
    """Test basic field extraction."""
    template = "Hello, {name}! Today is {day}."
    expected = ["name", "day"]
    assert sorted(talkpipe.util.data_manipulation.extract_template_field_names(template)) == sorted(expected)

def test_extract_field_names_with_braces():
    """Test field extraction with template surrounded by braces."""
    template = "{Hello, {name}! Today is {day}.}"
    expected = sorted(["name", "day"])
    ans = sorted(talkpipe.util.data_manipulation.extract_template_field_names(template))
    assert ans == sorted(expected)

def test_extract_field_names_with_escaped_braces():
    """Test field extraction with escaped braces."""
    template = "{{ This has literal braces and {field} }}"
    expected = ["field"]
    assert talkpipe.util.data_manipulation.extract_template_field_names(template) == expected

def test_extract_field_names_no_fields():
    """Test field extraction with no fields."""
    template = "No fields here"
    expected = []
    assert talkpipe.util.data_manipulation.extract_template_field_names(template) == expected

def test_extract_field_names_only_escaped_braces():
    """Test field extraction with only escaped braces."""
    template = "Only {{ escaped }} braces here"
    expected = []
    assert talkpipe.util.data_manipulation.extract_template_field_names(template) == expected

def test_extract_field_names_with_duplicates():
    """Test field extraction with duplicate fields."""
    template = "{name} is {name} and {name} is {age}"
    expected = ["name", "age"]
    assert sorted(talkpipe.util.data_manipulation.extract_template_field_names(template)) == sorted(expected)

def test_extract_field_names_with_spaces():
    """Test field extraction with spaces in field names."""
    template = "Hello, {user name}! Your {account type} is ready."
    expected = ["user name", "account type"]
    assert sorted(talkpipe.util.data_manipulation.extract_template_field_names(template)) == sorted(expected)

def test_extract_field_names_with_special_chars():
    """Test field extraction with special characters in field names."""
    template = "Hello, {user-name}! Your {account_type} and {item#123} are ready."
    expected = ["user-name", "account_type", "item#123"]
    assert sorted(talkpipe.util.data_manipulation.extract_template_field_names(template)) == sorted(expected)


# Tests for fill_template function
def test_fill_template_basic():
    """Test basic template filling."""
    template = "Hello, {name}! Today is {day}."
    values = {"name": "Alice", "day": "Monday"}
    expected = "Hello, Alice! Today is Monday."
    assert talkpipe.util.data_manipulation.fill_template(template, values) == expected

def test_fill_template_with_braces():
    """Test template filling with template surrounded by braces."""
    template = "{Hello, {name}! Today is {day}.}"
    values = {"name": "Alice", "day": "Monday"}
    expected = "{Hello, Alice! Today is Monday.}"
    assert talkpipe.util.data_manipulation.fill_template(template, values) == expected

def test_fill_template_with_escaped_braces():
    """Test template filling with escaped braces."""
    template = "{{ This has literal braces and {field} }}"
    values = {"field": "value"}
    expected = "{ This has literal braces and value }"
    assert talkpipe.util.data_manipulation.fill_template(template, values) == expected

def test_fill_template_missing_values():
    """Test template filling with missing values."""
    template = "Hello, {name}! Today is {day}."
    values = {"name": "Alice"}  # Missing "day"
    expected = "Hello, Alice! Today is {day}."  # {day} remains unchanged
    assert talkpipe.util.data_manipulation.fill_template(template, values) == expected

def test_fill_template_no_fields():
    """Test template filling with no fields."""
    template = "No fields here"
    values = {"name": "Alice"}
    expected = "No fields here"
    assert talkpipe.util.data_manipulation.fill_template(template, values) == expected

def test_fill_template_with_non_string_values():
    """Test template filling with non-string values."""
    template = "{name} is {age} years old and has ${balance}."
    values = {"name": "Bob", "age": 25, "balance": 125.50}
    expected = "Bob is 25 years old and has $125.5."
    assert talkpipe.util.data_manipulation.fill_template(template, values) == expected

def test_fill_template_with_multiple_same_fields():
    """Test template filling with multiple occurrences of the same field."""
    template = "{name} is {name} is {name}!"
    values = {"name": "Alice"}
    expected = "Alice is Alice is Alice!"
    assert talkpipe.util.data_manipulation.fill_template(template, values) == expected

def test_fill_template_complex():
    """Test complex template filling with mixed scenarios."""
    template = "{{ User {name} }} has {{id}} {id} and {type} {{type}}"
    values = {"name": "Charlie", "id": 12345, "type": "admin"}
    expected = "{ User Charlie } has {id} 12345 and admin {type}"
    assert talkpipe.util.data_manipulation.fill_template(template, values) == expected

def test_fill_template_extra_values():
    """Test template filling with extra values not in template."""
    template = "Hello, {name}!"
    values = {"name": "Alice", "age": 30, "city": "New York"}
    expected = "Hello, Alice!"
    assert talkpipe.util.data_manipulation.fill_template(template, values) == expected

