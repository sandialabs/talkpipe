from talkpipe.pipe import math

def test_range():
    r = math.arange(lower=0, upper=5)
    assert list(r()) == [0, 1, 2, 3, 4]

def test_eq():
    e = math.EQ(field="1", n=3)
    e = e.as_function(single_in=False, single_out=False)
    assert e([[1,2,3], [5,6,7]]) == []

    e = math.EQ(field="_", n="hello")
    e = e.as_function(single_in=False, single_out=True)
    assert e(["hello", "world"]) == "hello"

def test_neq():
    e = math.NEQ(field="1", n=3)
    e = e.as_function(single_in=False, single_out=False)
    assert e([[1,2,3], [5,6,7]]) == [[1,2,3], [5,6,7]]

    e = math.NEQ(field="_", n="hello")
    e = e.as_function(single_in=False, single_out=True)
    assert e(["hello", "world"]) == "world"

def test_gt():
    g = math.GT(field="1", n=3)
    g = g.as_function(single_in=False, single_out=True)
    assert g([[1,2,3], [5,6,7]]) == [5,6,7]

def test_gte():
    g = math.GTE(field="1", n=3)
    g = g.as_function(single_in=False, single_out=False)
    assert g([[1,2,3], [5,6,7], [1,3,2]]) == [[5,6,7], [1,3,2]]

def test_lte():
    g = math.LTE(field="1", n=3)
    g = g.as_function(single_in=False, single_out=False)
    assert g([[1,2,3], [5,6,7], [1,3,2]]) == [[1,2,3], [1,3,2]]

def test_lt():
    g = math.LT(field="1", n=3)
    g = g.as_function(single_in=False, single_out=True)
    assert g([[1,2,3], [5,6,7]]) == [1,2,3]
