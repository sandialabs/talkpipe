import logging
import pytest
from pathlib import Path
from unittest.mock import patch
from talkpipe.data.extraction import (
    ReadFile, readtxt, readhtml, readjson, readtsv, readdocx, readpdf, readcsv, readjsonl, listFiles,
    ExtractorRegistry, extract_text, extract_html, extract_docx, extract_pdf,
    extract_csv, extract_tsv, extract_json, extract_jsonl, skip_file,
    get_default_registry, global_extractor_registry, ExtractionResult
)

def test_readdocx(tmp_path):
    # Test reading individual docx file using existing test file
    rd = readdocx()
    result = list(rd(["tests/talkpipe/data/test.docx"]))[0]
    assert isinstance(result, ExtractionResult)
    assert result.content.startswith("This is a sample document.")
    assert "test.docx" in result.source
    assert result.id == result.source  # Single item, so id equals source

    # Test reading from directory (we'll create mock docx files for testing)
    # Since we can't easily create real .docx files in tests, we'll test the directory logic
    # by testing error cases and the path handling

    # Test FileNotFoundError for non-existent path
    with pytest.raises(FileNotFoundError, match="Path does not exist"):
        next(readdocx()(["nonexistent.docx"]))

    # Test FileNotFoundError for non-existent directory
    with pytest.raises(FileNotFoundError, match="Path does not exist"):
        next(readdocx()([tmp_path / "nonexistent_dir"]))
    

def test_readtxt(tmp_path):
    # Test reading individual text files
    with open(tmp_path / "test.txt", "w") as file:
        file.write("Hello World")
    result = next(readtxt()([tmp_path / "test.txt"]))
    assert isinstance(result, ExtractionResult)
    assert result.content == "Hello World"
    assert "test.txt" in result.source

    with open(tmp_path / "test.md", "w") as file:
        file.write("Hello Markdown")
    result = next(readtxt()([tmp_path / "test.md"]))
    assert result.content == "Hello Markdown"

    # Test reading empty file
    with open(tmp_path / "empty.txt", "w") as file:
        file.write("")
    result = next(readtxt()([tmp_path / "empty.txt"]))
    assert result.content == ""

    # Test reading multiple files
    with open(tmp_path / "file1.txt", "w") as file:
        file.write("Content 1")
    with open(tmp_path / "file2.txt", "w") as file:
        file.write("Content 2")

    results = list(readtxt()([tmp_path / "file1.txt", tmp_path / "file2.txt"]))
    assert len(results) == 2
    assert results[0].content == "Content 1"
    assert results[1].content == "Content 2"

    # Test FileNotFoundError for non-existent path
    with pytest.raises(FileNotFoundError, match="Path does not exist"):
        next(readtxt()([tmp_path / "nonexistent.txt"]))

    # Test FileNotFoundError for non-existent directory
    with pytest.raises(FileNotFoundError, match="Path does not exist"):
        next(readtxt()([tmp_path / "nonexistent_dir"]))

def test_FileExtractor(tmp_path):
    fe = ReadFile()

    with open(tmp_path / "test.txt", "w") as file:
        file.write("Hello World")
    result = next(fe([tmp_path / "test.txt"]))
    assert isinstance(result, ExtractionResult)
    assert result.content == "Hello World"
    assert "test.txt" in result.source
    assert result.id == result.source

    with open(tmp_path / "test.md", "w") as file:
        file.write("Hello Markdown")
    result = next(fe([tmp_path / "test.md"]))
    assert result.content == "Hello Markdown"

    # By default, unsupported files are skipped (yields nothing)
    with open(tmp_path / "test.doc", "w") as file:
        file.write("Hello Word")
    results = list(fe([tmp_path / "test.doc"]))
    assert results == []

    # With skip_unsupported=False, unsupported files raise an exception
    fe_strict = ReadFile(skip_unsupported=False)
    with pytest.raises(Exception):
        next(fe_strict([tmp_path / "test.doc"]))

def test_readfile_skips_unreadable_files(tmp_path, caplog):
    """A supported file whose extractor raises (e.g. a corrupt PDF) is skipped
    by default so it does not abort a batch, and re-raises when skip_errors=False."""

    def boom_extractor(file_path):
        raise ValueError("truncated file")
        yield  # pragma: no cover - makes this a generator function

    registry = ExtractorRegistry()
    registry.register("boom", boom_extractor)
    registry.register("txt", extract_text)

    bad = tmp_path / "bad.boom"
    bad.write_text("whatever")
    good = tmp_path / "good.txt"
    good.write_text("Hello World")

    # Default (skip_errors=True): the bad file is logged and skipped, and a
    # good file later in the same batch is still read.
    rf = ReadFile(registry=registry)
    with caplog.at_level(logging.WARNING):
        results = list(rf([bad, good]))
    assert [r.content for r in results] == ["Hello World"]
    assert any("bad.boom" in rec.message for rec in caplog.records)

    # skip_errors=False: the extractor error propagates.
    rf_strict = ReadFile(skip_errors=False, registry=registry)
    with pytest.raises(ValueError, match="truncated file"):
        list(rf_strict([bad]))

