from typing import Iterable
from numpy import random

import talkpipe.pipe.core as core

@core.segment()
def add_one(items: Iterable[int]) -> Iterable[int]:
    for item in items:
        yield item + 1

@core.segment()
def double(items: Iterable[float]) -> Iterable[float]:
    for item in items:
        yield item * 2

@core.segment(multiplier=2)
def scale(items: Iterable[int], multiplier: int) -> Iterable[int]:
    for item in items:
        yield item * multiplier

@core.segment(offset=0)
def add(items: Iterable[int], offset: int) -> Iterable[int]:
    for item in items:
        yield item + offset

@core.segment(divisor=2)
def divide(items: Iterable[int], divisor: int) -> Iterable[int]:
    for x in items:
        yield x // divisor

@core.source()
def randomInts(n: int) -> Iterable[int]:
    yield from random.randint(0, 100, n)

def test_ordering():
    composed0 = add_one() | double() | scale(multiplier=3)
    composed2 = (add_one() | double()) | scale(multiplier=3)
    composed1 = add_one() | (double() | scale(multiplier=3))

    assert list(composed0([1])) == [12]
    assert list(composed2([1])) == [12]
    assert list(composed1([1])) == [12]

def test_direct_call():

    composed = add_one() | double() | scale(multiplier=3)
    assert list(composed([1])) == [12]

def test_operation_decorator_noparams():
    pipe = add_one()

    assert list(pipe.transform([42])) == [43]
    assert list(pipe.transform([1, 2, 3])) == [2, 3, 4]

    pipe = add_one() | double()

    assert list(pipe.transform([1, 2, 3])) == [4, 6, 8]


def test_operation_decorator_named_params():

    pipe = scale()

    assert list(pipe.transform([1, 2, 3])) == [2, 4, 6]

    pipe = scale(multiplier=3)

    assert list(pipe.transform([1, 2, 3])) == [3, 6, 9]

    pipe = add(offset=10)

    assert list(pipe.transform([1, 2, 3])) == [11, 12, 13]

    pipe = scale(multiplier=2) | add(offset=10) | scale(multiplier=3)

    assert list(pipe.transform([1, 2, 3])) == [36, 42, 48]

    pipe = divide()
    assert list(pipe.transform([10])) == [5]

def test_input_operation():

    pipe = randomInts(10) | add_one()

    ints = list(pipe.transform())
    assert len(ints) == 10


def test_runtime_component():

    class GetAVar(core.AbstractSource):

        def __init__(self, var_name: str):
            super().__init__()
            self.var_name = var_name

        def generate(self):
            yield from self.runtime.variable_store[self.var_name]

    class SetAVar(core.AbstractSegment):
        
        def __init__(self, var_name: str):
            super().__init__()
            self.var_name = var_name

        def transform(self, items):
            list_of_items = list(items)
            self.runtime.variable_store[self.var_name] = list_of_items
            yield list_of_items

    runtime = core.RuntimeComponent()
    gav = GetAVar("var1")
    gav.runtime = runtime
    sav = SetAVar("var1")
    sav.runtime = runtime
    sav = sav.asFunction(single_in=True, single_out=True)

    sav("A string")
    assert list(gav()) == ["A string"]
    

def test_function_segment():

    @core.field_segment()
    def add_two(item: int) -> int:
        return item + 2

    pipe = add_two()
    assert list(pipe([1, 2, 3])) == [3, 4, 5]

    pipe = add_two(field="x")
    assert list(pipe([{"x": 1, 'y': 2}, {"x": 2}, {"x": 3}])) == [3, 4, 5]

    pipe = add_two(field="x", append_as="z")
    assert list(pipe([{"x": 1, 'y': 2}, {"x": 2}, {"x": 3}])) == [{"x": 1, 'y': 2, 'z': 3}, {"x": 2, 'z': 4}, {"x": 3, 'z': 5}]

    @core.field_segment()
    def add_n(item: int, n: int) -> int:
        return item + n 
    
    pipe = add_n(n=3)
    assert list(pipe([1, 2, 3])) == [4, 5, 6]

    pipe = add_n(n=3, field="x")
    assert list(pipe([{"x": 1, 'y': 2}, {"x": 2}, {"x": 3}])) == [4, 5, 6]

    pipe = add_n(n=3, field="x", append_as="z")
    assert list(pipe([{"x": 1, 'y': 2}, {"x": 2}, {"x": 3}])) == [{"x": 1, 'y': 2, 'z': 4}, {"x": 2, 'z': 5}, {"x": 3, 'z': 6}]