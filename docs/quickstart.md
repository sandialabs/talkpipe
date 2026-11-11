# Getting Started with TalkPipe

This guide takes you from installation to a working pipeline. You can start with **no LLM**—the first examples work with the base install—then add LLM support when you're ready.

## Installation

```bash
pip install talkpipe
```

The base install includes data processing, file I/O, search (Whoosh, LanceDB), and web serving. For LLM and PDF support, add optional extras. TalkPipe does not depend on any one LLM provider — install whichever you use:

```bash
# LLM providers (install one or more)
pip install "talkpipe[ollama]"      # Local models via Ollama
pip install "talkpipe[openai]"      # OpenAI (GPT-4, etc.)
pip install "talkpipe[anthropic]"   # Anthropic Claude
pip install "talkpipe[model2vec]"   # In-process embeddings (no server, no API key)

# PDF extraction
pip install "talkpipe[pypdf]"

# Combine extras
pip install "talkpipe[ollama,pypdf]"
pip install "talkpipe[openai,anthropic]"

# Everything: all LLM providers + PDF + images
pip install "talkpipe[all]"
```

Quote the extras: in zsh (the default shell on macOS) an unquoted `[...]` is a
glob and the command fails with "no matches found" before pip runs.

| Extra | Adds |
|-------|------|
| `ollama` | `ollama` package for local models (chat and embeddings) |
| `openai` | `openai` package for OpenAI API (chat and embeddings) |
| `anthropic` | `anthropic` package for Claude (chat) |
| `model2vec` | `model2vec` package for in-process static embeddings |
| `pypdf` | `pypdf` for PDF text extraction |
| `all` | All of the above, plus `Pillow` for images |

