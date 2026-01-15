"""MCP (Model Context Protocol) tool integration for TalkPipe pipelines.

This module provides a function to register TalkPipe pipelines as MCP tools
with FastMCP servers, and a ChatterLang segment for registering tools within scripts.
"""

from typing import Any, Optional, Union, Iterable, Iterator, Annotated
from inspect import Signature, Parameter
import logging

from talkpipe.chatterlang.compiler import compile as compile_pipeline
from talkpipe.pipe.core import Pipeline, Script, AbstractSource, AbstractSegment
from talkpipe.chatterlang.registry import register_segment

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


# Note: registerTool segment is deprecated. Use TOOL syntax in ChatterLang scripts instead.
# This class is kept for backward compatibility but is no longer registered as a segment.
class RegisterToolSegment(AbstractSegment):
    """Register a TalkPipe pipeline as an MCP tool within a ChatterLang script.
    
    This segment registers a tool with a FastMCP instance. If a FastMCP instance
    is already stored in runtime.const_store under the key "mcp" or "_mcp", it will
    be used. Otherwise, a new FastMCP instance will be created and stored for
    future use.
    
    After registration, this segment passes through all input items unchanged,
    making it safe to use in the middle of a pipeline.
    
    Args:
        pipeline: ChatterLang pipeline string to register as a tool
        name: Name of the tool
        description: Optional description of the tool
        param_name: Parameter name for segment pipelines (required if pipeline needs input)
        param_type: Parameter type for segment pipelines (e.g., "int", "str", "list")
        param_desc: Parameter description for segment pipelines
        input_param: Alternative way to specify input parameter as "name:type:description"
        mcp_key: Key in runtime.const_store where the FastMCP instance is stored/created (default: "mcp")
    
    Examples:
        ```chatterlang
        // Register a tool that doubles a number
        // FastMCP instance will be created automatically if not present
        | registerTool[
            pipeline="| lambda[expression='item*2']",
            name="double_number",
            param_name="item",
            param_type="int",
            param_desc="Number to double"
        ]
        
        // Or using input_param shorthand
        | registerTool[
            pipeline="| lambda[expression='item*2']",
            name="double_number",
            input_param="item:int:Number to double"
        ]
        ```
    """
    
    def __init__(
        self,
        pipeline: Annotated[str, "ChatterLang pipeline string to register as a tool"],
        name: Annotated[str, "Name of the tool"],
        description: Annotated[Optional[str], "Description of the tool"] = None,
        param_name: Annotated[Optional[str], "Parameter name for segment pipelines"] = None,
        param_type: Annotated[Optional[str], "Parameter type (e.g., 'int', 'str', 'list')"] = None,
        param_desc: Annotated[Optional[str], "Parameter description"] = None,
        input_param: Annotated[Optional[str], "Input parameter as 'name:type:description'"] = None,
        mcp_key: Annotated[str, "Key in runtime.const_store for FastMCP instance"] = "mcp"
    ):
        super().__init__()
        self.pipeline_str = pipeline
        self.name = name
        self.description = description
        self.mcp_key = mcp_key
        
        # Parse input_param if provided, otherwise use individual params
        if input_param:
            parts = input_param.split(":", 2)
            if len(parts) >= 2:
                self.param_name = parts[0]
                type_str = parts[1]
                self.param_desc = parts[2] if len(parts) > 2 else ""
            else:
                raise ValueError(f"input_param must be in format 'name:type:description', got: {input_param}")
        else:
            self.param_name = param_name
            self.param_desc = param_desc or ""
            type_str = param_type or "str"
        
        # Convert type string to Python type
        type_mapping = {
            "int": int,
            "str": str,
            "float": float,
            "bool": bool,
            "list": list,
            "dict": dict,
        }
        self.param_type = type_mapping.get(type_str.lower(), str)
        
        # Determine if input_param is needed
        self.input_param = None
        if self.param_name:
            self.input_param = (self.param_name, self.param_type, self.param_desc)
    
    def transform(self, input_iter: Iterable[Any]) -> Iterator[Any]:
        """Register the tool and pass through input items."""
        # Get MCP instance from runtime, or create a new one if not found
        if self.runtime is None:
            raise ValueError(
                "Runtime component not available. registerTool segment requires "
                "a runtime component."
            )
        
        mcp = self.runtime.const_store.get(self.mcp_key) or self.runtime.const_store.get("_mcp")
        if mcp is None:
            # Create a new FastMCP instance if one doesn't exist
            try:
                from fastmcp import FastMCP
                mcp = FastMCP("TalkPipe Tools")
                # Store it in const_store for future use
                self.runtime.const_store[self.mcp_key] = mcp
                logger.debug(f"Created new FastMCP instance and stored in runtime.const_store['{self.mcp_key}']")
            except ImportError:
                raise ImportError(
                    "FastMCP is not installed. Please install it with: pip install fastmcp"
                )
        
        # Register the tool
        register_talkpipe_tool(
            mcp,
            self.pipeline_str,
            input_param=self.input_param,
            name=self.name,
            description=self.description
        )
        
        logger.debug(f"Registered tool '{self.name}' with FastMCP instance")
        
        # Pass through all input items unchanged
        yield from input_iter