def test_listFiles(tmp_path):
    # Create test files
    (tmp_path / "file1.txt").write_text("content1")
    (tmp_path / "file2.txt").write_text("content2") 
    (tmp_path / "file3.py").write_text("content3")
    (tmp_path / "data.json").write_text("content4")
    
    # Create subdirectory with files
    subdir = tmp_path / "subdir"
    subdir.mkdir()
    (subdir / "sub1.txt").write_text("subcontent1")
    (subdir / "sub2.py").write_text("subcontent2")
    
    # Test wildcard pattern matching with full paths
    txt_files = list(listFiles()([str(tmp_path / "*.txt")]))
    assert len(txt_files) == 2
    assert all(f.endswith(".txt") for f in txt_files)
    assert all(tmp_path.name in f for f in txt_files)
    
    # Test wildcard pattern matching with filenames only
    txt_filenames = list(listFiles(full_path=False)([str(tmp_path / "*.txt")]))
    assert len(txt_filenames) == 2
    assert set(txt_filenames) == {"file1.txt", "file2.txt"}
    
    # Test recursive pattern matching
    all_txt = list(listFiles()([str(tmp_path / "**/*.txt")]))
    assert len(all_txt) == 3  # 2 in root + 1 in subdir
    
    # Test multiple patterns
    patterns = [str(tmp_path / "*.txt"), str(tmp_path / "*.py")]
    mixed_files = list(listFiles(full_path=False)(patterns))
    assert len(mixed_files) == 3
    assert set(mixed_files) == {"file1.txt", "file2.txt", "file3.py"}
    
    # Test non-matching pattern (should return empty)
    no_match = list(listFiles()([str(tmp_path / "*.xyz")]))
    assert no_match == []
    
    # Test exact filename (no wildcards)
    exact_file = list(listFiles(full_path=False)([str(tmp_path / "data.json")]))
    assert exact_file == ["data.json"]
    
    # Test directory without wildcard (should add implied "/*")
    dir_files = list(listFiles(full_path=False, files_only=True)([str(tmp_path)]))
    assert len(dir_files) == 4  # Should find all files in root directory
    assert set(dir_files) == {"file1.txt", "file2.txt", "file3.py", "data.json"}


def test_extractor_registry(tmp_path):
    """Test ExtractorRegistry class."""
    registry = ExtractorRegistry()

    # Test registering and using extractors
    registry.register("txt", extract_text)

    with open(tmp_path / "test.txt", "w") as f:
        f.write("Hello World")

    results = list(registry.extract(tmp_path / "test.txt"))
    assert len(results) == 1
    assert isinstance(results[0], ExtractionResult)
    assert results[0].content == "Hello World"
    assert results[0].title == "test.txt"

    # Test that unregistered extension raises ValueError when no default
    with open(tmp_path / "test.xyz", "w") as f:
        f.write("Unknown format")

    with pytest.raises(ValueError, match="No extractor registered"):
        list(registry.extract(tmp_path / "test.xyz"))

    # Test registering a default extractor
    registry.register_default(skip_file)
    assert registry.has_default()
    assert list(registry.extract(tmp_path / "test.xyz")) == []

    # Test registered_extensions property
    registry.register("md", extract_text)
    extensions = registry.registered_extensions
    assert "txt" in extensions
    assert "md" in extensions


def test_extractor_registry_get_extractor(tmp_path):
    """Test ExtractorRegistry.get_extractor method."""
    registry = ExtractorRegistry()
    registry.register("txt", extract_text)

    # Test getting extractor for registered extension
    extractor = registry.get_extractor(tmp_path / "test.txt")
    assert extractor is extract_text

    # Test getting extractor for unregistered extension (no default)
    extractor = registry.get_extractor(tmp_path / "test.xyz")
    assert extractor is None

    # Test getting extractor for unregistered extension (with default)
    registry.register_default(skip_file)
    extractor = registry.get_extractor(tmp_path / "test.xyz")
    assert extractor is skip_file


