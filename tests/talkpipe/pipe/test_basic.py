import pytest
import sys
import pandas as pd
from talkpipe.pipe import basic
import talkpipe.pipe.io
from talkpipe.chatterlang import compiler
import logging
from pydantic import BaseModel

def test_progressTicks_basic(capsys):
    # Should print a tick every 2 items, newline after 4 ticks, no count
    t = basic.progressTicks(tick="*", tick_count=2, eol_count=4, print_count=False)
    t = t.as_function(single_in=False, single_out=False)
    ans = list(t(range(9)))
    assert ans == list(range(9))
    captured = capsys.readouterr()
    # 9 items, tick every 2: ticks at 2,4,6,8 (4 ticks), newline after 4 ticks
    assert "****\n" in captured.err
    assert "\n" in captured.err

def test_progressTicks_with_print_count(capsys):
    # Should print tick and count at end of line
    t = basic.progressTicks(tick=".", tick_count=1, eol_count=3, print_count=True)
    t = t.as_function(single_in=False, single_out=False)
    ans = list(t(range(6)))
    assert ans == list(range(6))
    captured = capsys.readouterr()
    # Should print 3 dots, then '3', newline, then 3 dots, '6', newline
    assert "...3\n" in captured.err
    assert "...6\n" in captured.err

def test_firstN():
    f = basic.firstN(n=3)
    f = f.as_function(single_in=False, single_out=False)
    ans = list(f([1, 2, 3, 4, 5]))
    assert ans == [1, 2, 3]

    f = basic.firstN(n=2)
    f = f.as_function(single_in=False, single_out=False)
    ans = list(f([{"x": 1}, {"x": 2}, {"x": 3}, {"x": 4}]))
    assert ans == [{"x": 1}, {"x": 2}]

    ans = list(f([{"x": 1}]))
    assert ans == [{"x": 1}]

def test_print_segment(capsys):
    op = talkpipe.pipe.io.Print()
    assert list(op.transform([42, 43, 44])) == [42, 43, 44]
    captured = capsys.readouterr()
    assert captured.out == "42\n43\n44\n"

    pipeline = basic.firstN() | talkpipe.pipe.io.Print()
    assert list(pipeline.transform([42, 43, 44])) == [42]
    captured = capsys.readouterr()
    assert captured.out == "42\n"

def test_DescribeDataSegment():
    ddt = basic.DescribeData()
    assert list(ddt.transform([1])) == [[]]
    assert list(ddt.transform([{"key": "value", "key2": {"ka": "va", "kb": "vb"}}])) == [["key", {"key2": ["ka", "kb"]}]]

def test_CastSegment():
    ct = basic.Cast(str)
    assert list(ct.transform([1])) == ["1"]
    assert list(ct.transform([{"key": "value"}])) == ["{'key': 'value'}"]

    ct = basic.Cast(float)
    assert list(ct.transform([1])) == [1.0]
    assert list(ct.transform([1,2])) == [1.0, 2.0]

    ct = basic.Cast("str")
    assert list(ct.transform([1])) == ["1"]

class TestExtractProperty:
    a_dict = {"key": "value"}
    a_list = ["a", "b", "c"]

    @property
    def a_property(self):
        return "a_value"

    def a_func(self):
        return "a_result"

