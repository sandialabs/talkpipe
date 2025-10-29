
from talkpipe.data.text import operations as ops


def test_shingle_generator_count_mode():
    """Test shingle_generator function in count mode (counting chunks)."""
    texts = [
        "The quick brown fox jumps over the lazy dog",
        "The rain in Spain stays mainly in the plain"
    ]
    items = [{"key":1, "text":word} for word in texts[0].split(" ")]
    items.extend([{"key":2, "text":word} for word in texts[1].split(" ")])

    # Test with overlap
    result = list(ops.shingle_generator(
        items,
        string_field="text",
        key_field="key",
        shingle_size=3,
        overlap=2
    ))

    # Extract just the shingle text from (item, shingle_text) tuples
    shingles = [shingle_text for _, shingle_text in result]

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
    assert shingles == expected_shingles, f"Expected {expected_shingles}, got {shingles}"

    # Test with no overlap
    result_no_overlap = list(ops.shingle_generator(
        items,
        string_field="text",
        key_field="key",
        shingle_size=4,
        overlap=0
    ))

    shingles_no_overlap = [shingle_text for _, shingle_text in result_no_overlap]
    expected_shingles_no_overlap = [
        "The quick brown fox",
        "jumps over the lazy",
        "dog",
        "The rain in Spain",
        "stays mainly in the",
        "plain"
    ]
    assert shingles_no_overlap == expected_shingles_no_overlap, f"Expected {expected_shingles_no_overlap}, got {shingles_no_overlap}"


def test_shingle_generator_length_mode():
    """Test shingle_generator function in length mode (measuring character length)."""
    texts = [
        "The quick brown fox jumps over the lazy dog",
        "The rain in Spain stays mainly in the plain"
    ]
    items = [{"key":1, "text":word} for word in texts[0].split(" ")]
    items.extend([{"key":2, "text":word} for word in texts[1].split(" ")])

    # Test shingling by length with minimum length of 15 characters, overlap of 1 chunk
    result = list(ops.shingle_generator(
        items,
        string_field="text",
        key_field="key",
        shingle_size=15,
        overlap=1,
        size_mode="length"
    ))

    shingles = [shingle_text for _, shingle_text in result]

    # Shingles are yielded as soon as they reach minimum length (15 chars)
    # With overlap=1, we keep the last 1 chunk when creating next shingle
    expected_shingles = [
        "The quick brown",        # 15 chars (yields immediately when threshold reached)
        "brown fox jumps",        # 15 chars (starting from "brown" due to overlap=1)
        "jumps over the lazy",    # 19 chars
        "The rain in Spain",      # 17 chars
        "Spain stays mainly",     # 18 chars
        "mainly in the plain"     # 19 chars
    ]
    assert shingles == expected_shingles, f"Expected {expected_shingles}, got {shingles}"

    # Test with no overlap
    result_no_overlap = list(ops.shingle_generator(
        items,
        string_field="text",
        key_field="key",
        shingle_size=20,
        overlap=0,
        size_mode="length"
    ))

    shingles_no_overlap = [shingle_text for _, shingle_text in result_no_overlap]

    # With size_mode="length" and shingle_size=20, collect chunks until length >= 20
    # Yields as soon as threshold is reached, then clears (overlap=0)
    # Incomplete final shingles are also yielded because overlap=0
    expected_no_overlap = [
        "The quick brown fox jumps",  # 25 chars (yields when >= 20)
        "over the lazy dog",  # 17 chars (incomplete final)
        "The rain in Spain stays",  # 23 chars (yields when >= 20)
        "mainly in the plain"  # 19 chars (incomplete final)
    ]
    assert shingles_no_overlap == expected_no_overlap, f"Expected {expected_no_overlap}, got {shingles_no_overlap}"


def test_shingle_generator_no_field():
    """Test shingle_generator with simple strings (no field extraction)."""
    words = ["The", "quick", "brown", "fox"]

    result = list(ops.shingle_generator(
        words,
        string_field=None,
        key_field=None,
        shingle_size=2,
        overlap=1
    ))

    shingles = [shingle_text for _, shingle_text in result]
    expected = ["The quick", "quick brown", "brown fox"]
    assert shingles == expected, f"Expected {expected}, got {shingles}"
