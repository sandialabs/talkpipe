import pytest
from talkpipe.data.text import chunking_units as ch


def test_shingleText_basic_integration():
    """Test that ShingleText class correctly integrates with shingle_generator."""
    items = [{"text": word} for word in ["The", "quick", "brown", "fox"]]

    # Test basic functionality - returns shingle strings
    shingler = ch.ShingleText(field="text", shingle_size=2, overlap=0)
    shingler = shingler.as_function()
    result = list(shingler(items))

    # Just verify it produces shingles, detailed logic is tested in test_operations
    assert len(result) == 2
    assert result[0] == "The quick"
    assert result[1] == "brown fox"


def test_shingleText_set_as_parameter():
    """Test that ShingleText correctly uses set_as parameter to attach shingles to items."""
    items = [{"key": 1, "text": word} for word in ["The", "quick", "brown", "fox"]]

    # Test set_as parameter - should return modified items with shingle field
    shingler = ch.ShingleText(field="text", key="key", set_as="shingle", shingle_size=2, overlap=0)
    shingler = shingler.as_function()
    result = list(shingler(items))

    # Verify it returns dicts with the shingle field
    assert len(result) == 2
    assert isinstance(result[0], dict)
    assert "shingle" in result[0]
    assert result[0]["shingle"] == "The quick"
    assert result[0]["key"] == 1
    assert result[0]["text"] == "quick"  # Last item in the shingle

    assert result[1]["shingle"] == "brown fox"
    assert result[1]["key"] == 1
    assert result[1]["text"] == "fox"


def test_shingleText_size_mode_parameter():
    """Test that ShingleText correctly passes size_mode parameter to shingle_generator."""
    items = [{"text": word} for word in ["The", "quick", "brown", "fox", "jumps"]]

    # Test size_mode="length" - minimum character length
    shingler = ch.ShingleText(field="text", shingle_size=10, overlap=0, size_mode="length")
    shingler = shingler.as_function()
    result = list(shingler(items))

    # Just verify it works with size_mode, detailed logic tested in test_operations
    assert len(result) > 0
    assert all(len(s) >= 10 for s in result[:-1])  # All but last should be >= 10 chars


def test_shingleText_delimiter_parameter():
    """Test that ShingleText correctly passes delimiter parameter to shingle_generator."""
    items = [{"text": word} for word in ["The", "quick", "brown"]]

    # Test custom delimiter
    shingler = ch.ShingleText(field="text", shingle_size=2, overlap=0, delimiter="-")
    shingler = shingler.as_function()
    result = list(shingler(items))

    assert result[0] == "The-quick"


def test_splitText():
    text = "Hello world! This is a test. Let's split this text."

    # Test splitting by string
    criteria_str = " "
    splitter = ch.splitText(criteria=criteria_str)
    result_str = list(splitter([text]))
    expected_str = ["Hello", "world!", "This", "is", "a", "test.", "Let's", "split", "this", "text."]
    assert result_str == expected_str, f"Expected {expected_str}, got {result_str}"

    # Test splitting by integer
    criteria_int = 10
    splitter = ch.splitText(criteria=criteria_int)
    result_int = list(splitter([text]))
    expected_int = ["Hello worl", "d! This is", " a test. L", "et's split", " this text", "."]
    assert result_int == expected_int, f"Expected {expected_int}, got {result_int}"

    # Test invalid criteria
    with pytest.raises(ValueError):
        splitter = ch.splitText(criteria=3.5)
        list(splitter([text]))

    items = [{"text": "Hello world! This is a test.", "id": 1},
             {"text": "Another sentence here.", "id": 2}]
    splitter = ch.splitText(criteria=" ", field="text")
    result_field = list(splitter(items))
    expected_field = ["Hello", "world!", "This", "is", "a", "test.", "Another", "sentence", "here."]
    assert result_field == expected_field, f"Expected {expected_field}, got {result_field}"


def test_shingleText_emit_detail_without_set_as():
    """Test that ShingleText with emit_detail=True returns dictionaries with paragraph details."""
    items = [{"text": word} for word in ["The", "quick", "brown", "fox", "jumps", "over"]]

    # Test with emit_detail but no set_as - should return detail dicts directly
    shingler = ch.ShingleText(field="text", shingle_size=3, overlap=1, emit_detail=True)
    shingler = shingler.as_function()
    result = list(shingler(items))

    # First result should have detail dict
    assert len(result) > 0
    assert isinstance(result[0], dict)
    assert "text" in result[0]
    assert "first_paragraph" in result[0]
    assert "last_paragraph" in result[0]

    # Check first shingle
    assert result[0]["text"] == "The quick brown"
    assert result[0]["first_paragraph"] == 0
    assert result[0]["last_paragraph"] == 2

    # Check second shingle (with overlap=1, keeps last chunk which is "brown")
    assert result[1]["text"] == "brown fox jumps"
    assert result[1]["first_paragraph"] == 2
    assert result[1]["last_paragraph"] == 4


def test_shingleText_emit_detail_with_set_as():
    """Test that ShingleText with emit_detail=True and set_as appends detail dict to items."""
    items = [{"key": 1, "text": word} for word in ["The", "quick", "brown", "fox"]]

    # Test with emit_detail and set_as - should attach detail dict to items
    shingler = ch.ShingleText(field="text", key="key", set_as="shingle_detail",
                             shingle_size=2, overlap=0, emit_detail=True)
    shingler = shingler.as_function()
    result = list(shingler(items))

    # Should return items with the detail dict attached
    assert len(result) == 2
    assert isinstance(result[0], dict)
    assert "shingle_detail" in result[0]
    assert isinstance(result[0]["shingle_detail"], dict)

    # Check the detail dict structure
    detail = result[0]["shingle_detail"]
    assert detail["text"] == "The quick"
    assert detail["first_paragraph"] == 0
    assert detail["last_paragraph"] == 1

    # Original item data should still be present
    assert result[0]["key"] == 1
    assert result[0]["text"] == "quick"  # Last item in the shingle


def test_shingleText_emit_detail_false_unchanged():
    """Test that default behavior (emit_detail=False) is unchanged."""
    items = [{"text": word} for word in ["The", "quick", "brown", "fox"]]

    # Test default behavior
    shingler = ch.ShingleText(field="text", shingle_size=2, overlap=0)
    shingler = shingler.as_function()
    result = list(shingler(items))

    # Should return plain strings, not dicts
    assert len(result) == 2
    assert isinstance(result[0], str)
    assert result[0] == "The quick"
    assert result[1] == "brown fox"

def test_shingleText_single_incomplete_shingle():
    """Test that ShingleText handles single incomplete shingle correctly."""
    chunks = [{"chunk": f"Chunk_{i}", "path": "/test.txt"} for i in range(10)]

    # Configure shingling
    shingle_segment = ch.ShingleText(
        field="chunk",
        shingle_size=3,
        overlap=1,
        set_as="shingle_detail",
        key="path",
        emit_detail=True
    )

    # Process
    results = list(shingle_segment(chunks))

    assert len(results) == 5

    # Results:
    # - Input: 10 chunks (0-9)
    # - Output: 4 shingles
    # - Shingle 0: chunks [0, 1, 2]
    # - Shingle 1: chunks [2, 3, 4]
    # - Shingle 2: chunks [4, 5, 6]
    # - Shingle 3: chunks [6, 7, 8]
    # - MISSING: Chunk 9 is never included!