def test_extractProperty():
    # Test extracting from a dictionary
    e = basic.extractProperty(property="name")
    e = e.as_function(single_in=True, single_out=True)
    assert e({"name": "Alice", "age": 30}) == "Alice"

    # Test extracting nested properties with dot notation
    e = basic.extractProperty(property="person.name")
    e = e.as_function(single_in=True, single_out=True)
    assert e({"person": {"name": "Bob", "age": 25}}) == "Bob"

    # Test extracting from nested dictionaries (multi-level)
    e = basic.extractProperty(property="a.b.c")
    e = e.as_function(single_in=True, single_out=True)
    assert e({"a": {"b": {"c": "value"}}}) == "value"

    # Test extracting list elements by index
    e = basic.extractProperty(property="0")
    e = e.as_function(single_in=True, single_out=True)
    assert e(["first", "second", "third"]) == "first"

    e = basic.extractProperty(property="2")
    e = e.as_function(single_in=True, single_out=True)
    assert e(["a", "b", "c", "d"]) == "c"

    # Test extracting from nested lists in dictionaries
    e = basic.extractProperty(property="colors.1")
    e = e.as_function(single_in=True, single_out=True)
    assert e({"colors": ["red", "green", "blue"]}) == "green"

    # Test the "_" special case (returns entire item)
    e = basic.extractProperty(property="_")
    e = e.as_function(single_in=True, single_out=True)
    assert e({"whole": "object"}) == {"whole": "object"}
    assert e("string_value") == "string_value"

    # Test extracting object attributes
    test_obj = TestExtractProperty()
    e = basic.extractProperty(property="a_dict")
    e = e.as_function(single_in=True, single_out=True)
    assert e(test_obj) == {"key": "value"}

    # Test extracting from object attribute that's a list
    e = basic.extractProperty(property="a_list")
    e = e.as_function(single_in=True, single_out=True)
    assert e(test_obj) == ["a", "b", "c"]

    # Test extracting property (getter)
    e = basic.extractProperty(property="a_property")
    e = e.as_function(single_in=True, single_out=True)
    assert e(test_obj) == "a_value"

    # Test extracting callable (method)
    e = basic.extractProperty(property="a_func")
    e = e.as_function(single_in=True, single_out=True)
    assert e(test_obj) == "a_result"

    # Test nested extraction: object attribute that's a dict
    e = basic.extractProperty(property="a_dict.key")
    e = e.as_function(single_in=True, single_out=True)
    assert e(test_obj) == "value"

    # Test nested extraction: object attribute that's a list with index
    e = basic.extractProperty(property="a_list.1")
    e = e.as_function(single_in=True, single_out=True)
    assert e(test_obj) == "b"

    # Test with field parameter (extracting from a specific field first)
    e = basic.extractProperty(property="name", field="data")
    e = e.as_function(single_in=True, single_out=True)
    assert e({"data": {"name": "Charlie"}}) == "Charlie"

    # Test with set_as parameter (adding result as a new field)
    e = basic.extractProperty(property="name", set_as="extracted_name")
    e = e.as_function(single_in=True, single_out=True)
    result = e({"name": "David", "age": 35})
    assert result == {"name": "David", "age": 35, "extracted_name": "David"}

def test_MakeDictSegment():
    mdt = basic.ToDict()
    assert list(mdt.transform(["Hello"])) == [{"original": "Hello"}]

    mdt = basic.ToDict(field_list="_,2:middle", fail_on_missing=True)
    assert list(mdt.transform([[3,4,5,6,7]])) == [{"original": [3,4,5,6,7], "middle": 5}]

def test_setAs():
    aa = basic.setAs(field_list="a:A,b,c.2:D")
    aa = aa.as_function(single_in=True, single_out=True)
    ans = aa({"a": 1, "b": 2, "c": [3,4,5]})
    assert ans == {"a": 1, "b": 2, "c": [3,4,5], "A": 1, "D": 5}

def test_setAs_with_pydantic():
    """Test that setAs works with pydantic objects"""

    class TestModel(BaseModel):
        model_config = {"extra": "allow"}  # Allow extra fields
        a: int
        b: int
        c: list

    # Create a pydantic model instance
    model = TestModel(a=1, b=2, c=[3, 4, 5])

    # Apply setAs to add new fields
    aa = basic.setAs(field_list="a:A,b,c.2:D")
    aa = aa.as_function(single_in=True, single_out=True)
    result = aa(model)

    # Check that original fields are preserved
    assert result.a == 1
    assert result.b == 2
    assert result.c == [3, 4, 5]

    # Check that new fields were added (A and D are extra fields)
    assert result.A == 1
    assert result.D == 5


