"""Compiler for chatterlang scripts

These methods take either a script or a parsed script and compile it into a callable function.
For an end user, the most important method is the compile method that takes a string, but the
other methods are used internally to compile the parsed scripts.
"""

import contextlib
import difflib
import inspect
import logging
import re
import warnings
from collections.abc import Iterable, Iterator
from functools import singledispatch
from typing import Any

import networkx as nx
from parsy import ParseError

from talkpipe.chatterlang import registry
from talkpipe.chatterlang.parsers import (
    ForkNode,
    Identifier,
    ParsedLoop,
    ParsedPipeline,
    ParsedScript,
    SegmentNode,
    VariableName,
    script_parser,
)
from talkpipe.operations.thread_ops import QueueConsumer, ThreadedQueue
from talkpipe.pipe import io
from talkpipe.pipe.core import (
    AbstractSegment,
    AbstractSource,
    Loop,
    RuntimeComponent,
    Script,
)
from talkpipe.pipe.fork import ForkSegment

logger = logging.getLogger(__name__)


class CompileError(Exception):
    """Exception raised when a compilation error occurs in chatterlang

    Besides the formatted message, instances may carry optional structured
    location/context attributes (all default to None) so tooling such as the
    workbench lint endpoint can consume errors without re-parsing the text:
    ``line``/``column`` (1-indexed), ``kind`` ("syntax" | "unknown_name" |
    "bad_param"), and ``bad_name`` (the offending segment/source name).
    """

    def __init__(
        self,
        message: str = "",
        *,
        line: int | None = None,
        column: int | None = None,
        kind: str | None = None,
        bad_name: str | None = None,
    ) -> None:
        super().__init__(message)
        self.line = line
        self.column = column
        self.kind = kind
        self.bad_name = bad_name


def _valid_param_names(component: Any) -> list[str]:
    """Best-effort list of accepted keyword parameters for a component class.

    Returns an empty list when the signature can't be introspected or only
    forwards *args/**kwargs (as function-based segments do), so callers can
    avoid showing a misleading parameter list.
    """
    try:
        params = inspect.signature(component).parameters.values()
    except (TypeError, ValueError):
        return []
    return [
        p.name for p in params if p.kind in (p.POSITIONAL_OR_KEYWORD, p.KEYWORD_ONLY)
    ]


def _bad_param_message(kind: str, name: str, component: Any, error: TypeError) -> str:
    """Build a CompileError message for an invalid parameter on a component."""
    msg = f"{kind} '{name}' was given invalid parameters: {error}."
    valid = _valid_param_names(component)
    if valid:
        msg += f" Valid parameters: {', '.join(valid)}."
    return msg


def _construction_failed_message(kind: str, name: str, error: Exception) -> str:
    """Build a CompileError message for a component that rejected its options.

    Covers everything a component's constructor can raise other than a bad
    keyword (which ``_bad_param_message`` handles): an unsupported ``source``,
    a missing model, an out-of-range value. Without this, such errors escape
    compilation as raw exceptions and reach the user as a Python traceback.
    """
    detail = str(error) or type(error).__name__
    return f"{kind} '{name}' could not be created: {detail}"


