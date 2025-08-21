# Getting Started with TalkPipe

Welcome to TalkPipe! This guide will help you get up and running quickly with TalkPipe's dual-language architecture for building AI-powered data processing pipelines.

## Installation

```bash
pip install talkpipe
```

## Basic Concepts

TalkPipe provides two ways to build data processing pipelines:

- **Pipe API (Internal DSL)**: Pure Python using the `|` operator
- **ChatterLang (External DSL)**: Concise text-based syntax

Both approaches use the same underlying components and can be mixed freely.

## Your First Pipeline

### Using ChatterLang

Create a simple chat interface in python:

```python
from talkpipe.chatterlang import compiler

# Define a pipeline that prompts an LLM and prints the response.  Assumed Ollama is installed locally and llama3.2 is downloaded.
script = '| llmPrompt[model="llama3.2", source="ollama"] | print'
chat = compiler.compile(script).asFunction(single_in=True, single_out=True)

# Use it
response = chat("Hello! Tell me about the history of computers.")
```

### Using the Pipe API

A similar interactive pipeline in pure Python:

```python
from talkpipe.pipe import io
from talkpipe.llm import chat

# Create pipeline using the | operator
pipeline = io.Prompt() | chat.LLMPrompt(model="llama3.2", source="ollama") | io.Print()
pipeline_func = pipeline.asFunction()

# Run it
pipeline_func()  # This will prompt for input interactively
```

## Web Interface

Create a web interface for your pipeline from the command line:

```bash
# Start a web server with your pipeline
talkpipe_endpoint --port 2025 --display-property prompt --script "| llmPrompt[model=\"llama3.2\", source=\"ollama\", field=\"prompt\"]"
```

Note that you may need to change how the double quotes are escaped based on your shell.

Open http://localhost:2025/stream in your browser to interact with your pipeline through a web form.

## Next Steps

### Learn the Tools

- **[talkpipe_endpoint](api-reference/chatterlang-server.md)** - Create web APIs and forms
- **[chatterlang_workbench](api-reference/chatterlang-workbench.md)** - Interactive development environment
- **[chatterlang_script](api-reference/chatterlang-script.md)** - Run scripts from files

### Explore Tutorials

Check out the [tutorials directory](tutorials/) for complete tutorials:
- Document indexing and search
- RAG (Retrieval-Augmented Generation) systems  
- Multi-format report generation

### Dive Deeper

- [Architecture](architecture/) - Technical deep-dives
- [API Reference](api-reference/) - Complete command reference


Ready to build something amazing? Start with the [tutorials](tutorials/)!