def test_MakeDataFrameSegment():
    mdt = basic.ToDataFrame()
    input_data = [{"a": 1, "b": 2}, {"a": 3, "b": 4}]
    ans_list = list(mdt.transform(input_data))
    df = ans_list[0]
    assert len(ans_list) == 1
    assert isinstance(df, pd.DataFrame)
    assert list(df.columns) == ["a", "b"]
    assert list(df["a"]) == [1, 3]
    assert list(df["b"]) == [2, 4]

def test_MakeListSegment():
    mdt = basic.ToList()
    assert list(mdt.transform([1,2,3])) == [[1,2,3]]

def test_exec_command():
    # Use a cross-platform command that's almost guaranteed to exist
    if sys.platform.startswith('win'):
        # Windows-specific command
        command = "echo Hello, World!"
    else:
        # Unix/Linux command
        command = "echo 'Hello, World!'"

    e = basic.exec(command)
    ans = e()
    assert list(ans) == ["Hello, World!"]

    if sys.platform.startswith('win'):
        # Windows: use dir to list files
        command = "dir"
    else:
        # Unix/Linux: use ls to list files
        command = "ls"

    e = compiler.compile('INPUT FROM exec[command="' + command + '"] | print')
    ans = e()
    assert len(list(ans)) > 0
    
def each_char(s):
    for c in s:
        yield c

def test_concat():
    c = basic.concat(fields="a,b")
    c = c.as_function(single_in=True, single_out=True)
    ans = c({"a": "x", "b": "y"})
    assert ans == "x\n\ny"


    c = basic.concat(fields="a,b", delimiter="")
    c = c.as_function(single_in=True, single_out=True)
    ans = c({"a": "x", "b": "y"})
    assert ans == "xy"

    ans = c({"a": "x", "b": "y", "c": "z"})
    assert ans == "xy"

    c = basic.concat(fields="a,b", delimiter="|")
    c = c.as_function(single_in=True, single_out=True)
    ans = c({"a": "x", "b": "y"})
    assert ans == "x|y"

    ans = c({"a": "x", "b": "y", "c": "z"})
    assert ans == "x|y"

def test_slice():
    s = basic.slice()
    s = s.as_function(single_in=True, single_out=True)
    ans = s("abcdef")
    assert ans == "abcdef"

    s = basic.slice(range=":2")
    s = s.as_function(single_in=True, single_out=True)
    ans = s("abcdef")
    assert ans == "ab"

    s = basic.slice(range=":-2")
    s = s.as_function(single_in=True, single_out=True)
    ans = s("abcdef")
    assert ans == "abcd"

    s = basic.slice(range="2:")
    s = s.as_function(single_in=True, single_out=True)
    ans = s("abcdef")
    assert ans == "cdef"

    s = basic.slice(range="2:4")
    s = s.as_function(single_in=True, single_out=True)
    ans = s("abcdef")
    assert ans == "cd"

    s = basic.slice(field="x", range=":2")
    s = s.as_function(single_in=True, single_out=True)
    ans = s({"x": "abcdef"})
    assert ans == "ab"

    s = basic.slice(field="x", range=":2", set_as="y")
    s = s.as_function(single_in=True, single_out=True)
    ans = s({"x": "abcdef"})
    assert ans == {"x": "abcdef", "y": "ab"}

def test_isIn():
    i = basic.isIn(field = "_", value=1)
    i = i.as_function(single_in=True, single_out=False)
    assert list(i([1,2,3]))
    assert list(i([5,1,5]))
    assert len(list(i([2,3,4])))==0

    i = basic.isIn(field = "_", value=1, as_filter=False)
    i = i.as_function(single_in=True, single_out=False)
    assert list(i([1,2,3])) == [True]

    i = basic.isIn(value=1, field="x", set_as="y", as_filter=False)
    i = i.as_function(single_in=True, single_out=True)
    assert i({'x': [1,2,3]}) == {"x": [1,2,3], "y": True}