def _not_found_message(kind: str, name: str, reg: registry.HybridRegistry[Any]) -> str:
    """Build a CompileError message for an unknown segment/source name."""
    try:
        available = reg.available_names
    except Exception:  # pragma: no cover - defensive; never block the error path
        available = []

    # A name declared by a plugin entry point that failed to import lands here
    # too (available_names lists it without importing it). Reporting it as
    # merely "not found" — and then suggesting the same name as a typo fix —
    # is self-contradictory and hides the real (import) error from the user.
    load_error = None
    with contextlib.suppress(AttributeError):
        load_error = reg.load_error(name)

    if load_error is not None:
        msg = (
            f"{kind} '{name}' was declared by a plugin but failed to load: {load_error}"
        )
        other_available = [a for a in available if a != name]
        if other_available:
            msg += f" Other available {kind.lower()}s: {', '.join(other_available)}."
        return msg

    # A source name used where a segment belongs (or vice versa) is a common
    # newcomer mistake — e.g. a script that is just `echo`. Saying the name
    # exists as the other kind (and how to use it) beats a 90-name dump that
    # never mentions the component the user clearly meant.
    if kind == "Segment" and name in registry.input_registry.available_names:
        return (
            f"Segment '{name}' not found, but a source named '{name}' exists. "
            f"Sources start a pipeline: INPUT FROM {name} | ..."
        )
    if kind == "Source" and name in registry.segment_registry.available_names:
        return (
            f"Source '{name}' not found, but a segment named '{name}' exists. "
            f"Segments belong after a pipe: ... | {name}"
        )

    msg = f"{kind} '{name}' not found."
    suggestions = [
        s for s in difflib.get_close_matches(name, available, n=3) if s != name
    ]
    if suggestions:
        # Close matches make the full registry dump (90+ names) noise; only
        # fall back to the complete list when we have no better guess.
        msg += " Did you mean " + " or ".join(repr(s) for s in suggestions) + "?"
    elif available:
        msg += f" Available {kind.lower()}s: {', '.join(available)}."
    return msg


def _transform_label(transform: Any) -> str:
    """How a transform should be spelled back to the user in a diagnostic."""
    if isinstance(transform, SegmentNode):
        return transform.operation.name
    if isinstance(transform, VariableName):
        return f"@{transform.name}"
    if isinstance(transform, ForkNode):
        return "fork(...)"
    return "the first segment"


def iter_deprecated_syntax(script: ParsedScript) -> Iterator[tuple[int, int, str]]:
    """Yield (line, column, message) for each deprecated spelling in a script.

    Locations are 1-indexed and refer to the comment-stripped script text,
    which ``remove_comments`` keeps line- and column-aligned with the original.
    Separate from the warning itself so tooling -- the workbench lint endpoint
    -- can render the same diagnostics in an editor.
    """

    def walk(node: Any) -> Iterator[tuple[int, int, str]]:
        if isinstance(node, ParsedLoop):
            for inner in node.pipelines:
                yield from walk(inner)
            return
        if not isinstance(node, ParsedPipeline):
            return
        if node.missing_pipe_after_source is not None and node.transforms:
            line, column = node.missing_pipe_after_source
            label = _transform_label(node.transforms[0])
            message = (
                f"whitespace where '|' was expected, before '{label}'. Omitting "
                "the pipe between an input source and the first segment is "
                "deprecated and will be a syntax error in TalkPipe 2.0; write "
                f"'| {label}' instead."
            )
            yield line, column, message
        for transform in node.transforms:
            if isinstance(transform, ForkNode):
                for branch in transform.branches:
                    yield from walk(branch)

    for pipeline in script.pipelines:
        yield from walk(pipeline)


def warn_deprecated_syntax(script: ParsedScript) -> None:
    """Report every deprecated spelling in a parsed script.

    Each is raised as a ``DeprecationWarning`` (the project's deprecation
    policy) *and* logged at WARNING, because the audience is a ChatterLang
    author running ``chatterlang_script`` or the workbench: Python hides
    ``DeprecationWarning`` outside ``__main__``, and a warning nobody sees
    would not give anyone a chance to fix a script before 2.0.
    """
    for line, column, message in iter_deprecated_syntax(script):
        located = f"ChatterLang, line {line}, column {column}: {message}"
        # stacklevel points at compile() rather than at whoever called it:
        # singledispatch puts a varying number of functools frames in between,
        # and the location that matters is the one in the message anyway.
        warnings.warn(located, DeprecationWarning, stacklevel=2)
        logger.warning(located)


