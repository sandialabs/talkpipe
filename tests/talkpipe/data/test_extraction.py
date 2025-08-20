import pytest
from talkpipe.data.extraction import FileExtractor, readtxt, readdocx, listFiles

def test_readdocx(tmp_path):
    # Test reading individual docx file using existing test file
    rd = readdocx()
    text = list(rd(["tests/talkpipe/data/test.docx"]))[0]
    assert text.startswith("This is a sample document.")
    
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
    assert next(readtxt()([tmp_path / "test.txt"])) == "Hello World"

    with open(tmp_path / "test.md", "w") as file:
        file.write("Hello Markdown")
    assert next(readtxt()([tmp_path / "test.md"])) == "Hello Markdown"

    # Test reading empty file
    with open(tmp_path / "empty.txt", "w") as file:
        file.write("")
    assert next(readtxt()([tmp_path / "empty.txt"])) == ""

    # Test reading multiple files
    with open(tmp_path / "file1.txt", "w") as file:
        file.write("Content 1")
    with open(tmp_path / "file2.txt", "w") as file:
        file.write("Content 2")
    
    results = list(readtxt()([tmp_path / "file1.txt", tmp_path / "file2.txt"]))
    assert results == ["Content 1", "Content 2"]

    # Test FileNotFoundError for non-existent path
    with pytest.raises(FileNotFoundError, match="Path does not exist"):
        next(readtxt()([tmp_path / "nonexistent.txt"]))

    # Test FileNotFoundError for non-existent directory
    with pytest.raises(FileNotFoundError, match="Path does not exist"):
        next(readtxt()([tmp_path / "nonexistent_dir"]))

def test_FileExtractor(tmp_path):
    fe = FileExtractor()

    with open(tmp_path / "test.txt", "w") as file:
        file.write("Hello World")   
    assert next(fe([tmp_path / "test.txt"])) == "Hello World"

    with open(tmp_path / "test.md", "w") as file:
        file.write("Hello Markdown")
    assert next(fe([tmp_path / "test.md"])) == "Hello Markdown"

    with open(tmp_path / "test.doc", "w") as file:
        file.write("Hello Word")
    with pytest.raises(Exception):
        next(fe([tmp_path / "test.doc"]))

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

    