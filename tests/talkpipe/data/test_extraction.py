import pytest
from talkpipe.data.extraction import (
    ReadFile, readtxt, readdocx, listFiles,
    ExtractorRegistry, extract_text, extract_docx, skip_file, get_default_registry,
    global_extractor_registry, ExtractionResult
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