def parse_error_location(
    script: str, error: ParseError
) -> tuple[int, int] | tuple[None, None]:
    """Return the 1-indexed (line, column) of a parsy ParseError.

    Returns (None, None) when the error carries no usable position.
    """
    index = getattr(error, "index", None)
    stream = getattr(error, "stream", script)
    if index is None or not isinstance(stream, str):
        return None, None
    before = stream[:index]
    line_start = before.rfind("\n") + 1
    return before.count("\n") + 1, index - line_start + 1


def _format_parse_error(script: str, error: ParseError) -> str:
    """Turn a raw parsy ParseError into a friendly, located syntax error."""
    index = getattr(error, "index", None)
    stream = getattr(error, "stream", script)
    expected = getattr(error, "expected", None)
    if index is None or not isinstance(stream, str):
        return f"Could not parse ChatterLang script: {error}"
    before = stream[:index]
    line_start = before.rfind("\n") + 1
    line_no, col_no = parse_error_location(script, error)
    if line_no is None or col_no is None:  # already excluded above; narrows for typing
        return f"Could not parse ChatterLang script: {error}"
    line_end = stream.find("\n", index)
    if line_end == -1:
        line_end = len(stream)
    line_text = stream[line_start:line_end]
    caret = " " * (col_no - 1) + "^"
    exp = ""
    if expected:
        exp = " Expected one of: " + ", ".join(sorted(str(e) for e in expected)) + "."
    hint = ""
    # Failing right after `param=<bareword>` is almost always an unquoted
    # string value (e.g. model=llama3.2); the grammar jargon alone won't
    # tell a newcomer that.
    if re.search(r"\w+\s*=\s*[A-Za-z_][\w]*$", before):
        hint = (
            '\n    Hint: string parameter values must be quoted, e.g. model="llama3.2".'
        )
    return (
        f"Syntax error in ChatterLang script at line {line_no}, column {col_no}.{exp}\n"
        f"    {line_text}\n"
        f"    {caret}{hint}"
    )


