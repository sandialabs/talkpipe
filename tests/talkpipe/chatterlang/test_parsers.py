import os
from unittest import mock

import pytest
from parsy import ParseError

from talkpipe.chatterlang import parsers
from talkpipe.util.config import reset_config


def test_quoted_string():
    # Test double-quoted strings
    assert parsers.quoted_string.parse('"string"') == "string"
    assert parsers.quoted_string.parse('"string with spaces"') == "string with spaces"
    assert (
        parsers.quoted_string.parse('"string with ""escaped"" quotes"')
        == 'string with "escaped" quotes'
    )

    # Test single-quoted strings
    assert parsers.quoted_string.parse("'string'") == "string"
    assert parsers.quoted_string.parse("'string with spaces'") == "string with spaces"
    assert (
        parsers.quoted_string.parse("'string with ''escaped'' quotes'")
        == "string with 'escaped' quotes"
    )


def test_lexeme():
    lex = parsers.lexeme(",")
    assert lex.parse(" , ") == ","
    assert lex.parse("    ,") == ","
    assert lex.parse(" ,    ") == ","

    with pytest.raises(ParseError):
        lex.parse(" b,")


def test_variable():
    var = parsers.variable
    v = var.parse("@var")
    assert isinstance(v, parsers.VariableName)
    assert v.name == "var"
    v = var.parse("@var1")
    assert isinstance(v, parsers.VariableName)
    assert v.name == "var1"

    with pytest.raises(ParseError):
        var.parse("var")


def test_bool_value():
    bv = parsers.bool_value
    assert bv.parse("true")
    assert not bv.parse("false")
    assert bv.parse("True")
    assert not bv.parse("False")
    assert bv.parse("TRUE")
    assert not bv.parse("FALSE")


def test_parameter():
    param = parsers.parameter
    assert param.parse('"string"') == "string"
    assert param.parse("123") == 123
    assert param.parse("var") == parsers.Identifier(name="var")

    with pytest.raises(ParseError):
        param.parse("12var")

    with pytest.raises(ParseError):
        param.parse('"string')

    with pytest.raises(ParseError):
        param.parse("string with spaces")


def test_key_value():
    kv = parsers.key_value
    assert kv.parse('key="string"') == ("key", "string")
    assert kv.parse("key=123") == ("key", 123)
    assert kv.parse("key=var") == ("key", parsers.Identifier("var"))

    with pytest.raises(ParseError):
        kv.parse("key=12var")

    with pytest.raises(ParseError):
        kv.parse('key="string')

    with pytest.raises(ParseError):
        kv.parse("key=string with spaces")

    with pytest.raises(ParseError):
        kv.parse("key")


def test_bracket_content():
    bc = parsers.bracket_content
    assert bc.parse('key="string"') == {"key": "string"}
    assert bc.parse('key="string", key2=123') == {"key": "string", "key2": 123}

    with pytest.raises(ParseError):
        bc.parse('key="string", key2=12var')

    with pytest.raises(ParseError):
        bc.parse("key, key2")


def test_bracket_parser():
    bp = parsers.bracket_parser
    assert bp.parse('[key="string"]') == {"key": "string"}
    assert bp.parse('[key="string", key1=123.0]') == {"key": "string", "key1": 123.0}


def test_input_section():
    isec = parsers.source
    assert isec.parse("INPUT FROM @source") == parsers.InputNode(
        parsers.VariableName("source"), {}
    )
    assert isec.parse("INPUT FROM source") == parsers.InputNode(
        parsers.Identifier("source"), {}
    )
    assert isec.parse('INPUT FROM @source [key="string"]') == parsers.InputNode(
        parsers.VariableName("source"), {"key": "string"}
    )
    assert isec.parse(
        'INPUT FROM source [key="string", key1=123.0]'
    ) == parsers.InputNode(
        parsers.Identifier("source"), {"key": "string", "key1": 123.0}
    )

    assert isec.parse("NEW @source") == parsers.InputNode(
        parsers.VariableName("source"), {}
    )
    assert isec.parse("NEW source") == parsers.InputNode(
        parsers.Identifier("source"), {}
    )
    assert isec.parse('NEW @source [key="string"]') == parsers.InputNode(
        parsers.VariableName("source"), {"key": "string"}
    )
    assert isec.parse('NEW @source[key="string"]') == parsers.InputNode(
        parsers.VariableName("source"), {"key": "string"}
    )

    assert isec.parse("NEW FROM @source") == parsers.InputNode(
        parsers.VariableName("source"), {}
    )
    assert isec.parse("NEW FROM source") == parsers.InputNode(
        parsers.Identifier("source"), {}
    )
    assert isec.parse('NEW FROM @source [key="string"]') == parsers.InputNode(
        parsers.VariableName("source"), {"key": "string"}
    )
    assert isec.parse('NEW FROM source[key="string", key1=123.0]') == parsers.InputNode(
        parsers.Identifier("source"), {"key": "string", "key1": 123.0}
    )