def test_isNotIn():
    i = basic.isNotIn(field = "_", value=1)
    i = i.as_function(single_in=True, single_out=False)
    assert len(list(i([1,2,3])))==0
    assert len(list(i([5,1,5])))==0
    assert len(list(i([2,3,4])))==1

    i = basic.isNotIn(field = "_", value=1, as_filter=False)
    i = i.as_function(single_in=True, single_out=False)
    assert list(i([1,2,3])) == [False]

    i = basic.isNotIn(value=1, field="x", set_as="y", as_filter=False)
    i = i.as_function(single_in=True, single_out=True)
    assert i({'x': [1,2,3]}) == {"x": [1,2,3], "y": False}


def test_isTrue():
    i = basic.isTrue(field = "_", as_filter=True)
    i = i.as_function(single_in=False, single_out=False)
    ans = list(i([1,0,None,True,False,"","Hello"]))
    assert ans == [1, True, "Hello"]

    i = basic.isTrue(field = "_", as_filter=False)
    i = i.as_function(single_in=False, single_out=False)
    ans = list(i([1,0,None,True,False,"","Hello"]))
    assert ans == [True, False, False, True, False, False, True]

    i = basic.isTrue(field = "x", as_filter=True)
    i = i.as_function(single_in=False, single_out=False)
    ans = list(i([{"x": 1}, {"x": 0}, {"x": None}, {"x": True}, {"x": False}, {"x": ""}, {"x": "Hello"}]))
    assert ans == [{"x": 1}, {"x": True}, {"x": "Hello"}]

    i = basic.isTrue(field = "x", as_filter=False, set_as="y")
    i = i.as_function(single_in=False, single_out=False)
    ans = list(i([{"x": 1}, {"x": 0}, {"x": None}, {"x": True}, {"x": False}, {"x": ""}, {"x": "Hello"}]))
    assert ans == [{"x": 1, "y": True}, {"x": 0, "y": False}, {"x": None, "y": False}, {"x": True, "y": True}, {"x": False, "y": False}, {"x": "", "y": False}, {"x": "Hello", "y": True}]  

def test_isFalse():
    i = basic.isFalse(field = "_", as_filter=True)
    i = i.as_function(single_in=False, single_out=False)
    ans = list(i([1,0,None,True,False,"","Hello"]))
    assert ans == [0, None, False, ""]

    i = basic.isFalse(field = "_", as_filter=False)
    i = i.as_function(single_in=False, single_out=False)
    ans = list(i([1,0,None,True,False,"","Hello"]))
    assert ans == [False, True, True, False, True, True, False]

    i = basic.isFalse(field = "x", as_filter=True)
    i = i.as_function(single_in=False, single_out=False)
    ans = list(i([{"x": 1}, {"x": 0}, {"x": None}, {"x": True}, {"x": False}, {"x": ""}, {"x": "Hello"}]))
    assert ans == [{"x": 0}, {"x": None}, {"x": False}, {"x": ""}]

    i = basic.isFalse(field = "x", as_filter=False, set_as="y")
    i = i.as_function(single_in=False, single_out=False)
    ans = list(i([{"x": 1}, {"x": 0}, {"x": None}, {"x": True}, {"x": False}, {"x": ""}, {"x": "Hello"}]))
    assert ans == [{"x": 1, "y": False}, {"x": 0, "y": True}, {"x": None, "y": True}, {"x": True, "y": False}, {"x": False, "y": True}, {"x": "", "y": True}, {"x": "Hello", "y": False}]

def test_everyN():
    e = basic.everyN(n=3)
    e = e.as_function(single_in=False, single_out=False)
    assert list(e(range(10))) == [2, 5, 8]
    assert list(e(range(4))) == [2]

def test_flatten():
    f = basic.flatten()
    f = f.as_function(single_in=False, single_out=False)
    ans = list(f([[1,2], [3,4]]))
    assert ans == [1,2,3,4]

    ans = list(f([[1,2], [3,4], [5,6]]))
    assert ans == [1,2,3,4,5,6]

    ans = list(f([{"a": [1,2], "b": [3,4]}]))
    assert ans == [("a", [1,2]), ("b", [3,4])]

    assert list(f([1])) == [1]