@singledispatch
def compile(
    script: Any, runtime: RuntimeComponent | None = None
) -> AbstractSegment[Any, Any]:
    """Compile a parsed script into a callable function

    Args:
        script (ParsedScript): The script to compile
        v_store (VariableStore): The variable store to use
    """
    logger.debug(f"Compiling script with {len(script.pipelines)} pipelines")
    if isinstance(script, ParsedScript):
        warn_deprecated_syntax(script)
    runtime = runtime or RuntimeComponent()
    # Add script constants without overriding existing runtime constants
    runtime.add_constants(script.constants, override=False)
    logger.debug(f"Initialized runtime with {len(runtime.const_store)} constants")

    # Build fork graph from arrow syntax using networkx
    # Use a directed graph where:
    # - Pipeline nodes are represented by their index (e.g., "pipeline_0")
    # - Fork nodes are represented by their name (e.g., "fork_name")
    # - Edges represent producer->fork and fork->consumer relationships
    graph = nx.DiGraph()
    fork_segments: dict[str, ArrowForkSegment] = {}

    # First pass: build graph structure
    for idx, pipeline in enumerate(script.pipelines):
        if isinstance(pipeline, ParsedPipeline):
            pipeline_node = f"pipeline_{idx}"
            if pipeline.fork_target:
                # This pipeline feeds into a fork
                graph.add_edge(pipeline_node, pipeline.fork_target)
            if pipeline.fork_source:
                # This pipeline reads from a fork
                graph.add_edge(pipeline.fork_source, pipeline_node)

    # Create ArrowForkSegment instances for all forks in the graph
    fork_nodes = {node for node in graph.nodes() if not node.startswith("pipeline_")}
    for fork_name in fork_nodes:
        fork_segments[fork_name] = ArrowForkSegment(fork_name)

    # Second pass: compile all pipelines (without fork connections)
    # Use list indices as keys since ParsedPipeline is not hashable
    compiled_pipelines_list: list[Any] = []
    pipeline_index_map: dict[int, int] = {}  # Maps original index to compiled index
    for idx, pipeline in enumerate(script.pipelines):
        if isinstance(pipeline, ParsedPipeline):
            # Create a copy of the pipeline without fork_source/fork_target for compilation
            # We'll handle fork connections separately
            pipeline_copy = ParsedPipeline(
                pipeline.input_node,
                pipeline.transforms,
                fork_target=None,
                fork_source=None,
            )
            compiled = compile(pipeline_copy, runtime)
            compiled_pipelines_list.append(compiled)
            pipeline_index_map[idx] = len(compiled_pipelines_list) - 1
        else:
            # Loops are compiled normally
            compiled = compile(pipeline, runtime)
            compiled_pipelines_list.append(compiled)
            pipeline_index_map[idx] = len(compiled_pipelines_list) - 1

    # Third pass: connect pipelines to forks using graph structure
    # Register producers (pipelines that feed into forks)
    # Use graph successors to find forks that pipelines feed into
    for pipeline_node in graph.nodes():
        if pipeline_node.startswith("pipeline_"):
            pipeline_idx = int(pipeline_node.split("_")[1])
            pipeline = script.pipelines[pipeline_idx]
            if isinstance(pipeline, ParsedPipeline):
                # Check if this pipeline feeds into any fork (has outgoing edges to forks)
                for fork_name in graph.successors(pipeline_node):
                    if not fork_name.startswith("pipeline_"):  # It's a fork node
                        fork_segment = fork_segments[fork_name]
                        compiled_idx = pipeline_index_map[pipeline_idx]
                        compiled_pipeline = compiled_pipelines_list[compiled_idx]
                        fork_segment.register_producer(compiled_pipeline)

    # Create consumer wrapper segments for pipelines that read from forks
    consumer_wrappers: dict[int, Any] = {}  # Maps pipeline index to wrapper
    # Use graph predecessors to find forks that pipelines read from
    for pipeline_node in graph.nodes():
        if pipeline_node.startswith("pipeline_"):
            pipeline_idx = int(pipeline_node.split("_")[1])
            pipeline = script.pipelines[pipeline_idx]
            if isinstance(pipeline, ParsedPipeline):
                # Check if this pipeline reads from any fork (has incoming edges from forks)
                for fork_name in graph.predecessors(pipeline_node):
                    if not fork_name.startswith("pipeline_"):  # It's a fork node
                        fork_segment = fork_segments[fork_name]
                        compiled_idx = pipeline_index_map[pipeline_idx]
                        compiled_pipeline = compiled_pipelines_list[compiled_idx]
                        consumer = fork_segment.register_consumer(compiled_pipeline)

                        # Create a wrapper segment that reads from the consumer and feeds into the pipeline
                        class ForkConsumerWrapper(AbstractSegment[Any, Any]):
                            def __init__(
                                self,
                                consumer_iter: Iterable[Any],
                                downstream_pipeline: Any,
                            ) -> None:
                                super().__init__()
                                self.consumer_iter = consumer_iter
                                self.downstream_pipeline = downstream_pipeline

                            def transform(
                                self, input_iter: Iterable[Any]
                            ) -> Iterator[Any]:
                                # Execute downstream pipeline with items from consumer
                                # Ignore input_iter and use consumer_iter instead
                                # Use __call__() to ensure metadata handling
                                yield from self.downstream_pipeline(self.consumer_iter)

                        wrapper = ForkConsumerWrapper(consumer, compiled_pipeline)
                        consumer_wrappers[pipeline_idx] = wrapper

    # For wrappers that are both consumers and producers, register them as producers
    # to the target fork. They will execute in background threads via ThreadedQueue.
    # Use graph to find pipelines that are both consumers and producers
    for pipeline_node in graph.nodes():
        if pipeline_node.startswith("pipeline_"):
            pipeline_idx = int(pipeline_node.split("_")[1])
            pipeline = script.pipelines[pipeline_idx]
            if isinstance(pipeline, ParsedPipeline):
                # Check if pipeline is both a consumer (has incoming edges from forks)
                # and a producer (has outgoing edges to forks)
                has_incoming_fork = any(
                    not pred.startswith("pipeline_")
                    for pred in graph.predecessors(pipeline_node)
                )
                has_outgoing_fork = any(
                    not succ.startswith("pipeline_")
                    for succ in graph.successors(pipeline_node)
                )
                if (
                    has_incoming_fork
                    and has_outgoing_fork
                    and pipeline_idx in consumer_wrappers
                ):
                    wrapper = consumer_wrappers[pipeline_idx]
                    # Find the target fork (outgoing edge to a fork)
                    for fork_name in graph.successors(pipeline_node):
                        if not fork_name.startswith("pipeline_"):  # It's a fork node
                            target_fork = fork_segments[fork_name]

                            # Register a producer that executes the wrapper
                            # This will run in a background thread, so it can block waiting for source fork
                            # We create a generator function that will be called in start()
                            def make_producer(w: Any) -> Any:
                                def producer() -> Iterator[Any]:
                                    # Execute wrapper - it will consume from source fork and produce items
                                    yield from w()

                                return producer

                            # Store the producer function, not call it yet
                            target_fork.register_producer(make_producer(wrapper))

    # Start all forks (this registers producers and starts the queue system)
    # ThreadedQueue will start producers in background threads, so they can block
    # waiting for items from source forks without deadlocking
    for fork_segment in fork_segments.values():
        fork_segment.start()

    # Build final pipeline list
    # Include:
    # 1. Consumer-only pipelines (read from fork but don't feed to another fork) - use wrappers
    # 2. Standalone pipelines (no fork connections)
    # Producer-only pipelines are handled by forks and don't need to be in final_pipelines
    # Pipelines that are both consumers and producers are handled by forks (as producers in background threads)
    final_pipelines: list[AbstractSegment[Any, Any]] = []
    for idx, pipeline in enumerate(script.pipelines):
        if isinstance(pipeline, ParsedPipeline):
            if pipeline.fork_source and not pipeline.fork_target:
                # This pipeline reads from a fork but doesn't feed to another fork
                # Use the wrapper - it will execute and produce final output
                if idx in consumer_wrappers:
                    final_pipelines.append(consumer_wrappers[idx])
                else:
                    # Should not happen, but handle gracefully
                    compiled_idx = pipeline_index_map[idx]
                    final_pipelines.append(compiled_pipelines_list[compiled_idx])
            elif not pipeline.fork_target and not pipeline.fork_source:
                # Normal pipeline (no fork connections)
                compiled_idx = pipeline_index_map[idx]
                final_pipelines.append(compiled_pipelines_list[compiled_idx])
            # Pipelines that feed into forks (fork_target) are handled by fork's start()
            # Pipelines that are both consumers and producers are also handled by fork's start()
        else:
            # Loops
            compiled_idx = pipeline_index_map[idx]
            final_pipelines.append(compiled_pipelines_list[compiled_idx])

    logger.debug("Successfully compiled all pipelines")
    return Script(final_pipelines)


