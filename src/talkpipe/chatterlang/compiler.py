""" Compiler for chatterlang scripts 

These methods take either a script or a parsed script and compile it into a callable function.
For an end user, the most important method is the compile method that takes a string, but the
other methods are used internally to compile the parsed scripts.
"""

from typing import Callable, Union, Iterator
import logging
from functools import singledispatch
from talkpipe.chatterlang.parsers import script_parser, ParsedScript, ParsedLoop, ParsedPipeline, VariableName, SegmentNode, Identifier, ForkNode, ForkReference
from talkpipe.chatterlang import registry 
from talkpipe.pipe.core import Loop, Pipeline, Script, RuntimeComponent, AbstractSource
from talkpipe.pipe.fork import ForkSegment
from talkpipe.pipe import io
from talkpipe.operations.thread_ops import ThreadedQueue

logger = logging.getLogger(__name__)

class CompileError(Exception):
    """ Exception raised when a compilation error occurs in chatterlang """
    pass

class ForkAwareScript(Script):
    """A Script that handles fork startup and shutdown.
    
    This script ensures that all fork producers and consumers are registered
    before starting the forks. It does a two-phase execution:
    1. Registration phase: register all consumers and create producer generators
    2. Start forks and execute
    """
    
    def __init__(self, segments, runtime):
        super().__init__(segments)
        self.runtime = runtime
    
    def _reset_fork_segment_state(self, segment):
        """Recursively reset registration state for fork-related segments."""
        if isinstance(segment, ForkPullSource):
            segment._consumer_registered = False
            segment.consumer = None
        elif isinstance(segment, ForkPushSegment):
            segment._producer_id = None
            # Also reset state in the wrapped pipeline
            if hasattr(segment, 'wrapped_pipeline'):
                self._reset_fork_segment_state(segment.wrapped_pipeline)
        elif isinstance(segment, Pipeline):
            # Pipeline has operations - check recursively
            for op in segment.operations:
                self._reset_fork_segment_state(op)
    
    def _register_fork_consumers(self, segment):
        """Recursively find and register ForkPullSource instances."""
        if isinstance(segment, ForkPullSource):
            # Get or create the fork's ThreadedQueue
            if segment.fork_name not in self.runtime.fork_store:
                self.runtime.fork_store[segment.fork_name] = ThreadedQueue()
            fork_queue = self.runtime.fork_store[segment.fork_name]
            # Register consumer (must be before fork starts)
            if not segment._consumer_registered:
                segment.consumer = fork_queue.register_consumer()
                segment._consumer_registered = True
        elif isinstance(segment, ForkPushSegment):
            # ForkPushSegment wraps a pipeline that might contain ForkPullSource
            # (e.g., "afork -> lambda -> bfork" creates ForkPushSegment wrapping Pipeline with ForkPullSource)
            if hasattr(segment, 'wrapped_pipeline'):
                self._register_fork_consumers(segment.wrapped_pipeline)
        elif isinstance(segment, Pipeline):
            # Pipeline has operations - check ALL operations recursively
            # (not just the first one, in case ForkPullSource appears later)
            for op in segment.operations:
                self._register_fork_consumers(op)
    
    def transform(self, initial_input=None):
        # Clear fork_store to ensure fresh state for each transform() call
        # This prevents state pollution when the same script is executed multiple times
        # or when tests run in sequence
        for fork_name, fork_queue in list(self.runtime.fork_store.items()):
            if fork_queue._started:
                fork_queue.shutdown()
        self.runtime.fork_store.clear()
        
        # Reset registration state for all fork-related segments to handle multiple executions
        # This ensures each transform() call starts fresh, which is important for tests
        for seg in self.segments:
            self._reset_fork_segment_state(seg)
        
        # Phase 1: Register all consumers (they don't need input)
        # ForkPullSource might be inside Pipelines, so we need to check recursively
        for seg in self.segments:
            self._register_fork_consumers(seg)
        
        # Phase 2: Register all producers by executing segments
        # We need to create generators and register them before starting forks
        current_iter = initial_input
        
        for i, seg in enumerate(self.segments):
            if isinstance(seg, AbstractSource):
                if not isinstance(seg, ForkPullSource):
                    # Regular sources - get their generator for producer registration
                    current_iter = seg()
            else:
                if isinstance(seg, ForkPushSegment):
                    # Register producer for this fork
                    seg._register_producer(self.runtime, current_iter)
                    # Set current_iter to empty iterator for next segment
                    current_iter = iter([])
                else:
                    # Regular segments - execute to get output for next segment
                    current_iter = seg(current_iter)
        
        # Phase 3: Start all forks (all registrations should be done)
        for fork_name, fork_queue in self.runtime.fork_store.items():
            if not fork_queue._started:
                fork_queue.start()
                logger.debug(f"Started fork {fork_name}")
        
        # Phase 4: Execute script normally - consumers will feed into subsequent segments
        try:
            yield from super().transform(initial_input)
        finally:
            # Shutdown all forks after execution
            for fork_name, fork_queue in self.runtime.fork_store.items():
                fork_queue.shutdown()
                logger.debug(f"Shutdown fork {fork_name}")

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
    
    compiled_pipelines = [compile(item, runtime) for item in script.pipelines]
    logger.debug("Successfully compiled all pipelines")
    fork_aware_script = ForkAwareScript(compiled_pipelines, runtime)
    # Store reference to script in runtime for fork startup coordination
    runtime._script = fork_aware_script
    return fork_aware_script

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
    
    # Handle fork_pull: use ForkPullSource as input
    if pipeline.fork_pull is not None:
        ans = ForkPullSource(pipeline.fork_pull.name)
        ans.runtime = runtime
        logger.debug(f"Created fork pull source for {pipeline.fork_pull.name}")
    elif pipeline.input_node is not None:
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
    
    # Handle fork_push: wrap the entire pipeline in ForkPushSegment
    if pipeline.fork_push is not None:
        ans = ForkPushSegment(pipeline.fork_push.name, ans)
        ans.runtime = runtime
        logger.debug(f"Wrapped pipeline in fork push segment for {pipeline.fork_push.name}")
    
    if ans is not None:
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

