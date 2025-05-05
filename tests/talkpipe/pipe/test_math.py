from talkpipe.pipe import math

def test_range():
    r = math.arange(lower=0, upper=5)
    assert list(r()) == [0, 1, 2, 3, 4]

def test_eq():
    e = math.eq(field="1", n=3)
    e = e.asFunction(single_in=False, single_out=False)
    assert e([[1,2,3], [5,6,7]]) == []

    e = math.eq(field="_", n="hello")
    e = e.asFunction(single_in=False, single_out=True)
    assert e(["hello", "world"]) == "hello"

def test_neq():
    e = math.neq(field="1", n=3)
    e = e.asFunction(single_in=False, single_out=False)
    assert e([[1,2,3], [5,6,7]]) == [[1,2,3], [5,6,7]]

    e = math.neq(field="_", n="hello")
    e = e.asFunction(single_in=False, single_out=True)
    assert e(["hello", "world"]) == "world"

def test_gt():
    g = math.gt(field="1", n=3)
    g = g.asFunction(single_in=False, single_out=True)
    assert g([[1,2,3], [5,6,7]]) == [5,6,7]

def test_gte():
    g = math.gte(field="1", n=3)
    g = g.asFunction(single_in=False, single_out=False)
    assert g([[1,2,3], [5,6,7], [1,3,2]]) == [[5,6,7], [1,3,2]]

def test_lte():
    g = math.lte(field="1", n=3)
    g = g.asFunction(single_in=False, single_out=False)
    assert g([[1,2,3], [5,6,7], [1,3,2]]) == [[1,2,3], [1,3,2]]

def test_lt():
    g = math.lt(field="1", n=3)
    g = g.asFunction(single_in=False, single_out=True)
    assert g([[1,2,3], [5,6,7]]) == [1,2,3]