def _resolve_value(value: Any, runtime: RuntimeComponent) -> Any:
    """Resolve a single parameter value, handling constants and arrays recursively."""
    if isinstance(value, Identifier):
        return runtime.const_store[value.name]
    if isinstance(value, list):
        return [_resolve_value(elem, runtime) for elem in value]
    return value


def _resolve_params(
    params: dict[Any, Any], runtime: RuntimeComponent
) -> dict[str, Any]:
    """Resolve the parameters for a segment"""
    return {k: _resolve_value(params[k], runtime) for k in params}


@compile.register(ParsedPipeline)
def _(
    pipeline: ParsedPipeline, runtime: RuntimeComponent
) -> AbstractSource[Any] | AbstractSegment[Any, Any]:
    """Compile a parsed pipeline into a Pipeline object

    Args:
        pipeline (ParsedPipeline): The pipeline to compile
        v_store (VariableStore): The variable store to use
    """
    logger.debug("Starting pipeline compilation")
    ans: AbstractSource[Any] | AbstractSegment[Any, Any] | None = None
    if pipeline.input_node is not None:
        input_source = pipeline.input_node.source
        logger.debug(f"Processing input node of type {type(input_source)}")
        if isinstance(input_source, str):
            ans = io.echo(input_source, delimiter=None)
            logger.debug("Created echo input with string source")
        elif pipeline.input_node.is_variable:
            ans = VariableSource(input_source.name)
            logger.debug(f"Created variable source with name {input_source.name}")
        else:
            source_name = input_source.name
            try:
                source_cls = registry.input_registry.get(source_name)
            except KeyError:
                raise CompileError(
                    _not_found_message("Source", source_name, registry.input_registry),
                    kind="unknown_name",
                    bad_name=source_name,
                ) from None
            try:
                ans = source_cls(
                    **_resolve_params(pipeline.input_node.params, runtime=runtime)
                )
            except TypeError as e:
                raise CompileError(
                    _bad_param_message("Source", source_name, source_cls, e),
                    kind="bad_param",
                    bad_name=source_name,
                ) from None
            except CompileError:
                raise
            except Exception as e:
                raise CompileError(
                    _construction_failed_message("Source", source_name, e),
                    bad_name=source_name,
                ) from None
            logger.debug(f"Created registered input {source_name}")
        ans.runtime = runtime

    logger.debug(f"Processing {len(pipeline.transforms)} transforms")
    for transform in pipeline.transforms:
        next_transform: AbstractSegment[Any, Any]
        if isinstance(transform, VariableName):
            next_transform = VariableSetSegment(transform.name)
            logger.debug(f"Created variable set segment for {transform.name}")
        elif isinstance(transform, SegmentNode):
            segment_name = transform.operation.name
            try:
                segment_cls = registry.segment_registry.get(segment_name)
            except KeyError:
                raise CompileError(
                    _not_found_message(
                        "Segment", segment_name, registry.segment_registry
                    ),
                    kind="unknown_name",
                    bad_name=segment_name,
                ) from None
            try:
                next_transform = segment_cls(
                    **_resolve_params(transform.params, runtime=runtime)
                )
            except TypeError as e:
                raise CompileError(
                    _bad_param_message("Segment", segment_name, segment_cls, e),
                    kind="bad_param",
                    bad_name=segment_name,
                ) from None
            except CompileError:
                raise
            except Exception as e:
                raise CompileError(
                    _construction_failed_message("Segment", segment_name, e),
                    bad_name=segment_name,
                ) from None
            logger.debug(f"Created segment {segment_name}")
        elif isinstance(transform, ForkNode):
            next_transform = compile(transform, runtime)
        else:  # defensive: the parser is untyped, so keep the runtime check
            logger.error(f"Unknown segment type: {transform}")  # type: ignore[unreachable]
            raise ValueError(f"Unknown segment type: {transform}")
        next_transform.runtime = runtime

        if ans is None:
            ans = next_transform
        else:
            ans |= next_transform
    if ans is None:
        raise ValueError("Cannot compile an empty pipeline")
    ans.runtime = runtime
    logger.debug("Completed pipeline compilation")
    return ans