class ForkPushSegment(io.AbstractSegment):
    """A segment that pushes items to a fork's ThreadedQueue.
    
    This segment wraps a pipeline and registers it as a producer
    for the specified fork. The items are consumed by the fork
    but not yielded downstream (the fork handles distribution).
    """
    
    def __init__(self, fork_name: str, wrapped_pipeline):
        super().__init__(process_metadata=True)  # Preserve metadata through forks
        self.fork_name = fork_name
        self.wrapped_pipeline = wrapped_pipeline
        self._producer_id = None

    def _set_runtime_recursive(self, component, runtime):
        """Recursively set runtime on component and its operations."""
        if hasattr(component, 'runtime') and component.runtime is None:
            component.runtime = runtime
        if isinstance(component, Pipeline):
            for op in component.operations:
                self._set_runtime_recursive(op, runtime)

    def _register_producer(self, runtime, input_iter):
        """Register this segment as a producer for its fork."""
        # Ensure wrapped pipeline and all its segments have runtime set
        self._set_runtime_recursive(self.wrapped_pipeline, runtime)
        
        # Get or create the fork's ThreadedQueue
        if self.fork_name not in runtime.fork_store:
            runtime.fork_store[self.fork_name] = ThreadedQueue()
        fork_queue = runtime.fork_store[self.fork_name]
        
        # Determine if pipeline starts with a source
        is_source = isinstance(self.wrapped_pipeline, AbstractSource)
        is_pipeline_with_source = (isinstance(self.wrapped_pipeline, Pipeline) and 
                                   len(self.wrapped_pipeline.operations) > 0 and
                                   isinstance(self.wrapped_pipeline.operations[0], AbstractSource))
        
        # Create producer generator
        if is_source:
            producer_gen = self.wrapped_pipeline()
        elif is_pipeline_with_source:
            producer_gen = self.wrapped_pipeline.transform(None)
        else:
            producer_gen = self.wrapped_pipeline.transform(input_iter)
        
        # Register producer (only once per instance)
        if self._producer_id is None:
            self._producer_id = fork_queue.register_producer(producer_gen)
            logger.debug(f"Registered producer {self._producer_id} for fork {self.fork_name}")

    def transform(self, items):
        # Producer was already registered in Phase 2, but if called directly,
        # ensure it's registered (e.g., for testing or direct usage)
        if self._producer_id is None and self.runtime:
            self._register_producer(self.runtime, items)
        
        # Don't yield anything - the fork consumers will get the items
        return iter([])

class ForkPullSource(AbstractSource):
    """A source that pulls items from a fork's ThreadedQueue.
    
    This source creates a consumer from the fork's ThreadedQueue
    and yields items from it.
    """
    
    def __init__(self, fork_name: str):
        super().__init__()
        self.fork_name = fork_name
        self.consumer = None
        self._consumer_registered = False

    def generate(self):
        # Get or create the fork's ThreadedQueue
        if self.fork_name not in self.runtime.fork_store:
            self.runtime.fork_store[self.fork_name] = ThreadedQueue()
        
        fork_queue = self.runtime.fork_store[self.fork_name]
        
        # Register this as a consumer (only once, and only before fork starts)
        # If already registered (e.g., in Phase 1), use the existing consumer
        if not self._consumer_registered:
            if fork_queue._started:
                # Fork already started - this shouldn't happen if registration worked correctly
                # But if it does, we can't register now, so raise an error
                raise RuntimeError(f"Cannot register consumer for fork {self.fork_name} after fork has started. "
                                 f"This usually means the consumer wasn't registered in Phase 1.")
            self.consumer = fork_queue.register_consumer()
            self._consumer_registered = True
        elif self.consumer is None:
            # Consumer should have been registered in Phase 1
            raise RuntimeError(f"Consumer for fork {self.fork_name} was not properly registered")
        
        # Yield items from the consumer - metadata should be preserved since it's in the queue
        # We explicitly yield all items including metadata to ensure they flow through
        for item in self.consumer:
            yield item

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