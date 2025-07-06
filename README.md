<center><img src="docs/TalkPipe.png" width=500></center>

**Build and iterate on smarter AI workflows in minutes.**

TalkPipe is a Python toolkit that makes it easy to create, test, and deploy workflows that integrate Generative AI with your existing tools and data sources. TalkPipe treats LLMs as one tool in your arsenal - letting you build practical solutions that combine AI with data processing, file handling, and more.  

## What Can You Do With TalkPipe?

- **Chat with LLMs** - Create multi-turn conversations with OpenAI or Ollama models in just 2 lines of code
- **Process Documents** - Extract text from PDFs, analyze research papers, score content relevance
- **Analyze Web Content** - Download web pages (respecting robots.txt), extract readable text, and summarize
- **Build Data Pipelines** - Chain together data transformations, filtering, and analysis with Unix-like simplicity
- **Create AI Agents** - Build agents that can debate topics, evaluate streams of documents, or monitor RSS feeds
- **Deploy Anywhere** - Run in Jupyter notebooks, as Docker containers, or as standalone Python applications

## Quick Start

Install TalkPipe:
```bash
pip install talkpipe
```

Create a multi-turn chat function in 2 lines:
```python
from talkpipe.chatterlang import compiler

script = '| llmPrompt[name="llama3.2", source="ollama", multi_turn=True]'
chat = compiler.compile(script).asFunction(single_in=True, single_out=True)

response = chat("Hello! My name is Alice.")
response = chat("What's my name?")  # Will remember context
```

# Core Components

## 1. The Pipe API (Internal DSL)

TalkPipe's Pipe API is a Pythonic way to build data pipelines using the `|` operator to chain components:

```python
from talkpipe.pipe import io
from talkpipe.llm import chat

# Create a pipeline that prompts for input, gets an LLM response, and prints it
pipeline = io.Prompt() | chat.LLMPrompt(name="llama3.2") | io.Print()
pipeline = pipeline.asFunction()
pipeline()  # Run the interactive pipeline
```

### Creating Custom Components

Add new functionality with simple decorators:

```python
from talkpipe.pipe import core, io

@core.segment()
def uppercase(items):
    """Convert each item to uppercase"""
    for item in items:
        yield item.upper()

# Use it in a pipeline
pipeline = io.echo(data="hello,world") | uppercase() | io.Print()
result = pipeline.asFunction(single_out=False)()

# Output:
# HELLO
# WORLD
# Returns: ['HELLO', 'WORLD']
```

## 2. ChatterLang (External DSL)

ChatterLang provides a Unix-like syntax for building pipelines, perfect for rapid prototyping and experimentation:

```
INPUT FROM echo[data="1,2,hello,3"] | cast[cast_type="int"] | print
```

### Key ChatterLang Features

- **Variables**: Store intermediate results with `@variable_name`
- **Constants**: Define reusable values with `CONST name = "value"`
- **Loops**: Repeat operations with `LOOP n TIMES { ... }`
- **Multiple Pipelines**: Chain workflows with `;` or newlines

## 3. Built-in Applications

### Interactive Web Interface
```bash
chatterlang_server [--port 8080]
```
A web UI for writing and testing ChatterLang scripts with real-time execution and logging.

### Command-Line Tools
- `chatterlang_server` - Start the interactive web interface for experimenting with ChatterLang
- `chatterlang_script` - Run ChatterLang scripts from files or command line
- `talkpipe_ref` - Generate documentation for all available sources and segments
- `talkpipe_endpoint` - Create a customizable user-accessible web interface and REST API from ChatterLang scripts

### Jupyter Integration
TalkPipe components work seamlessly in Jupyter notebooks for interactive data analysis.

# Detailed Examples

## Example 1: Multi-Agent Debate

Create agents with different perspectives that debate a topic:

```python
from talkpipe.chatterlang import compiler

script = """
CONST economist_prompt = "You are an economist. Reply in one sentence.";
CONST theologian_prompt = "You are a theologian. Reply in one sentence.";

INPUT FROM echo[data="The US should give free puppies to all children."] 
    | @topic 
    | accum[variable=@conversation] 
    | print;

LOOP 3 TIMES {
    INPUT FROM @topic 
        | llmPrompt[system_prompt=economist_prompt] 
        | @topic 
        | accum[variable=@conversation] 
        | print;
    
    INPUT FROM @topic 
        | llmPrompt[system_prompt=theologian_prompt] 
        | @topic 
        | accum[variable=@conversation] 
        | print;
};

INPUT FROM @conversation
"""

pipeline = compiler.compile(script).asFunction()
debate = pipeline()  # Watch the debate unfold!
```

## Example 2: Document Stream Evaluation