def test_transform():
    t = parsers.segment
    assert t.parse("operation") == parsers.SegmentNode(
        parsers.Identifier("operation"), {}
    )
    assert t.parse('operation [key="string"]') == parsers.SegmentNode(
        parsers.Identifier("operation"), {"key": "string"}
    )
    assert t.parse('operation [key="string", key1=123.0]') == parsers.SegmentNode(
        parsers.Identifier("operation"), {"key": "string", "key1": 123.0}
    )


def test_transforms_section():
    ts = parsers.transforms_section
    assert ts.parse('| operation [key="string"]') == [
        parsers.SegmentNode(parsers.Identifier("operation"), {"key": "string"})
    ]
    assert ts.parse('| operation [key="string"] | operation2 [key="string"]') == [
        parsers.SegmentNode(parsers.Identifier("operation"), {"key": "string"}),
        parsers.SegmentNode(parsers.Identifier("operation2"), {"key": "string"}),
    ]


def test_loop_section():
    ls = parsers.loop
    parsed = ls.parse("LOOP 2 TIMES {INPUT FROM source| do_something}")
    assert isinstance(parsed, parsers.ParsedLoop)
    assert isinstance(parsed.pipelines, parsers.ParsedScript)
    assert len(parsed.pipelines.pipelines) == 1

    parsed = ls.parse(
        "LOOP 2 TIMES {INPUT FROM source | do_something; INPUT FROM do_something_else}"
    )
    assert isinstance(parsed, parsers.ParsedLoop)
    assert isinstance(parsed.pipelines, parsers.ParsedScript)
    assert len(parsed.pipelines.pipelines) == 2


def test_pipeline():
    pipe = parsers.pipeline
    parsed = pipe.parse("INPUT FROM source | do_something")
    assert isinstance(parsed, parsers.ParsedPipeline)
    assert isinstance(parsed.input_node, parsers.InputNode)
    assert len(parsed.transforms) == 1

    parsed = pipe.parse("INPUT FROM source | do_something | do_something_else")
    assert isinstance(parsed, parsers.ParsedPipeline)
    assert isinstance(parsed.input_node, parsers.InputNode)
    assert len(parsed.transforms) == 2

    parsed = pipe.parse(
        "INPUT FROM source | do_something | do_something_else | do_something_more"
    )
    assert isinstance(parsed, parsers.ParsedPipeline)
    assert isinstance(parsed.input_node, parsers.InputNode)
    assert len(parsed.transforms) == 3

    parsed = pipe.parse("do_something")
    assert isinstance(parsed, parsers.ParsedPipeline)
    assert parsed.input_node is None
    assert len(parsed.transforms) == 1


def test_parsed_script():
    ps = parsers.script_parser.parse("an_operation")
    assert isinstance(ps, parsers.ParsedScript)
    assert len(ps.pipelines) == 1

    ps = parsers.script_parser.parse("an_operation; another_operation")
    assert isinstance(ps, parsers.ParsedScript)
    assert len(ps.pipelines) == 2

    ps = parsers.script_parser.parse(
        "LOOP 2 TIMES {INPUT FROM some_numbers | lessthan2 | get_types; cast[type=int] }"
    )
    # ps = cl2.pipelines.parse('INPUT FROM some_numbers | lessthan2 | get_types')

    assert isinstance(ps, parsers.ParsedScript)
    assert len(ps.pipelines) == 1
    assert isinstance(ps.pipelines[0], parsers.ParsedLoop)
    assert ps.pipelines[0].iterations == 2
    assert len(ps.pipelines[0].pipelines.pipelines) == 2


def test_fork():
    ps = parsers.script_parser.parse(
        "INPUT FROM some_numbers | do_something | fork(branch1, branch2)"
    )
    assert isinstance(ps, parsers.ParsedScript)
    assert len(ps.pipelines) == 1
    assert isinstance(ps.pipelines[0], parsers.ParsedPipeline)
    assert len(ps.pipelines[0].transforms) == 2
    assert isinstance(ps.pipelines[0].transforms[0], parsers.SegmentNode)
    assert isinstance(ps.pipelines[0].transforms[1], parsers.ForkNode)
    assert len(ps.pipelines[0].transforms[1].branches) == 2
    assert isinstance(ps.pipelines[0].transforms[1].branches[0], parsers.ParsedPipeline)
    assert isinstance(ps.pipelines[0].transforms[1].branches[1], parsers.ParsedPipeline)


def test_array_parameter():
    """Test parsing of array parameters like [1, "str", MY_CONST]"""
    param = parsers.parameter

    # Basic array with numbers
    result = param.parse("[1, 2, 3]")
    assert result == [1, 2, 3]

    # Array with mixed types
    result = param.parse('[1, "str", 3.5]')
    assert result == [1, "str", 3.5]

    # Array with identifier (constant reference)
    result = param.parse('[1, MY_CONST, "str"]')
    assert result == [1, parsers.Identifier("MY_CONST"), "str"]

    # Empty array
    result = param.parse("[]")
    assert result == []

    # Array with booleans
    result = param.parse("[true, false, 1]")
    assert result == [True, False, 1]

    # Nested arrays
    result = param.parse("[[1, 2], [3, 4]]")
    assert result == [[1, 2], [3, 4]]