Which provider needs what (servers, API keys) and how to select one is summarized under [LLM providers](guides/model-and-source-configuration.md#llm-providers).

## Basic Concepts

A **pipeline** is a chain of components joined with `|`, through which items flow one at a time:

- A **source** starts the pipeline by producing items (`echo` emits the values you give it; others read files, feeds, or prompts).
- A **segment** receives the items from the step before it, transforms, filters, or acts on them, and passes the results on (`cast`, `print`, `llmPrompt`, …).

TalkPipe provides two ways to write the same pipeline:

- **Pipe API**: pure Python, using the `|` operator on component objects (the docs also call this the *internal DSL*, a mini-language embedded in Python)
- **ChatterLang**: a concise text syntax you can keep in a string or a file (the *external DSL*, a small language of its own)

Both use the same components and can be mixed.

> **One word, two meanings:** a pipeline *source* is the component that starts a pipeline. The `source="..."` *parameter* on LLM segments is unrelated: it names the model provider (`"ollama"`, `"openai"`, `"anthropic"`).

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

`compiler.compile(script)` builds the pipeline and `.as_function()` turns it into an ordinary Python function. Pipelines work on streams of items, so by default that function accepts an iterable of items and returns a list of results. Two flags adapt it to single values, and you will see them throughout the docs:

| Flag | Meaning |
|------|---------|
| `single_in=True` | The argument is **one item**, not an iterable of items. Use it when you pass one string or one dict — without it a string is treated as a stream of characters. |
| `single_out=True` | Return the **one result itself** instead of a one-element list. Raises `ValueError` if the pipeline did not produce exactly one result. |

This script begins with `INPUT FROM echo[...]`, so it supplies its own input and the function is called with no argument. A script that begins with `|` (as in the chat examples below) has no source: its input is the argument you pass to the function.

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

## Local Syntax Sandbox (No LLM Backend Needed)

If you do not have Ollama/OpenAI/Anthropic access yet, you can still practice
TalkPipe and ChatterLang syntax with `source="eliza"`.

`eliza` is **not** an LLM provider. It is a local deterministic adapter meant for
testing pipeline shape, parameter wiring, and multi-turn flow.

### ChatterLang

```python
from talkpipe.chatterlang import compiler

script = '| llmPrompt[model="Dr. Eliza", source="eliza", multi_turn=True] | print'
chat = compiler.compile(script).as_function(single_in=True, single_out=True)

chat("Hello, my name is Alice.")
chat("What's my name?")
```

Expected output (Eliza's replies are scripted, so they are the same on every run):

```
I am Dr. Eliza. Hi there. What question keeps returning for you?
Earlier you said your name is Alice. Is that still how you introduce yourself?
```

## Your First Pipeline (With LLM)

Any supported provider works; the provider is the `source` parameter on the LLM segment. The examples below use Ollama, which requires `talkpipe[ollama]` and Ollama running with a model (e.g. `ollama pull llama3.2`). If you point TalkPipe at a remote Ollama server via `TALKPIPE_OLLAMA_SERVER_URL`, the model must already be pulled on that server (run `ollama pull llama3.2` there, or `OLLAMA_HOST=http://your-ollama-host:11434 ollama pull llama3.2` from your machine, substituting your server's address).

To use a hosted provider instead, no Ollama needed:

| Provider | Install | Credentials | Segment parameters |
|----------|---------|-------------|--------------------|
| OpenAI | `pip install "talkpipe[openai]"` | `export OPENAI_API_KEY=...` | `source="openai", model="gpt-4o-mini"` |
| Anthropic | `pip install "talkpipe[anthropic]"` | `export ANTHROPIC_API_KEY=...` | `source="anthropic", model="claude-haiku-4-5"` |

### ChatterLang

<!-- doc-example: requires-ollama -->
```python
from talkpipe.chatterlang import compiler

script = '| llmPrompt[model="llama3.2", source="ollama"] | print'
# Using OpenAI:    model="gpt-4o-mini", source="openai"
# Using Anthropic: model="claude-haiku-4-5", source="anthropic"
chat = compiler.compile(script).as_function(single_in=True, single_out=True)

response = chat("Hello! Tell me about the history of computers.")
```

To avoid repeating `model` and `source` on every segment, set defaults in `~/.talkpipe.toml` or environment variables. See [Model and source configuration](guides/model-and-source-configuration.md).

For `llmPrompt` memory behavior (`context_token_trigger`, `memory_mode`, `unsummarized_message_count`, `memory_size`), see
[ChatterLang memory controls](architecture/chatterlang.md#llmprompt-conversation-memory-controls).

### Pipe API

<!-- doc-example: requires-ollama -->
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

Open http://localhost:2025/stream. Type in the form and submit; the pipeline echoes your input as formatted text. The same pipeline is also a JSON API (`POST http://localhost:2025/process`). Stop the server with Ctrl+C.

### With LLM

```bash
chatterlang_serve --port 2025 --display-property prompt --script '| llmPrompt[model="llama3.2", source="ollama", field="prompt"] | print'
```

Open http://localhost:2025/stream to chat with the LLM. With OpenAI or Anthropic, change `source` and `model` in the script as in the table above.

## RAG from Documents

For a minimal document Q&A workflow without writing scripts:

```bash
makevectordatabase "docs/*.md" --path ./mydb --embedding_source ollama --embedding_model nomic-embed-text
serverag --path ./mydb --embedding_source ollama --embedding_model nomic-embed-text --completion_source ollama --completion_model llama3.2
```

`"docs/*.md"` is a placeholder for your own files: point it at any folder of Markdown, text, or PDF documents (keep the quotes so the shell passes the pattern through unexpanded). `serverag` needs both the embedding flags (to search the database) and the completion flags (to generate the answer) — these are required unless you set defaults in `~/.talkpipe.toml`. The example above needs Ollama running with both models pulled (`ollama pull nomic-embed-text` and `ollama pull llama3.2`). Then open http://localhost:2026/stream. See [makevectordatabase and serverag](guides/makevectordatabase-and-serverag.md) for full options.

The embedding and completion providers are independent, and neither has to be Ollama. For example, in-process model2vec embeddings with Anthropic answers (`pip install "talkpipe[model2vec,anthropic]"`, `ANTHROPIC_API_KEY` set):

```bash
makevectordatabase "docs/*.md" --path ./mydb --embedding_source model2vec --embedding_model minishlab/potion-base-8M
serverag --path ./mydb --embedding_source model2vec --embedding_model minishlab/potion-base-8M --completion_source anthropic --completion_model claude-haiku-4-5
```

Both commands validate this configuration at startup: a missing or unsupported
model/source is reported on stderr with an actionable error and a non-zero exit,
so a configuration mistake shows up immediately rather than on the first query.

## Next Steps

### Learn the Tools

- **[chatterlang_serve](api-reference/chatterlang-server.md)** - Web APIs and forms
- **[chatterlang_workbench](api-reference/chatterlang-workbench.md)** - Interactive development
- **[chatterlang_script](api-reference/chatterlang-script.md)** - Run scripts from files

### Find More Sources and Segments

```bash
chatterlang_reference_browser      # interactive: list, search <term>, show <name>
chatterlang_reference_generator    # writes chatterlang_ref.html and chatterlang_ref.txt
```

Both list every source and segment installed, with its description and parameters; see [reference tools](api-reference/talkpipe-ref.md). The [ChatterLang reference](architecture/chatterlang.md) covers the language itself (variables, constants, loops).

### Explore Tutorials

[Tutorials](tutorials/) walk through document indexing, RAG, and report generation. Tutorial 1 can use the included `stories.json` if you skip the LLM data-generation step.

### Extend with Plugins

```bash
talkpipe_plugins --list
pip install <plugin-package-name>   # replace with the plugin you want to install
```

See [Extending TalkPipe](architecture/extending-talkpipe.md) to create plugins.

### Dive Deeper

- [Architecture](architecture/) - Technical deep-dives
- [API Reference](api-reference/) - Command reference