@compile.register(ForkNode)
def _(fork: ForkNode, runtime: RuntimeComponent) -> ForkSegment:
    """Compile a fork node into a Pipeline object

    Args:
        fork (ForkNode): The fork node to compile
        v_store (VariableStore): The variable store to use
    """
    logger.debug("Starting fork compilation")
    pipelines: list[AbstractSegment[Any, Any] | AbstractSource[Any]] = [
        compile(pipeline, runtime) for pipeline in fork.branches
    ]
    logger.debug("Completed fork compilation")
    return ForkSegment(pipelines)


@compile.register(ParsedLoop)
def _(loop: ParsedLoop, runtime: RuntimeComponent) -> Loop:
    """Compile a parsed loop into a Loop object

    Args:
        loop (ParsedLoop): The loop to compile
        v_store (VariableStore): The variable store to use
    """
    pipelines = [compile(pipeline, runtime) for pipeline in loop.pipelines]
    return Loop(loop.iterations, Script(pipelines))


def remove_comments(text: str) -> str:
    """
    Remove comments from the given multi-line string.
    A comment starts with a hash (#) outside double quotes and continues to the end of the line.

    Parameters:
        text (str): The input string with potential comments.

    Returns:
        str: The string with comments removed.
    """
    result = []
    in_quotes = False
    i = 0
    while i < len(text):
        char = text[i]
        if char == '"':
            in_quotes = not in_quotes
            result.append(char)
            i += 1
        elif char == "#" and not in_quotes:
            # Skip all characters until the end of the line or end of string
            while i < len(text) and text[i] != "\n":
                i += 1
            # If we stopped because of a newline, add it to the result.
            if i < len(text) and text[i] == "\n":
                result.append("\n")
                i += 1
        else:
            result.append(char)
            i += 1
    return "".join(result)


