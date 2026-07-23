import pytest
from pathlib import Path
from talkpipe.util.os import get_process_temp_dir


def test_get_process_temp_dir_creates_directory():
    """Test that get_process_temp_dir creates a directory."""
    path = get_process_temp_dir("test_create")

    assert Path(path).exists()
    assert Path(path).is_dir()
    assert "talkpipe_tmp" in path
    assert path.endswith("test_create")


def test_same_name_returns_same_path():
    """Test that same name returns same path within a process."""
    path1 = get_process_temp_dir("shared_temp")
    path2 = get_process_temp_dir("shared_temp")

    assert path1 == path2
    assert Path(path1).exists()


def test_different_names_return_different_paths():
    """Test that different names return different paths."""
    path1 = get_process_temp_dir("temp1")
    path2 = get_process_temp_dir("temp2")

    assert path1 != path2
    assert Path(path1).exists()
    assert Path(path2).exists()


def test_invalid_name_with_slash_raises_error():
    """Test that names with slashes raise ValueError."""
    with pytest.raises(ValueError, match="path separators"):
        get_process_temp_dir("invalid/name")


def test_invalid_name_with_backslash_raises_error():
    """Test that names with backslashes raise ValueError."""
    with pytest.raises(ValueError, match="path separators"):
        get_process_temp_dir("invalid\\name")


def test_invalid_name_with_dotdot_raises_error():
    """Test that names with .. raise ValueError."""
    with pytest.raises(ValueError, match="path separators"):
        get_process_temp_dir("../invalid")


def test_temp_dir_is_writable():
    """Test that created temp directories are writable."""
    path = get_process_temp_dir("writable_test")
    test_file = Path(path) / "test.txt"

    # Should be able to write to the directory
    test_file.write_text("test content")
    assert test_file.exists()
    assert test_file.read_text() == "test content"


def test_temp_dir_persists_across_calls():
    """Test that files in temp dir persist across get_process_temp_dir calls."""
    path = get_process_temp_dir("persist_test")
    test_file = Path(path) / "persistent.txt"
    test_file.write_text("data")

    # Get the same path again
    path2 = get_process_temp_dir("persist_test")
    test_file2 = Path(path2) / "persistent.txt"

    # File should still exist
    assert test_file2.exists()
    assert test_file2.read_text() == "data"


def test_temp_dir_cleanup_on_process_exit():
    """Test that temp directories are cleaned up when the process exits."""
    import subprocess
    import sys

    # Python code that will run in subprocess
    subprocess_code = """
import sys
import tempfile
from pathlib import Path

# Add src to path so we can import talkpipe
sys.path.insert(0, '/home/travis/Documents/talkpipe/src')

from talkpipe.util.os import get_process_temp_dir

# Create temp directories and write some files
path1 = get_process_temp_dir("cleanup_test_1")
path2 = get_process_temp_dir("cleanup_test_2")

(Path(path1) / "file1.txt").write_text("data1")
(Path(path2) / "file2.txt").write_text("data2")

# Print the paths so parent can verify them
print(path1)
print(path2)

# Exit normally - atexit should trigger cleanup
"""

    # Run subprocess and capture output
    result = subprocess.run(
        [sys.executable, "-c", subprocess_code],
        capture_output=True,
        text=True
    )

    # Verify subprocess succeeded
    assert result.returncode == 0, f"Subprocess failed: {result.stderr}"

    # Get the paths that were created
    lines = result.stdout.strip().split('\n')
    assert len(lines) >= 2, f"Expected at least 2 lines of output, got: {result.stdout}"

    path1 = lines[0].strip()
    path2 = lines[1].strip()

    # Verify paths were in expected location
    assert "talkpipe_tmp" in path1
    assert "talkpipe_tmp" in path2

    # Verify the directories were cleaned up after subprocess exit
    assert not Path(path1).exists(), f"Directory {path1} should have been cleaned up"
    assert not Path(path2).exists(), f"Directory {path2} should have been cleaned up"

    # Verify the base directory is also cleaned up if empty
    temp_base = Path(path1).parent  # This should be .../talkpipe_tmp
    # It might still exist if other tests are running, but the specific subdirs should be gone
    if temp_base.exists():
        # At minimum, our specific test directories should not exist
        assert not (temp_base / "cleanup_test_1").exists()
        assert not (temp_base / "cleanup_test_2").exists()


def test_limit_malloc_arenas_env_var_takes_precedence(monkeypatch):
    """An explicit MALLOC_ARENA_MAX in the environment is left in charge."""
    import ctypes

    from talkpipe.util.os import limit_malloc_arenas

    monkeypatch.setenv("MALLOC_ARENA_MAX", "2")

    def fail_if_loaded(*args, **kwargs):
        raise AssertionError("mallopt must not run when the env var governs")

    monkeypatch.setattr(ctypes, "CDLL", fail_if_loaded)
    assert limit_malloc_arenas() is True


def test_limit_malloc_arenas_applies_or_degrades_gracefully(monkeypatch):
    """On glibc the cap applies; elsewhere it reports False, never raises."""
    from talkpipe.util.os import limit_malloc_arenas

    monkeypatch.delenv("MALLOC_ARENA_MAX", raising=False)
    assert limit_malloc_arenas() in (True, False)


def test_limit_malloc_arenas_missing_libc_reports_false(monkeypatch):
    import ctypes

    from talkpipe.util.os import limit_malloc_arenas

    monkeypatch.delenv("MALLOC_ARENA_MAX", raising=False)

    def no_libc(*args, **kwargs):
        raise OSError("no libc here")

    monkeypatch.setattr(ctypes, "CDLL", no_libc)
    assert limit_malloc_arenas() is False
