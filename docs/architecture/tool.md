# Tool Integration Architecture

## Overview

TalkPipe integrates with the Model Context Protocol (MCP) to enable LLMs to call custom tools during conversations. Tools are defined using the `TOOL` syntax in ChatterLang scripts, which compiles TalkPipe pipelines into callable functions that LLMs can invoke.

## Unified Server Model

Both `TOOL` and `MCP_SERVER` use the same server name concept. The `mcp_server` parameter in `TOOL` references a server that can be either:
- **Local server**: Automatically created when first `TOOL` uses it
- **External server**: Explicitly defined via `MCP_SERVER`

## TOOL Syntax

The `TOOL` keyword registers TalkPipe pipelines as tools that can be used by LLMs.

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
- **`mcp_server`** (optional): The name of the MCP server to register the tool with. References a server name (local or external). Defaults to `"mcp"` if not specified

## MCP_SERVER Syntax

The `MCP_SERVER` keyword connects to external MCP servers. Once connected, tools from that server are available for use with `llmPrompt`.

### Basic Syntax

```chatterlang
MCP_SERVER server_name = "url_or_config" [parameters];
```

### Parameters

- **`url`** (required): The URL or connection string for the external MCP server
- **`transport`** (optional): Transport type - `"http"`, `"sse"`, or `"stdio"`. Defaults to `"http"`
- **`auth`** (optional): Authentication type - `"bearer"` or `"oauth"`
- **`token`** (optional): Bearer token for authentication
- **`headers`** (optional): Custom HTTP headers as a dictionary
- **`command`** (optional): For stdio transport - command to execute
- **`args`** (optional): For stdio transport - command arguments
- **`cwd`** (optional): For stdio transport - working directory
- **`env`** (optional): For stdio transport - environment variables

The server is stored in `runtime.const_store[server_name]` and can be referenced in `llmPrompt` using `tools=server_name`.

## MCP Server Management

Both local and external MCP servers use the same server name system. The `mcp_server` parameter in `TOOL` references the server name defined by `MCP_SERVER` or created automatically.

### Local Servers (Created Automatically)

When you define a `TOOL` with a `mcp_server` parameter, a local FastMCP server is automatically created if it doesn't exist:

```chatterlang
TOOL double = "| lambda[expression='item*2']" [input_param="item:int:Number to double", mcp_server="math_tools"];
TOOL add_ten = "| lambda[expression='item+10']" [input_param="item:int:Number to add 10 to", mcp_server="math_tools"];
```

The server `math_tools` is created automatically when the first tool is registered.

### External Servers (MCP_SERVER Syntax)

To connect to an external MCP server, use the `MCP_SERVER` keyword:

```chatterlang
# Connect to an external MCP server over HTTP
MCP_SERVER external_tools = "https://api.example.com/mcp" [transport="http", auth="bearer", token="your-token"];

# Tools from the external server are automatically available
INPUT FROM echo[data="Use the external tools"]
| llmPrompt[model="llama3.1", source="ollama", tools=external_tools]
| print
```

### MCP_SERVER Parameters

- **`url`** (required): The URL or connection string for the external server
- **`transport`** (optional): Transport type - `"http"`, `"sse"`, or `"stdio"`. Defaults to `"http"`
- **`auth`** (optional): Authentication type - `"bearer"` or `"oauth"`
- **`token`** (optional): Bearer token for authentication
- **`headers`** (optional): Custom HTTP headers as a dictionary
- **`command`** (optional): For stdio transport - command to execute
- **`args`** (optional): For stdio transport - command arguments
- **`cwd`** (optional): For stdio transport - working directory
- **`env`** (optional): For stdio transport - environment variables

### Mixed Usage

You can combine local tools and external servers in the same script:

```chatterlang
# Connect to external server
MCP_SERVER external_api = "https://api.example.com/mcp" [transport="http", auth="bearer", token="token"];

# Define local tools on a local server
TOOL double = "| lambda[expression='item*2']" [input_param="item:int:Number to double", mcp_server="math_tools"];

# Use either server with llmPrompt
INPUT FROM echo[data="Use math tools"]
| llmPrompt[model="llama3.1", source="ollama", tools=math_tools]
| print

INPUT FROM echo[data="Use external API"]
| llmPrompt[model="llama3.1", source="ollama", tools=external_api]
| print
```

**Note**: You cannot register local `TOOL` definitions on an external `MCP_SERVER`. External servers provide their own tools that are already available. If you try to register a `TOOL` with `mcp_server` pointing to an external server, a warning will be logged and the tool registration will be skipped.

### Server Storage

All MCP servers (both local and external) are stored in `runtime.const_store[server_name]` and can be referenced directly in the script using the server name identifier.

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

1. **Parsing**: The `MCP_SERVER` and `TOOL` definitions are parsed during script compilation, similar to `CONST` definitions
2. **External Server Connection**: `MCP_SERVER` definitions create FastMCP Client connections to external servers
3. **Grouping**: Tools are grouped by their `mcp_server` parameter
4. **Local Server Creation**: For tools referencing servers that don't exist, local FastMCP server instances are created
5. **Tool Registration**: Each tool is registered with its corresponding MCP server using `register_talkpipe_tool()` (only for local servers)
6. **Storage**: All MCP server instances (local and external) are stored in `runtime.const_store[server_name]` for later reference

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
