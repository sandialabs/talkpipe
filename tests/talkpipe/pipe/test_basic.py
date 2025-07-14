import pytest
import sys
import pandas as pd
from talkpipe.pipe import basic
import talkpipe.pipe.io
from talkpipe.chatterlang import compiler

def test_progressTicks_basic(capsys):
    # Should print a tick every 2 items, newline after 4 ticks, no count
    t = basic.progressTicks(tick="*", tick_count=2, eol_count=4, print_count=False)
    t = t.asFunction(single_in=False, single_out=False)
    ans = list(t(range(9)))
    assert ans == list(range(9))
    captured = capsys.readouterr()
    # 9 items, tick every 2: ticks at 2,4,6,8 (4 ticks), newline after 4 ticks
    assert captured.out.count("*") == 4
    assert "\n" in captured.out

def test_progressTicks_with_print_count(capsys):
    # Should print tick and count at end of line
    t = basic.progressTicks(tick=".", tick_count=1, eol_count=3, print_count=True)
    t = t.asFunction(single_in=False, single_out=False)
    ans = list(t(range(6)))
    assert ans == list(range(6))
    captured = capsys.readouterr()
    # Should print 3 dots, then '3', newline, then 3 dots, '6', newline
    assert captured.out.count(".") == 6
    assert "3" in captured.out and "6" in captured.out

def test_firstN():
    f = basic.firstN(n=3)
    f = f.asFunction(single_in=False, single_out=False)
    ans = list(f([1, 2, 3, 4, 5]))
    assert ans == [1, 2, 3]

    f = basic.firstN(n=2)
    f = f.asFunction(single_in=False, single_out=False)
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

def test_MakeDictSegment():
    mdt = basic.ToDict()
    assert list(mdt.transform(["Hello"])) == [{"original": "Hello"}]

    mdt = basic.ToDict(field_list="_,2:middle", fail_on_missing=True)
    assert list(mdt.transform([[3,4,5,6,7]])) == [{"original": [3,4,5,6,7], "middle": 5}]

def test_appendAs():
    aa = basic.appendAs(field_list="a:A,b,c.2:D")
    aa = aa.asFunction(single_in=True, single_out=True)
    ans = aa({"a": 1, "b": 2, "c": [3,4,5]})
    assert ans == {"a": 1, "b": 2, "c": [3,4,5], "A": 1, "D": 5}


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
    c = c.asFunction(single_in=True, single_out=True)
    ans = c({"a": "x", "b": "y"})
    assert ans == "x\n\ny"


    c = basic.concat(fields="a,b", delimiter="")
    c = c.asFunction(single_in=True, single_out=True)
    ans = c({"a": "x", "b": "y"})
    assert ans == "xy"

    ans = c({"a": "x", "b": "y", "c": "z"})
    assert ans == "xy"

    c = basic.concat(fields="a,b", delimiter="|")
    c = c.asFunction(single_in=True, single_out=True)
    ans = c({"a": "x", "b": "y"})
    assert ans == "x|y"

    ans = c({"a": "x", "b": "y", "c": "z"})
    assert ans == "x|y"

def test_slice():
    s = basic.slice()
    s = s.asFunction(single_in=True, single_out=True)
    ans = s("abcdef")
    assert ans == "abcdef"

    s = basic.slice(range=":2")
    s = s.asFunction(single_in=True, single_out=True)
    ans = s("abcdef")
    assert ans == "ab"

    s = basic.slice(range=":-2")
    s = s.asFunction(single_in=True, single_out=True)
    ans = s("abcdef")
    assert ans == "abcd"

    s = basic.slice(range="2:")
    s = s.asFunction(single_in=True, single_out=True)
    ans = s("abcdef")
    assert ans == "cdef"

    s = basic.slice(range="2:4")
    s = s.asFunction(single_in=True, single_out=True)
    ans = s("abcdef")
    assert ans == "cd"

    s = basic.slice(field="x", range=":2")
    s = s.asFunction(single_in=True, single_out=True)
    ans = s({"x": "abcdef"})
    assert ans == "ab"

    s = basic.slice(field="x", range=":2", append_as="y")
    s = s.asFunction(single_in=True, single_out=True)
    ans = s({"x": "abcdef"})
    assert ans == {"x": "abcdef", "y": "ab"}

def test_isIn():
    i = basic.isIn(field = "_", value=1)
    i = i.asFunction(single_in=True, single_out=False)
    assert list(i([1,2,3]))
    assert list(i([5,1,5]))
    assert len(list(i([2,3,4])))==0