Score documents based on relevance to a topic:

```python
import pandas as pd
from talkpipe.chatterlang import compiler

# Sample document data
documents = [
    '{"title": "Dog", "description": "Dogs are loyal companions..."}',
    '{"title": "Cat", "description": "Cats are independent pets..."}',
    '{"title": "Wolf", "description": "Wolves are wild canines..."}'
]

script = """
CONST scorePrompt = "Rate 1-10 how related to dogs this is:";

| loadsJsonl 
| llmScore[system_prompt=scorePrompt, name="llama3.2", append_as="dog_relevance"] 
| appendAs[field_list="dog_relevance.score:relevance_score"] 
| toDataFrame
"""

pipeline = compiler.compile(script).asFunction(single_in=False, single_out=True)
df = pipeline(documents)
# df now contains relevance scores for each document
```

## Example 3: Web Page Analysis

Download and summarize web content:

```python
from talkpipe.chatterlang import compiler

script = """
| downloadURL
| htmlToText
| llmPrompt[
    system_prompt="Summarize this article in 3 bullet points",
    name="llama3.2"
  ]
| print
"""

analyzer = compiler.compile(script).asFunction(single_in=True)
analyzer("https://example.com/")
```

## Example 4: Content Evaluation Pipeline

Evaluate and filter articles based on relevance scores:

```python
from talkpipe.chatterlang import compiler

# Sample article data
articles = [
    '{"title": "New LLM Model Released", "summary": "AI Company announces new LLM with improved reasoning"}',
    '{"title": "Smart Home IoT Devices", "summary": "Review of latest Arduino-based home automation"}',
    '{"title": "Cat Videos Go Viral", "summary": "Funny cats take over social media again"}',
    '{"title": "RAG Systems in Production", "summary": "How companies deploy retrieval-augmented generation"}',
]

script = """
# Define evaluation prompts
CONST ai_prompt = "Rate 0-10 how relevant this is to AI practitioners. Consider mentions of AI, ML, algorithms, or applications.";
CONST iot_prompt = "Rate 0-10 how relevant this is to IoT researchers. Consider hardware, sensors, or embedded systems.";

# Process articles
| loadsJsonl
| concat[fields="title,summary", append_as="full_text"]

# Score for AI relevance
| llmScore[system_prompt=ai_prompt, field="full_text", append_as="ai_eval", name="llama3.2"]
| appendAs[field_list="ai_eval.score:ai_score,ai_eval.explanation:ai_reason"]

# Score for IoT relevance  
| llmScore[system_prompt=iot_prompt, field="full_text", append_as="iot_eval", name="llama3.2"]
| appendAs[field_list="iot_eval.score:iot_score,iot_eval.explanation:iot_reason"]

# Find highest score
| lambda[expression="max(item['ai_score'],item['iot_score'])", append_as="max_score"]

# Filter articles with score > 6
| gt[field="max_score", n=6]

# Format output
| toDict[field_list="title,ai_score,iot_score,max_score"]
| print
"""

evaluator = compiler.compile(script).asFunction(single_in=False, single_out=False)
results = evaluator(articles)

# Output shows only relevant articles with their scores:
# {'title': 'New LLM Model Released', 'ai_score': 9, 'iot_score': 2, 'max_score': 9}
# {'title': 'Smart Home IoT Devices', 'ai_score': 3, 'iot_score': 9, 'max_score': 9}
# {'title': 'RAG Systems in Production', 'ai_score': 8, 'iot_score': 2, 'max_score': 8}
```

# Architecture & Development

## Design Principles

### Dual-Language Architecture
- **Internal DSL (Pipe API)**: Pure Python for maximum flexibility and IDE support
- **External DSL (ChatterLang)**: Concise syntax for rapid prototyping

### Streaming Architecture
TalkPipe uses Python generators throughout, enabling:
- Memory-efficient processing of large datasets
- Real-time results as data flows through pipelines
- Natural integration with streaming data sources

### Extensibility First
- Simple decorators (`@source`, `@segment`, `@field_segment`) for adding functionality
- Components are just Python functions - easy to test and debug
- Mix TalkPipe with any Python code or library

## Project Structure

```
talkpipe/
├── app/          # Runnable applications (servers, CLIs)
├── chatterlang/  # ChatterLang parser, compiler, and components
├── data/         # Data manipulation and I/O components
├── llm/          # LLM integrations (OpenAI, Ollama)
├── operations/   # Algorithms and data processing
└── pipe/         # Core pipeline infrastructure
```

## Configuration

TalkPipe uses a flexible configuration system via `~/.talkpipe.toml` or environment variables:

