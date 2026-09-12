import logging
import os
import time
import warnings
from unittest.mock import patch

import numpy as np
import pytest

from talkpipe.chatterlang import compiler, parsers, registry
from talkpipe.pipe import (
    basic,
    core,
    io,  # Import to register flushN and collectMetadata
)
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
    assert all(isinstance(x, np.int64) for x in ans)

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
    assert ans[0] == script_text[len('INPUT FROM "') : -2]

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
    script = compiler.compile(
        "INPUT FROM randomInts[n=5] | @var1; INPUT FROM randomInts[n=5] | @var2",
        v_store,
    )
    list(script())
    ans = v_store.variable_store["var1"]
    assert len(ans) == 5
    ans = v_store.variable_store["var2"]
    assert len(ans) == 5


def test_pipeline_variables():
    v_store = core.RuntimeComponent()
    script = compiler.compile(
        "INPUT FROM randomInts[n=5, lower=-2, upper=5] | @some_nums", v_store
    )
    list(script())
    ans = v_store.variable_store["some_nums"]
    assert len(ans) == 5
    assert all(isinstance(x, np.int64) for x in ans)
    assert all(x >= -2 and x < 5 for x in ans)

    script = compiler.compile(
        "INPUT FROM randomInts[n=5, lower=-2, upper=5] | @some_nums | firstN", v_store
    )
    ans = list(script())
    assert len(ans) == 1
    assert isinstance(ans[0], np.int64)
    assert ans[0] in v_store.variable_store["some_nums"]
    assert ans[0] >= -2
    assert ans[0] < 5
    assert len(v_store.variable_store["some_nums"]) == 5

    script = compiler.compile(
        "INPUT FROM range[lower=0, upper=5] | @some_nums; INPUT FROM @some_nums | scale | @some_other_nums",
        v_store,
    )
    ans = list(script())
    assert len(ans) == 5
    assert ans == [0, 2, 4, 6, 8]
    assert v_store.variable_store["some_other_nums"] == ans
    first_nums = v_store.variable_store["some_nums"]
    assert len(first_nums) == 5
    assert first_nums == list(range(5))


def test_loop_compiler():
    v_store = core.RuntimeComponent()
    script = compiler.compile(
        "INPUT FROM range[lower=0, upper=2] | @nums; LOOP 2 TIMES { INPUT FROM @nums | scale[multiplier=2] | @nums }",
        v_store,
    )
    list(script())
    ans = v_store.variable_store["nums"]
    assert len(ans) == 2
    assert ans == [0, 4]


def test_fork_compiler():
    rtc = core.RuntimeComponent()
    script = compiler.compile(
        "INPUT FROM range[lower=0, upper=2] | fork(scale[multiplier=2], scale[multiplier=3])",
        rtc,
    )
    ans = list(script())
    assert len(ans) == 4
    assert set(ans) == {0, 2, 3}


def test_fork_compiler_multiple_inputs():
    script = compiler.compile(
        'fork(INPUT FROM echo[data="1,2,3"], INPUT FROM echo[data="4,5,6"])'
    )
    ans = list(script())
    assert set(ans) == {"1", "2", "3", "4", "5", "6"}


def test_fork_parallel():

    @registry.register_source("slowNums")
    @core.source()
    def slowNums():
        for i in range(5):
            time.sleep(0.25)
            yield i

    script = compiler.compile(
        'fork(INPUT FROM slowNums, INPUT FROM echo[data="a,b,c,d,e"])'
    )
    ans = list(script())
    assert ans == ["a", "b", "c", "d", "e", 0, 1, 2, 3, 4]


def test_fork_preserves_metadata():
    script = compiler.compile(
        """INPUT FROM range[lower=0, upper=3] | flushN[n=1] | collectMetadata | toList"""
    )
    ans = list(script())
    assert len(ans) == 1
    assert len(ans[0]) == 3
    assert all(isinstance(item, str) for item in ans[0])

    script = compiler.compile("""
            INPUT FROM range[lower=0, upper=3] | flushN[n=1] |
            fork(collectMetadata | toList)""")
    ans = list(script())
    assert len(ans) == 1
    assert len(ans[0]) == 3
    assert all(isinstance(item, str) for item in ans[0])


