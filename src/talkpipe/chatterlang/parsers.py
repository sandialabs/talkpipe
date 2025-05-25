"""The parsers and executors for the Chatterlang pipeline language.

This module contains code to convert strings into an internal
representation that can then be processed by the compilers module
into something that can then be executed.
"""

from typing import List, Optional, Any, Dict, Union
from parsy import string, regex, seq, whitespace, generate, line_info
from dataclasses import dataclass, field
from talkpipe.util.config import get_config

@dataclass(frozen=True)
class VariableName:
    """A variable name in the pipeline language."""
    name: str
    """The name of the variable."""
    
    @property
    def is_variable(self):
        return True
    
@dataclass(frozen=True)
class Identifier:
    """An identifier in the pipeline language."""
    name: str
    """The name of the identifier."""
    
    @property
    def is_variable(self):
        return False
    
    def __str__(self):
        return self.name
    
    def __repr__(self):
        return self.name

@dataclass
class InputNode:
    """A node representing the input section of a pipeline."""
    source: Union[VariableName, Identifier, str]
    """The source of the input data."""
    params: Dict[Identifier, Any]
    """The parameters for the input source.  Used when the handler is created."""
    
    @property
    def is_variable(self):
        return not isinstance(self.source, str) and self.source.is_variable

@dataclass
class ParsedLoop:
    """A node representing a loop in the pipeline language."""
    iterations: int
    """The number of iterations for the loop."""
    pipelines: List['ParsedPipeline']
    """The pipelines to execute in the loop."""

    def __iter__(self):
        return iter(self.pipelines)
    
    @property
    def input_nodes(self) -> List[InputNode]:
        """Get the input nodes for all pipelines in the loop."""
        return [p.input_node for p in self.pipelines if isinstance(p, ParsedPipeline)]

@dataclass
class SegmentNode:
    """A node representing a transform section of a pipeline."""
    operation: str
    """The operation to perform."""
    params: Dict[Identifier, Any]
    """The parameters for the operation.  Used when the handler is created."""

@dataclass
class ForkNode:
    """A node representing a fork in the pipeline language."""
    branches: List[List[Union[SegmentNode, VariableName]]]
    """The branches of the fork, each containing a list of segments."""
    mode: str = "round_robin"
    """The distribution mode for the fork (round_robin or broadcast)."""
    params: Dict[Identifier, Any] = field(default_factory=dict)
    """Additional parameters for the fork."""


@dataclass
class ParsedPipeline:
    """A node representing a pipeline in the pipeline language."""
    input_node: Optional[InputNode]
    """The input node for the pipeline."""
    transforms: List[Union[SegmentNode, VariableName, ForkNode]]
    """The transforms to perform on the data, now including possible forks."""

@dataclass
class ParsedScript:
    """A parsed script containing a list of pipelines and loops.
    
    This is an intermediate stage where the text script has already
    been parsed.
    """
    pipelines: List[Union[ParsedPipeline, ParsedLoop]]
    constants: Dict[str, Any] = field(default_factory=dict)

    def __iter__(self):
        return iter(self.pipelines)

    @property
    def input_nodes(self) -> List[InputNode]:
        """Get the input nodes for all pipelines in the script"""
        ans = []
        for p in self.pipelines:
            if isinstance(p, ParsedPipeline):
                ans.append(p.input_node)
            elif isinstance(p, ParsedLoop):
                ans.extend(p.input_nodes)
        return ans
    
    def input_nodes_contain(self, input_node_name):
        """Check if the input nodes contain a specific input node name."""
        for n in self.input_nodes:
            if n.source == Identifier(name=input_node_name):
                return True
        return False

whitespace_wrap = lambda p: (whitespace.many() >> p << whitespace.many())
lexeme = lambda s: whitespace_wrap(string(s))
whitespace_or_newline = regex(r'[ \t\n\r]+')
fork_whitespace = lambda p: (whitespace_or_newline.many() >> p << whitespace_or_newline.many())
bool_value = (regex(r'true|false|TRUE|FALSE|True|False')).map(lambda s: s.lower() == 'true')
"""A parser for boolean values."""
identifier = regex(r'[a-zA-Z][a-zA-Z0-9_]*').map(lambda s: Identifier(name=s))
"""A parser for identifiers.  Identifiers are used for operation names, variable names, etc.""" 
variable = (string('@') >> identifier).map(lambda x: x).map(lambda x: VariableName(name=x.name))
"""A parser for variable names.  Variables are used to store and retrieve data in the pipeline."""
environmentVariable = (string('$') >> identifier).map(lambda x: get_config()[x.name])
# quoted_string = regex(r'"[^"]*"').map(lambda s: s[1:-1])
quoted_string = regex(r'"(?:[^"]|"")*"').map(
    lambda s: s[1:-1].replace('""', '"')
)
"""A parser for quoted strings."""
number = regex(r'-?\d+(\.\d+)?').map(lambda s: int(s) if '.' not in s else float(s))
"""A parser for numbers.  Returns both ints and floats."""

parameter = quoted_string | bool_value | number | identifier | variable | environmentVariable
"""A parser for parameters.  Parameters can be strings, booleans, numbers, or identifiers."""

key_value = seq(
    key=identifier << lexeme('='),
    value=parameter
).map(lambda x: (x['key'].name, x['value']))
"""A parser for key=value pairs.  Used for parameters in brackets."""

