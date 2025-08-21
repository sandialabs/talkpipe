# ChatterLang Workbench

**`chatterlang_workbench`** - Interactive web interface for writing, testing, and running ChatterLang scripts in real-time.

## Overview

The ChatterLang Server provides a browser-based development environment for TalkPipe's external DSL. It features a script editor, real-time script execution and built-in examples. This tool is perfect for experimenting with ChatterLang syntax, prototyping pipelines, and learning TalkPipe concepts interactively.

## Usage

### Command Line Interface

```bash
chatterlang_workbench [options]
```

### Command Line Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--host` | string | `127.0.0.1` | Server host address |
| `--port` | integer | `4143` | Server port number |
| `--reload` | flag | `false` | Enable auto-reload for development |
| `--load-module` | string | | Path to custom module file to import (can be used multiple times) |

### Examples

```bash
# Start server with default settings
chatterlang_workbench

# Start on custom host and port
chatterlang_workbench --host 0.0.0.0 --port 8080

# Enable development mode with auto-reload
chatterlang_workbench --reload

# Load custom modules before starting
chatterlang_workbench --load-module /path/to/custom_segments.py
```

## Web Interface Features

### Interactive Execution
The server supports two execution modes:

#### Non-Interactive Scripts
Scripts that start with `INPUT FROM` or other source commands execute immediately when compiled, displaying all output at once.

**Example:**
```
INPUT FROM echo[data="Hello World"] | print
```

#### Interactive Scripts  
Scripts that start with `|` (pipe) require user input and support multi-turn interactions.

**Example:**
```
| llmPrompt[model="llama3.2", source="ollama", multi_turn=True]
```

### Built-in Examples

The interface provides categorized example scripts:

#### Basic Examples
- **Hello World**: Simple data echo and print
- **Data Transformation**: Type casting and data manipulation
- **Using Variables**: Variable storage and reuse patterns

#### LLM Examples
- **Simple Chat**: Single-turn LLM interactions
- **Agent Conversation**: Multi-agent debate scenarios
- **Web Page Summarizer**: URL processing and summarization

#### Advanced Examples
- **Data Analysis Loop**: Iterative data processing with loops
- **Document Evaluation**: Scoring and relevance assessment

### System Logging
- **Real-time Logs**: Live system and execution logs
- **Log Levels**: Color-coded INFO, WARNING, and ERROR messages
- **Log Management**: Clear and refresh capabilities
- **Persistent Display**: Logs persist across script executions

## Configuration

### Environment Variables
All TalkPipe configuration variables are supported:


## Development Features

### Custom Module Loading
Load custom TalkPipe components before starting the server:

```bash
chatterlang_workbench --load-module ./my_custom_segments.py
```

This allows you to:
- Test custom sources and segments
- Prototype new functionality
- Integrate domain-specific components

### Auto-reload Mode
Enable development mode for automatic server restarts:

```bash
chatterlang_workbench --reload
```

**Note**: Only use `--reload` in development environments.

## Troubleshooting

### Common Issues

**Server won't start**
- Check if port is already in use
- Verify TalkPipe installation
- Check for missing dependencies

**Scripts fail to compile**
- Verify ChatterLang syntax
- Check for missing LLM configurations
- Review system logs for detailed errors

**Interactive mode not working**
- Ensure script starts with `|` character
- Verify LLM connectivity (Ollama/OpenAI)
- Check API key configuration

**Examples not loading**
- Check browser console for JavaScript errors
- Restart server if needed

---

*For conceptual information about ChatterLang, see [ChatterLang Architecture](../architecture/chatterlang.md). 

---
Last Reviewed: 20250814