```toml
# ~/.talkpipe.toml
default_model_name = "llama3.2"
default_model_source = "ollama"
smtp_server = "smtp.gmail.com"
smtp_port = 587
```

Environment variables use the `TALKPIPE_` prefix:
```bash
export TALKPIPE_email_password="your-password"
export TALKPIPE_openai_api_key="sk-..."
```

## Development Guidelines

### Naming Conventions
- **Classes**: `CamelCase` (e.g., `LLMPrompt`)
- **Decorated functions**: `camelCase` (e.g., `@segment def extractText`)
- **ChatterLang names**: `camelCase` (e.g., `llmPrompt`, `toDataFrame`)

### Creating Components

**Sources** generate data:
```python
from talkpipe.pipe import core, io

@core.source()
def fibonacci(n=10):
    a, b = 0, 1
    for _ in range(n):
        yield a
        a, b = b, a + b

# Use it in a pipeline
pipeline = fibonacci(n=5) | io.Print()
result = pipeline.asFunction(single_out=False)()

# Output:
# 0
# 1
# 1
# 2
# 3
# Returns: [0, 1, 1, 2, 3]
```

**Segments** transform data:
```python
@core.segment()
def multiplyBy(items, factor=2):
    for item in items:
        yield item * factor

# Use it to double the Fibonacci numbers
pipeline = fibonacci(n=5) | multiplyBy(factor=3) | io.Print()
result = pipeline.asFunction(single_out=False)()

# Output:
# 0
# 3
# 3
# 6
# 9
# Returns: [0, 3, 3, 6, 9]
```

**Field Segments** provide a convenient way to create 1:1 segments:
```python
from datetime import datetime
from talkpipe.chatterlang import registry

@registry.register_segment("addTimestamp")
@core.field_segment()
def addTimestamp(item):
    # Handle a single item, not an iterable
    # The decorator handles append_as and field parameters automatically
    return datetime.now()

# Use it with dictionaries
data = [{'name': 'Alice'}, {'name': 'Bob'}]
pipeline = addTimestamp(append_as="timestamp") | io.Print()
    
result = pipeline.asFunction(single_in=False, single_out=False)(data)

# Output (timestamps will vary):
# {'name': 'Alice', 'timestamp': datetime.datetime(2024, 1, 15, 10, 30, 45, 123456)}
# {'name': 'Bob', 'timestamp': datetime.datetime(2024, 1, 15, 10, 30, 45, 234567)}

# Now it's also available in ChatterLang:
# script = '| addTimestamp[append_as="timestamp"] | print'
```

### Best Practices

1. **Units with side effects should pass data through** - e.g., `writeFile` should yield items after writing
2. **Use descriptive parameter names** with underscores (e.g., `fail_on_error`, `append_as`)
3. **Handle errors gracefully** - use `fail_on_error` parameter pattern
4. **Document with docstrings** - they appear in generated documentation
5. **Test with both APIs** - ensure components work in both Python and ChatterLang

## Roadmap & Contributing

TalkPipe is under active development. Current priorities:

- **Enhanced LLM Support**: Additional providers (Anthropic, Cohere, local models)
- **Data Connectors**: More database integrations, API clients, file formats
- **Workflow Features**: Conditional branching, error handling, retry logic
- **Performance**: Parallel processing, caching, optimization
- **Developer Tools**: Better debugging, testing utilities, IDE plugins

We welcome contributions! Whether it's new components, bug fixes, documentation, or examples, please check our [GitHub repository](https://github.com/sandialabs/talkpipe) for contribution guidelines.

## Status

TalkPipe is currently in active development. While feature-rich and actively used, APIs may evolve. We follow semantic versioning - minor versions maintain compatibility within the same major version, while major version changes may include breaking changes.

## License

TalkPipe is licensed under the Apache License 2.0. See LICENSE file for details.

# Developer Documentation

## Glossary

* **Segment** - A unit that reads from another Unit and may or may not yield data of its own.  All units that
are not at the start of a pipeline is a Segment.
* **Source** - A unit that takes nothing as input and yields data items.  These Units are used in the
"INPUT FROM..." portion of a pipeline.  
* **Unit** - A component in a pipeline that either produces or processes data.  There are two types of units, Source, and Segments.

## Conventions

### Versioning