def test_get_default_registry(tmp_path):
    """Test get_default_registry factory function."""
    registry = get_default_registry()

    # Verify default extractors are registered
    assert "txt" in registry.registered_extensions
    assert "md" in registry.registered_extensions
    assert "docx" in registry.registered_extensions
    assert registry.has_default()

    # Test extraction works
    with open(tmp_path / "test.txt", "w") as f:
        f.write("Default registry test")
    results = list(registry.extract(tmp_path / "test.txt"))
    assert len(results) == 1
    assert isinstance(results[0], ExtractionResult)
    assert results[0].content == "Default registry test"

    # Test default skips unknown files
    with open(tmp_path / "test.unknown", "w") as f:
        f.write("Unknown")
    assert list(registry.extract(tmp_path / "test.unknown")) == []


def test_ReadFile_with_custom_registry(tmp_path):
    """Test ReadFile with a custom registry."""
    # Create a custom registry with only txt support
    custom_registry = ExtractorRegistry()
    custom_registry.register("txt", extract_text)

    fe = ReadFile(registry=custom_registry)

    with open(tmp_path / "test.txt", "w") as f:
        f.write("Custom registry")

    result = next(fe([tmp_path / "test.txt"]))
    assert isinstance(result, ExtractionResult)
    assert result.content == "Custom registry"

    # Without default, should raise for unknown extension
    with open(tmp_path / "test.md", "w") as f:
        f.write("Markdown")

    with pytest.raises(Exception):
        next(fe([tmp_path / "test.md"]))


def test_extract_html(tmp_path):
    """Test extract_html: readable text, raw_html preserved, same metadata as extract_text."""
    html_path = tmp_path / "page.html"
    raw = (
        "<html><head><title>Ignored title</title></head>"
        "<body><p>Hello HTML</p><script>function_call()</script></body></html>"
    )
    html_path.write_text(raw, encoding="utf-8")

    results = list(extract_html(html_path))
    assert len(results) == 1
    r = results[0]
    assert isinstance(r, ExtractionResult)
    assert "Hello HTML" in r.content
    assert "function_call" not in r.content
    assert r.raw_html == raw
    assert str(html_path.resolve()) in r.source
    assert r.id == r.source
    assert r.title == "page.html"

    with pytest.raises(FileNotFoundError):
        list(extract_html(tmp_path / "missing.html"))


def test_html_in_default_registry(tmp_path):
    """Test html/htm registered in default registry and extractable via ReadFile.

    Would have failed before: html was not registered AND extract_html did not yield.
    """
    registry = get_default_registry()
    assert "html" in registry.registered_extensions
    assert "htm" in registry.registered_extensions

    raw = "<html><body><p>Registry HTML</p></body></html>"
    for ext in ("html", "htm"):
        p = tmp_path / f"test.{ext}"
        p.write_text(raw, encoding="utf-8")

        results = list(registry.extract(p))
        assert len(results) == 1
        assert "Registry HTML" in results[0].content
        assert results[0].raw_html == raw

    fe = ReadFile()
    html_path = tmp_path / "readfile.html"
    html_path.write_text(raw, encoding="utf-8")
    results = list(fe([str(html_path)]))
    assert len(results) == 1
    assert "Registry HTML" in results[0].content


def test_standalone_extractors(tmp_path):
    """Test standalone extractor functions."""
    # Test extract_text
    with open(tmp_path / "test.txt", "w") as f:
        f.write("Standalone text")
    results = list(extract_text(tmp_path / "test.txt"))
    assert len(results) == 1
    assert isinstance(results[0], ExtractionResult)
    assert results[0].content == "Standalone text"
    assert results[0].title == "test.txt"

    # Test extract_text with non-existent file
    with pytest.raises(FileNotFoundError):
        list(extract_text(tmp_path / "nonexistent.txt"))

    # Test skip_file yields nothing
    assert list(skip_file(tmp_path / "any.file")) == []


def test_global_extractor_registry(tmp_path):
    """Test that global_extractor_registry is pre-configured and usable."""
    # Verify it has default extractors
    assert "txt" in global_extractor_registry.registered_extensions
    assert "md" in global_extractor_registry.registered_extensions
    assert "docx" in global_extractor_registry.registered_extensions
    assert global_extractor_registry.has_default()

    # Verify extraction works
    with open(tmp_path / "global_test.txt", "w") as f:
        f.write("Global registry test")
    results = list(global_extractor_registry.extract(tmp_path / "global_test.txt"))
    assert len(results) == 1
    assert isinstance(results[0], ExtractionResult)
    assert results[0].content == "Global registry test"