def test_hash():
    assert basic.hash_data("a") == basic.hash_data("a")
    assert basic.hash_data({"a": 1}) == basic.hash_data({"a": 1})
    assert basic.hash_data({"a": 1, "b": 3}) != basic.hash_data({"a": 2, "b": 6})
    assert basic.hash_data({"a": 1, "b": 3}, field_list=["a"]) != basic.hash_data({"a": 2, "b": 6}, field_list=["a"])
    assert basic.hash_data({"a": 1, "b": 3}, field_list=["_"]) != basic.hash_data({"a": 1, "b": 6}, field_list=["_"])

    assert basic.hash_data("a", use_repr=True) == basic.hash_data("a", use_repr=True)
    assert basic.hash_data({"a": 1}, use_repr=True) == basic.hash_data({"a": 1}, use_repr=True)
    assert basic.hash_data({"a": 1, "b": 3}, use_repr=True) != basic.hash_data({"a": 2, "b": 6}, use_repr=True)
    assert basic.hash_data({"a": 1, "b": 3}, field_list=["a"], use_repr=True) != basic.hash_data({"a": 2, "b": 6}, field_list=["a"], use_repr=True)
    assert basic.hash_data({"a": 1, "b": 3}, field_list=["_"], use_repr=True) != basic.hash_data({"a": 1, "b": 6}, field_list=["_"], use_repr=True)

    basic.hash_data({"a": None}, field_list="_") is not None

    with pytest.raises(ValueError):
        basic.hash_data({"a": 1}, field_list=["a"], use_repr=True, algorithm="unknown")

    with pytest.raises(AttributeError):
        basic.hash_data({"b": 1}, field_list=["a"])

    assert basic.hash_data("a", algorithm="SHA224") != basic.hash_data("a", algorithm="SHA256")

def test_hash_segment():
    s = basic.Hash()
    s = s.as_function(single_in=True, single_out=True)
    assert s("a") == s("a")

    s = basic.Hash(field_list="a")
    s = s.as_function(single_in=True, single_out=True)
    assert s({"a": 1, "b":2}) == s({"a": 1, "c":3})
    
    h = basic.hash_data(1)
    s = basic.Hash(set_as="hash", field_list="a")
    s = s.as_function(single_in=True, single_out=True)
    assert s({"a": 1}) == {"a": 1, "hash": h}

def test_fillTemplate():
    f = basic.fillTemplate(template="Hello {name}")
    f = f.as_function(single_in=True, single_out=True)
    assert f({"name": "World"}) == "Hello World"

    f = basic.fillTemplate(template="Hello {_}")
    f = f.as_function(single_in=True, single_out=True)
    assert f("World") == "Hello World"

    f = basic.fillTemplate(template="Hello {_}", field="name")
    f = f.as_function(single_in=True, single_out=True)
    assert f({"name": "World"}) == "Hello World"

    f = basic.fillTemplate(template="Hello {name}", set_as="greeting")
    f = f.as_function(single_in=True, single_out=True)
    assert f({"name": "World"}) == {"name": "World", "greeting": "Hello World"}

    f = basic.fillTemplate(template="Hello {{name}}")
    f = f.as_function(single_in=True, single_out=True)
    assert f({"name": "World"}) == "Hello {name}"

def test_lambda():
    f = basic.EvalExpression("item*2")
    f = f.as_function()
    ans = list(f([1, 2, 3]))
    assert ans == [2, 4, 6]

    f = basic.EvalExpression("len(item)")
    f = f.as_function()
    ans = list(f(["Hello", "World!"]))
    assert ans == [5, 6]

    f = basic.EvalExpression("item+1", field="x", set_as="y")
    f = f.as_function()
    ans = f([{"x": 1}, {"x": 2}])
    assert ans == [{"x": 1, "y": 2}, {"x": 2, "y": 3}]

    f = basic.EvalExpression("item+1", field="x")
    f = f.as_function()
    ans = f([{"x": 1}, {"x": 2}])
    assert ans == [2,3]

    f = basic.EvalExpression("'(TAG) ' +item")
    f = f.as_function()
    ans = f(["Hello", "World!"])
    assert ans == ["(TAG) Hello", "(TAG) World!"]

    f = basic.EvalExpression("'(LONG) '+item if len(item)>5 else item")
    f = f.as_function()
    ans = f(["Hello", "World!"])
    assert ans == ["Hello", "(LONG) World!"]


