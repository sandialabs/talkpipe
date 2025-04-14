from talkpipe.pipe import math

def test_range():
    r = math.arange(lower=0, upper=5)
    assert list(r()) == [0, 1, 2, 3, 4]

def test_gt():
    g = math.gt(field="1", n=3)
    g = g.asFunction(single_in=False, single_out=True)
    assert g([[1,2,3], [5,6,7]]) == [5,6,7]

def test_lt():
    g = math.lt(field="1", n=3)
    g = g.asFunction(single_in=False, single_out=True)
    assert g([[1,2,3], [5,6,7]]) == [1,2,3]