@compile.register(str)
def _(
    script: str, runtime: RuntimeComponent | None = None
) -> AbstractSegment[Any, Any]:
    """Compile a script into a callable function

    Args:
        script (str): The script to compile
        v_store (VariableStore): The variable store to use
    """
    preprocessed_script = remove_comments(script)
    try:
        parsed = script_parser.parse(preprocessed_script)
    except ParseError as e:
        line, column = parse_error_location(preprocessed_script, e)
        raise CompileError(
            _format_parse_error(preprocessed_script, e),
            line=line,
            column=column,
            kind="syntax",
        ) from None
    return compile(parsed, runtime)


class ArrowForkSegment:
    """A coordinator for named forks using ThreadedQueue.

    This class manages the ThreadedQueue for a named fork, ensuring
    metadata items are properly passed through by using the proper
    execution mechanism (__call__) for pipelines.

    ThreadedQueue naturally provides broadcast-style distribution:
    - All items from all producers are broadcast to all consumers
    - Each consumer sees every item from every producer
    """

    def __init__(self, fork_name: str):
        self.fork_name = fork_name
        self.queue_system = ThreadedQueue()  # Broadcasts by default
        self.producer_pipelines: list[Any] = []
        self.consumer_pipelines: list[Any] = []
        self._started = False

    def register_producer(self, pipeline: Any) -> None:
        """Register a pipeline as a producer to this fork.

        The pipeline will be executed using __call__() to ensure
        metadata is handled correctly. All items will be broadcast
        to all registered consumers.
        """
        if self._started:
            raise RuntimeError(
                f"Cannot register producers after fork {self.fork_name} has started"
            )
        self.producer_pipelines.append(pipeline)

    def register_consumer(self, pipeline: Any) -> QueueConsumer:
        """Register a pipeline as a consumer from this fork.

        Returns a consumer iterator that yields items from the queue.
        The consumer will receive all items from all producers
        (broadcast-style distribution).
        """
        if self._started:
            raise RuntimeError(
                f"Cannot register consumers after fork {self.fork_name} has started"
            )
        self.consumer_pipelines.append(pipeline)
        return self.queue_system.register_consumer()

    def start(self) -> None:
        """Start the fork by registering all producers and starting the queue system."""
        if self._started:
            return

        # Register all producers - execute them using __call__() for metadata handling
        for pipeline in self.producer_pipelines:
            # Execute pipeline using __call__() to ensure metadata flows correctly
            producer_iter = pipeline()
            self.queue_system.register_producer(producer_iter)

        # Start the queue system
        self.queue_system.start()
        self._started = True


def _variable_store(
    component: AbstractSource[Any] | AbstractSegment[Any, Any],
) -> dict[str, Any]:
    """Return the variable store of the runtime attached to a compiled component.

    Components that read or write ChatterLang variables are only meaningful once
    the compiler has attached a runtime; fail clearly otherwise.
    """
    runtime = component.runtime
    if runtime is None:
        raise RuntimeError(
            f"{type(component).__name__} is not attached to a runtime; "
            "it must be created by compiling a ChatterLang script"
        )
    return runtime.variable_store


