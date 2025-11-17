import json
import pytest
from pydantic import BaseModel
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


def test_extract_property_underscore_passthrough():
    """Test that '_' acts as a passthrough in dotted paths.

    The '_' character should:
    - Return the entire item when used by itself
    - Act as a no-op (passthrough) when used in a dotted path

    Examples:
    - "X._" should be equivalent to "X"
    - "X._.1" should be equivalent to "X.1"
    - "_.1" should be equivalent to "1"
    """
    # Test 1: X._ should be equivalent to X
    data1 = {"X": ["a", "b", "c"]}
    result1 = data_manipulation.extract_property(data1, "X._")
    expected1 = data_manipulation.extract_property(data1, "X")
    assert result1 == expected1, f"X._ should return {expected1}, but got {result1}"
    assert result1 == ["a", "b", "c"]

    # Test 2: X._.1 should be equivalent to X.1
    data2 = {"X": ["a", "b", "c"]}
    result2 = data_manipulation.extract_property(data2, "X._.1")
    expected2 = data_manipulation.extract_property(data2, "X.1")
    assert result2 == expected2, f"X._.1 should return {expected2}, but got {result2}"
    assert result2 == "b"

    # Test 3: Multiple underscores should all be treated as passthrough
    data3 = {"nested": {"deep": {"value": 42}}}
    result3 = data_manipulation.extract_property(data3, "nested._.deep._.value")
    expected3 = data_manipulation.extract_property(data3, "nested.deep.value")
    assert result3 == expected3, f"nested._.deep._.value should return {expected3}, but got {result3}"
    assert result3 == 42

    # Test 4: _ by itself should still return the entire item
    data4 = {"foo": "bar"}
    result4 = data_manipulation.extract_property(data4, "_")
    assert result4 == data4, f"_ by itself should return the entire item"

    # Test 5: _.1 should be equivalent to 1 (underscore at the beginning)
    data5 = ["a", "b", "c"]
    result5 = data_manipulation.extract_property(data5, "_.1")
    expected5 = data_manipulation.extract_property(data5, "1")
    assert result5 == expected5, f"_.1 should return {expected5}, but got {result5}"
    assert result5 == "b"


def test_assign_property_dict():
    """Test assign_property works with dictionaries."""
    data = {"a": 1, "b": 2}
    data_manipulation.assign_property(data, "c", 3)
    assert data["c"] == 3
    assert data == {"a": 1, "b": 2, "c": 3}

    # Test overwriting existing property
    data_manipulation.assign_property(data, "a", 10)
    assert data["a"] == 10


def test_assign_property_pydantic():
    """Test assign_property works with pydantic models."""

    class TestModel(BaseModel):
        model_config = {"extra": "allow"}  # Allow extra fields
        a: int
        b: int

    model = TestModel(a=1, b=2)

    # Test 1: Overwrite a declared field
    data_manipulation.assign_property(model, "a", 10)
    assert model.a == 10
    assert model.b == 2

    # Test 2: Overwrite another declared field
    data_manipulation.assign_property(model, "b", 20)
    assert model.b == 20
    assert model.a == 10

    # Test 3: Add a new extra field (requires extra='allow')
    data_manipulation.assign_property(model, "c", 3)
    assert model.c == 3
    assert model.a == 10
    assert model.b == 20


def test_assign_property_plain_object():
    """Test assign_property works with plain Python objects."""

    class PlainObject:
        def __init__(self):
            self.a = 1
            self.b = 2

    obj = PlainObject()

    # Add a new attribute
    data_manipulation.assign_property(obj, "c", 3)
    assert obj.c == 3
    assert obj.a == 1
    assert obj.b == 2

    # Overwrite existing attribute
    data_manipulation.assign_property(obj, "a", 10)
    assert obj.a == 10


def test_assign_property_different_types():
    """Test assign_property with different value types."""
    data = {}

    # String value
    data_manipulation.assign_property(data, "string_field", "hello")
    assert data["string_field"] == "hello"

    # List value
    data_manipulation.assign_property(data, "list_field", [1, 2, 3])
    assert data["list_field"] == [1, 2, 3]

    # Dict value
    data_manipulation.assign_property(data, "dict_field", {"nested": "value"})
    assert data["dict_field"] == {"nested": "value"}

    # None value
    data_manipulation.assign_property(data, "none_field", None)
    assert data["none_field"] is None


