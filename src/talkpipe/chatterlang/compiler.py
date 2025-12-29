""" Compiler for chatterlang scripts 

These methods take either a script or a parsed script and compile it into a callable function.
For an end user, the most important method is the compile method that takes a string, but the
other methods are used internally to compile the parsed scripts.
"""

from typing import Callable, Union, Iterator, Any, Dict, List, Optional
import logging
from functools import singledispatch
import networkx as nx
from talkpipe.chatterlang.parsers import script_parser, ParsedScript, ParsedLoop, ParsedPipeline, VariableName, SegmentNode, Identifier, ForkNode
from talkpipe.chatterlang import registry 
from talkpipe.pipe.core import Loop, Pipeline, Script, RuntimeComponent, AbstractSource, AbstractSegment
from talkpipe.pipe.fork import ForkSegment
from talkpipe.pipe import io
from talkpipe.operations.thread_ops import ThreadedQueue

logger = logging.getLogger(__name__)

class CompileError(Exception):
    """ Exception raised when a compilation error occurs in chatterlang """
    pass

@singledispatch
def compile(script: ParsedScript, runtime: RuntimeComponent = None) -> Callable:
    """ Compile a parsed script into a callable function 
    
    Args:
        script (ParsedScript): The script to compile
        v_store (VariableStore): The variable store to use
    """
    logger.debug(f"Compiling script with {len(script.pipelines)} pipelines")
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
    fork_segments: Dict[str, ArrowForkSegment] = {}
    
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
    compiled_pipelines_list: List[Any] = []
    pipeline_index_map: Dict[int, int] = {}  # Maps original index to compiled index
    for idx, pipeline in enumerate(script.pipelines):
        if isinstance(pipeline, ParsedPipeline):
            # Create a copy of the pipeline without fork_source/fork_target for compilation
            # We'll handle fork connections separately
            pipeline_copy = ParsedPipeline(
                pipeline.input_node,
                pipeline.transforms,
                fork_target=None,
                fork_source=None
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
    consumer_wrappers: Dict[int, Any] = {}  # Maps pipeline index to wrapper
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
                        class ForkConsumerWrapper(AbstractSegment):
                            def __init__(self, consumer_iter, downstream_pipeline):
                                super().__init__()
                                self.consumer_iter = consumer_iter
                                self.downstream_pipeline = downstream_pipeline
                            
                            def transform(self, input_iter: Iterator[Any]) -> Iterator[Any]:
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
                has_incoming_fork = any(not pred.startswith("pipeline_") for pred in graph.predecessors(pipeline_node))
                has_outgoing_fork = any(not succ.startswith("pipeline_") for succ in graph.successors(pipeline_node))
                if has_incoming_fork and has_outgoing_fork and pipeline_idx in consumer_wrappers:
                    wrapper = consumer_wrappers[pipeline_idx]
                    # Find the target fork (outgoing edge to a fork)
                    for fork_name in graph.successors(pipeline_node):
                        if not fork_name.startswith("pipeline_"):  # It's a fork node
                            target_fork = fork_segments[fork_name]
                            # Register a producer that executes the wrapper
                            # This will run in a background thread, so it can block waiting for source fork
                            # We create a generator function that will be called in start()
                            def make_producer(w):
                                def producer():
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
    final_pipelines = []
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

def _resolve_value(value, runtime):
    """Resolve a single parameter value, handling constants and arrays recursively."""
    if isinstance(value, Identifier):
        return runtime.const_store[value.name]
    elif isinstance(value, list):
        return [_resolve_value(elem, runtime) for elem in value]
    else:
        return value

def _resolve_params(params, runtime):
    """ Resolve the parameters for a segment """
    return {k: _resolve_value(params[k], runtime) for k in params}

@compile.register(ParsedPipeline)
def _(pipeline: ParsedPipeline, runtime: RuntimeComponent) -> Pipeline:
    """ Compile a parsed pipeline into a Pipeline object 
    
    Args:
        pipeline (ParsedPipeline): The pipeline to compile
        v_store (VariableStore): The variable store to use
    """
    logger.debug("Starting pipeline compilation")
    ans = None
    if pipeline.input_node is not None:
        logger.debug(f"Processing input node of type {type(pipeline.input_node.source)}")
        if isinstance(pipeline.input_node.source, str):
            ans =  io.echo(pipeline.input_node.source, delimiter=None)
            logger.debug("Created echo input with string source")
        elif pipeline.input_node.is_variable:
            ans = VariableSource(pipeline.input_node.source.name)
            logger.debug(f"Created variable source with name {pipeline.input_node.source.name}")
        else:
            try:
                ans = registry.input_registry.get(pipeline.input_node.source.name)(**_resolve_params(pipeline.input_node.params, runtime=runtime))
            except KeyError:
                raise CompileError(f"Source '{pipeline.input_node.source.name}' not found")
            logger.debug(f"Created registered input {pipeline.input_node.source.name}")
        ans.runtime = runtime

    logger.debug(f"Processing {len(pipeline.transforms)} transforms")
    for transform in pipeline.transforms:
        if isinstance(transform, VariableName):
            next_transform = VariableSetSegment(transform.name)
            logger.debug(f"Created variable set segment for {transform.name}")
        elif isinstance(transform, SegmentNode):
            try:
                next_transform = registry.segment_registry.get(transform.operation.name)(**_resolve_params(transform.params, runtime=runtime))
            except KeyError:
                raise CompileError(f"Segment '{transform.operation.name}' not found")
            logger.debug(f"Created segment {transform.operation.name}")
        elif isinstance(transform, ForkNode):
            next_transform = compile(transform, runtime)
        else:
            logger.error(f"Unknown segment type: {transform}")
            raise ValueError(f"Unknown segment type: {transform}")
        next_transform.runtime = runtime

        if ans is None:
            ans = next_transform
        else:
            ans |= next_transform
    ans.runtime = runtime
    logger.debug("Completed pipeline compilation")
    return ans

@compile.register(ForkNode)
def _(fork: ForkNode, runtime: RuntimeComponent) -> ForkSegment:
    """ Compile a fork node into a Pipeline object 
    
    Args:
        fork (ForkNode): The fork node to compile
        v_store (VariableStore): The variable store to use
    """
    logger.debug("Starting fork compilation")
    pipelines = [compile(pipeline, runtime) for pipeline in fork.branches]
    logger.debug("Completed fork compilation")
    return ForkSegment(pipelines)

@compile.register(ParsedLoop)
def _(loop: ParsedLoop, runtime: RuntimeComponent) -> Loop:
    """ Compile a parsed loop into a Loop object 
    
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
        elif char == '#' and not in_quotes:
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
def _(script: str, runtime: RuntimeComponent = None) -> Callable:
    """ Compile a script into a callable function 
    
    Args:
        script (str): The script to compile
        v_store (VariableStore): The variable store to use
    """
    preprocessed_script = remove_comments(script)
    return compile(script_parser.parse(preprocessed_script), runtime)

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
        self.producer_pipelines: List[Any] = []
        self.consumer_pipelines: List[Any] = []
        self._started = False
    
    def register_producer(self, pipeline):
        """Register a pipeline as a producer to this fork.
        
        The pipeline will be executed using __call__() to ensure
        metadata is handled correctly. All items will be broadcast
        to all registered consumers.
        """
        if self._started:
            raise RuntimeError(f"Cannot register producers after fork {self.fork_name} has started")
        self.producer_pipelines.append(pipeline)
    
    def register_consumer(self, pipeline):
        """Register a pipeline as a consumer from this fork.
        
        Returns a consumer iterator that yields items from the queue.
        The consumer will receive all items from all producers
        (broadcast-style distribution).
        """
        if self._started:
            raise RuntimeError(f"Cannot register consumers after fork {self.fork_name} has started")
        self.consumer_pipelines.append(pipeline)
        return self.queue_system.register_consumer()
    
    def start(self):
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

class VariableSource(AbstractSource):
    """A source that gets a variable from the variable store and returns its
    contents item by item. 
    
    Is used in chatterlang via the INPUT FROM @variable_name syntax.
    """
    
    def __init__(self, variable_name: str):
        super().__init__()
        self.variable_name = variable_name

    def generate(self):
        yield from self.runtime.variable_store[self.variable_name]

class VariableSetSegment(io.AbstractSegment):
    """A segment that sets a variable in the variable store.
    
    It trains its input stream, stores the result as a list and then
    emits each item one by one.  It is not used directly but is
    by the @variable_name syntax in chatterlang. 
    """
    
    def __init__(self, variable_name: str):
        super().__init__()
        self.variable_name = variable_name

    def transform(self, items):
        list_of_items = list(items)
        self.runtime.variable_store[self.variable_name] = list_of_items
        yield from list_of_items

@registry.register_segment(name="accum")
class Accum(io.AbstractSegment):
    """Accumulates items from the input stream both in an internal buffer and in the specified variable.  
    This is useful for accumulating the results of running the pipeline multiple times.     
    
    Args:
        variable (Union[VariableName, str], optional): The name of the variable to store the accumulated data in. Defaults to None.
        reset (bool, optional): Whether to reset the accumulator each time the segment is run. Defaults to True."""
    
    def __init__(self, variable: Union[VariableName, str] = None, reset: bool = True):
        super().__init__()
        if variable is None:
            self.variable_name = None
        else:
            self.variable_name = variable if isinstance(variable, str) else variable.name
        self.reset = reset
        self.accumulator = []

    def transform(self, items):
        if self.reset:
            self.accumulator = []

        if self.variable_name and self.variable_name not in self.runtime.variable_store:
            self.runtime.variable_store[self.variable_name] = []

        for item in self.accumulator:
            yield item
            
        for item in items:
            self.accumulator.append(item)
            if self.variable_name:
                self.runtime.variable_store[self.variable_name].append(item)
            yield item


@registry.register_segment(name="snippet")
class Snippet(io.AbstractSegment):
    """A segment that loads a chatterlang script from a file and compiles it, after which it
    functions as a normal segment that can be integrated into a pipeline.

    Args:
        file (str): The path to the chatterlang script file.
        runtime (RuntimeComponent, optional): The runtime component to use. Defaults to None.
    """    

    def __init__(self, script_source: str):
        super().__init__()
        self.script_source = script_source
        self.script = None

    def transform(self, items):
        if self.script is None:
            try:
                with open(self.script_source, "r") as f:
                    script_text = f.read()
            except FileNotFoundError:
                # If file doesn't exist, treat self.script_source as the script content
                script_text = self.script_source
            self.script = compile(script_text, self.runtime)
        yield from self.script(items)