This codebase will use [semantic versioning](https://semver.org/) with the addtional convention that during the 0.x.y development that each MINOR version will maintain backward compatibility and PATCH versions will include substantial new capability.  So, for example, every 0.2.x version will be backward compatible, but 0.3.0 might contain code reorganization.

### Codebase Structure

The following are the main breakdown of the codebase.  These should be considered firm but not strict breakdowns.  Sometimes a source could fit within either operations or data, for exmaple.  

* **talkpipe.app** - Contains the primary runnable applications. 
  * Example: runscript
* **talkpipe.operations** - Contains general algorithm implementations.  Associated segments and sources can be included next to the algorithm implementations, but the algorithms themselves should also work stand-alone.
  * Exmaple: bloom filters
* **talkpipe.data** - Contain components having to do with complex, type-specific data manipulation.  
  * Example: extracting text from files.
* **talkpipe.llm** - Contain the abstract classes and implementations for accessing LLMs, both code for accessing specific LLMs and code for doing prompting.
  * Example: Code for talking with Ollama or OpenAI
* **talkpipe.pipe** - Code that implements the core classes and decorators for the pipe api as well and misc implementations of helper segments and sources.
  * Example: echo and the definition of the @segment decorator
* **talkpipe.chatterlang** - The definition, parsers, and compiler for the chatterlang language as well as any chatterlang specific segments and sources
  * Example: the chatterlang compiler and the variable segment

### Source/Segment Names

- **For your own Units, do whatever you want!** These conventions are for authors writing units intended for broader reuse.
- **Classes that implement Units** are named in CamelCase with the initial letter in uppercase.
- **Units defined using `@segment` and `@source` decorators** should be named in camelCase with an initial lowercase letter.
- In **ChatterLang**, sources and segments also use camelCase with an initial lowercase letter.
- Except for the **`cast`** segment, segments that convert data into a specific format—whether they process items one-by-one or drain the entire input—should be named using the form `[tT]oX`, where **X** is the output data type (e.g., `toDataFrame` outputs a pandas DataFrame).
- **Segments that write files** use the form `[Ww]riteX`, where **X** is the file type (e.g., `writeExcel` writes an Excel file, `writePickle` writes a pickle file).
- **Segments that read files** use the form `[Rr]eadX`, where **X** is the file type (e.g., `readExcel` should read an Excel file).
- **Parameter names in segments** should be in all lower case with words separated by an underscore (_)

### Parameter Names

These parameter names should behave consistently across all units:

- **append_as**  
  If used, any processed output is attached to the original data using bracket notation. The original item is then emitted.

- **fail_on_error**
  If True, an operation the exception should be raised, likely aborting the pipeline.  If False, the operation should continue
  and either None should be yielded or nothing, depending on the segment or source.  A warning message should be logged.

- **field**  
  Specifies that the unit should operate on data accessed via “field syntax.” This syntax can include indices, properties, or parameter-free methods, separated by periods.  
  - For example, given `{"X": ["a", "b", ["c", "d"]]}`, the field `"X.2.0"` refers to `"c"`.

- **field_list**
  Specifies that a list of fields can or shoudl be provided, with each field separated
  by a comma.  In some cases, each field needs to be mapped to some other name.  In
  those case, the field and name should be separated by a colon.  In field_lists,
  the underscore (_) refers to the item as a whole.  
  - For example, "X.2.0:SomeName,X.1:SomeOtherName".  If no "name" is provided, 
  the fieldname itself is used.  Where only a list of fields is needed and no names,
  the names can still be provided but have no effect.  

### General Behavior Principles

* Units that have side effects (e.g. writing data to a disk) should generally also pass
on their data.

### Source and Segement Reference

The chatterlang_server command starts a web service designed for experimentation.  It also contains links to HTML and text versions
of all the sources and segments included in TalkPipe.

After talkpipe is installed, a script called "talkpipe_ref" is avaialble that will write an HTML and text file in the current directory, each of which contains the documentation for build-in sources and segments.

### Standard Configuration File Items

 Configuration constants can be defined either in ~/.talkpipe.toml or in environment variables.  Any constant defined in an environment variable needs to be prefixed with TALKPIPE_.  So email_password, stored in an environment variable, needs to be TALKPIPE_email_password.  Note that in Chatterlang, any variable stored in the format
 can be specified as a parameter using $var_name.  This will get dereferenced to 
 the environment varaible TALKPIPE_var_name or var_name in talkpipe.toml.

* **default_embedding_source** - The default source (e.g. ollama) to be used for creating sentence embeddings.
* **default_embedding_model_name** - The name of the LLM model to be used for creating sentence embeddings.
* **default_model_name** - The default name of a LLM model to be used in chat
* **default_model_source** - The default source (e.g. ollama) to be used in chat
* **email_password** - Password for the SMTP server
* **logger_files** - Files to store logs, in the form logger1:fname1,logger2:fname2,...
* **logger_levels** - Logger levles in the form logger1:level1,logger2:level2
* **recipient_email** - Who should receive a sent email
* **rss_url** - The default URL used by the rss segment
* **sender_email** - Who the sender of an email should be
* **smtp_port** - SMTP server port
* **smtp_server** - SMTP server hostname