def test_multi_emit_extractor(tmp_path):
    """Test that extractors can yield multiple items."""
    # Create a multi-emit extractor (like for CSV or JSONL)
    def extract_lines(file_path):
        from pathlib import Path
        p = Path(file_path)
        source_str = str(p.resolve())
        with open(file_path, "r") as f:
            for idx, line in enumerate(f):
                result_id = source_str if idx == 0 else f"{source_str}:{idx}"
                yield ExtractionResult(
                    content=line.strip(),
                    source=source_str,
                    id=result_id,
                    title=f"{p.name}:line{idx+1}"
                )

    registry = ExtractorRegistry()
    registry.register("lines", extract_lines)

    # Create a test file with multiple lines
    with open(tmp_path / "test.lines", "w") as f:
        f.write("line1\nline2\nline3\n")

    # Verify multi-emit works at registry level
    results = list(registry.extract(tmp_path / "test.lines"))
    assert len(results) == 3
    assert all(isinstance(r, ExtractionResult) for r in results)
    assert results[0].content == "line1"
    assert results[1].content == "line2"
    assert results[2].content == "line3"

    # Test with ReadFile - returns ExtractionResult objects
    fe = ReadFile(registry=registry)
    results = list(fe([tmp_path / "test.lines"]))
    assert len(results) == 3
    assert all(isinstance(r, ExtractionResult) for r in results)
    assert results[0].content == "line1"
    assert results[1].content == "line2"
    assert results[2].content == "line3"

    # Verify IDs are unique for multi-emit
    assert results[0].id == results[0].source  # First item: id == source
    assert results[1].id == f"{results[1].source}:1"  # Second item: source:1
    assert results[2].id == f"{results[2].source}:2"  # Third item: source:2

    # Verify titles include line numbers
    assert "line1" in results[0].title
    assert "line2" in results[1].title
    assert "line3" in results[2].title


def test_extract_csv(tmp_path):
    """Test extract_csv function."""
    # Test basic CSV without ExtractionResult field names
    csv_content = "name,email,age\nAlice,alice@example.com,30\nBob,bob@example.com,25\n"
    csv_path = tmp_path / "test.csv"
    csv_path.write_text(csv_content)

    results = list(extract_csv(csv_path))
    assert len(results) == 2

    # Check first row
    assert isinstance(results[0], ExtractionResult)
    assert "name: Alice" in results[0].content
    assert "email: alice@example.com" in results[0].content
    assert "age: 30" in results[0].content
    assert str(csv_path.resolve()) in results[0].source
    assert results[0].id == f"{csv_path.resolve()}:1"
    assert results[0].title == "test.csv:1"
    # All CSV fields should be present as extra fields
    assert results[0].name == "Alice"
    assert results[0].email == "alice@example.com"
    assert results[0].age == "30"

    # Check second row
    assert results[1].id == f"{csv_path.resolve()}:2"
    assert results[1].title == "test.csv:2"
    assert results[1].name == "Bob"


def test_extract_csv_with_matching_fields(tmp_path):
    """Test extract_csv when CSV has columns matching ExtractionResult fields."""
    csv_content = "content,title,extra_field\nMy content,My title,extra_value\n"
    csv_path = tmp_path / "matching.csv"
    csv_path.write_text(csv_content)

    results = list(extract_csv(csv_path))
    assert len(results) == 1

    result = results[0]
    # Matching fields should be used
    assert result.content == "My content"
    assert result.title == "My title"
    # Non-matching fields should use defaults
    assert str(csv_path.resolve()) in result.source
    assert result.id == f"{csv_path.resolve()}:1"
    # All CSV fields should still be present as extra fields
    assert result.extra_field == "extra_value"


def test_extract_csv_all_matching_fields(tmp_path):
    """Test extract_csv when CSV has all ExtractionResult field names."""
    csv_content = "content,source,id,title,custom\nCustom content,custom_source,custom_id,custom_title,custom_val\n"
    csv_path = tmp_path / "all_matching.csv"
    csv_path.write_text(csv_content)

    results = list(extract_csv(csv_path))
    assert len(results) == 1

    result = results[0]
    # All fields should use CSV values
    assert result.content == "Custom content"
    assert result.source == "custom_source"
    assert result.id == "custom_id"
    assert result.title == "custom_title"
    assert result.custom == "custom_val"