def test_array_in_segment_params():
    """Test array parameters in segment brackets"""
    seg = parsers.segment
    result = seg.parse("my_segment[arr=[1, 2, 3]]")
    assert result.params["arr"] == [1, 2, 3]

    result = seg.parse('my_segment[arr=[1, "str", MY_CONST], other="value"]')
    assert result.params["arr"] == [1, "str", parsers.Identifier("MY_CONST")]
    assert result.params["other"] == "value"


def test_environmentVariables():

    # Use mock to patch os.environ
    with mock.patch.dict(os.environ, {"TALKPIPE_my_string": "Some_String"}):
        reset_config()
        ps = parsers.script_parser.parse("INPUT FROM $my_string | print")
        assert isinstance(ps, parsers.ParsedScript)
        assert len(ps.pipelines) == 1
        assert isinstance(ps.pipelines[0], parsers.ParsedPipeline)
        assert isinstance(ps.pipelines[0].input_node, parsers.InputNode)
        assert ps.pipelines[0].input_node.source == "Some_String"
        assert len(ps.pipelines[0].transforms) == 1
        assert isinstance(ps.pipelines[0].transforms[0], parsers.SegmentNode)
        assert ps.pipelines[0].transforms[0].operation == parsers.Identifier("print")

        ps = parsers.script_parser.parse(
            "INPUT FROM somewhere | do_something[key=$my_string]"
        )
        assert ps.pipelines[0].transforms[0].params["key"] == "Some_String"


class TestMissingPipeAfterSource:
    """The pipe between an input source and the first segment.

    It has always been optional, so scripts written without it must keep
    parsing; the parser now records where it was left out so the compiler can
    deprecate the spelling.
    """

    def test_omitted_pipe_still_parses_and_is_recorded(self):
        parsed = parsers.script_parser.parse('INPUT FROM echo[data="1,2"] print')
        pipeline = parsed.pipelines[0]
        assert len(pipeline.transforms) == 1
        assert pipeline.transforms[0].operation == parsers.Identifier("print")
        # Column 29 is the 'p' of 'print'.
        assert pipeline.missing_pipe_after_source == (1, 29)

    def test_pipe_present_is_not_recorded(self):
        parsed = parsers.script_parser.parse('INPUT FROM echo[data="1,2"] | print')
        assert parsed.pipelines[0].missing_pipe_after_source is None

    def test_location_is_the_first_transform(self):
        parsed = parsers.script_parser.parse(
            'INPUT FROM echo[data="1"] | print;\nINPUT FROM echo[data="2"] print'
        )
        assert parsed.pipelines[0].missing_pipe_after_source is None
        assert parsed.pipelines[1].missing_pipe_after_source == (2, 27)

    def test_recorded_for_variables_forks_and_loops(self):
        parsed = parsers.script_parser.parse('INPUT FROM echo[data="1"] @x')
        assert isinstance(parsed.pipelines[0].transforms[0], parsers.VariableName)
        assert parsed.pipelines[0].missing_pipe_after_source == (1, 27)

        parsed = parsers.script_parser.parse(
            'fork(INPUT FROM echo[data="1"] print, INPUT FROM echo[data="2"] | print)'
        )
        branches = parsed.pipelines[0].transforms[0].branches
        assert branches[0].missing_pipe_after_source == (1, 32)
        assert branches[1].missing_pipe_after_source is None

        parsed = parsers.script_parser.parse(
            'LOOP 2 TIMES { INPUT FROM echo[data="1"] print }'
        )
        loop_pipeline = parsed.pipelines[0].pipelines.pipelines[0]
        assert loop_pipeline.missing_pipe_after_source == (1, 42)

    def test_only_the_first_pipe_was_ever_optional(self):
        """Later pipes are still required -- accepting them would be a new hole."""
        with pytest.raises(ParseError):
            parsers.script_parser.parse('INPUT FROM echo[data="1"] print print')
        with pytest.raises(ParseError):
            parsers.script_parser.parse('INPUT FROM echo[data="1"] | | print')

    def test_source_without_brackets_still_requires_the_pipe(self):
        """`INPUT FROM @x print` has always been an error; it stays one."""
        with pytest.raises(ParseError):
            parsers.script_parser.parse("INPUT FROM @x print")

    def test_a_pipeline_with_no_source_may_begin_with_a_bare_segment(self):
        """Fork consumers and script fragments are not affected."""
        for script in ("myfork -> print | print", "print | print", "| print"):
            parsed = parsers.script_parser.parse(script)
            assert parsed.pipelines[0].missing_pipe_after_source is None
