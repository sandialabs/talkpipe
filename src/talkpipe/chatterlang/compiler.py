""" Compiler for chatterlang scripts 

These methods take either a script or a parsed script and compile it into a callable function.
For an end user, the most important method is the compile method that takes a string, but the
other methods are used internally to compile the parsed scripts.
"""

from typing import Callable, Union
import logging
from functools import singledispatch
from talkpipe.chatterlang.parsers import script_parser, ParsedScript, ParsedLoop, ParsedPipeline, VariableName, SegmentNode, Identifier, ForkNode
from talkpipe.chatterlang import registry 
from talkpipe.pipe.core import Loop, Pipeline, Script, RuntimeComponent
from talkpipe.pipe.fork import ForkSegment
from talkpipe.pipe import io

logger = logging.getLogger(__name__)

@singledispatch
def compile(script: ParsedScript, runtime: RuntimeComponent = None) -> Callable:
    """ Compile a parsed script into a callable function 
    
    Args:
        script (ParsedScript): The script to compile
        v_store (VariableStore): The variable store to use
    """
    logger.debug(f"Compiling script with {len(script.pipelines)} pipelines")
    runtime = runtime or RuntimeComponent()
    runtime.const_store = script.constants.copy()
    logger.debug(f"Initialized runtime with {len(script.constants)} constants")
    
    compiled_pipelines = [compile(item, runtime) for item in script.pipelines]
    logger.debug("Successfully compiled all pipelines")
    return Script(compiled_pipelines)

def _resolve_params(params, runtime):
    """ Resolve the parameters for a segment """
    ans = {k: runtime.const_store[params[k].name] if isinstance(params[k], Identifier) else params[k] for k in params}
    return ans

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
            ans = registry.input_registry.get(pipeline.input_node.source.name)(**_resolve_params(pipeline.input_node.params, runtime=runtime))
            logger.debug(f"Created registered input {pipeline.input_node.source.name}")
        ans.runtime = runtime

    logger.debug(f"Processing {len(pipeline.transforms)} transforms")
    for transform in pipeline.transforms:
        if isinstance(transform, VariableName):
            next_transform = VariableSetSegment(transform.name)
            logger.debug(f"Created variable set segment for {transform.name}")
        elif isinstance(transform, SegmentNode):
            next_transform = registry.segment_registry.get(transform.operation.name)(**_resolve_params(transform.params, runtime=runtime))
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

class VariableSource(io.AbstractSource):
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