def test_extract_csv_error_cases(tmp_path):
    """Test extract_csv error handling."""
    # Non-existent file
    with pytest.raises(FileNotFoundError, match="Path does not exist"):
        list(extract_csv(tmp_path / "nonexistent.csv"))

    # Directory instead of file
    (tmp_path / "subdir").mkdir()
    with pytest.raises(FileNotFoundError, match="Unsupported path type"):
        list(extract_csv(tmp_path / "subdir"))


def test_readcsv(tmp_path):
    """Test readcsv segment."""
    csv_content = "product,price,quantity\nApple,1.50,10\nBanana,0.75,20\n"
    csv_path = tmp_path / "products.csv"
    csv_path.write_text(csv_content)

    results = list(readcsv()([str(csv_path)]))
    assert len(results) == 2

    # Check first row
    assert isinstance(results[0], ExtractionResult)
    assert results[0].product == "Apple"
    assert results[0].price == "1.50"
    assert results[0].quantity == "10"
    assert "products.csv:1" in results[0].title

    # Check second row
    assert results[1].product == "Banana"
    assert "products.csv:2" in results[1].title


def test_csv_in_default_registry(tmp_path):
    """Test that CSV extractor is registered in default registry."""
    registry = get_default_registry()
    assert "csv" in registry.registered_extensions

    csv_content = "col1,col2\nval1,val2\n"
    csv_path = tmp_path / "registry_test.csv"
    csv_path.write_text(csv_content)

    results = list(registry.extract(csv_path))
    assert len(results) == 1
    assert results[0].col1 == "val1"
    assert results[0].col2 == "val2"


def test_extract_jsonl_with_dicts(tmp_path):
    """Test extract_jsonl with dictionary objects."""
    jsonl_content = '{"name": "Alice", "age": 30}\n{"name": "Bob", "age": 25}\n'
    jsonl_path = tmp_path / "test.jsonl"
    jsonl_path.write_text(jsonl_content)

    results = list(extract_jsonl(jsonl_path))
    assert len(results) == 2

    # Check first line
    assert isinstance(results[0], ExtractionResult)
    assert "name: Alice" in results[0].content
    assert "age: 30" in results[0].content
    assert str(jsonl_path.resolve()) in results[0].source
    assert results[0].id == f"{jsonl_path.resolve()}:1"
    assert results[0].title == "test.jsonl:1"
    # Dict fields should be passed through
    assert results[0].name == "Alice"
    assert results[0].age == 30

    # Check second line
    assert results[1].id == f"{jsonl_path.resolve()}:2"
    assert results[1].name == "Bob"


def test_extract_jsonl_with_matching_fields(tmp_path):
    """Test extract_jsonl when JSON has keys matching ExtractionResult fields."""
    jsonl_content = '{"content": "My content", "title": "My title", "extra": "value"}\n'
    jsonl_path = tmp_path / "matching.jsonl"
    jsonl_path.write_text(jsonl_content)

    results = list(extract_jsonl(jsonl_path))
    assert len(results) == 1

    result = results[0]
    assert result.content == "My content"
    assert result.title == "My title"
    assert str(jsonl_path.resolve()) in result.source
    assert result.id == f"{jsonl_path.resolve()}:1"
    assert result.extra == "value"


def test_extract_jsonl_non_dict_string(tmp_path):
    """Test extract_jsonl with string values."""
    jsonl_content = '"hello world"\n"another string"\n'
    jsonl_path = tmp_path / "strings.jsonl"
    jsonl_path.write_text(jsonl_content)

    results = list(extract_jsonl(jsonl_path))
    assert len(results) == 2

    # String value should be used directly as content
    assert results[0].content == "hello world"
    assert results[0].value == "hello world"
    assert results[0].id == f"{jsonl_path.resolve()}:1"

    assert results[1].content == "another string"
    assert results[1].value == "another string"


def test_extract_jsonl_non_dict_numbers(tmp_path):
    """Test extract_jsonl with number values."""
    jsonl_content = '42\n3.14\n'
    jsonl_path = tmp_path / "numbers.jsonl"
    jsonl_path.write_text(jsonl_content)

    results = list(extract_jsonl(jsonl_path))
    assert len(results) == 2

    # Number should be JSON stringified for content, original value in 'value'
    assert results[0].content == "42"
    assert results[0].value == 42

    assert results[1].content == "3.14"
    assert results[1].value == 3.14


def test_extract_jsonl_non_dict_array(tmp_path):
    """Test extract_jsonl with array values."""
    jsonl_content = '[1, 2, 3]\n["a", "b"]\n'
    jsonl_path = tmp_path / "arrays.jsonl"
    jsonl_path.write_text(jsonl_content)

    results = list(extract_jsonl(jsonl_path))
    assert len(results) == 2

    assert results[0].content == "[1, 2, 3]"
    assert results[0].value == [1, 2, 3]

    assert results[1].content == '["a", "b"]'
    assert results[1].value == ["a", "b"]