def test_fork_arrow_syntax_multiple_inputs():

    script = """
             INPUT FROM range[lower=0, upper=5] | sleep[seconds=1] -> afork;
             INPUT FROM range[lower=10, upper=15] | sleep[seconds=1] -> afork;
             afork -> toList
             """
    f = compiler.compile(script).as_function(single_in=True, single_out=True)
    ans = f()
    assert sorted(ans) == [0, 1, 2, 3, 4, 10, 11, 12, 13, 14]


def test_fork_arrow_syntax_multiple_outputs():
    script = """
             INPUT FROM range[lower=0, upper=5] -> afork;
             afork -> lambda[expression="item * 2"] -> bfork;
             afork -> lambda[expression="item * 3"] -> bfork;
             bfork -> toList
             """
    f = compiler.compile(script).as_function(single_in=True, single_out=True)
    ans = f()
    assert sorted(ans) == sorted([0, 2, 4, 6, 8, 0, 3, 6, 9, 12])


def test_fork_arrow_syntax_multiple_forks():
    """Test that multiple independent forks can be used in a single script."""
    script = """
             INPUT FROM range[lower=0, upper=3] -> fork1;
             INPUT FROM range[lower=10, upper=13] -> fork2;
             fork1 -> lambda[expression="item * 2"] | lambda[expression="item + 1"] -> fork3;
             fork2 -> lambda[expression="item + 100"] -> fork3;
             fork3 -> toList
             """
    f = compiler.compile(script).as_function(single_in=True, single_out=True)
    ans = f()
    assert sorted(ans) == sorted([1, 3, 5, 110, 111, 112])


def test_fork_arrow_syntax_metadata():

    script = """INPUT FROM range[lower=0, upper=3] | flushN[n=1] | collectMetadata | toList"""
    f = compiler.compile(script).as_function(single_in=True, single_out=True)
    ans = f()
    assert len(ans) == 3
    assert all(isinstance(item, str) for item in ans)

    script = """
             INPUT FROM range[lower=0, upper=3] | flushN[n=1] -> fork1;
             fork1 -> collectMetadata | toList
             """
    f = compiler.compile(script).as_function(single_in=True, single_out=True)
    ans2 = f()
    assert ans == ans2


def test_fork_arrow_syntax_with_mixed_segments():
    script = compiler.compile("""INPUT FROM range[lower=0, upper=10] | toList""")
    ans = list(script())
    assert len(ans) == 1
    assert ans[0] == [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]

    script_a = compiler.compile(
        """INPUT FROM range[lower=0, upper=10] -> fork1; fork1 -> lambda[expression="item"] | toList"""
    )
    ans_a = list(script_a())
    assert len(ans_a) == 1
    assert ans_a[0] == [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]

    script_b = compiler.compile(
        """INPUT FROM range[lower=0, upper=10] -> fork1; fork1 -> lambda[expression="item"]"""
    )
    script_c = compiler.compile("toList")
    script_d = script_b | script_c
    ans_b = list(script_d())
    assert len(ans_b) == 1
    assert ans_b[0] == [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]

    script_b = compiler.compile(
        """INPUT FROM range[lower=0, upper=10] -> fork1; fork1 -> lambda[expression="item"]"""
    )
    script_c = compiler.compile("toList")
    script_d = script_b | script_c
    ans_b = list(script_d())
    assert len(ans_b) == 1
    assert ans_b[0] == [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]


def test_variables_as_parameters():
    v_score = core.RuntimeComponent()
    script = compiler.compile(
        'CONST var1 = "Hello"; INPUT FROM echo[data=var1] | print', v_score
    ).as_function(single_out=True)
    ans = script()
    assert ans == "Hello"
    assert v_score.const_store["var1"] == "Hello"


def test_constant_declarations():
    runtime = core.RuntimeComponent()
    script = compiler.compile(
        'CONST var1 = "Hello"; INPUT FROM "goodbye" | print', runtime
    ).as_function(single_out=True)
    ans = script()
    assert ans == "goodbye"
    assert runtime.const_store["var1"] == "Hello"


def test_multiple_constants():
    runtime = core.RuntimeComponent()
    script = compiler.compile(
        """
        CONST var1 = "Hello";
        CONST var2 = "World";
        INPUT FROM "goodbye" | print""",
        runtime,
    ).as_function(single_out=True)
    ans = script()
    assert ans == "goodbye"
    assert runtime.const_store["var1"] == "Hello"


