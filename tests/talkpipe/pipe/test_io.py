import json, pickle, os
from talkpipe.pipe import io
from talkpipe.util import config
from talkpipe.chatterlang import compiler

def test_echo_operation():
    f = compiler.compile('INPUT FROM echo[data="howdy|do", delimiter="|"]').asFunction(single_in=True, single_out=False)
    ans = f(None)
    assert ans == ["howdy", "do"]

    f = compiler.compile('INPUT FROM echo[data="howdy,do"]').asFunction(single_in=True, single_out=False)
    ans = f(None)
    assert ans == ["howdy", "do"]

    f = io.echo(data="howdy|do", delimiter='|')
    ans = list(f())
    assert ans == ["howdy", "do"]

def test_readJSONL(tmpdir):
    data = [
        {"name": "Alice", "age": 30},
        {"name": "Bob", "age": 25},
        {"name": "Charlie", "age": 35}
    ]

    temp_file_path = tmpdir.join("test.jsonl")
    with open(temp_file_path, 'w') as temp_file:
        for entry in data:
            temp_file.write(json.dumps(entry) + '\n')

    f = io.readJsonl()
    ans = list(f([temp_file_path]))
    assert ans == data

def test_dumpsJsonl():
    data = [
        {"name": "Alice", "age": 30},
        {"name": "Bob", "age": 25},
        {"name": "Charlie", "age": 35}
    ]

    f = io.dumpsJsonl()
    ans = list(f(data))
    assert ans == [json.dumps(entry) for entry in data]
        
def test_print(capsys):
    f = io.Print()
    ans = list(f(["howdy", "do"]))
    assert ans == ["howdy", "do"]
    captured = capsys.readouterr()
    assert captured.out == "howdy\ndo\n"
    
    f = io.Print(field_list="age")
    ans = list(f([{"name": "Alice", "age": 30}, {"name": "Bob", "age": 25}]))
    assert ans == [{"name": "Alice", "age": 30}, {"name": "Bob", "age": 25}]
    captured = capsys.readouterr()
    assert captured.out == "{'age': 30}\n{'age': 25}\n"

def test_log(capsys, tmpdir):

    config.configure_logger("test.log:INFO")
    f = io.Log(level="DEBUG", log_name="test.log")
    ans = list(f(["howdy", "do"]))
    assert ans == ["howdy", "do"]
    captured = capsys.readouterr()
    assert "howdy" not in captured.out 
    assert "do" not in captured.out

    config.configure_logger("test.log:DEBUG")
    f = io.Log(level="DEBUG", log_name="test.log")
    ans = list(f(["howdy", "do"]))
    assert ans == ["howdy", "do"]
    captured = capsys.readouterr()
    assert "howdy" in captured.err 
    assert "do" in captured.err

    config.configure_logger("test.log:DEBUG", logger_files=f"test.log:{os.path.join(str(tmpdir), 'test.log')}")
    f = io.Log(level="DEBUG", log_name="test.log")
    ans = list(f(["howdy", "do"]))
    assert ans == ["howdy", "do"]
    captured = capsys.readouterr()
    assert "howdy" in captured.err 
    assert "do" in captured.err
    with open(os.path.join(str(tmpdir), 'test.log'), 'r') as f:
        assert "howdy" in f.readline()
        assert "do" in f.readline()

def test_writePickle_basic_functionality(tmpdir):
    """Test basic writePickle functionality - writes all items and yields them."""
    data = [
        {"name": "Alice", "age": 30},
        {"name": "Bob", "age": 25},
        {"name": "Charlie", "age": 35}
    ]
    
    temp_file_path = tmpdir.join("test_basic.pickle")
    f = io.writePickle(fname=str(temp_file_path))
    
    # Test that all items are yielded
    result = list(f(data))
    assert result == data
    
    # Test that all items were written to pickle file
    with open(str(temp_file_path), 'rb') as file:
        loaded_items = []
        try:
            while True:
                loaded_items.append(pickle.load(file))
        except EOFError:
            pass
    assert loaded_items == data

def test_writePickle_first_only_true(tmpdir):
    """Test writePickle with first_only=True - only writes first item but yields all."""
    data = [
        {"name": "Alice", "age": 30},
        {"name": "Bob", "age": 25},
        {"name": "Charlie", "age": 35}
    ]
    
    temp_file_path = tmpdir.join("test_first_only.pickle")
    f = io.writePickle(fname=str(temp_file_path), first_only=True)
    
    # Test that all items are still yielded
    result = list(f(data))
    assert result == data
    
    # Test that only first item was written to pickle file
    with open(str(temp_file_path), 'rb') as file:
        first_item = pickle.load(file)
        assert first_item == data[0]
        
        # Verify no more items in file
        try:
            pickle.load(file)
            assert False, "Expected only one item in pickle file"
        except EOFError:
            pass  # Expected behavior

def test_writePickle_empty_data(tmpdir):
    """Test writePickle with empty input data."""
    temp_file_path = tmpdir.join("test_empty.pickle")
    f = io.writePickle(fname=str(temp_file_path))
    
    result = list(f([]))
    assert result == []
    
    # File should exist but be empty
    assert os.path.exists(str(temp_file_path))
    with open(str(temp_file_path), 'rb') as file:
        try:
            pickle.load(file)
            assert False, "Expected empty pickle file"
        except EOFError:
            pass  # Expected behavior

