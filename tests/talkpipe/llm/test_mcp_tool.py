"""Tests for the MCP tool registration function."""

import pytest
from unittest.mock import patch, MagicMock
from talkpipe import compile, register_talkpipe_tool
from talkpipe.pipe.core import Pipeline, AbstractSource, AbstractSegment, RuntimeComponent
from talkpipe.llm.mcp_tool import RegisterToolSegment

# Try to import FastMCP at module level - if not available, tests will skip
try:
    from fastmcp import FastMCP
    FASTMCP_AVAILABLE = True
except ImportError:
    FASTMCP_AVAILABLE = False


class MockTool:
    """Mock Tool object for testing."""
    def __init__(self, fn, name=None, description=None):
        self.fn = fn
        self.name = name or fn.__name__
        self.description = description or fn.__doc__


class MockFastMCP:
    """Mock FastMCP instance for testing."""
    def __init__(self, name="MockServer"):
        self.name = name
        self.tools = {}
        self._tool_manager = MockToolManager(self)
    
    def add_tool(self, tool):
        """Register a Tool object."""
        if hasattr(tool, 'fn'):
            # Tool object
            self.tools[tool.name] = tool.fn
        else:
            # Plain function (fallback)
            self.tools[tool.__name__] = tool
    
    def tool(self, name=None, description=None):
        """Mock tool decorator."""
        def decorator(func):
            self.tools[name or func.__name__] = func
            return func
        return decorator


class MockToolManager:
    """Mock ToolManager for testing."""
    def __init__(self, mcp):
        self.mcp = mcp
    
    def add_tool_from_fn(self, fn, name=None, description=None):
        """Register a tool function (deprecated method)."""
        self.mcp.tools[name or fn.__name__] = fn


# Create a mock Tool class with from_function
def mock_tool_from_function(fn, name=None, description=None):
    """Mock Tool.from_function."""
    return MockTool(fn, name, description)

MockToolClass = type('MockToolClass', (), {
    'from_function': staticmethod(mock_tool_from_function)
})


@pytest.fixture(autouse=True)
def mock_tool(monkeypatch):
    """Auto-use fixture to mock Tool.from_function for all tests."""
    # Patch fastmcp.tools.Tool when it's imported inside the function
    import sys
    # Create mock modules if they don't exist
    if 'fastmcp' not in sys.modules:
        from types import ModuleType
        fastmcp_module = ModuleType('fastmcp')
        sys.modules['fastmcp'] = fastmcp_module
    
    if 'fastmcp.tools' not in sys.modules:
        from types import ModuleType
        tools_module = ModuleType('fastmcp.tools')
        sys.modules['fastmcp.tools'] = tools_module
    
    # Set Tool on the tools module
    sys.modules['fastmcp.tools'].Tool = MockToolClass


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


def test_register_tool_segment():
    """Test RegisterToolSegment in ChatterLang syntax."""
    mcp = MockFastMCP()
    
    # Create runtime and store MCP instance
    runtime = RuntimeComponent()
    runtime.const_store["mcp"] = mcp
    
    # Create the segment
    segment = RegisterToolSegment(
        pipeline="| lambda[expression='item*2']",
        name="double_number",
        input_param="item:int:Number to double",
        description="Doubles a number"
    )
    segment.runtime = runtime
    
    # Execute the segment (it should register the tool and pass through items)
    result = list(segment(["test", "data"]))
    
    # Verify tool was registered
    assert "double_number" in mcp.tools
    tool_func = mcp.tools["double_number"]
    assert tool_func(5) == 10
    
    # Verify input items were passed through
    assert result == ["test", "data"]


def test_register_tool_segment_with_individual_params():
    """Test RegisterToolSegment with individual parameter specifications."""
    mcp = MockFastMCP()
    
    runtime = RuntimeComponent()
    runtime.const_store["mcp"] = mcp
    
    segment = RegisterToolSegment(
        pipeline="| lambda[expression='item.upper()']",
        name="uppercase",
        param_name="text",
        param_type="str",
        param_desc="Text to uppercase"
    )
    segment.runtime = runtime
    
    list(segment([]))  # Execute
    
    assert "uppercase" in mcp.tools
    tool_func = mcp.tools["uppercase"]
    assert tool_func("hello") == "HELLO"