# Square bracket parser that handles key=value pairs
bracket_content = seq(
    params=key_value.sep_by(lexeme(','), min=0)
).map(lambda x: dict(x['params']))
"""A parser for the content inside square brackets.  This is used for parameters in the pipeline language."""

bracket_parser = (
    lexeme('[') >>
    bracket_content <<
    lexeme(']')
).optional().map(lambda x: x if x else {})
"""A parser for square brackets.  This is used for parameters in the pipeline language."""

# New parser for constant definitions
@generate
def constant_definition():
    yield (lexeme('CONST') | lexeme("SET"))
    const_name = yield identifier
    yield lexeme('=')
    const_value = yield parameter
    return (const_name.name, const_value)
"""A parser for defining constants with 'SET' keyword."""

source = (
    (lexeme('INPUT') >> lexeme('FROM') | lexeme('NEW') >> lexeme('FROM') | lexeme('NEW')) >>
    seq(
        source=(variable | identifier | quoted_string | environmentVariable),
        bracket_content=bracket_parser
    )
).map(lambda x: InputNode(
    x['source'], 
    x['bracket_content']
))
"""A parser for the input section of a pipeline.  'INPUT FROM', 'NEW FROM', and 'NEW' are all valid equivalent syntax."""

# Transform section parser
segment = seq(
    operation=identifier,
    bracket_content=bracket_parser
).map(lambda x: SegmentNode(
    x['operation'],
    x['bracket_content']
))
"""A parser for the transform section of a pipeline."""

#@generate
#def fork_branch():
#    """Parser for a single branch within a fork."""
#    transforms = yield (
#        # First transform can be without a leading pipe
#        (segment | variable).map(lambda x: [x]) |
#        # Subsequent transforms require a leading pipe
#        (lexeme('|') >> (segment | variable)).many()
#    )
#    return transforms

#@generate
#def fork_branch():
#    """Parser for a single branch within a fork."""
#    transforms = yield pipeline
#    return transforms

@generate
def fork_branch_pipeline():
    """
    Parser for a pipeline fragment inside a fork branch.
    This can be either a full pipeline or just transform segments.
    """
    # Check if this branch starts with an input source
    start_pos = yield line_info
    
    # Try to match an input source
    input_node = yield source.optional()
    
    # If we found an input source, parse the rest as a normal pipeline
    if input_node is not None:
        transforms = yield transforms_section
        yield whitespace.many()
        return ParsedPipeline(input_node, transforms)
    
    # If no input source, try to parse as a sequence of segments
    # First segment might not have a leading pipe
    first_transform = yield (fork_section | segment | variable)
    transforms = [first_transform]
    
    # Parse remaining segments (with leading pipes)
    remaining = yield (lexeme('|') >> (fork_section | segment | variable)).many()
    transforms.extend(remaining)
    
    # Return a pipeline with no input node
    return ParsedPipeline(None, transforms)

@generate
def fork_branch():
    """Parser for a single branch within a fork."""
    branch = yield fork_branch_pipeline
    return branch

@generate
def fork_content():
    """Parser for the content inside fork()."""
    yield whitespace.many()
    first_branch = yield fork_branch
    remaining_branches = yield (
        (lexeme(',') >> whitespace.many() >> fork_branch)
        .many()
    )
    yield whitespace.many()
    return [first_branch] + remaining_branches

@generate
def fork_section():
    """Parser for a complete fork section."""
    yield lexeme('fork')
    yield lexeme('(')
    bracket_content = yield bracket_parser
    branches = yield fork_content
    yield lexeme(')')
    return ForkNode(branches=branches, params=bracket_content)

transforms_section = (
    # First transform can be without a leading pipe
    (fork_section | segment | variable).map(lambda x: [x]) |
    # Subsequent transforms require a leading pipe
    (lexeme('|') >> (fork_section | segment | variable)).many()
)
"""A parser for the transforms section.  Transforms are separated by the '|' character."""

@generate
def pipeline():
    yield whitespace.many()
    input_node = yield source.optional()
    transforms = yield transforms_section
    yield whitespace.many()
    return ParsedPipeline(input_node or None, transforms)
"""A parser for a pipeline in the pipeline language.  Pipelines consist of an input section and a series of transforms."""

@generate
def loop():
    yield lexeme('LOOP')
    iterations = yield number
    yield lexeme('TIMES')
    yield lexeme('{')
    pipes = yield script_parser
    yield lexeme('}')
    return ParsedLoop(int(iterations), pipes)
"""A parser for a loop in the pipeline language.  Loops consist of a number of iterations over a series of pipelines."""

pipeline_separator = lexeme(';')
"""A parser for the separator between pipelines in a script."""

@generate
def script_parser():
    # First parse constants
    constants = yield constant_definition.sep_by(pipeline_separator)
    constants = {k: v for k, v in constants}

    # Parse pipelines and loops
    pipelines = yield (loop | pipeline).sep_by(pipeline_separator)

    pipelines = [p for p in pipelines if not isinstance(p, ParsedPipeline) or (p.input_node or len(p.transforms)>0)]
    
    # Create and return a ParsedScript with constants
    return ParsedScript(pipelines, constants)
"""A parser for a script in the pipeline language.  Scripts contain a series of pipelines and loops."""

