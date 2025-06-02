import pytest
import os
from unittest import mock
from parsy import ParseError

from talkpipe.chatterlang import parsers
from talkpipe.util.config import reset_config

def test_quoted_string():
    assert parsers.quoted_string.parse('"string"') == 'string'
    assert parsers.quoted_string.parse('"string with spaces"') == 'string with spaces'
    assert parsers.quoted_string.parse('"string with ""escaped"" quotes"') == 'string with "escaped" quotes'
    

def test_lexeme():
    lex = parsers.lexeme(',')
    assert lex.parse(' , ') == ","
    assert lex.parse('    ,') == ","
    assert lex.parse(' ,    ') == ","
    
    with pytest.raises(ParseError):
        lex.parse(' b,')
        
def test_variable():
    var = parsers.variable
    v =  var.parse('@var')
    assert isinstance(v, parsers.VariableName)
    assert v.name == 'var'
    v = var.parse('@var1') 
    assert isinstance(v, parsers.VariableName)
    assert v.name == 'var1'
    
    with pytest.raises(ParseError):
        var.parse('var')
        
def test_bool_value():
    bv = parsers.bool_value
    assert bv.parse('true') == True
    assert bv.parse('false') == False
    assert bv.parse('True') == True
    assert bv.parse('False') == False
    assert bv.parse('TRUE') == True
    assert bv.parse('FALSE') == False
        
        
def test_parameter():
    param = parsers.parameter
    assert param.parse('"string"') == "string"
    assert param.parse('123') == 123
    assert param.parse('var') == parsers.Identifier(name='var')
    
    with pytest.raises(ParseError):
        param.parse('12var')
        
    with pytest.raises(ParseError):
        param.parse('"string')
        
    with pytest.raises(ParseError):
        param.parse('string with spaces')
        
def test_key_value():
    kv = parsers.key_value
    assert kv.parse('key="string"') == ('key', 'string')
    assert kv.parse('key=123') == ('key', 123)
    assert kv.parse('key=var') == ('key', parsers.Identifier('var'))
        
    with pytest.raises(ParseError):
        kv.parse('key=12var')
    
    with pytest.raises(ParseError):
        kv.parse('key="string') 
        
    with pytest.raises(ParseError):
        kv.parse('key=string with spaces')
        
    with pytest.raises(ParseError):
        kv.parse('key') 
        
def test_bracket_content():
    bc = parsers.bracket_content
    assert bc.parse('key="string"') == {'key': 'string'}
    assert bc.parse('key="string", key2=123') == {'key': 'string', 'key2': 123}
    
    with pytest.raises(ParseError):
        bc.parse('key="string", key2=12var')
        
    with pytest.raises(ParseError):
        bc.parse('key, key2')
        
def test_bracket_parser():
    bp = parsers.bracket_parser
    assert bp.parse('[key="string"]') == {'key': 'string'}
    assert bp.parse('[key="string", key1=123.0]') == {'key': 'string', 'key1': 123.0}

def test_input_section():
    isec = parsers.source
    assert isec.parse('INPUT FROM @source') == parsers.InputNode(parsers.VariableName("source"), {})
    assert isec.parse('INPUT FROM source') == parsers.InputNode(parsers.Identifier('source'), {})
    assert isec.parse('INPUT FROM @source [key="string"]') == parsers.InputNode(parsers.VariableName("source"), {'key': 'string'})
    assert isec.parse('INPUT FROM source [key="string", key1=123.0]') == parsers.InputNode(parsers.Identifier('source'), {'key': 'string', 'key1': 123.0})

    assert isec.parse('NEW @source') == parsers.InputNode(parsers.VariableName("source"), {})
    assert isec.parse('NEW source') == parsers.InputNode(parsers.Identifier('source'), {})
    assert isec.parse('NEW @source [key="string"]') == parsers.InputNode(parsers.VariableName("source"), {'key': 'string'})
    assert isec.parse('NEW @source[key="string"]') == parsers.InputNode(parsers.VariableName("source"), {'key': 'string'})

    assert isec.parse('NEW FROM @source') == parsers.InputNode(parsers.VariableName("source"), {})
    assert isec.parse('NEW FROM source') == parsers.InputNode(parsers.Identifier('source'), {})
    assert isec.parse('NEW FROM @source [key="string"]') == parsers.InputNode(parsers.VariableName("source"), {'key': 'string'})
    assert isec.parse('NEW FROM source[key="string", key1=123.0]') == parsers.InputNode(parsers.Identifier('source'), {'key': 'string', 'key1': 123.0})
    
def test_transform():
    t = parsers.segment
    assert t.parse('operation') == parsers.SegmentNode(parsers.Identifier('operation'), {})
    assert t.parse('operation [key="string"]') == parsers.SegmentNode(parsers.Identifier('operation'), {'key': 'string'})
    assert t.parse('operation [key="string", key1=123.0]') == parsers.SegmentNode(parsers.Identifier('operation'), {'key': 'string', 'key1': 123.0})
    
