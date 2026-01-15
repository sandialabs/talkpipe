# Tool Integration Architecture

## Overview

TalkPipe integrates with the Model Context Protocol (MCP) to enable LLMs to call custom tools during conversations. Tools are defined using the `TOOL` syntax in ChatterLang scripts, which compiles TalkPipe pipelines into callable functions that LLMs can invoke.

## TOOL Syntax

The `TOOL` keyword in ChatterLang allows you to register TalkPipe pipelines as tools that can be used by LLMs. Tools are registered during script compilation and stored in FastMCP server instances.

### Basic Syntax

```chatterlang
TOOL tool_name = "pipeline_string" [parameters];
```

### Parameters

- **`pipeline`** (required): A quoted string containing a ChatterLang pipeline that defines the tool's behavior
- **`name`** (optional): The name of the tool as it appears to the LLM. Defaults to `tool_name` if not specified
- **`description`** (optional): A description of what the tool does, shown to the LLM
- **`input_param`** (optional): Input parameter specification in format `"name:type:description"` (e.g., `"item:int:Number to double"`)
- **`param_name`**, **`param_type`**, **`param_desc`** (optional): Individual parameter specifications as an alternative to `input_param`
- **`mcp_server`** (optional): The name of the MCP server to register the tool with. Defaults to `"mcp"` if not specified

### Example

```chatterlang
TOOL double = "| lambda[expression='item*2']" [input_param="item:int:Number to double", description="Doubles a number", mcp_server="math_tools"];
TOOL add_ten = "| lambda[expression='item+10']" [input_param="item:int:Number to add 10 to", description="Adds 10 to a number", mcp_server="math_tools"];
```

## Multiple MCP Servers

You can define multiple MCP servers in a single script by specifying different `mcp_server` values. Each server maintains its own set of tools.

```chatterlang
TOOL double = "| lambda[expression='item*2']" [input_param="item:int:Number to double", mcp_server="math_tools"];
TOOL uppercase = "| lambda[expression='item.upper()']" [input_param="item:str:Text to uppercase", mcp_server="text_tools"];
```

Each MCP server instance is stored in `runtime.const_store[server_name]` and can be referenced directly in the script.

## Using Tools with LLMPrompt

Once tools are registered, you can use them with the `llmPrompt` segment by referencing the MCP server:

```chatterlang
TOOL double = "| lambda[expression='item*2']" [input_param="item:int:Number to double", mcp_server="math_tools"];
TOOL add_ten = "| lambda[expression='item+10']" [input_param="item:int:Number to add 10 to", mcp_server="math_tools"];

INPUT FROM echo[data="Double 7, then add 10. What is the final number?"]
| llmPrompt[model="llama3.1", source="ollama", tools=math_tools, temperature=0.0]
| print
```

The `tools` parameter accepts the MCP server identifier, which is automatically resolved from `runtime.const_store`.

## Implementation Details

### Compilation Process

1. **Parsing**: The `TOOL` definitions are parsed during script compilation, similar to `CONST` definitions
2. **Grouping**: Tools are grouped by their `mcp_server` parameter
3. **Server Creation**: FastMCP instances are created for each unique server name
4. **Tool Registration**: Each tool is registered with its corresponding MCP server using `register_talkpipe_tool()`
5. **Storage**: MCP server instances are stored in `runtime.const_store[server_name]` for later reference

### Tool Execution

When an LLM requests a tool call:

1. The LLM sends a tool call request with the tool name and arguments
2. The tool function is looked up in the MCP server's tool registry
3. The underlying TalkPipe pipeline is executed with the provided arguments
4. The result is returned to the LLM as a tool response
5. The LLM can use the result to continue the conversation

### Pipeline Types

Tools can be defined using:

- **Segment pipelines**: Require an `input_param` specification to define the input parameter. These transform input data.
- **Source pipelines**: Don't require input parameters (they generate their own data). These are less common for tools since tools typically need input from the LLM.

Example of a segment pipeline tool that processes input:

```chatterlang
TOOL reverse = "| lambda[expression='item[::-1]']" [input_param="text:str:Text to reverse", description="Reverses a string"];
```

Example of a more complex tool with multiple operations:

```chatterlang
TOOL word_count = "| lambda[expression='item.split()'] | lambda[expression='len(item)']" [input_param="text:str:Text to count words in", description="Counts the number of words in a text"];
```

## Best Practices

1. **Descriptive Names**: Use clear, descriptive tool names that indicate their purpose
2. **Good Descriptions**: Provide detailed descriptions to help the LLM understand when to use each tool
3. **Type Specifications**: Always specify parameter types in `input_param` for better LLM understanding
4. **Server Organization**: Group related tools on the same MCP server for better organization
5. **Error Handling**: Ensure your pipelines handle edge cases and invalid inputs gracefully

## Related Documentation

- [ChatterLang Architecture](chatterlang.md) - For general ChatterLang syntax
- [Pipe API](pipe-api.md) - For understanding how pipelines work
- [LLM Integration](../api-reference/chatterlang-script.md) - For using LLMs in ChatterLang
