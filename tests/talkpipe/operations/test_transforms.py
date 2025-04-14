import pytest
from talkpipe.operations import transforms

def test_regex_replace():
    op = transforms.regex_replace(pattern="a", replacement="b")
    op = op.asFunction(single_in=True, single_out=True)
    assert op("apple") == "bpple"
    assert op("banana") == "bbnbnb"
    assert op("cherry") == "cherry"

    op = transforms.regex_replace(pattern="a", replacement="b", field="x")
    op = op.asFunction(single_in=True, single_out=True)
    assert op({"y": "apple", "x": "y"}) == {"y": "apple", "x": "y"}
    assert op({"y": "apple", "x": "banana"}) == {"y": "apple", "x": "bbnbnb"}
    assert op({"y": "apple", "x": "cherry"}) == {"y": "apple", "x": "cherry"}

    with pytest.raises(TypeError):
        op({"x": 42})
    with pytest.raises(TypeError):
        op({"z": "apple", "x": 42})

    with pytest.raises(ValueError):
        op = transforms.regex_replace(pattern="a", replacement="b", field="x.2")
        op = op.asFunction(single_in=True, single_out=True)
        with pytest.raises(TypeError):
            op({"x": ["apple", "banana", "cherry"]})
    

def test_fill_null():
    op = transforms.fill_null(x=3)
    op = op.asFunction(single_in=True, single_out=True)
    assert op({"y": "apple", "x": None}) == {"y": "apple", "x": 3}
    assert op({"y": "apple", "x": "banana"}) == {"y": "apple", "x": "banana"}
    assert op({"y": None, "x": "cherry"}) == {"y": '', "x": "cherry"}


### makeLists tests


def test_makelists_basic():
    """Test the basic functionality of MakeLists with default parameters."""
    # Create a MakeLists instance with default parameters
    ml = transforms.MakeLists()
    
    # Test with a simple list of integers
    input_data = [1, 2, 3, 4, 5]
    result = list(ml.transform(input_data))
    
    # With default parameters, it should return a single list with all items
    assert len(result) == 1
    assert result[0] == [1, 2, 3, 4, 5]

def test_makelists_num_items():
    """Test MakeLists with specified num_items parameter."""
    # Create a MakeLists instance with num_items=2
    ml = transforms.MakeLists(num_items=2)
    
    # Test with a list of integers
    input_data = [1, 2, 3, 4, 5]
    result = list(ml.transform(input_data))
    
    # Should yield lists of 2 items, with the remainder at the end
    assert len(result) == 3
    assert result[0] == [1, 2]
    assert result[1] == [3, 4]
    assert result[2] == [5]

def test_makelists_cumulative():
    """Test MakeLists with cumulative=True."""
    # Create a MakeLists instance with num_items=2 and cumulative=True
    ml = transforms.MakeLists(num_items=2, cumulative=True)
    
    # Test with a list of integers
    input_data = [1, 2, 3, 4, 5]
    result = list(ml.transform(input_data))
    
    # Should yield overlapping lists
    assert len(result) == 3
    assert result[0] == [1, 2]
    assert result[1] == [1, 2, 3, 4]
    assert result[2] == [1, 2, 3, 4, 5]

def test_makelists_field():
    """Test MakeLists with field parameter."""
    # Create a MakeLists instance with field="value"
    ml = transforms.MakeLists(field="value")
    
    # Test with a list of dictionaries
    input_data = [
        {"id": 1, "value": "a"},
        {"id": 2, "value": "b"},
        {"id": 3, "value": "c"}
    ]
    result = list(ml.transform(input_data))
    
    # Should extract the "value" field from each dictionary
    assert len(result) == 1
    assert result[0] == ["a", "b", "c"]

def test_makelists_ignore_none():
    """Test MakeLists with ignoreNone=True."""
    # Create a MakeLists instance with ignoreNone=True
    ml = transforms.MakeLists(ignoreNone=True)
    
    # Test with a list including None values
    input_data = [1, None, 3, None, 5]
    result = list(ml.transform(input_data))
    
    # Should skip None values
    assert len(result) == 1
    assert result[0] == [1, 3, 5]

def test_makelists_combinations():
    """Test MakeLists with combinations of parameters."""
    # Create a MakeLists instance with multiple parameters
    ml = transforms.MakeLists(num_items=3, cumulative=True, field="data", ignoreNone=True)
    
    # Test with complex data
    input_data = [
        {"id": 1, "data": "a"},
        {"id": 2, "data": None},
        {"id": 3, "data": "c"},
        {"id": 4, "data": "d"},
        {"id": 5, "data": None},
        {"id": 6, "data": "f"}
    ]
    result = list(ml.transform(input_data))
    
    # Should extract "data" field, ignore None values, and yield cumulative lists of size 3
    assert len(result) == 2
    assert result[0] == ["a", "c", "d"]
    assert result[1] == ["a", "c", "d", "f"]

def test_makelists_invalid_parameters():
    """Test MakeLists with invalid parameters."""
    # Test with negative num_items
    with pytest.raises(AssertionError, match="num_vectors must be None or a positive integer"):
        ml = transforms.MakeLists(num_items=-1)
        list(ml.transform([1, 2, 3]))

def test_makelists_empty_input():
    """Test MakeLists with empty input."""
    ml = transforms.MakeLists()
    result = list(ml.transform([]))
    assert len(result) == 0

def test_makelists_exact_num_items():
    """Test MakeLists when input length is exactly num_items."""
    ml = transforms.MakeLists(num_items=3)
    input_data = [1, 2, 3]
    result = list(ml.transform(input_data))
    
    assert len(result) == 1
    assert result[0] == [1, 2, 3]

def test_makelists_nested_field():
    """Test MakeLists with nested field extraction."""
    ml = transforms.MakeLists(field="user.name")
    
    input_data = [
        {"user": {"name": "Alice", "age": 30}},
        {"user": {"name": "Bob", "age": 25}},
        {"user": {"name": "Charlie", "age": 35}}
    ]
    result = list(ml.transform(input_data))
    
    assert len(result) == 1
    assert result[0] == ["Alice", "Bob", "Charlie"]