def test_accum():
    runtime = core.RuntimeComponent()
    pipeline = compiler.compile(
        """
        | accum[variable=@s] | accum[variable=@a] | scale[multiplier=2] | accum[variable=@a]
        """,
        runtime,
    )

    ans = list(pipeline([1, 2, 3]))
    assert ans == [2, 4, 6]
    assert runtime.variable_store["s"] == [1, 2, 3]
    assert runtime.variable_store["a"] == [1, 2, 2, 4, 3, 6]

    ans = list(pipeline([4, 5, 6]))
    assert ans == [8, 10, 12]
    assert runtime.variable_store["s"] == [1, 2, 3, 4, 5, 6]
    assert runtime.variable_store["a"] == [1, 2, 2, 4, 3, 6, 4, 8, 5, 10, 6, 12]

    accum = compiler.Accum(reset=False)
    pipeline = (
        io.echo(data="1,2,ok,3", delimiter=",") | basic.Cast(cast_type=int) | accum
    )
    ans = list(pipeline())
    ans = list(pipeline())
    assert ans == [1, 2, 3, 1, 2, 3]
    assert accum.accumulator == [1, 2, 3, 1, 2, 3]

    accum = compiler.Accum(reset=True)
    pipeline = (
        io.echo(data="1,2,ok,3", delimiter=",") | basic.Cast(cast_type=int) | accum
    )
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
        "a = 5 # initialize a\n"
        'b = "Not a # comment" # real comment\n'
        'c = "Another # example"\n'
        "# Full line comment\n"
        "d = 10\n"
    )
    expected = 'a = 5 \nb = "Not a # comment" \nc = "Another # example"\n\nd = 10\n'
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
        """,
        v_store,
    )
    list(script())
    ans = v_store.variable_store["nums"]
    assert len(ans) == 2
    assert ans == [0, 4]


def test_snippet_script_source():
    v_store = core.RuntimeComponent()
    script = compiler.compile(
        """
        | snippet[script_source="scale[multiplier=2]"]
        """,
        v_store,
    )
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
        """,
        v_store,
    )
    ans = list(script([0, 2]))
    assert len(ans) == 2
    assert ans == [0, 4]


def test_snippet_missing_file_that_looks_like_path_raises(tmp_path):
    v_store = core.RuntimeComponent()
    missing = tmp_path / "does_not_exist.script"
    script = compiler.compile(
        f"""
        | snippet[script_source="{missing}"]
        """,
        v_store,
    )
    with pytest.raises(FileNotFoundError):
        list(script([0, 2]))


def test_snippet_inline_fallback_warns(caplog):
    v_store = core.RuntimeComponent()
    script = compiler.compile(
        """
        | snippet[script_source="scale[multiplier=2]"]
        """,
        v_store,
    )
    with caplog.at_level(logging.WARNING, logger="talkpipe.chatterlang.compiler"):
        ans = list(script([0, 2]))
    assert ans == [0, 4]
    assert any("inline" in rec.getMessage() for rec in caplog.records)


