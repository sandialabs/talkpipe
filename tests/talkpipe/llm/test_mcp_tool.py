"""Tests for the MCP tool registration function."""

import pytest
from talkpipe import compile, register_talkpipe_tool
from talkpipe.pipe.core import Pipeline, AbstractSource, AbstractSegment


class MockFastMCP:
    """Mock FastMCP instance for testing."""
    def __init__(self):
        self.tools = {}
    
    def add_tool(self, func):
        """Register a tool function."""
        self.tools[func.__name__] = func


def test_register_talkpipe_tool_with_script_string():
    """Test register_talkpipe_tool with a script string."""
    mcp = MockFastMCP()
    
    register_talkpipe_tool(
        mcp,
        "| lambda[expression='item*2']",
        input_param=("item", int, "Number to double"),
        name="double_number",
        description="Doubles a number"
    )
    
    # Check tool was registered
    assert "double_number" in mcp.tools
    tool_func = mcp.tools["double_number"]
    
    # Test the function works
    result = tool_func(5)
    assert result == 10
    
    result = tool_func(10)
    assert result == 20
    
    # Check metadata
    assert tool_func.__name__ == "double_number"
    assert tool_func.__doc__ == "Doubles a number"
    assert 'item' in tool_func.__annotations__
    assert tool_func.__annotations__['item'] == int


def test_register_talkpipe_tool_with_compiled_pipeline():
    """Test register_talkpipe_tool with a compiled pipeline."""
    mcp = MockFastMCP()
    pipeline = compile("| lambda[expression='item*2']")
    
    register_talkpipe_tool(
        mcp,
        pipeline,
        input_param=("item", int, "The number to double"),
        name="double_number",
        description="Doubles a number"
    )
    
    tool_func = mcp.tools["double_number"]
    result = tool_func(5)
    assert result == 10


def test_register_talkpipe_tool_with_source_pipeline():
    """Test register_talkpipe_tool with a source pipeline (no input needed)."""
    mcp = MockFastMCP()
    pipeline = compile("INPUT FROM echo[data='Hello, World!']")
    
    register_talkpipe_tool(
        mcp,
        pipeline,
        name="greet",
        description="Returns a greeting"
    )
    
    tool_func = mcp.tools["greet"]
    result = tool_func()
    # Result might be a list, so handle both cases
    if isinstance(result, list):
        assert "Hello" in result[0] or result[0] == "Hello, World!"
    else:
        assert "Hello" in str(result) or result == "Hello, World!"
    
    # Check metadata
    assert tool_func.__name__ == "greet"
    assert tool_func.__doc__ == "Returns a greeting"


def test_register_talkpipe_tool_with_multiple_inputs():
    """Test register_talkpipe_tool with multiple input items."""
    mcp = MockFastMCP()
    
    register_talkpipe_tool(
        mcp,
        "| lambda[expression='item*2']",
        input_param=("items", list, "List of numbers to double"),
        name="double_numbers"
    )
    
    tool_func = mcp.tools["double_numbers"]
    result = tool_func([1, 2, 3, 4, 5])
    assert result == [2, 4, 6, 8, 10]


def test_register_talkpipe_tool_with_string_operations():
    """Test register_talkpipe_tool with string operations."""
    mcp = MockFastMCP()
    
    register_talkpipe_tool(
        mcp,
        "| lambda[expression='item.upper()']",
        input_param=("text", str, "Text to uppercase"),
        name="uppercase_text",
        description="Converts text to uppercase"
    )
    
    tool_func = mcp.tools["uppercase_text"]
    result = tool_func("hello")
    assert result == "HELLO"


def test_register_talkpipe_tool_with_complex_pipeline():
    """Test register_talkpipe_tool with a more complex pipeline."""
    mcp = MockFastMCP()
    
    register_talkpipe_tool(
        mcp,
        "| lambda[expression='item*2'] | lambda[expression='item+1']",
        input_param=("item", int, "The number to process"),
        name="process_number",
        description="Doubles and adds one to a number"
    )
    
    tool_func = mcp.tools["process_number"]
    result = tool_func(5)
    assert result == 11  # (5 * 2) + 1


def test_register_talkpipe_tool_annotations():
    """Test that register_talkpipe_tool creates correct type annotations."""
    mcp = MockFastMCP()
    
    register_talkpipe_tool(
        mcp,
        "| lambda[expression='item*2']",
        input_param=("item", int, "The number"),
        name="double_number"
    )
    
    tool_func = mcp.tools["double_number"]
    # Check annotations come from input_param
    assert 'item' in tool_func.__annotations__
    assert tool_func.__annotations__['item'] == int
    assert 'return' in tool_func.__annotations__


def test_register_talkpipe_tool_name_and_description():
    """Test that register_talkpipe_tool respects name and description parameters."""
    mcp = MockFastMCP()
    
    register_talkpipe_tool(
        mcp,
        "| lambda[expression='item*2']",
        input_param=("item", int, "The number"),
        name="custom_double",
        description="Custom description for doubling"
    )
    
    tool_func = mcp.tools["custom_double"]
    assert tool_func.__name__ == "custom_double"
    assert tool_func.__doc__ == "Custom description for doubling"


def test_register_talkpipe_tool_default_name():
    """Test that register_talkpipe_tool uses default name when not provided."""
    mcp = MockFastMCP()
    
    register_talkpipe_tool(
        mcp,
        "| lambda[expression='item*2']",
        input_param=("item", int, "The number")
    )
    
    tool_func = mcp.tools["tool"]
    assert tool_func.__name__ == "tool"
    assert "Tool created from TalkPipe pipeline" in tool_func.__doc__


def test_register_talkpipe_tool_segment_requires_input_param():
    """Test that segment pipelines require input_param."""
    mcp = MockFastMCP()
    
    with pytest.raises(ValueError, match="input_param is required"):
        register_talkpipe_tool(
            mcp,
            "| lambda[expression='item*2']"
        )


def test_register_talkpipe_tool_empty_pipeline():
    """Test register_talkpipe_tool with empty input (should handle gracefully)."""
    mcp = MockFastMCP()
    
    register_talkpipe_tool(
        mcp,
        "| lambda[expression='item*2']",
        input_param=("item", int, "The number"),
        name="double_number"
    )
    
    tool_func = mcp.tools["double_number"]
    # Should work normally
    result = tool_func(0)
    assert result == 0


def test_register_talkpipe_tool_invalid_pipeline_type():
    """Test that register_talkpipe_tool raises error for invalid pipeline type."""
    mcp = MockFastMCP()
    
    with pytest.raises(ValueError, match="Invalid pipeline_or_script type"):
        register_talkpipe_tool(mcp, 12345)  # Invalid type