def test_lambdaFilter():
    f = basic.FilterExpression("item>2")
    f = f.as_function()
    ans = list(f([1, 2, 3, 4]))
    assert ans == [3, 4]

    f = basic.FilterExpression("item>2", field="x")
    f = f.as_function()
    ans = list(f([{"x": 3}, {"x": 2}, {"x": 4}]))
    assert ans == [{"x": 3}, {"x": 4}]

    # Test with field=None (use item directly, not extracting a field)
    f = basic.FilterExpression("item>2", field=None)
    f = f.as_function()
    ans = list(f([1, 2, 3, 4]))
    assert ans == [3, 4]

def test_longestStr():
    f = basic.longestStr(field_list="x,y")
    f = f.as_function(single_in=False, single_out=False)
    ans = list(f([{"x": "short", "y": "longest", "z":"reallymuchlonger"}, {"x": "longer", "y": "short", "z": "tiny"}]))
    assert ans == ["longest", "longer"]

    f = basic.longestStr(field_list="x,y", set_as="longest")
    f = f.as_function(single_in=False, single_out=False)
    ans = list(f([{"x": "short", "y": "longest", "z":"reallymuchlonger"}, {"x": "longer", "y": "short", "z": "tiny"}]))
    assert ans[0]["longest"] == "longest"
    assert ans[1]["longest"] == "longer"

def test_sleep():
    s = basic.sleep(seconds=1, n=2)
    s = s.as_function(single_in=False, single_out=False)
    import time
    start_time = time.time()
    ans = list(s([1,2,3,4,5]))
    end_time = time.time()
    assert ans == [1,2,3,4,5]
    elapsed = end_time - start_time
    # Should have slept approximately 2 times (after 2nd and 4th items)
    assert 2 <= elapsed < 4


# Additional tests for increased coverage


def test_cast_fail_not_silently():
    """Test Cast with fail_silently=False."""
    ct = basic.Cast(int, fail_silently=False)
    assert list(ct.transform([1, "2"])) == [1, 2]

    # Should raise ValueError when cast fails
    with pytest.raises(ValueError, match="Could not cast"):
        list(ct.transform(["not_a_number"]))


def test_formatted_item():
    """Test FormattedItem segment."""
    fi = basic.FormattedItem(field_list="title,content")
    result = list(fi.transform([{"title": "Hello", "content": "World"}]))
    assert len(result) == 1
    assert "title: Hello" in result[0]
    assert "content: World" in result[0]

    # Test with custom separators
    fi = basic.FormattedItem(
        field_list="a,b",
        field_name_separator=" = ",
        field_separator=" | ",
        item_suffix="END"
    )
    result = list(fi.transform([{"a": "1", "b": "2"}]))
    assert len(result) == 1
    assert "a = 1" in result[0]
    assert "b = 2" in result[0]
    assert "END" in result[0]


def test_assign_segment():
    """Test assign (set) segment."""
    # Call the assign function through the decorator-created class
    from talkpipe.chatterlang import compile
    f = compile('| set[value=42, set_as="answer"]')
    result = list(f([{"x": 1}, {"y": 2}]))
    assert result == [{"x": 1, "answer": 42}, {"y": 2, "answer": 42}]


def test_concat_with_set_as():
    """Test concat with set_as parameter."""
    c = basic.concat(fields="a,b", delimiter=" ", set_as="combined")
    c = c.as_function(single_in=True, single_out=True)
    result = c({"a": "hello", "b": "world"})
    assert result == {"a": "hello", "b": "world", "combined": "hello world"}


