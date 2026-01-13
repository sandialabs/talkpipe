"""MCP (Model Context Protocol) tool integration for TalkPipe pipelines.

This module provides a function to register TalkPipe pipelines as MCP tools
with FastMCP servers.
"""

from typing import Any, Optional, Union
from inspect import Signature, Parameter
import logging

from talkpipe.chatterlang.compiler import compile as compile_pipeline
from talkpipe.pipe.core import Pipeline, Script, AbstractSource, AbstractSegment

logger = logging.getLogger(__name__)


def register_talkpipe_tool(
    mcp: Any,  # FastMCP instance - using Any to avoid import dependency
    pipeline_or_script: Union[str, Pipeline, AbstractSegment],
    *,
    input_param: Optional[tuple[str, type, str]] = None,
    name: Optional[str] = None,
    description: Optional[str] = None
) -> None:
    """Register a TalkPipe pipeline as an MCP tool with FastMCP.
    
    This function compiles the pipeline (if needed), creates a wrapper function
    with the appropriate signature, and registers it with the FastMCP instance.
    
    Args:
        mcp: FastMCP instance to register the tool with
        pipeline_or_script: A compiled pipeline, pipeline string, or AbstractSegment.
        input_param: Optional tuple of (param_name, param_type, param_description) for single input.
                    Required for segment pipelines (those that need input). Not needed for source pipelines.
        name: Optional name for the tool. If not provided, defaults to "tool".
        description: Optional description for the tool. If not provided, uses a default message.
    
    Examples:
        ```python
        from fastmcp import FastMCP
        from talkpipe import compile, register_talkpipe_tool
        
        mcp = FastMCP("Demo")
        
        # Register a segment pipeline (needs input)
        register_talkpipe_tool(
            mcp,
            "| lambda[expression='item*2']",
            input_param=("item", int, "Number to double"),
            name="double_number",
            description="Doubles a number"
        )
        
        # Register a source pipeline (no input needed)
        pipeline = compile("INPUT FROM echo[data='Hello, World!']")
        register_talkpipe_tool(
            mcp,
            pipeline,
            name="greet",
            description="Returns a greeting"
        )
        
        # Start the server
        mcp.run()
        ```
    """
    # Compile pipeline if string is provided
    if isinstance(pipeline_or_script, str):
        pipeline = compile_pipeline(pipeline_or_script)
    elif isinstance(pipeline_or_script, (Pipeline, AbstractSegment)):
        pipeline = pipeline_or_script
    else:
        raise ValueError(f"Invalid pipeline_or_script type: {type(pipeline_or_script)}. Expected str, Pipeline, or AbstractSegment.")
    
    # Determine if pipeline is a source (no input) or segment (needs input)
    is_source = isinstance(pipeline, AbstractSource) or (
        isinstance(pipeline, Pipeline) and 
        len(pipeline.operations) > 0 and 
        isinstance(pipeline.operations[0], AbstractSource)
    ) or (
        isinstance(pipeline, Script) and 
        len(pipeline.segments) > 0 and 
        isinstance(pipeline.segments[0], AbstractSource)
    )
    
    # Create wrapper function
    if is_source:
        # Pipeline is a source - no input needed
        def wrapper() -> Any:
            """Execute the pipeline as a source."""
            result = list(pipeline())
            # Return single item if only one result, otherwise return list
            if len(result) == 1:
                return result[0]
            return result
        
        wrapper.__name__ = name or "tool"
        wrapper.__doc__ = description or "Tool created from TalkPipe pipeline."
        wrapper.__annotations__ = {'return': Any}
        
    else:
        # Pipeline is a segment - needs input
        if input_param is None:
            raise ValueError(
                "input_param is required for segment pipelines (pipelines that need input). "
                "Provide a tuple of (param_name, param_type, param_description)."
            )
        
        param_name, param_type, param_desc = input_param
        
        # Create signature with the input parameter
        sig_params = [
            Parameter(param_name, Parameter.POSITIONAL_OR_KEYWORD, annotation=param_type)
        ]
        new_sig = Signature(sig_params)
        
        def wrapper(*args, **kwargs) -> Any:
            """Execute the pipeline with input parameters."""
            # Bind arguments to the signature
            bound = new_sig.bind(*args, **kwargs)
            bound.apply_defaults()
            
            # Get the input value
            input_value = bound.arguments[param_name]
            
            # Convert single value to iterable if needed
            if not isinstance(input_value, (list, tuple)):
                input_iter = [input_value]
            else:
                input_iter = input_value
            
            # Execute pipeline
            result = list(pipeline(input_iter))
            
            # Return single item if only one result, otherwise return list
            if len(result) == 1:
                return result[0]
            return result
        
        # Set up annotations and signature
        wrapper.__name__ = name or "tool"
        wrapper.__doc__ = description or f"Tool created from TalkPipe pipeline. Parameter: {param_desc}"
        wrapper.__annotations__ = {param_name: param_type, 'return': Any}
        wrapper.__signature__ = new_sig
    
    # Register with FastMCP
    # FastMCP's add_tool() expects a Tool object, not a plain function
    # Use the recommended approach: Tool.from_function() then add_tool()
    try:
        # Try the recommended approach first (newer FastMCP versions)
        from fastmcp.tools import Tool
        tool = Tool.from_function(
            fn=wrapper,
            name=wrapper.__name__,
            description=wrapper.__doc__ or "Tool created from TalkPipe pipeline."
        )
        mcp.add_tool(tool)
    except (ImportError, AttributeError):
        # Fallback to deprecated add_tool_from_fn (older FastMCP versions)
        if hasattr(mcp, '_tool_manager') and hasattr(mcp._tool_manager, 'add_tool_from_fn'):
            mcp._tool_manager.add_tool_from_fn(
                fn=wrapper,
                name=wrapper.__name__,
                description=wrapper.__doc__ or "Tool created from TalkPipe pipeline."
            )
        elif hasattr(mcp, 'tool'):
            # Fallback: use the @mcp.tool decorator pattern by calling it as a function
            # This mimics: @mcp.tool(name=..., description=...)
            mcp.tool(name=wrapper.__name__, description=wrapper.__doc__ or "Tool created from TalkPipe pipeline.")(wrapper)
        else:
            raise ValueError(
                "FastMCP instance does not support tool registration. "
                "Ensure you're using a compatible version of FastMCP. "
                "Expected either Tool.from_function() or _tool_manager.add_tool_from_fn() support."
            )
