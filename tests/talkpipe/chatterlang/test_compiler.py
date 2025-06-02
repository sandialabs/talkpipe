import os
from unittest.mock import patch
import time
import numpy as np
from talkpipe.chatterlang import parsers, compiler
from talkpipe.chatterlang import registry
from talkpipe.pipe import io
from talkpipe.pipe import basic
from talkpipe.pipe import core
from talkpipe.util.config import reset_config

def test_pipeline_compiler():
    parsed = parsers.script_parser.parse("firstN")
    compiled = compiler.compile(parsed)
    assert list(compiled.transform([42, 10, 20])) == [42]

    compiled = compiler.compile("firstN")
    assert list(compiled.transform([42, 10, 20])) == [42]

    compiled = compiler.compile("| firstN | firstN")
    assert list(compiled.transform([42, 10, 20])) == [42]

    compiled = compiler.compile("INPUT FROM randomInts[n=5]")
    ans = list(compiled.transform())
    assert len(ans) == 5
    assert all([isinstance(x, np.int64) for x in ans]) 

    compiled = compiler.compile("INPUT FROM randomInts[n=5] | firstN")
    ans = list(compiled.transform())
    assert len(ans) == 1
    assert isinstance(ans[0], np.int64)

    compiled = compiler.compile('INPUT FROM "This is a string"')
    ans = list(compiled())
    assert len(ans) == 1
    assert ans[0] == "This is a string"

    script_text = """INPUT FROM "This is a string
    with a newline" """
    compiled = compiler.compile(script_text)
    ans = list(compiled())
    assert len(ans) == 1
    assert ans[0] == script_text[len("INPUT FROM \""):-2]

    v_store = core.RuntimeComponent()
    script = compiler.compile('INPUT FROM "Hello all!" | @var1', v_store)
    list(script())
    ans = v_store.variable_store["var1"]
    assert len(ans) == 1
    assert ans[0] == "Hello all!"

def test_pipeline_two_pipelines():
    v_store = core.RuntimeComponent()
    script = compiler.compile("INPUT FROM randomInts[n=5] | @var1", v_store)
    list(script())
    ans = v_store.variable_store["var1"]
    assert len(ans) == 5

    v_store = core.RuntimeComponent()
    script = compiler.compile("INPUT FROM randomInts[n=5] | @var1; INPUT FROM randomInts[n=5] | @var2", v_store)
    list(script())
    ans = v_store.variable_store["var1"]
    assert len(ans) == 5
    ans = v_store.variable_store["var2"]
    assert len(ans) == 5



def test_pipeline_variables():
    v_store = core.RuntimeComponent()
    script = compiler.compile("INPUT FROM randomInts[n=5, lower=-2, upper=5] | @some_nums", v_store)
    list(script())
    ans = v_store.variable_store["some_nums"]
    assert len(ans) == 5
    assert all([isinstance(x, np.int64) for x in ans])
    assert all([x >= -2 and x < 5 for x in ans])

    script = compiler.compile("INPUT FROM randomInts[n=5, lower=-2, upper=5] | @some_nums | firstN", v_store)
    ans = list(script())
    assert len(ans) == 1
    assert isinstance(ans[0], np.int64)
    assert ans[0] in v_store.variable_store["some_nums"]
    assert ans[0] >= -2 and ans[0] < 5
    assert len(v_store.variable_store["some_nums"]) == 5

    script = compiler.compile("INPUT FROM range[lower=0, upper=5] | @some_nums; INPUT FROM @some_nums | scale | @some_other_nums", v_store)
    ans = list(script())
    assert len(ans) == 5
    assert ans == [0, 2, 4, 6, 8]
    assert v_store.variable_store["some_other_nums"] == ans
    first_nums = v_store.variable_store["some_nums"]
    assert len(first_nums) == 5
    assert first_nums == list(range(5))


def test_loop_compiler():
    v_store = core.RuntimeComponent()
    script = compiler.compile("INPUT FROM range[lower=0, upper=2] | @nums; LOOP 2 TIMES { INPUT FROM @nums | scale[multiplier=2] | @nums }", v_store)
    list(script())
    ans = v_store.variable_store["nums"]
    assert len(ans) == 2
    assert ans == [0, 4]

def test_fork_compiler():
    rtc = core.RuntimeComponent()
    script = compiler.compile("INPUT FROM range[lower=0, upper=2] | fork(scale[multiplier=2], scale[multiplier=3])", rtc)
    ans = list(script())
    assert len(ans) == 4
    assert set(ans) == set([0, 2, 0, 3])

def test_fork_compiler_multiple_inputs():
    script = compiler.compile('fork(INPUT FROM echo[data="1,2,3"], INPUT FROM echo[data="4,5,6"])')
    ans = list(script())
    assert set(ans) == set(["1", "2", "3", "4", "5", "6"])

def test_fork_parallel():

    @registry.register_source("slowNums")
    @core.source()
    def slowNums():
        for i in range(5):
            time.sleep(.25)
            yield i

    script = compiler.compile('fork(INPUT FROM slowNums, INPUT FROM echo[data="a,b,c,d,e"])')
    ans = list(script())
    assert ans == ["a", "b", "c", "d", "e", 0, 1, 2, 3, 4]


def test_variables_as_parameters():
    v_score = core.RuntimeComponent()
    script = compiler.compile('CONST var1 = "Hello"; INPUT FROM echo[data=var1] | print', v_score).asFunction(single_out=True)    
    ans = script()
    assert ans == "Hello"
    assert v_score.const_store["var1"] == "Hello"