def test_longestStr_with_none_field():
    """Test longestStr when field is None or missing."""
    f = basic.longestStr(field_list="x,y,z")
    f = f.as_function(single_in=False, single_out=False)
    # Test with missing field (z doesn't exist)
    result = list(f([{"x": "short", "y": "longest"}]))
    assert result == ["longest"]

    # Test with set_as
    f = basic.longestStr(field_list="a,b", set_as="result")
    f = f.as_function(single_in=False, single_out=False)
    result = list(f([{"a": "tiny", "b": None}]))
    assert result[0]["result"] == "tiny"


def test_configure_logger():
    """Test ConfigureLogger segment."""
    cl = basic.ConfigureLogger(logger_levels="test:DEBUG")
    result = list(cl.transform([1, 2, 3]))
    assert result == [1, 2, 3]  # Should pass through unchanged


def test_hash_data_with_none_and_fail_on_missing():
    """Test hash_data when field value is None and fail_on_missing is True."""
    with pytest.raises(ValueError, match="Field .* value was None"):
        basic.hash_data({"a": None}, field_list=["a"], fail_on_missing=True)


def test_hash_data_with_none_and_not_fail_on_missing():
    """Test hash_data when field value is None and fail_on_missing is False."""
    # Should log a warning but not raise
    result = basic.hash_data({"a": None}, field_list=["a"], fail_on_missing=False)
    assert isinstance(result, str)


def test_hash_data_json_fallback():
    """Test hash_data JSON serialization fallback for non-JSON-serializable objects."""
    class CustomObject:
        def __init__(self, value):
            self.value = value

        def __repr__(self):
            return f"CustomObject({self.value})"

        def __str__(self):
            # Make str() raise an exception to force JSON fallback to repr
            raise TypeError("Cannot convert to string")

    obj = CustomObject(42)
    # Should use JSON first, then fallback to repr when JSON fails
    result = basic.hash_data(obj, use_repr=False)
    assert isinstance(result, str)

    # Also test with a set, which is not JSON serializable
    result2 = basic.hash_data({"a": {1, 2, 3}}, field_list=["a"], use_repr=False)
    assert isinstance(result2, str)


def test_hash_invalid_algorithm():
    """Test Hash segment with invalid algorithm."""
    with pytest.raises(ValueError, match="Unsupported or insecure hash algorithm"):
        basic.Hash(algorithm="MD5")

    with pytest.raises(ValueError, match="Unsupported or insecure hash algorithm"):
        basic.Hash(algorithm="invalid_algo")


def test_fillTemplate_none_template():
    """Test fillTemplate with None template."""
    f = basic.fillTemplate(template=None)
    f = f.as_function(single_in=True, single_out=True)

    with pytest.raises(ValueError, match="Template cannot be None"):
        f({"name": "World"})


def test_lambda_error_handling():
    """Test EvalExpression error handling."""
    f = basic.EvalExpression("1/item")
    f = f.as_function()

    # Should raise an error when dividing by zero
    with pytest.raises(Exception):
        list(f([0]))


def test_copy_segment():
    """Test copy segment."""
    c = basic.copy_segment()
    c = c.as_function(single_in=False, single_out=False)

    original = [{"a": 1}, {"b": 2}]
    result = list(c(original))

    # Should be equal but not the same object
    assert result == original
    assert result[0] is not original[0]

    # Modifying the copy shouldn't affect the original
    result[0]["a"] = 99
    assert original[0]["a"] == 1


def test_deep_copy_segment():
    """Test deep copy segment."""
    dc = basic.deep_copy_segment()
    dc = dc.as_function(single_in=False, single_out=False)

    original = [{"a": {"nested": 1}}, {"b": [1, 2, 3]}]
    result = list(dc(original))

    # Should be equal but not the same object
    assert result == original
    assert result[0] is not original[0]
    assert result[0]["a"] is not original[0]["a"]

    # Modifying nested structures shouldn't affect the original
    result[0]["a"]["nested"] = 99
    assert original[0]["a"]["nested"] == 1