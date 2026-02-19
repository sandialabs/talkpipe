# Getting Started with TalkPipe

This guide gets you up and running with TalkPipe's dual-language architecture for building data processing pipelines. You can start with **no LLM**—examples below work with the base install—then add LLM support when you're ready.

## Installation

```bash
pip install talkpipe
```

The base install includes data processing, file I/O, search (Whoosh, LanceDB), and web serving. For LLM and PDF support, add optional extras:

```bash
# LLM providers (install one or more)
pip install talkpipe[ollama]      # Local models via Ollama
pip install talkpipe[openai]      # OpenAI (GPT-4, etc.)
pip install talkpipe[anthropic]   # Anthropic Claude

# PDF extraction
pip install talkpipe[pypdf]

# Combine extras
pip install talkpipe[ollama,pypdf]
pip install talkpipe[openai,anthropic]

# Everything: all LLM providers + PDF
pip install talkpipe[all]
```

| Extra | Adds |
|-------|------|
| `ollama` | `ollama` package for local models |
| `openai` | `openai` package for OpenAI API |
| `anthropic` | `anthropic` package for Claude |
| `pypdf` | `pypdf` for PDF text extraction |
| `all` | All of the above |

## Basic Concepts

TalkPipe provides two ways to build pipelines:

- **Pipe API (Internal DSL)**: Pure Python using the `|` operator
- **ChatterLang (External DSL)**: Concise text-based syntax

Both use the same components and can be mixed.

## Your First Pipeline (No LLM Required)

### ChatterLang

```python
from talkpipe.chatterlang import compiler

script = 'INPUT FROM echo[data="hello,world,test"] | print'
pipeline = compiler.compile(script).as_function(single_out=False)

result = pipeline()
# Prints: hello, world, test (each on its own line)
# Returns: ['hello', 'world', 'test']
```

### Pipe API

```python
from talkpipe.pipe import io

pipeline = io.echo(data="hello,world,test") | io.Print()
result = pipeline.as_function(single_out=False)()

# Same output and return value
```

### Data Transformation (No LLM)

```python
from talkpipe.chatterlang import compiler

# Parse numbers, filter, and print
script = 'INPUT FROM echo[data="1,2,hello,3,4"] | cast[cast_type="int"] | print'
pipeline = compiler.compile(script).as_function(single_out=False)
pipeline()  # Skips "hello", prints 1, 2, 3, 4
```

## Your First Pipeline (With LLM)

Requires `talkpipe[ollama]` and Ollama running with a model (e.g. `ollama pull llama3.2`).

### ChatterLang

```python
from talkpipe.chatterlang import compiler

script = '| llmPrompt[model="llama3.2", source="ollama"] | print'
chat = compiler.compile(script).as_function(single_in=True, single_out=True)

response = chat("Hello! Tell me about the history of computers.")
```

### Pipe API

```python
from talkpipe.pipe import io
from talkpipe.llm import chat

pipeline = io.Prompt() | chat.LLMPrompt(model="llama3.2", source="ollama") | io.Print()
pipeline_func = pipeline.as_function()
pipeline_func()  # Prompts for input interactively
```

## Web Interface

Use `--display-property` so the stream UI shows the input field value instead of raw JSON. Use `formatItem` to format output for readable display.

### Without LLM (Echo / Transform)

```bash
chatterlang_serve --port 2025 --display-property prompt --script '| formatItem[field_list="prompt:You entered"] | print'
```

Open http://localhost:2025/stream. Type in the form and submit; the pipeline echoes your input as formatted text.

### With LLM

```bash
chatterlang_serve --port 2025 --display-property prompt --script '| llmPrompt[model="llama3.2", source="ollama", field="prompt"] | print'
```

Open http://localhost:2025/stream to chat with the LLM.

## Next Steps

### Learn the Tools

- **[chatterlang_serve](api-reference/chatterlang-server.md)** - Web APIs and forms
- **[chatterlang_workbench](api-reference/chatterlang-workbench.md)** - Interactive development
- **[chatterlang_script](api-reference/chatterlang-script.md)** - Run scripts from files

### Explore Tutorials

[Tutorials](tutorials/) walk through document indexing, RAG, and report generation. Tutorial 1 can use the included `stories.json` if you skip the LLM data-generation step.

### Extend with Plugins

```bash
talkpipe_plugins --list
pip install talkpipe-some-plugin
```

See [Extending TalkPipe](architecture/extending-talkpipe.md) to create plugins.

### Dive Deeper

- [Architecture](architecture/) - Technical deep-dives
- [API Reference](api-reference/) - Command reference
