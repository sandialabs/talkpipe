"""The parsers and executors for the Chatterlang pipeline language.

This module contains code to convert strings into an internal
representation that can then be processed by the compilers module
into something that can then be executed.
"""

from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any

from parsy import generate as _parsy_generate
from parsy import line_info, regex, seq, string, whitespace

from talkpipe.util.config import get_config

# parsy ships no type information; give its @generate decorator an explicit
# signature so the parser functions below are not "untyped" to mypy.
generate: Callable[[Callable[..., Any]], Any] = _parsy_generate


@dataclass(frozen=True)
class VariableName:
    """A variable name in the pipeline language."""

    name: str
    """The name of the variable."""

    @property
    def is_variable(self) -> bool:
        return True


@dataclass(frozen=True)
class Identifier:
    """An identifier in the pipeline language."""

    name: str
    """The name of the identifier."""

    @property
    def is_variable(self) -> bool:
        return False

    def __str__(self) -> str:
        return self.name

    def __repr__(self) -> str:
        return self.name


@dataclass
class InputNode:
    """A node representing the input section of a pipeline."""

    source: VariableName | Identifier | str
    """The source of the input data."""
    params: dict[Identifier, Any]
    """The parameters for the input source.  Used when the handler is created."""

    @property
    def is_variable(self) -> bool:
        return not isinstance(self.source, str) and self.source.is_variable


@dataclass
class ParsedLoop:
    """A node representing a loop in the pipeline language."""

    iterations: int
    """The number of iterations for the loop."""
    pipelines: list["ParsedPipeline"]
    """The pipelines to execute in the loop."""

    def __iter__(self) -> Iterator["ParsedPipeline"]:
        return iter(self.pipelines)

    @property
    def input_nodes(self) -> list[InputNode | None]:
        """Get the input nodes for all pipelines in the loop."""
        return [p.input_node for p in self.pipelines if isinstance(p, ParsedPipeline)]


@dataclass
class SegmentNode:
    """A node representing a transform section of a pipeline."""

    operation: Identifier
    """The operation to perform."""
    params: dict[Identifier, Any]
    """The parameters for the operation.  Used when the handler is created."""


@dataclass
class ForkNode:
    """A node representing a fork in the pipeline language."""

    branches: list["ParsedPipeline"]
    """The branches of the fork, each a pipeline of segments (no input node)."""
    mode: str = "round_robin"
    """The distribution mode for the fork (round_robin or broadcast)."""
    params: dict[Identifier, Any] = field(default_factory=dict)
    """Additional parameters for the fork."""


@dataclass
class ParsedPipeline:
    """A node representing a pipeline in the pipeline language."""

    input_node: InputNode | None
    """The input node for the pipeline."""
    transforms: list[SegmentNode | VariableName | ForkNode]
    """The transforms to perform on the data, now including possible forks."""
    fork_target: str | None = None
    """Optional fork name that this pipeline feeds into (for -> fork_name syntax)."""
    fork_source: str | None = None
    """Optional fork name that this pipeline reads from (for fork_name -> syntax)."""
    missing_pipe_after_source: tuple[int, int] | None = None
    """1-indexed (line, column) of a first transform written without its leading '|'.

    ``INPUT FROM echo[data="1"] print`` has always parsed as though the pipe
    were there.  That spelling is deprecated (see
    ``talkpipe.chatterlang.compiler.warn_deprecated_syntax``); the location is
    recorded here so the deprecation can be reported, and is ``None`` for a
    pipeline written with the pipe.
    """


@dataclass
class ParsedScript:
    """A parsed script containing a list of pipelines and loops.

    This is an intermediate stage where the text script has already
    been parsed.
    """

    pipelines: list[ParsedPipeline | ParsedLoop]
    constants: dict[str, Any] = field(default_factory=dict)

    def __iter__(self) -> Iterator[ParsedPipeline | ParsedLoop]:
        return iter(self.pipelines)

    @property
    def input_nodes(self) -> list[InputNode | None]:
        """Get the input nodes for all pipelines in the script"""
        ans: list[InputNode | None] = []
        for p in self.pipelines:
            if isinstance(p, ParsedPipeline):
                ans.append(p.input_node)
            elif isinstance(p, ParsedLoop):
                ans.extend(p.input_nodes)
        return ans

    def input_nodes_contain(self, input_node_name: str) -> bool:
        """Check if the input nodes contain a specific input node name."""
        for n in self.input_nodes:
            if n is not None and n.source == Identifier(name=input_node_name):
                return True
        return False


def whitespace_wrap(p: Any) -> Any:
    return whitespace.many() >> p << whitespace.many()


def lexeme(s: str) -> Any:
    return whitespace_wrap(string(s))


whitespace_or_newline = regex(r"[ \t\n\r]+")


def fork_whitespace(p: Any) -> Any:
    return whitespace_or_newline.many() >> p << whitespace_or_newline.many()


