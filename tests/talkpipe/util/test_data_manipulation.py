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