def test_extract_jsonl_non_dict_boolean_null(tmp_path):
    """Test extract_jsonl with boolean and null values."""
    jsonl_content = 'true\nfalse\nnull\n'
    jsonl_path = tmp_path / "misc.jsonl"
    jsonl_path.write_text(jsonl_content)

    results = list(extract_jsonl(jsonl_path))
    assert len(results) == 3

    assert results[0].content == "true"
    assert results[0].value is True

    assert results[1].content == "false"
    assert results[1].value is False

    assert results[2].content == "null"
    assert results[2].value is None


def test_extract_jsonl_skips_empty_lines(tmp_path):
    """Test that extract_jsonl skips empty lines."""
    jsonl_content = '{"a": 1}\n\n{"b": 2}\n   \n{"c": 3}\n'
    jsonl_path = tmp_path / "empty_lines.jsonl"
    jsonl_path.write_text(jsonl_content)

    results = list(extract_jsonl(jsonl_path))
    assert len(results) == 3
    assert results[0].a == 1
    assert results[1].b == 2
    assert results[2].c == 3


def test_extract_jsonl_error_cases(tmp_path):
    """Test extract_jsonl error handling."""
    # Non-existent file
    with pytest.raises(FileNotFoundError, match="Path does not exist"):
        list(extract_jsonl(tmp_path / "nonexistent.jsonl"))

    # Directory instead of file
    (tmp_path / "subdir").mkdir()
    with pytest.raises(FileNotFoundError, match="Unsupported path type"):
        list(extract_jsonl(tmp_path / "subdir"))


def test_readjsonl(tmp_path):
    """Test readjsonl segment."""
    jsonl_content = '{"product": "Apple", "price": 1.50}\n{"product": "Banana", "price": 0.75}\n'
    jsonl_path = tmp_path / "products.jsonl"
    jsonl_path.write_text(jsonl_content)

    results = list(readjsonl()([str(jsonl_path)]))
    assert len(results) == 2

    assert isinstance(results[0], ExtractionResult)
    assert results[0].product == "Apple"
    assert results[0].price == 1.50
    assert "products.jsonl:1" in results[0].title

    assert results[1].product == "Banana"
    assert "products.jsonl:2" in results[1].title


def _create_pdf_with_text(path, text: str = "Hello PDF") -> None:
    """Create a minimal PDF file with the given text content."""
    content = f"""BT
/F1 12 Tf
100 700 Td
({text}) Tj
ET
""".encode()
    obj1 = b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
    obj2 = b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
    obj3 = b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources 5 0 R >>\nendobj\n"
    obj4 = (
        b"4 0 obj\n<< /Length " + str(len(content)).encode("ascii") + b" >>\nstream\n"
        + content + b"\nendstream\nendobj\n"
    )
    obj5 = b"5 0 obj\n<< /Font << /F1 6 0 R >> >>\nendobj\n"
    obj6 = b"6 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n"
    body = obj1 + obj2 + obj3 + obj4 + obj5 + obj6
    startxref = 9 + len(body)
    offsets = [9]
    for obj in [obj1, obj2, obj3, obj4, obj5]:
        offsets.append(offsets[-1] + len(obj))
    xref = b"xref\n0 7\n0000000000 65535 f \n"
    for i in range(1, 7):
        xref += f"{offsets[i - 1]:010d} 00000 n \n".encode()
    trailer = f"trailer\n<< /Size 7 /Root 1 0 R >>\nstartxref\n{startxref}\n%%EOF\n".encode()
    Path(path).write_bytes(b"%PDF-1.4\n" + body + xref + trailer)


def test_extract_pdf_requires_pypdf(tmp_path):
    """Test that extract_pdf raises helpful ImportError when pypdf is not installed."""
    pdf_path = tmp_path / "test.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 minimal\n")

    import builtins
    real_import = builtins.__import__

    def mock_import(name, *args, **kwargs):
        if name == "pypdf":
            raise ImportError("No module named 'pypdf'")
        return real_import(name, *args, **kwargs)

    with patch.object(builtins, "__import__", side_effect=mock_import):
        with pytest.raises(ImportError) as exc_info:
            list(extract_pdf(pdf_path))
        assert "pypdf" in str(exc_info.value)
        assert "pip install talkpipe[pypdf]" in str(exc_info.value)