def test_constant_declarations():
    runtime = core.RuntimeComponent()
    script = compiler.compile('CONST var1 = "Hello"; INPUT FROM "goodbye" | print', runtime).asFunction(single_out=True)
    ans = script()
    assert ans == "goodbye"
    assert runtime.const_store["var1"] == "Hello"

def test_multiple_constants():
    runtime = core.RuntimeComponent()
    script = compiler.compile(
        """
        CONST var1 = "Hello";
        CONST var2 = "World";
        INPUT FROM "goodbye" | print""", runtime).asFunction(single_out=True)
    ans = script()
    assert ans == "goodbye"
    assert runtime.const_store["var1"] == "Hello"

def test_accum():
    runtime = core.RuntimeComponent()
    pipeline = compiler.compile(
        """
        | accum[variable=@s] | accum[variable=@a] | scale[multiplier=2] | accum[variable=@a]
        """, runtime)

    ans = list(pipeline([1, 2, 3]))
    assert ans == [2, 4, 6]
    assert runtime.variable_store["s"] == [1, 2, 3]
    assert runtime.variable_store["a"] == [1, 2, 2, 4, 3, 6]

    ans = list(pipeline([4, 5, 6]))
    assert ans == [8, 10, 12]
    assert runtime.variable_store["s"] == [1, 2, 3, 4, 5, 6]
    assert runtime.variable_store["a"] == [1, 2, 2, 4, 3, 6, 4, 8, 5, 10, 6, 12]

    accum = compiler.Accum(reset=False)
    pipeline = io.echo(data="1,2,ok,3", delimiter=",") | basic.Cast(cast_type=int) | accum
    ans = list(pipeline())
    ans = list(pipeline())
    assert ans == [1,2,3,1, 2, 3]
    assert accum.accumulator == [1, 2, 3, 1, 2, 3]

    accum = compiler.Accum(reset=True)
    pipeline = io.echo(data="1,2,ok,3", delimiter=",") | basic.Cast(cast_type=int) | accum
    ans = list(pipeline())
    ans = list(pipeline())
    assert ans == [1, 2, 3]
    assert accum.accumulator == [1, 2, 3]

    
def test_remove_comments_single_line():
    # Comment outside of quotes should be removed.
    input_text = 'print("Hello, world!") # This prints greeting\n'
    expected = 'print("Hello, world!") \n'
    assert compiler.remove_comments(input_text) == expected

def test_remove_comments_with_hash_in_quotes():
    # Hash inside quotes should remain.
    input_text = 'print("This is a # character") # remove comment\n'
    expected = 'print("This is a # character") \n'
    assert compiler.remove_comments(input_text) == expected

def test_remove_comments_multiple_lines():
    # Test multiple lines with and without comments.
    input_text = (
        'a = 5 # initialize a\n'
        'b = "Not a # comment" # real comment\n'
        'c = "Another # example"\n'
        '# Full line comment\n'
        'd = 10\n'
    )
    expected = (
        'a = 5 \n'
        'b = "Not a # comment" \n'
        'c = "Another # example"\n'
        '\n'
        'd = 10\n'
    )
    assert compiler.remove_comments(input_text) == expected

def test_remove_comments_no_comment():
    # When there are no comments, the text remains unchanged.
    input_text = 'print("No comment here")\n'
    expected = 'print("No comment here")\n'
    assert compiler.remove_comments(input_text) == expected    

def test_pipeline_with_comments():
    v_store = core.RuntimeComponent()
    script = compiler.compile(
        """
        # here is an opening comment
        INPUT FROM range[lower=0, upper=2] | @nums; LOOP 2 TIMES #end of line comment
        # in the mittle of a loop comment (don't do this!) #### more to check this
        { INPUT FROM @nums | scale[multiplier=2] | @nums }

        #end of script comment after a blank line.
        """, v_store)
    list(script())
    ans = v_store.variable_store["nums"]
    assert len(ans) == 2
    assert ans == [0, 4]

def test_snippet_script_source():
    v_store = core.RuntimeComponent()
    script = compiler.compile(
        """
        | snippet[script_source="scale[multiplier=2]"]
        """, v_store)
    ans = list(script([0, 2]))
    assert len(ans) == 2
    assert ans == [0, 4]

def test_snippet_file_source(tmp_path):
    v_store = core.RuntimeComponent()
    with open(tmp_path / "test_snippet.py", "w") as f:
        f.write("scale[multiplier=2]")
    # Test the snippet with a file source
    script = compiler.compile(
        f"""
        | snippet[script_source="{tmp_path}/test_snippet.py"]
        """, v_store)
    ans = list(script([0, 2]))
    assert len(ans) == 2
    assert ans == [0, 4]
 
def test_snippet_multi_use():
    v_store = core.RuntimeComponent()
    script = compiler.compile(
        """
        CONST subscript = "scale[multiplier=2]"
        | fork (snippet[script_source=subscript], snippet[script_source=subscript])
        """, v_store)
    ans = sorted(list(script([0, 2])))
    assert len(ans) == 4
    assert ans == [0, 0, 4, 4]

def test_fork_with_tests():
    v_store = core.RuntimeComponent()
    script = compiler.compile(
        """
        INPUT FROM range[lower=0, upper=5] | fork (
            gt[field="_", n=2] | scale[multiplier=2],
            lte[field="_", n=2]
        )
        """, v_store)
    ans = sorted(list(script()))
    assert len(ans) == 5
    assert ans == [0,1,2,6,8]

def test_environment_variable_support():
    with patch.dict(os.environ, {'TALKPIPE_some_var': 'a,b,c,d'}):
        reset_config()
        f = compiler.compile("""
            INPUT FROM echo[data=$some_var]
        """)
        f = f.asFunction(single_out=False)
        ans = list(f())
        assert ans == ['a', 'b', 'c', 'd']