def test_snippet_multi_use():
    v_store = core.RuntimeComponent()
    script = compiler.compile(
        """
        CONST subscript = "scale[multiplier=2]"
        | fork (snippet[script_source=subscript], snippet[script_source=subscript])
        """,
        v_store,
    )
    ans = sorted(script([0, 2]))
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
        """,
        v_store,
    )
    ans = sorted(script())
    assert len(ans) == 5
    assert ans == [0, 1, 2, 6, 8]


def test_environment_variable_support():
    with patch.dict(os.environ, {"TALKPIPE_some_var": "a,b,c,d"}):
        reset_config()
        f = compiler.compile("""
            INPUT FROM echo[data=$some_var]
        """)
        f = f.as_function(single_out=False)
        ans = list(f())
        assert ans == ["a", "b", "c", "d"]


def test_compile_error_missing_segment():
    with pytest.raises(
        compiler.CompileError, match="Segment 'unknownSegment' not found"
    ):
        compiler.compile("""INPUT FROM "test" | unknownSegment""")


def test_compile_error_in_source():
    with pytest.raises(compiler.CompileError, match="Source 'unknownSource' not found"):
        compiler.compile("""INPUT FROM unknownSource""")


def test_compile_error_missing_segment_lists_available():
    """A missing segment lists available components instead of a bare message."""
    with pytest.raises(compiler.CompileError) as excinfo:
        compiler.compile("""INPUT FROM "test" | unknownSegment""")
    msg = str(excinfo.value)
    assert "Available segments:" in msg
    # A real registered segment should appear in the list.
    assert "print" in msg


def test_compile_error_missing_segment_suggests_close_match():
    """A near-miss segment name gets a 'Did you mean' suggestion."""
    with pytest.raises(compiler.CompileError) as excinfo:
        compiler.compile("""INPUT FROM "test" | prin""")
    assert "Did you mean 'print'?" in str(excinfo.value)


def test_compile_error_close_match_omits_full_dump():
    """When a close match exists, the full registry dump is omitted."""
    with pytest.raises(compiler.CompileError) as excinfo:
        compiler.compile("""INPUT FROM "test" | prin""")
    assert "Available segments:" not in str(excinfo.value)


def test_compile_error_source_used_as_segment_gets_hint():
    """A source name in segment position points at INPUT FROM, not a name dump."""
    with pytest.raises(compiler.CompileError) as excinfo:
        compiler.compile("""INPUT FROM "test" | echo""")
    msg = str(excinfo.value)
    assert "a source named 'echo' exists" in msg
    assert "INPUT FROM echo" in msg
    assert "Available segments:" not in msg


def test_compile_error_bare_source_script_gets_hint():
    """A script that is just a source name (the classic newcomer stumble)."""
    with pytest.raises(compiler.CompileError) as excinfo:
        compiler.compile("echo")
    assert "a source named 'echo' exists" in str(excinfo.value)


def test_compile_error_segment_used_as_source_gets_hint():
    """A segment name after INPUT FROM points at pipe usage."""
    with pytest.raises(compiler.CompileError) as excinfo:
        compiler.compile("INPUT FROM print")
    msg = str(excinfo.value)
    assert "a segment named 'print' exists" in msg
    assert "| print" in msg
    assert "Available sources:" not in msg


def test_parse_error_hints_unquoted_string_value():
    """A parse failure right after param=<bareword> suggests quoting the value."""
    with pytest.raises(compiler.CompileError) as excinfo:
        compiler.compile("| llmPrompt[model=llama3.2, source=ollama]")
    assert "Hint: string parameter values must be quoted" in str(excinfo.value)


def test_compile_error_invalid_parameter_lists_valid_params():
    """An unknown keyword argument reports the segment's valid parameters."""
    with pytest.raises(compiler.CompileError) as excinfo:
        compiler.compile('INPUT FROM echo[data="hi"] | cast[type="int"]')
    msg = str(excinfo.value)
    assert "invalid parameters" in msg
    assert "cast_type" in msg  # valid parameter of the Cast segment


def test_compile_error_when_component_rejects_its_options():
    """A constructor that raises (not a bad keyword) still yields a CompileError.

    ``llmPrompt[source=<unknown>]`` used to escape compilation as a raw
    ValueError, so the CLI printed a Python traceback and --verbose made no
    difference.
    """

    @registry.register_segment("pickySegment")
    class PickySegment(io.AbstractSegment):
        def __init__(self, mode: str = "ok"):
            super().__init__()
            if mode != "ok":
                raise ValueError(f"mode '{mode}' is not supported")

        def transform(self, input_iter):
            yield from input_iter

    with pytest.raises(compiler.CompileError) as excinfo:
        compiler.compile('INPUT FROM echo[data="hi"] | pickySegment[mode="nope"]')
    msg = str(excinfo.value)
    assert "Segment 'pickySegment' could not be created" in msg
    assert "mode 'nope' is not supported" in msg
    assert excinfo.value.bad_name == "pickySegment"
    # Same no-chaining convention as the other compile errors.
    assert excinfo.value.__cause__ is None
    assert excinfo.value.__suppress_context__


def test_compile_error_when_source_rejects_its_options():
    """The same wrapping applies to a source constructor."""

    @registry.register_source("pickySource")
    class PickySource(io.AbstractSource):
        def __init__(self, mode: str = "ok"):
            super().__init__()
            if mode != "ok":
                raise ValueError(f"mode '{mode}' is not supported")

        def generate(self):
            yield "x"

    with pytest.raises(compiler.CompileError) as excinfo:
        compiler.compile('INPUT FROM pickySource[mode="nope"] | print')
    msg = str(excinfo.value)
    assert "Source 'pickySource' could not be created" in msg
    assert "mode 'nope' is not supported" in msg


