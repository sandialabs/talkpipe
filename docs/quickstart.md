# Getting Started with TalkPipe

Welcome to TalkPipe! This guide will help you get up and running quickly with TalkPipe's dual-language architecture for building AI-powered data processing pipelines.

## Installation

```bash
pip install talkpipe
```

For LLM support, install the provider(s) you need:
```bash
# Install specific providers
pip install talkpipe[openai]    # For OpenAI
pip install talkpipe[ollama]    # For Ollama
pip install talkpipe[anthropic] # For Anthropic Claude

# Or install all LLM providers
pip install talkpipe[all]
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
chat = compiler.compile(script).as_function(single_in=True, single_out=True)

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
pipeline_func = pipeline.as_function()

# Run it
pipeline_func()  # This will prompt for input interactively
```

## Web Interface

Create a web interface for your pipeline from the command line:

```bash
# Use single quotes to avoid escaping double quotes inside
chatterlang_serve --port 2025 --display-property prompt --script '| llmPrompt[model="llama3.2", source="ollama", field="prompt"]'
```

Open http://localhost:2025/stream in your browser to interact with your pipeline through a web form.

## Debug Pipelines with diagPrint

Use `diagPrint` to inspect data as it flows through a pipeline without altering outputs.

### Pipe API

```python
from talkpipe.pipe import basic

debug = basic.DiagPrint(
	label="chunk",
	field_list="id,text",
	expression="len(item['text'])",
	output="stderr",  # or a logger name
)
pipeline = debug | basic.firstN(n=3)
list(pipeline([{"id": 1, "text": "hello world"}]))
```

### ChatterLang

```
| diagPrint[label="chunk", field_list="id,text", expression="len(item['text'])", output="stderr"]
```

### Config-driven output

Set a config key (e.g., in `~/.talkpipe.toml`):

```toml
diag_output = "stderr"
```

Then point `diagPrint` to it:

```
| diagPrint[output="config:diag_output"]
```

Tips:
- Use `field_list` to print only the fields you need.
- `None` or `"None"` for `output` suppresses all diagnostic output.
- The elapsed time line shows spacing between successive items.

## Next Steps

### Learn the Tools

- **[chatterlang_serve](api-reference/chatterlang-server.md)** - Create web APIs and forms
- **[chatterlang_workbench](api-reference/chatterlang-workbench.md)** - Interactive development environment
- **[chatterlang_script](api-reference/chatterlang-script.md)** - Run scripts from files

### Explore Tutorials

Check out the [tutorials directory](tutorials/) for complete tutorials:
- Document indexing and search
- RAG (Retrieval-Augmented Generation) systems  
- Multi-format report generation

### Extend with Plugins

TalkPipe supports plugins to add custom functionality:

```bash
# List installed plugins
talkpipe_plugins --list

# Install third-party plugins
pip install talkpipe-some-plugin
```

Plugins automatically extend ChatterLang with new sources and segments. See [Extending TalkPipe](architecture/extending-talkpipe.md) to create your own plugins.

### Dive Deeper

- [Architecture](architecture/) - Technical deep-dives
- [API Reference](api-reference/) - Complete command reference


Ready to build something amazing? Start with the [tutorials](tutorials/)!