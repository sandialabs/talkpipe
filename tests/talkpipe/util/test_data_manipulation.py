import json
import pytest
from talkpipe.util import data_manipulation

# Note that many of the utils for this module are in test_util.py because of an earlier refactor.
@pytest.mark.parametrize(
    "item, expected",
    [
        (
            {"name": "Alice", "age": 30},
            "name: Alice\nage: 30"
        ),
        (
            {"name": "Bob", "active": True},
            "name: Bob\nactive: True"
        ),
        (
            {"price": 1234.5678},
            "price: 1234.5678"
        ),
        (
            {"description": "This is a long text. " * 20},
            None  # We'll check for wrapping, not exact string
        ),
        (
            {"html": "<b>Bold</b> and <i>italic</i>."},
            "html: <b>Bold</b> and <i>italic</i>."  # The script does not clean HTML, so we expect raw HTML
        ),
        (
            {"missing": None},
            "missing: None"
        ),
        (
            {"nested": {"x": 1}},
            "nested: {'x': 1}"
        ),
    ]
)
def test_dict_to_text(item, expected):
    result = data_manipulation.dict_to_text(item)
    if expected is not None:
        assert result == expected
    else:
        # For long text, check wrapping and presence of content
        assert "This is a long text." in result
        assert "\n" in result

def test_dict_to_text_separator_and_field_separator():
    item = {"a": 1, "b": 2}
    out = data_manipulation.dict_to_text(item, field_name_separator=" = ", field_separator=" | ")
    assert out == "a = 1 | b = 2"


def test_compileLambda_blocks_import():
    """Test that __import__ is blocked in compileLambda expressions."""
    try:
        dangerous_lambda = data_manipulation.compileLambda("__import__('os')")
        result = dangerous_lambda(1)
        # If we get here, the vulnerability exists - fail the test
        pytest.fail(f"SECURITY VULNERABILITY: __import__ was accessible and returned: {type(result)}")
    except ValueError:
        # This is the expected secure behavior
        pass


def test_compileLambda_blocks_open():
    """Test that open() is blocked in compileLambda expressions."""
    try:
        dangerous_lambda = data_manipulation.compileLambda("open('/etc/passwd')")
        result = dangerous_lambda(1)
        # If we get here, the vulnerability exists - fail the test
        pytest.fail(f"SECURITY VULNERABILITY: open() was accessible and returned: {type(result)}")
    except ValueError:
        # This is the expected secure behavior
        pass


def test_compileLambda_blocks_exec():
    """Test that exec is blocked in compileLambda expressions."""
    try:
        dangerous_lambda = data_manipulation.compileLambda("exec('print(1)')")
        result = dangerous_lambda(1)
        # If we get here, the vulnerability exists - fail the test
        pytest.fail(f"SECURITY VULNERABILITY: exec was accessible and returned: {type(result)}")
    except ValueError:
        # This is the expected secure behavior
        pass


def test_compileLambda_safe_operations_work():
    """Test that safe operations continue to work in compileLambda."""
    # Test basic math
    math_lambda = data_manipulation.compileLambda("item * 2")
    assert math_lambda(5) == 10
    
    # Test safe builtins
    len_lambda = data_manipulation.compileLambda("len(item)")
    assert len_lambda([1, 2, 3]) == 3
    
    # Test string operations
    str_lambda = data_manipulation.compileLambda("str(item).upper()")
    assert str_lambda("hello") == "HELLO"