def test_compile_error_does_not_chain_internal_exceptions():
    """CompileError already embeds the underlying cause in its message, so the
    internal KeyError/TypeError/ParseError must not be chained (F-003)."""
    cases = [
        'INPUT FROM "test" | unknownSegment',  # missing name (KeyError)
        'INPUT FROM echo[data="hi"] | cast[type="int"]',  # bad parameter (TypeError)
        'INPUT FROM echo[data="hi" | print',  # syntax error (ParseError)
    ]
    for script in cases:
        with pytest.raises(compiler.CompileError) as excinfo:
            compiler.compile(script)
        assert excinfo.value.__cause__ is None, script
        assert excinfo.value.__suppress_context__, script


def test_compile_error_parse_error_is_located():
    """A syntax error is wrapped in a located CompileError with a caret."""
    with pytest.raises(compiler.CompileError) as excinfo:
        compiler.compile('INPUT FROM echo[data="hi" | print')
    msg = str(excinfo.value)
    assert "Syntax error in ChatterLang script" in msg
    assert "line 1" in msg
    assert "^" in msg


def test_array_parameter_with_constants():
    """Test that constants inside arrays are properly resolved"""
    runtime = core.RuntimeComponent()

    # Register a test segment that accepts an array parameter
    @registry.register_segment("testArrayParam")
    class TestArrayParam(io.AbstractSegment):
        def __init__(self, arr):
            super().__init__()
            self.arr = arr

        def transform(self, items):
            for item in items:
                yield {"input": item, "arr": self.arr}

    # Test with constants in array
    script = compiler.compile(
        """
        CONST MY_CONST = "hello";
        CONST MY_NUM = 42;
        INPUT FROM echo[data="test"] | testArrayParam[arr=[1, MY_CONST, MY_NUM]]
        """,
        runtime,
    )

    result = list(script())
    assert len(result) == 1
    assert result[0]["arr"] == [1, "hello", 42]


def test_array_parameter_basic():
    """Test basic array parameter parsing and compilation"""
    runtime = core.RuntimeComponent()

    @registry.register_segment("testBasicArray")
    class TestBasicArray(io.AbstractSegment):
        def __init__(self, numbers):
            super().__init__()
            self.numbers = numbers

        def transform(self, items):
            for _item in items:
                yield sum(self.numbers)

    script = compiler.compile(
        """INPUT FROM echo[data="x"] | testBasicArray[numbers=[1, 2, 3]]""", runtime
    )

    result = list(script())
    assert result == [6]


class TestDeprecatedMissingPipe:
    """Omitting the '|' after an input source compiles, but is deprecated."""

    SCRIPT = 'INPUT FROM echo[data="1,2"] print'

    def test_it_still_compiles_and_runs(self):
        with pytest.warns(DeprecationWarning, match="TalkPipe 2.0"):
            compiled = compiler.compile(self.SCRIPT)
        assert list(compiled()) == ["1", "2"]

    def test_the_warning_locates_the_segment_and_names_the_removal(self):
        with pytest.warns(DeprecationWarning, match="deprecated") as record:
            compiler.compile(self.SCRIPT)
        message = str(record[0].message)
        assert "line 1, column 29" in message
        assert "'| print'" in message
        assert "TalkPipe 2.0" in message

    def test_it_is_also_logged(self, caplog):
        # A DeprecationWarning alone is invisible to someone running
        # chatterlang_script, so the compiler logs it too.
        with caplog.at_level(logging.WARNING, logger="talkpipe.chatterlang.compiler"):
            compiler.compile(self.SCRIPT)
        assert any("TalkPipe 2.0" in r.message for r in caplog.records)

    def test_the_pipe_spelling_warns_about_nothing(self):
        with warnings.catch_warnings():
            warnings.simplefilter("error", DeprecationWarning)
            compiled = compiler.compile('INPUT FROM echo[data="1,2"] | print')
        assert list(compiled()) == ["1", "2"]

    def test_one_warning_per_occurrence(self):
        script = (
            'INPUT FROM echo[data="1"] print;\n'
            'INPUT FROM echo[data="2"] | print;\n'
            'INPUT FROM echo[data="3"] print'
        )
        parsed = parsers.script_parser.parse(script)
        found = list(compiler.iter_deprecated_syntax(parsed))
        assert [(line, column) for line, column, _ in found] == [(1, 27), (3, 27)]

    def test_comments_do_not_shift_the_reported_location(self):
        script = '# a comment\nINPUT FROM echo[data="1"] print  # trailing\n'
        parsed = parsers.script_parser.parse(compiler.remove_comments(script))
        assert [
            (line, col) for line, col, _ in compiler.iter_deprecated_syntax(parsed)
        ] == [(2, 27)]