class VariableSource(AbstractSource[Any]):
    """A source that gets a variable from the variable store and returns its
    contents item by item.

    Is used in chatterlang via the INPUT FROM @variable_name syntax.
    """

    def __init__(self, variable_name: str):
        super().__init__()
        self.variable_name = variable_name

    def generate(self) -> Iterator[Any]:
        yield from _variable_store(self)[self.variable_name]


class VariableSetSegment(AbstractSegment[Any, Any]):
    """A segment that sets a variable in the variable store.

    It trains its input stream, stores the result as a list and then
    emits each item one by one.  It is not used directly but is
    by the @variable_name syntax in chatterlang.
    """

    def __init__(self, variable_name: str):
        super().__init__()
        self.variable_name = variable_name

    def transform(self, items: Iterable[Any]) -> Iterator[Any]:
        list_of_items = list(items)
        _variable_store(self)[self.variable_name] = list_of_items
        yield from list_of_items


@registry.register_segment(name="accum")
class Accum(AbstractSegment[Any, Any]):
    """Accumulates items from the input stream both in an internal buffer and in the specified variable.
    This is useful for accumulating the results of running the pipeline multiple times.

    Args:
        variable (Union[VariableName, str], optional): The name of the variable to store the accumulated data in. Defaults to None.
        reset (bool, optional): Whether to reset the accumulator each time the segment is run. Defaults to True."""

    def __init__(self, variable: VariableName | str | None = None, reset: bool = True):
        super().__init__()
        self.variable_name: str | None
        if variable is None:
            self.variable_name = None
        else:
            self.variable_name = (
                variable if isinstance(variable, str) else variable.name
            )
        self.reset = reset
        self.accumulator: list[Any] = []

    def transform(self, items: Iterable[Any]) -> Iterator[Any]:
        if self.reset:
            self.accumulator = []

        if self.variable_name and self.variable_name not in _variable_store(self):
            _variable_store(self)[self.variable_name] = []

        for item in self.accumulator:
            yield item

        for item in items:
            self.accumulator.append(item)
            if self.variable_name:
                _variable_store(self)[self.variable_name].append(item)
            yield item


def _looks_like_script_path(text: str) -> bool:
    """Heuristic: a single token with a path separator or a script-file suffix,
    and no pipeline syntax, was almost certainly meant as a file path."""
    if "|" in text or any(ch.isspace() for ch in text):
        return False
    return (
        "/" in text
        or "\\" in text
        or text.endswith((".script", ".txt", ".chatterlang"))
    )


@registry.register_segment(name="snippet")
class Snippet(AbstractSegment[Any, Any]):
    """A segment that loads a chatterlang script from a file and compiles it, after which it
    functions as a normal segment that can be integrated into a pipeline.

    Args:
        file (str): The path to the chatterlang script file.
        runtime (RuntimeComponent, optional): The runtime component to use. Defaults to None.
    """

    def __init__(self, script_source: str):
        super().__init__()
        self.script_source = script_source
        self.script: AbstractSegment[Any, Any] | None = None

    def transform(self, items: Iterable[Any]) -> Iterator[Any]:
        if self.script is None:
            try:
                with open(self.script_source) as f:
                    script_text = f.read()
            except FileNotFoundError:
                if _looks_like_script_path(self.script_source):
                    raise
                # Otherwise treat self.script_source as inline script content,
                # but say so: a typo'd path would otherwise surface as a
                # confusing parse error.
                logger.warning(
                    "snippet: %r is not an existing file; treating it as an "
                    "inline chatterlang script",
                    self.script_source,
                )
                script_text = self.script_source
            self.script = compile(script_text, self.runtime)
        yield from self.script(items)