def test_isNotIn():
    i = basic.isNotIn(field = "_", value=1)
    i = i.asFunction(single_in=True, single_out=False)
    assert len(list(i([1,2,3])))==0
    assert len(list(i([5,1,5])))==0
    assert len(list(i([2,3,4])))==1

def test_everyN():
    e = basic.everyN(n=3)
    e = e.asFunction(single_in=False, single_out=False)
    assert list(e(range(10))) == [2, 5, 8]
    assert list(e(range(4))) == [2]

def test_flatten():
    f = basic.flatten()
    f = f.asFunction(single_in=False, single_out=False)
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

    assert basic.hash_data("a", algorithm="md5") != basic.hash_data("a", algorithm="SHA1")

def test_hash_segment():
    s = basic.Hash()
    s = s.asFunction(single_in=True, single_out=True)
    assert s("a") == s("a")

    s = basic.Hash(field_list="a")
    s = s.asFunction(single_in=True, single_out=True)
    assert s({"a": 1, "b":2}) == s({"a": 1, "c":3})
    
    h = basic.hash_data(1)
    s = basic.Hash(append_as="hash", field_list="a")
    s = s.asFunction(single_in=True, single_out=True)
    assert s({"a": 1}) == {"a": 1, "hash": h}

def test_fillTemplate():
    f = basic.fillTemplate(template="Hello {name}")
    f = f.asFunction(single_in=True, single_out=True)
    assert f({"name": "World"}) == "Hello World"

    f = basic.fillTemplate(template="Hello {_}")
    f = f.asFunction(single_in=True, single_out=True)
    assert f("World") == "Hello World"

    f = basic.fillTemplate(template="Hello {_}", field="name")
    f = f.asFunction(single_in=True, single_out=True)
    assert f({"name": "World"}) == "Hello World"

    f = basic.fillTemplate(template="Hello {name}", append_as="greeting")
    f = f.asFunction(single_in=True, single_out=True)
    assert f({"name": "World"}) == {"name": "World", "greeting": "Hello World"}

    f = basic.fillTemplate(template="Hello {{name}}")
    f = f.asFunction(single_in=True, single_out=True)
    assert f({"name": "World"}) == "Hello {name}"

def test_lambda():
    f = basic.EvalExpression("item*2")
    f = f.asFunction()
    ans = list(f([1, 2, 3]))
    assert ans == [2, 4, 6]

    f = basic.EvalExpression("len(item)")
    f = f.asFunction()
    ans = list(f(["Hello", "World!"]))
    assert ans == [5, 6]

    f = basic.EvalExpression("item+1", field="x", append_as="y")
    f = f.asFunction()
    ans = f([{"x": 1}, {"x": 2}])
    assert ans == [{"x": 1, "y": 2}, {"x": 2, "y": 3}]

    f = basic.EvalExpression("item+1", field="x")
    f = f.asFunction()
    ans = f([{"x": 1}, {"x": 2}])
    assert ans == [2,3]

    f = basic.EvalExpression("'(TAG) ' +item")
    f = f.asFunction()
    ans = f(["Hello", "World!"])
    assert ans == ["(TAG) Hello", "(TAG) World!"]

    f = basic.EvalExpression("'(LONG) '+item if len(item)>5 else item")
    f = f.asFunction()
    ans = f(["Hello", "World!"])
    assert ans == ["Hello", "(LONG) World!"]


def test_lambdaFilter():
    f = basic.FilterExpression("item>2")
    f = f.asFunction()
    ans = list(f([1, 2, 3, 4]))
    assert ans == [3, 4]

    f = basic.FilterExpression("item>2", field="x")
    f = f.asFunction()
    ans = list(f([{"x": 3}, {"x": 2}, {"x": 4}]))
    assert ans == [{"x": 3}, {"x": 4}]

def test_longestStr():
    f = basic.longestStr(field_list="x,y")
    f = f.asFunction(single_in=False, single_out=False)
    ans = list(f([{"x": "short", "y": "longest", "z":"reallymuchlonger"}, {"x": "longer", "y": "short", "z": "tiny"}]))
    assert ans == ["longest", "longer"]

    f = basic.longestStr(field_list="x,y", append_as="longest")
    f = f.asFunction(single_in=False, single_out=False)
    ans = list(f([{"x": "short", "y": "longest", "z":"reallymuchlonger"}, {"x": "longer", "y": "short", "z": "tiny"}]))
    assert ans[0]["longest"] == "longest"
    assert ans[1]["longest"] == "longer"