def test_extract_pdf_file_not_found():
    """Test extract_pdf raises FileNotFoundError for missing file."""
    pytest.importorskip("pypdf")
    with pytest.raises(FileNotFoundError, match="Path does not exist"):
        list(extract_pdf("/nonexistent/path.pdf"))


def test_extract_pdf_with_pypdf(tmp_path):
    """Test PDF extraction when pypdf is installed."""
    pytest.importorskip("pypdf")

    pdf_path = tmp_path / "test.pdf"
    _create_pdf_with_text(pdf_path, "Hello PDF")

    results = list(extract_pdf(pdf_path))
    assert len(results) == 1
    assert isinstance(results[0], ExtractionResult)
    assert "test.pdf" in results[0].source
    assert results[0].id == results[0].source
    assert results[0].title == "test.pdf"
    assert "Hello PDF" in results[0].content


def test_readpdf_segment(tmp_path):
    """Test readpdf segment when pypdf is installed."""
    pytest.importorskip("pypdf")

    pdf_path = tmp_path / "segment_test.pdf"
    _create_pdf_with_text(pdf_path, "Segment test content")

    results = list(readpdf()([str(pdf_path)]))
    assert len(results) == 1
    assert isinstance(results[0], ExtractionResult)
    assert "segment_test.pdf" in results[0].source
    assert "Segment test content" in results[0].content


def test_pdf_in_default_registry(tmp_path):
    """Test that PDF extractor is registered in default registry."""
    registry = get_default_registry()
    assert "pdf" in registry.registered_extensions


def test_ReadFile_with_pdf(tmp_path):
    """Test ReadFile extracts PDF when pypdf is installed."""
    pytest.importorskip("pypdf")

    pdf_path = tmp_path / "readfile_test.pdf"
    _create_pdf_with_text(pdf_path, "ReadFile PDF content")

    fe = ReadFile()
    results = list(fe([str(pdf_path)]))
    assert len(results) == 1
    assert isinstance(results[0], ExtractionResult)
    assert "readfile_test.pdf" in results[0].source
    assert "ReadFile PDF content" in results[0].content


def test_jsonl_in_default_registry(tmp_path):
    """Test that JSONL extractor is registered in default registry."""
    registry = get_default_registry()
    assert "jsonl" in registry.registered_extensions

    jsonl_content = '{"key": "value"}\n'
    jsonl_path = tmp_path / "registry_test.jsonl"
    jsonl_path.write_text(jsonl_content)

    results = list(registry.extract(jsonl_path))
    assert len(results) == 1
    assert results[0].key == "value"


# --- extract_json tests ---

def test_extract_json_dict(tmp_path):
    """Test extract_json with a dictionary value."""
    json_path = tmp_path / "test.json"
    json_path.write_text('{"name": "Alice", "age": 30}', encoding="utf-8")

    results = list(extract_json(json_path))
    assert len(results) == 1
    r = results[0]
    assert isinstance(r, ExtractionResult)
    assert "name: Alice" in r.content
    assert "age: 30" in r.content
    assert str(json_path.resolve()) in r.source
    assert r.id == r.source
    assert r.title == "test.json"
    assert r.name == "Alice"
    assert r.age == 30


def test_extract_json_dict_with_matching_fields(tmp_path):
    """Test extract_json when dict keys match ExtractionResult fields."""
    json_path = tmp_path / "matching.json"
    json_path.write_text('{"content": "My content", "title": "My title", "extra": "val"}', encoding="utf-8")

    results = list(extract_json(json_path))
    assert len(results) == 1
    r = results[0]
    assert r.content == "My content"
    assert r.title == "My title"
    assert r.extra == "val"
    assert str(json_path.resolve()) in r.source


def test_extract_json_non_dict(tmp_path):
    """Test extract_json with non-dict values (string, number, array)."""
    str_path = tmp_path / "string.json"
    str_path.write_text('"hello world"', encoding="utf-8")
    results = list(extract_json(str_path))
    assert len(results) == 1
    assert results[0].content == "hello world"
    assert results[0].value == "hello world"

    num_path = tmp_path / "number.json"
    num_path.write_text('42', encoding="utf-8")
    results = list(extract_json(num_path))
    assert results[0].content == "42"
    assert results[0].value == 42

    arr_path = tmp_path / "array.json"
    arr_path.write_text('[1, 2, 3]', encoding="utf-8")
    results = list(extract_json(arr_path))
    assert results[0].content == "[1, 2, 3]"
    assert results[0].value == [1, 2, 3]