def test_writePickle_compiler_integration(tmpdir):
    """Test writePickle integration with compiler system."""
    data = [
        {"name": "Alice", "age": 30},
        {"name": "Bob", "age": 25}
    ]
    
    temp_file_path = tmpdir.join("test_compiler.pickle")
    
    # Test compilation and execution
    pipeline = compiler.compile(f'| writePickle[fname="{str(temp_file_path)}"]')
    f = pipeline.asFunction(single_in=False, single_out=False)
    result = f(data)
    assert result == data
    
    # Verify pickle file contents
    with open(str(temp_file_path), 'rb') as file:
        loaded_items = []
        try:
            while True:
                loaded_items.append(pickle.load(file))
        except EOFError:
            pass
    assert loaded_items == data

def test_writePickle_different_data_types(tmpdir):
    """Test writePickle with various data types."""
    data = [
        42,
        "string_data", 
        [1, 2, 3],
        {"nested": {"dict": True}},
        None
    ]
    
    temp_file_path = tmpdir.join("test_types.pickle")
    f = io.writePickle(fname=str(temp_file_path))
    
    result = list(f(data))
    assert result == data
    
    # Verify all types were pickled correctly
    with open(str(temp_file_path), 'rb') as file:
        loaded_items = []
        try:
            while True:
                loaded_items.append(pickle.load(file))
        except EOFError:
            pass
    assert loaded_items == data

def test_writeString_basic_functionality(tmpdir):
    """Test basic writeString functionality - writes all items and yields them."""
    data = ["Alice", "Bob", "Charlie"]
    
    temp_file_path = tmpdir.join("test_basic.txt")
    f = io.writeString(fname=str(temp_file_path))
    
    # Test that all items are yielded
    result = list(f(data))
    assert result == data
    
    # Test that all items were written to file with newlines
    with open(str(temp_file_path), 'r') as file:
        content = file.read()
    assert content == "Alice\nBob\nCharlie\n"

def test_writeString_first_only_true(tmpdir):
    """Test writeString with first_only=True - only writes first item but yields all."""
    data = ["Alice", "Bob", "Charlie"]
    
    temp_file_path = tmpdir.join("test_first_only.txt")
    f = io.writeString(fname=str(temp_file_path), first_only=True)
    
    # Test that all items are still yielded
    result = list(f(data))
    assert result == data
    
    # Test that only first item was written to file
    with open(str(temp_file_path), 'r') as file:
        content = file.read()
    assert content == "Alice\n"

def test_writeString_no_newline(tmpdir):
    """Test writeString with new_line=False."""
    data = ["Alice", "Bob", "Charlie"]
    
    temp_file_path = tmpdir.join("test_no_newline.txt")
    f = io.writeString(fname=str(temp_file_path), new_line=False)
    
    # Test that all items are yielded
    result = list(f(data))
    assert result == data
    
    # Test that items were written without newlines
    with open(str(temp_file_path), 'r') as file:
        content = file.read()
    assert content == "AliceBobCharlie"

def test_writeString_first_only_no_newline(tmpdir):
    """Test writeString with first_only=True and new_line=False."""
    data = ["Alice", "Bob", "Charlie"]
    
    temp_file_path = tmpdir.join("test_first_no_newline.txt")
    f = io.writeString(fname=str(temp_file_path), first_only=True, new_line=False)
    
    # Test that all items are still yielded
    result = list(f(data))
    assert result == data
    
    # Test that only first item was written without newline
    with open(str(temp_file_path), 'r') as file:
        content = file.read()
    assert content == "Alice"

def test_writeString_empty_data(tmpdir):
    """Test writeString with empty input data."""
    temp_file_path = tmpdir.join("test_empty.txt")
    f = io.writeString(fname=str(temp_file_path))
    
    result = list(f([]))
    assert result == []
    
    # File should exist but be empty
    assert os.path.exists(str(temp_file_path))
    with open(str(temp_file_path), 'r') as file:
        content = file.read()
    assert content == ""

def test_writeString_different_data_types(tmpdir):
    """Test writeString with various data types."""
    data = [
        42,
        3.14,
        True,
        None,
        [1, 2, 3],
        {"name": "Alice"}
    ]
    
    temp_file_path = tmpdir.join("test_types.txt")
    f = io.writeString(fname=str(temp_file_path))
    
    result = list(f(data))
    assert result == data
    
    # Verify all types were converted to strings correctly
    with open(str(temp_file_path), 'r') as file:
        content = file.read()
    expected = "42\n3.14\nTrue\nNone\n[1, 2, 3]\n{'name': 'Alice'}\n"
    assert content == expected

def test_writeString_compiler_integration(tmpdir):
    """Test writeString integration with compiler system."""
    data = ["Alice", "Bob"]
    
    temp_file_path = tmpdir.join("test_compiler.txt")
    
    # Test compilation and execution
    pipeline = compiler.compile(f'| writeString[fname="{str(temp_file_path)}"]')
    f = pipeline.asFunction(single_in=False, single_out=False)
    result = f(data)
    assert result == data
    
    # Verify file contents
    with open(str(temp_file_path), 'r') as file:
        content = file.read()
    assert content == "Alice\nBob\n"

def test_writeString_single_item(tmpdir):
    """Test writeString with single item."""
    data = ["single_item"]
    
    temp_file_path = tmpdir.join("test_single.txt")
    f = io.writeString(fname=str(temp_file_path))
    
    result = list(f(data))
    assert result == data
    
    with open(str(temp_file_path), 'r') as file:
        content = file.read()
    assert content == "single_item\n"