def test_transforms_section():
    ts = parsers.transforms_section
    assert ts.parse('| operation [key="string"]') == [parsers.SegmentNode(parsers.Identifier('operation'), {'key': 'string'})]
    assert ts.parse('| operation [key="string"] | operation2 [key="string"]') == [parsers.SegmentNode(parsers.Identifier('operation'), {'key': 'string'}), parsers.SegmentNode(parsers.Identifier('operation2'), {'key': 'string'})]    

def test_loop_section():
    ls = parsers.loop
    parsed = ls.parse('LOOP 2 TIMES {INPUT FROM source| do_something}') 
    assert isinstance(parsed, parsers.ParsedLoop)
    assert isinstance(parsed.pipelines, parsers.ParsedScript)
    assert len(parsed.pipelines.pipelines) == 1

    parsed = ls.parse('LOOP 2 TIMES {INPUT FROM source | do_something; INPUT FROM do_something_else}')
    assert isinstance(parsed, parsers.ParsedLoop)
    assert isinstance(parsed.pipelines, parsers.ParsedScript)
    assert len(parsed.pipelines.pipelines) == 2

def test_pipeline():
    pipe = parsers.pipeline
    parsed = pipe.parse('INPUT FROM source | do_something')
    assert isinstance(parsed, parsers.ParsedPipeline)
    assert isinstance(parsed.input_node, parsers.InputNode)
    assert len(parsed.transforms) == 1
    
    parsed = pipe.parse('INPUT FROM source | do_something | do_something_else')
    assert isinstance(parsed, parsers.ParsedPipeline)
    assert isinstance(parsed.input_node, parsers.InputNode)
    assert len(parsed.transforms) == 2
    
    parsed = pipe.parse('INPUT FROM source | do_something | do_something_else | do_something_more')
    assert isinstance(parsed, parsers.ParsedPipeline)
    assert isinstance(parsed.input_node, parsers.InputNode)
    assert len(parsed.transforms) == 3

    parsed = pipe.parse('do_something')
    assert isinstance(parsed, parsers.ParsedPipeline)
    assert parsed.input_node == None
    assert len(parsed.transforms) == 1

def test_parsed_script():
    ps = parsers.script_parser.parse("an_operation")
    assert isinstance(ps, parsers.ParsedScript)
    assert len(ps.pipelines) == 1

    ps = parsers.script_parser.parse("an_operation; another_operation")
    assert isinstance(ps, parsers.ParsedScript)
    assert len(ps.pipelines) == 2

    ps = parsers.script_parser.parse('LOOP 2 TIMES {INPUT FROM some_numbers | lessthan2 | get_types; cast[type=int] }')
    #ps = cl2.pipelines.parse('INPUT FROM some_numbers | lessthan2 | get_types')    
    
    assert isinstance(ps, parsers.ParsedScript)    
    assert len(ps.pipelines) == 1
    assert isinstance(ps.pipelines[0], parsers.ParsedLoop)
    assert ps.pipelines[0].iterations == 2
    assert len(ps.pipelines[0].pipelines.pipelines) == 2

def test_fork():
    ps = parsers.script_parser.parse('INPUT FROM some_numbers | do_something | fork(branch1, branch2)')
    assert isinstance(ps, parsers.ParsedScript)
    assert len(ps.pipelines) == 1
    assert isinstance(ps.pipelines[0], parsers.ParsedPipeline)
    assert len(ps.pipelines[0].transforms) == 2
    assert isinstance(ps.pipelines[0].transforms[0], parsers.SegmentNode)
    assert isinstance(ps.pipelines[0].transforms[1], parsers.ForkNode)
    assert len(ps.pipelines[0].transforms[1].branches) == 2
    assert isinstance(ps.pipelines[0].transforms[1].branches[0], parsers.ParsedPipeline)
    assert isinstance(ps.pipelines[0].transforms[1].branches[1], parsers.ParsedPipeline)

def test_environmentVariables():
    
    # Use mock to patch os.environ
    with mock.patch.dict(os.environ, {"TALKPIPE_my_string": "Some_String"}):
        reset_config()
        ps = parsers.script_parser.parse('INPUT FROM $my_string | print')
        assert isinstance(ps, parsers.ParsedScript)
        assert len(ps.pipelines) == 1
        assert isinstance(ps.pipelines[0], parsers.ParsedPipeline)
        assert isinstance(ps.pipelines[0].input_node, parsers.InputNode)
        assert ps.pipelines[0].input_node.source == "Some_String"
        assert len(ps.pipelines[0].transforms) == 1
        assert isinstance(ps.pipelines[0].transforms[0], parsers.SegmentNode)
        assert ps.pipelines[0].transforms[0].operation == parsers.Identifier("print")

        ps = parsers.script_parser.parse('INPUT FROM somewhere | do_something[key=$my_string]')
        assert ps.pipelines[0].transforms[0].params['key'] == 'Some_String'