bool_value = (regex(r"true|false|TRUE|FALSE|True|False")).map(
    lambda s: s.lower() == "true"
)
"""A parser for boolean values."""
identifier = regex(r"[a-zA-Z][a-zA-Z0-9_]*").map(lambda s: Identifier(name=s))
"""A parser for identifiers.  Identifiers are used for operation names, variable names, etc."""
variable = (string("@") >> identifier).map(lambda x: VariableName(name=x.name))
"""A parser for variable names.  Variables are used to store and retrieve data in the pipeline."""
environmentVariable = (string("$") >> identifier).map(lambda x: get_config()[x.name])
# quoted_string supports both double and single quotes with escaping
quoted_string = regex(r'"(?:[^"]|"")*"').map(
    lambda s: s[1:-1].replace('""', '"')
) | regex(r"'(?:[^']|'')*'").map(lambda s: s[1:-1].replace("''", "'"))
"""A parser for quoted strings. Supports both double quotes ("...") and single quotes ('...')."""
number = regex(r"-?\d+(\.\d+)?").map(lambda s: int(s) if "." not in s else float(s))
"""A parser for numbers.  Returns both ints and floats."""

atomic_parameter = (
    quoted_string | bool_value | number | identifier | variable | environmentVariable
)
"""A parser for atomic (non-array) parameters."""


@generate
def array_parameter() -> Any:
    """A parser for array parameters like [1, "str", MY_CONST].

    Arrays can contain any valid parameter type including nested arrays.
    Elements are separated by commas with optional whitespace.
    """
    yield lexeme("[")
    elements = yield parameter.sep_by(lexeme(","), min=0)
    yield lexeme("]")
    return elements


parameter = atomic_parameter | array_parameter
"""A parser for parameters.  Parameters can be strings, booleans, numbers, identifiers, arrays, or variables."""

key_value = seq(key=identifier << lexeme("="), value=parameter).map(
    lambda x: (x["key"].name, x["value"])
)
"""A parser for key=value pairs.  Used for parameters in brackets."""

# Square bracket parser that handles key=value pairs
bracket_content = seq(params=key_value.sep_by(lexeme(","), min=0)).map(
    lambda x: dict(x["params"])
)
"""A parser for the content inside square brackets.  This is used for parameters in the pipeline language."""

bracket_parser = (
    (lexeme("[") >> bracket_content << lexeme("]"))
    .optional()
    .map(lambda x: x if x else {})
)
"""A parser for square brackets.  This is used for parameters in the pipeline language."""


# New parser for constant definitions
@generate
def constant_definition() -> Any:
    yield (lexeme("CONST") | lexeme("SET"))
    const_name = yield identifier
    yield lexeme("=")
    const_value = yield parameter
    return (const_name.name, const_value)


"""A parser for defining constants with 'SET' keyword."""

source = (
    (
        lexeme("INPUT") >> lexeme("FROM")
        | lexeme("NEW") >> lexeme("FROM")
        | lexeme("NEW")
    )
    >> seq(
        source=(variable | identifier | quoted_string | environmentVariable),
        bracket_content=bracket_parser,
    )
).map(lambda x: InputNode(x["source"], x["bracket_content"]))
"""A parser for the input section of a pipeline.  'INPUT FROM', 'NEW FROM', and 'NEW' are all valid equivalent syntax."""

# Transform section parser
segment = seq(operation=identifier, bracket_content=bracket_parser).map(
    lambda x: SegmentNode(x["operation"], x["bracket_content"])
)
"""A parser for the transform section of a pipeline."""


@generate
def fork_branch_pipeline() -> Any:
    """
    Parser for a pipeline fragment inside a fork branch.
    This can be either a full pipeline or just transform segments.
    """
    # Check if this branch starts with an input source
    yield line_info

    # Try to match an input source
    input_node = yield source.optional()

    # If we found an input source, parse the rest as a normal pipeline
    if input_node is not None:
        transforms, missing_pipe = yield transforms_after_source
        yield whitespace.many()
        return ParsedPipeline(
            input_node, transforms, missing_pipe_after_source=missing_pipe
        )

    # If no input source, try to parse as a sequence of segments
    # First segment might not have a leading pipe
    first_transform = yield (fork_section | segment | variable)
    transforms = [first_transform]

    # Parse remaining segments (with leading pipes)
    remaining = yield (lexeme("|") >> (fork_section | segment | variable)).many()
    transforms.extend(remaining)

    # Return a pipeline with no input node
    return ParsedPipeline(None, transforms)


@generate
def fork_branch() -> Any:
    """Parser for a single branch within a fork."""
    branch = yield fork_branch_pipeline
    return branch


@generate
def fork_content() -> Any:
    """Parser for the content inside fork()."""
    yield whitespace.many()
    first_branch = yield fork_branch
    remaining_branches = yield (
        (lexeme(",") >> whitespace.many() >> fork_branch).many()
    )
    yield whitespace.many()
    return [first_branch, *remaining_branches]