def test_extract_json_error_cases(tmp_path):
    """Test extract_json error handling."""
    with pytest.raises(FileNotFoundError, match="Path does not exist"):
        list(extract_json(tmp_path / "nonexistent.json"))

    (tmp_path / "subdir").mkdir()
    with pytest.raises(FileNotFoundError, match="Unsupported path type"):
        list(extract_json(tmp_path / "subdir"))


def test_readjson(tmp_path):
    """Test readjson segment."""
    json_path = tmp_path / "data.json"
    json_path.write_text('{"product": "Apple", "price": 1.50}', encoding="utf-8")

    results = list(readjson()([str(json_path)]))
    assert len(results) == 1
    assert results[0].product == "Apple"
    assert results[0].price == 1.50


def test_json_in_default_registry(tmp_path):
    """Test that JSON extractor is registered in default registry."""
    registry = get_default_registry()
    assert "json" in registry.registered_extensions

    json_path = tmp_path / "registry_test.json"
    json_path.write_text('{"key": "value"}', encoding="utf-8")
    results = list(registry.extract(json_path))
    assert len(results) == 1
    assert results[0].key == "value"


# --- extract_tsv tests ---

def test_extract_tsv(tmp_path):
    """Test extract_tsv with basic tab-separated data."""
    tsv_content = "name\temail\tage\nAlice\talice@example.com\t30\nBob\tbob@example.com\t25\n"
    tsv_path = tmp_path / "test.tsv"
    tsv_path.write_text(tsv_content)

    results = list(extract_tsv(tsv_path))
    assert len(results) == 2

    assert isinstance(results[0], ExtractionResult)
    assert results[0].name == "Alice"
    assert results[0].email == "alice@example.com"
    assert results[0].age == "30"
    assert results[0].id == f"{tsv_path.resolve()}:1"
    assert results[0].title == "test.tsv:1"

    assert results[1].name == "Bob"
    assert results[1].id == f"{tsv_path.resolve()}:2"


def test_extract_tsv_with_matching_fields(tmp_path):
    """Test extract_tsv when columns match ExtractionResult fields."""
    tsv_content = "content\ttitle\textra\nMy content\tMy title\textra_val\n"
    tsv_path = tmp_path / "matching.tsv"
    tsv_path.write_text(tsv_content)

    results = list(extract_tsv(tsv_path))
    assert len(results) == 1
    assert results[0].content == "My content"
    assert results[0].title == "My title"
    assert results[0].extra == "extra_val"


def test_extract_tsv_error_cases(tmp_path):
    """Test extract_tsv error handling."""
    with pytest.raises(FileNotFoundError, match="Path does not exist"):
        list(extract_tsv(tmp_path / "nonexistent.tsv"))


def test_readtsv(tmp_path):
    """Test readtsv segment."""
    tsv_content = "product\tprice\nApple\t1.50\nBanana\t0.75\n"
    tsv_path = tmp_path / "products.tsv"
    tsv_path.write_text(tsv_content)

    results = list(readtsv()([str(tsv_path)]))
    assert len(results) == 2
    assert results[0].product == "Apple"
    assert results[0].price == "1.50"
    assert results[1].product == "Banana"


def test_tsv_in_default_registry(tmp_path):
    """Test that TSV extractor is registered in default registry."""
    registry = get_default_registry()
    assert "tsv" in registry.registered_extensions

    tsv_content = "col1\tcol2\nval1\tval2\n"
    tsv_path = tmp_path / "registry_test.tsv"
    tsv_path.write_text(tsv_content)

    results = list(registry.extract(tsv_path))
    assert len(results) == 1
    assert results[0].col1 == "val1"
    assert results[0].col2 == "val2"


# --- RST in default registry ---

def test_rst_in_default_registry(tmp_path):
    """Test that .rst files are handled via extract_text in the default registry."""
    registry = get_default_registry()
    assert "rst" in registry.registered_extensions

    rst_path = tmp_path / "readme.rst"
    rst_path.write_text("=====\nTitle\n=====\n\nSome reStructuredText.", encoding="utf-8")

    results = list(registry.extract(rst_path))
    assert len(results) == 1
    assert "Title" in results[0].content
    assert "reStructuredText" in results[0].content
    assert results[0].title == "readme.rst"


# --- Comprehensive default registry extensions check ---

def test_default_registry_has_all_extensions():
    """Verify all expected extensions are registered in the default registry."""
    registry = get_default_registry()
    expected = {"txt", "md", "rst", "html", "htm", "docx", "pdf", "csv", "tsv", "json", "jsonl"}
    actual = set(registry.registered_extensions)
    assert expected.issubset(actual), f"Missing extensions: {expected - actual}"
