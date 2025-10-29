from email.mime import text
import pytest

from talkpipe.data.text import chunking as ch

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

def test_shingleText():
    texts = [
        "The quick brown fox jumps over the lazy dog",
        "The rain in Spain stays mainly in the plain"
    ]
    items = [{"key":1, "text":word} for word in texts[0].split(" ")]
    items.extend([{"key":2, "text":word} for word in texts[1].split(" ")])

    shingler = ch.ShingleText(field="text", key="key", shingle_size=3, overlap=2)
    shingler = shingler.as_function()
    result = list(shingler(items))
    expected_shingles = [
        "The quick brown",
        "quick brown fox",
        "brown fox jumps",
        "fox jumps over",
        "jumps over the",
        "over the lazy",
        "the lazy dog",
        "The rain in",
        "rain in Spain",
        "in Spain stays",
        "Spain stays mainly",
        "stays mainly in",
        "mainly in the",
        "in the plain"
    ]
    assert result == expected_shingles, f"Expected {expected_shingles}, got {result}"
    
    # Test shingling with no overlap
    shingler_no_overlap = ch.ShingleText(field="text", key="key", set_as="shingles", shingle_size=4, overlap=0)
    shingler_no_overlap = shingler_no_overlap.as_function()
    result_no_overlap = list(shingler_no_overlap(items))
    expected_shingles_no_overlap = [
        {"key": 1, "text": "fox", "shingles": "The quick brown fox"},
        {"key": 1, "text": "lazy", "shingles": "jumps over the lazy"},
        {"key": 1, "text": "dog", "shingles": "dog"},
        {"key": 2, "text": "Spain", "shingles": "The rain in Spain"},
        {"key": 2, "text": "the", "shingles": "stays mainly in the"},
        {"key": 2, "text": "plain", "shingles": "plain"}
    ]
    assert result_no_overlap == expected_shingles_no_overlap, f"Expected {expected_shingles_no_overlap}, got {result_no_overlap}"