@generate
def fork_section() -> Any:
    """Parser for a complete fork section."""
    yield lexeme("fork")
    yield lexeme("(")
    bracket_content = yield bracket_parser
    branches = yield fork_content
    yield lexeme(")")
    return ForkNode(branches=branches, params=bracket_content)


@generate
def transforms_section() -> Any:
    """A parser for the transforms section.  Transforms are separated by the '|' character.

    Used where a pipeline has no input source of its own and so legitimately
    begins with a bare segment: a fork branch, a fork consumer
    (``fork_name -> print``), or a script fragment such as ``| print``.  After
    an input source, use :data:`transforms_after_source` instead, which treats
    the omitted pipe as deprecated rather than as ordinary syntax.
    """
    # First transform may or may not have a leading pipe (optional to allow empty transforms)
    first_transform = yield (
        lexeme("|").optional() >> (fork_section | segment | variable)
    ).optional()
    if first_transform is None:
        return []

    transforms = [first_transform]

    # Parse remaining segments (with leading pipes)
    remaining = yield (lexeme("|") >> (fork_section | segment | variable)).many()
    transforms.extend(remaining)

    return transforms


@generate
def transforms_after_source() -> Any:
    """A parser for the transforms that follow an input source.

    Returns ``(transforms, missing_pipe)``, where ``missing_pipe`` is the
    1-indexed (line, column) of the first transform when its leading ``|`` was
    omitted -- ``INPUT FROM echo[data="1"] print`` -- and ``None`` otherwise.
    That spelling is accepted for backward compatibility and reported as
    deprecated by the compiler; only the *first* pipe was ever optional, so
    ``INPUT FROM echo[data="1"] print print`` remains a syntax error.
    """
    piped = yield (lexeme("|") >> (fork_section | segment | variable)).optional()
    if piped is not None:
        first_transform, missing_pipe = piped, None
    else:
        # No leading pipe.  Note the position before trying a bare transform so
        # the deprecation can point at it.  Whitespace is deliberately not
        # skipped here: the source parser consumes what follows a `]`, and
        # skipping more would newly accept spellings (`INPUT FROM @x print`)
        # that have always been errors.
        line, column = yield line_info
        first_transform = yield (fork_section | segment | variable).optional()
        if first_transform is None:
            return [], None
        missing_pipe = (line + 1, column + 1)

    transforms = [first_transform]

    # Parse remaining segments (with leading pipes)
    remaining = yield (lexeme("|") >> (fork_section | segment | variable)).many()
    transforms.extend(remaining)

    return transforms, missing_pipe


# Parser for arrow fork target: -> identifier
arrow_fork_target = (lexeme("->") >> identifier).map(lambda x: x.name)
"""A parser for arrow fork target syntax: -> fork_name"""

# Parser for arrow fork source: identifier ->
arrow_fork_source = (identifier << lexeme("->")).map(lambda x: x.name)
"""A parser for arrow fork source syntax: fork_name ->"""


@generate
def pipeline() -> Any:
    yield whitespace.many()

    # Check for fork source at the start: fork_name ->
    fork_source = yield arrow_fork_source.optional()

    input_node = yield source.optional()
    if input_node is not None:
        transforms, missing_pipe = yield transforms_after_source
    else:
        transforms = yield transforms_section
        missing_pipe = None

    # Check for fork target at the end: -> fork_name
    fork_target = yield arrow_fork_target.optional()

    yield whitespace.many()
    return ParsedPipeline(
        input_node or None,
        transforms,
        fork_target=fork_target,
        fork_source=fork_source,
        missing_pipe_after_source=missing_pipe,
    )


"""A parser for a pipeline in the pipeline language.  Pipelines consist of an input section and a series of transforms."""


@generate
def loop() -> Any:
    yield lexeme("LOOP")
    iterations = yield number
    yield lexeme("TIMES")
    yield lexeme("{")
    pipes = yield script_parser
    yield lexeme("}")
    return ParsedLoop(int(iterations), pipes)


"""A parser for a loop in the pipeline language.  Loops consist of a number of iterations over a series of pipelines."""

pipeline_separator = lexeme(";")
"""A parser for the separator between pipelines in a script."""


@generate
def script_parser() -> Any:
    # First parse constants
    constants = yield constant_definition.sep_by(pipeline_separator)
    constants = dict(constants)

    # Parse pipelines and loops
    pipelines = yield (loop | pipeline).sep_by(pipeline_separator)

    pipelines = [
        p
        for p in pipelines
        if not isinstance(p, ParsedPipeline) or (p.input_node or len(p.transforms) > 0)
    ]

    # Create and return a ParsedScript with constants
    return ParsedScript(pipelines, constants)


"""A parser for a script in the pipeline language.  Scripts contain a series of pipelines and loops."""