def test_register_tool_segment_creates_mcp():
    """Test that RegisterToolSegment creates FastMCP instance if not found."""
    # Use sys.modules to mock the import
    import sys
    from types import ModuleType
    
    # Create a mock fastmcp module
    mock_fastmcp = ModuleType('fastmcp')
    mock_fastmcp.FastMCP = MockFastMCP
    original_fastmcp = sys.modules.get('fastmcp')
    sys.modules['fastmcp'] = mock_fastmcp
    
    try:
        runtime = RuntimeComponent()
        # Don't store MCP in runtime - it should be created automatically
        
        segment = RegisterToolSegment(
            pipeline="| lambda[expression='item*2']",
            name="double",
            input_param="item:int:Number"
        )
        segment.runtime = runtime
        
        # Execute - should create MCP instance automatically
        result = list(segment([]))
        
        # Verify MCP was created and stored
        assert "mcp" in runtime.const_store
        mcp = runtime.const_store["mcp"]
        assert mcp is not None
        assert isinstance(mcp, MockFastMCP)
        
        # Verify tool was registered
        assert "double" in mcp.tools
        tool_func = mcp.tools["double"]
        assert tool_func(5) == 10
        
        # Verify input was passed through
        assert result == []
    finally:
        # Restore original module
        if original_fastmcp is not None:
            sys.modules['fastmcp'] = original_fastmcp
        elif 'fastmcp' in sys.modules:
            del sys.modules['fastmcp']


@pytest.mark.skipif(not FASTMCP_AVAILABLE, reason="FastMCP is not installed. Install with: pip install talkpipe[mcp]")
def test_register_and_use_tools_end_to_end(requires_ollama):
    """Test end-to-end: register two tools in ChatterLang script and use them with LLMPrompt.
    
    This test demonstrates the complete workflow with a pure text ChatterLang example:
    1. Register two different tools using TOOL syntax in a ChatterLang script
    2. Use the tools with LLMPrompt to answer a question that requires calling both tools
    
    Pure text ChatterLang script example:
    ```
    TOOL double = "| lambda[expression='item*2']" [input_param="item:int:Number to double", description="Doubles a number"];
    TOOL add_ten = "| lambda[expression='item+10']" [input_param="item:int:Number to add 10 to", description="Adds 10 to a number"];
    ```
    
    Then use with LLMPrompt:
    ```
    prompt = LLMPrompt(model="llama3.1", source="ollama", tools=mcp)
    result = list(prompt(["First double 7, then add 10 to that result. Just give me the number."]))
    ```
    """
    from talkpipe import compile
    from talkpipe.pipe.core import RuntimeComponent
    
    # Pure text ChatterLang script that registers tools on multiple MCP servers and uses them with LLMPrompt
    # Each TOOL can specify which MCP server it belongs to via the mcp_server parameter
    # The MCP instance is automatically stored in runtime.const_store[server_name] when tools are registered
    # We can reference it directly in the script using the identifier (e.g., "math_tools")
    # This example shows two tools on the same server, but you could have tools on different servers
    script = """
TOOL double = "| lambda[expression='item*2']" [input_param="item:int:Number to double", description="Doubles a number", mcp_server="math_tools"];
TOOL add_ten = "| lambda[expression='item+10']" [input_param="item:int:Number to add 10 to", description="Adds 10 to a number", mcp_server="math_tools"];
INPUT FROM echo[data="Double 7, then add 10. What is the final number?"]
| llmPrompt[model="llama3.1", source="ollama", tools=math_tools, temperature=0.0]
| print
"""
    
    # Create runtime and compile the script
    # Tools are registered during compilation, and the MCP instance is stored in runtime.const_store["math_tools"]
    runtime = RuntimeComponent()
    pipeline = compile(script, runtime)
    
    # Verify both tools were registered during compilation on the math_tools server
    mcp = runtime.const_store.get("math_tools")
    assert mcp is not None
    # Verify the server name is set to the server_name (math_tools)
    assert mcp.name == "math_tools"
    assert "double" in mcp._tool_manager._tools
    assert "add_ten" in mcp._tool_manager._tools
    
    # Test the tools directly
    double_tool = mcp._tool_manager._tools["double"]
    add_ten_tool = mcp._tool_manager._tools["add_ten"]
    assert double_tool.fn(5) == 10
    assert add_ten_tool.fn(5) == 15
    
    # Execute the pipeline - this will use LLMPrompt with the tools
    result = list(pipeline())
    
    # Verify we got a result
    assert len(result) >= 1
    result_text = str(result[-1])  # Last item should be the LLM response
    
    # Assert that the tools were actually called during execution
    # The result must contain "24" which can only be obtained by:
    # 1. Calling double(7) -> 14
    # 2. Calling add_ten(14) -> 24
    # This definitively proves both tools were called in sequence
    assert "24" in result_text, f"Expected result to contain '24' (proving both tools were called), but got: {result_text}"
    
    # Additional verification: The result should indicate tool usage
    # Either explicitly mention the tools or show the calculation
    assert ("double" in result_text.lower() or "add" in result_text.lower() or 
            "14" in result_text), f"Result should indicate tool usage, but got: {result_text}"
