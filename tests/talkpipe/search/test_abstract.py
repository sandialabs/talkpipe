import pytest
from talkpipe.search.abstract import SearchResult


def test_prompt_worthy_string_with_priority_fields():
    """Test that priority fields are listed first in the output."""
    doc = {
        "title": "Test Document",
        "author": "John Doe",
        "content": "This is test content",
        "date": "2024-01-01"
    }
    result = SearchResult(score=0.95, doc_id="doc1", document=doc)

    output = result.prompt_worthy_string(priority_fields=["title", "author"])

    # Priority fields should appear first
    lines = output.split("\n")
    assert lines[0] == "Title: Test Document"
    assert lines[1] == "Author: John Doe"
    # Other fields should follow
    assert "Content: This is test content" in output
    assert "Date: 2024-01-01" in output


def test_prompt_worthy_string_with_missing_priority_fields():
    """Test that missing priority fields are skipped."""
    doc = {
        "title": "Test Document",
        "content": "This is test content"
    }
    result = SearchResult(score=0.95, doc_id="doc1", document=doc)

    # Request priority fields that don't all exist
    output = result.prompt_worthy_string(priority_fields=["author", "title", "missing_field"])

    lines = output.split("\n")
    # Only "title" exists in priority fields, so it should be first
    assert lines[0] == "Title: Test Document"
    assert lines[1] == "Content: This is test content"
    assert "Author" not in output
    assert "Missing_field" not in output


def test_prompt_worthy_string_with_empty_priority_fields():
    """Test with empty priority fields list."""
    doc = {
        "title": "Test Document",
        "author": "Jane Doe",
        "content": "Test content"
    }
    result = SearchResult(score=0.85, doc_id="doc2", document=doc)

    output = result.prompt_worthy_string(priority_fields=[])

    # All fields should be present (in document iteration order)
    assert "Title: Test Document" in output
    assert "Author: Jane Doe" in output
    assert "Content: Test content" in output


def test_prompt_worthy_string_field_capitalization():
    """Test that field names are properly capitalized."""
    doc = {
        "lowercase": "value1",
        "UPPERCASE": "value2",
        "MixedCase": "value3"
    }
    result = SearchResult(score=0.75, doc_id="doc3", document=doc)

    output = result.prompt_worthy_string(priority_fields=[])

    # Field names should be capitalized (first letter uppercase)
    assert "Lowercase: value1" in output
    assert "Uppercase: value2" in output
    assert "Mixedcase: value3" in output


def test_prompt_worthy_string_ordering():
    """Test that fields maintain correct ordering: priority fields first, then others."""
    doc = {
        "alpha": "a",
        "beta": "b",
        "gamma": "g",
        "delta": "d"
    }
    result = SearchResult(score=0.90, doc_id="doc4", document=doc)

    output = result.prompt_worthy_string(priority_fields=["gamma", "beta"])

    lines = output.split("\n")
    # Priority fields in order
    assert lines[0] == "Gamma: g"
    assert lines[1] == "Beta: b"
    # Remaining fields should follow
    remaining_lines = lines[2:]
    assert "Alpha: a" in remaining_lines
    assert "Delta: d" in remaining_lines


def test_prompt_worthy_string_single_field():
    """Test with a document containing only one field."""
    doc = {"content": "Single field document"}
    result = SearchResult(score=0.60, doc_id="doc5", document=doc)

    output = result.prompt_worthy_string(priority_fields=["content"])

    assert output == "Content: Single field document"


def test_prompt_worthy_string_no_duplicate_fields():
    """Test that fields appearing in priority_fields are not duplicated."""
    doc = {
        "title": "No Duplicates",
        "content": "Test content"
    }
    result = SearchResult(score=0.88, doc_id="doc6", document=doc)

    output = result.prompt_worthy_string(priority_fields=["title"])

    # Count occurrences of "Title:"
    assert output.count("Title:") == 1
    assert output.count("Content:") == 1
