# ChatterLang Architecture

## Overview

ChatterLang is TalkPipe's external Domain-Specific Language (DSL): a high-level, declarative syntax for building data processing pipelines. It hides Python implementation details so complex workflows can be expressed in simple, human-readable commands.

The LLM examples on this page happen to use `source="ollama"`. Nothing here is
Ollama-specific: `source` and `model` are ordinary segment parameters, so
`source="openai"` or `source="anthropic"` works the same way — see
[LLM providers](../guides/model-and-source-configuration.md#llm-providers).

While the Pipe API requires Python programming knowledge, ChatterLang enables data analysts, researchers, and non-programmers to create sophisticated pipelines through text-based scripts.

## The language at a glance

Everything the language has, in one script. Save it as `glance.script` and run it with `chatterlang_script --script glance.script --greeting hello` (or paste it into `chatterlang_workbench`, with `greeting = "hello"` in `~/.talkpipe.toml`):

```chatterlang
# A comment runs from `#` to the end of the line.
CONST factor = 10;

INPUT FROM echo[data="1,2,3"] | cast[cast_type="int"] | @numbers;

LOOP 2 TIMES {
    INPUT FROM @numbers | scale[multiplier=factor] | @numbers
};

INPUT FROM @numbers | print;
INPUT FROM $greeting | print
```

```
100
200
300
hello
```

| Rule | Meaning |
|------|---------|
| **Statements end with `;`** | A script is a list of statements — `CONST` definitions, pipelines, and `LOOP` blocks — separated by `;`. A newline does **not** end a statement, which is why a pipeline can be spread over several lines. The last statement needs no `;`. |
| **`INPUT FROM <source>`** | Starts a pipeline with a source. The source can be a registered one with parameters (`echo[data="1,2,3"]`), a quoted string (`INPUT FROM "Hello"` emits that one string), a variable (`@numbers`), or a configuration value (`$greeting`). `NEW FROM` is a synonym for `INPUT FROM`. |
| **`\| segment[param=value, ...]`** | Each `\|` hands the items to the next segment. Parameters go in `[...]`; leave the brackets off when there are none (`\| print`). String values are quoted, numbers and `true`/`false` are not. |
| **A pipeline that starts with `\|`** | Has no source: its input is supplied by whoever runs it — the argument of the Python function, a `chatterlang_serve` request, or the workbench's input box. |
| **`@name`** | A variable. As a segment (`\| @numbers`) it stores every item that passes; as a source (`INPUT FROM @numbers`) it replays them. |
| **`CONST name = value`** | A constant, used as a bare word in a parameter (`multiplier=factor`). `SET` is a synonym. Constants come first in a script. |
| **`$name`** | A configuration value: `--name value` on the command line, a `TALKPIPE_`-prefixed environment variable, or `name = ...` in `~/.talkpipe.toml` (see [Configuration](configuration.md)). An unset `$name` is an error that names the key. |
| **`LOOP n TIMES { ... }`** | Runs the statements in the braces `n` times. |
| **`fork(a, b)` and `-> name`** | Send the stream down several branches; see [Forking](#forking) below. |

To see which sources and segments exist and what parameters they take, run `chatterlang_reference_browser` (see [reference tools](../api-reference/talkpipe-ref.md)). The rest of this page explains how the language is implemented and covers a few features in more depth.

## Design Philosophy

### Human-Readable Syntax

ChatterLang uses Unix-inspired syntax that makes data pipelines easier to read and write:

```chatterlang
INPUT FROM echo[data="Hello World"] | print
```

(`echo` splits its `data` on commas into separate items, so `data="Hello, World!"` would print two lines. To emit one string whole, use it as the source directly: `INPUT FROM "Hello, World!" | print`.)

### Declarative Pipeline Definition

Users specify *what* they want to achieve rather than *how* to implement it:

```chatterlang
INPUT FROM echo[data="Intro to ChatterLang::ChatterLang is a DSL for building data pipelines.--How it works::It compiles human-readable scripts to the Pipe API.", delimiter="--"]
| lambda[expression="item.split('::',1)"]
| lambda[expression="{'title': item[0].strip(), 'content': item[1].strip()}"]
| formatItem[field_list="title,content"]
| llmPrompt[source="ollama", model="llama3.2", system_prompt="Express the ideas in this text as haiku:"]
| print
```

### Component Composition

ChatterLang promotes building complex workflows by composing simple, reusable components.

## Architecture Components

### 1. Parser Layer

**File**: `src/talkpipe/chatterlang/parsers.py`

The parser converts ChatterLang text into an Abstract Syntax Tree (AST) using the Parsy parsing library. The AST includes nodes for scripts, pipelines, input sources, segments, variables, constants, loops, and forks.

#### Grammar Elements

**Sources**: Define where data comes from (three alternatives; each one starts a pipeline of its own)
```chatterlang
INPUT FROM echo[data="Hello"]
NEW FROM range[lower=0, upper=10]
INPUT FROM @variable_name
```

**Segments**: Transform data as it flows through the pipeline
```chatterlang
| print
| scale[multiplier=2]
| llmPrompt[system_prompt="Analyze this:"]
```

**Every segment is introduced by a `|`, including the first one.** A source
and the segment after it are separated by a pipe just like any other pair:

```chatterlang
INPUT FROM echo[data="1,2"] | print
```

> **Deprecated:** historically the pipe *immediately after an input source*
> could be left out — `INPUT FROM echo[data="1,2"] print` parsed as though the
> pipe were there, while every later pipe was still required, so
> `INPUT FROM echo[data="1,2"] print print` was an error. Scripts written that
> way still run, but compiling one emits a `DeprecationWarning` (and a logged
> warning) naming the line and column, and the workbench editor marks it. The
> omitted pipe will be a syntax error in TalkPipe 2.0; add the `|`.
>
> This only ever applied to a source's own first segment. A pipeline with no
> source of its own still legitimately begins with a bare segment — a fork
> branch, a fork consumer (`fork_name -> print`), or a fragment such as
> `| print | formatItem[...]` passed to `chatterlang_serve --script`.

#### `llmPrompt` conversation memory controls

For `model`, `source`, and global defaults, see [Model and source configuration](../guides/model-and-source-configuration.md).

When using `llmPrompt`, three parameters control memory compaction behavior:

- `context_token_trigger`: **when** compaction triggers.
  - If `context_token_trigger >= 1`, it is treated as an approximate absolute token threshold.
  - Values `< 1` are ignored.
- `memory_mode`: **how** compaction works once triggered.
  - `full`: no compaction
  - `recent_only`: keep only recent messages, drop older messages
  - `summary_llm`: summarize older messages with the LLM
  - `summary_deterministic`: summarize older messages with deterministic fallback logic
  - `summary_truncate`: summarize older messages by truncation
- `unsummarized_message_count`: how many recent messages are kept verbatim during compaction.
  This is a **message count**, not a user+assistant turn-pair count.
- `memory_size`: target max token count for summaries generated during compaction.

Example:

```chatterlang
| llmPrompt[
    model="llama3.2",
    source="ollama",
    memory_mode="summary_llm",
    context_token_trigger=7000,
    unsummarized_message_count=6,
    memory_size=512
  ]
| print
```

Adapter implementations get deterministic and truncate summarization from the shared prompt-adapter memory mixin.
Adapters only need to implement `complete_text_without_context(...)` when they support `memory_mode="summary_llm"`.

#### Capping the response length with `max_tokens`

`llmPrompt` and the guided-generation segments built on it (`llmScore`,
`llmExtractTerms`, `llmBinaryAnswer`) accept `max_tokens`: the most tokens the
model may generate per response. It is an **output** cap — prompt tokens do not
count — and it defaults to `None`, which leaves the backend default. Without it,
a model that fails to emit a stop token generates until its context window
fills; `timeout` only fails the pipeline, while `max_tokens` bounds the item.

```chatterlang
| llmScore[system_prompt=p, field="toanalyze", set_as="ai_eval", max_tokens=1024]
```

- It maps to `num_predict` on Ollama, `max_output_tokens` on OpenAI, and
  `max_tokens` on Anthropic (where it replaces the adapter's 4096 default).
  Adapters that generate nothing to cap (`eliza`) ignore it.
- On reasoning/thinking models (Anthropic extended thinking, OpenAI reasoning
  models, Ollama thinking models) the thinking tokens count against the cap, so
  leave room for them.
- A truncated response from a guided-generation segment such as `llmScore`
  fails schema validation rather than returning a partial score.

**Variables**: Store intermediate results
```chatterlang
INPUT FROM echo[data="1,2"] | @my_variable;    # Store results in variable
INPUT FROM @my_variable | print                # Use stored results as input
```

**Constants**: Define reusable values (`CONST` and `SET` are equivalent)
```chatterlang
CONST multiplier = 5;
SET greeting = "hello";
INPUT FROM echo[data=greeting] | print
```

**Loops**: Repeat operations multiple times
```chatterlang
INPUT FROM range[lower=0, upper=3] | @data;
LOOP 3 TIMES {
    INPUT FROM @data | scale[multiplier=2] | @data
};
INPUT FROM @data | print
```

This prints `0`, `8`, and `16`. Note the `;` after the closing brace: a loop is a statement like any other.

#### Forking

`fork(...)` sends every item down each of its branches and merges what the branches emit back into one stream. Branches are separated by commas and written **without** a leading `|`; a branch can itself be a chain of segments:

```chatterlang
INPUT FROM range[lower=1, upper=3]
| fork(scale[multiplier=10], scale[multiplier=100] | scale[multiplier=2])
| print
```

This prints `10`, `20`, `200`, and `400`. The branches run concurrently, so the order in which their results interleave is not guaranteed.

A *named* fork joins separate pipelines instead: `-> name` at the end of a pipeline feeds a fork, and `name ->` at the start of another reads from it.

```chatterlang
INPUT FROM range[lower=0, upper=2] -> nums;
INPUT FROM range[lower=10, upper=12] -> nums;
nums -> print
```

This prints `0`, `1`, `10`, and `11` (again in no guaranteed order).

### 2. Compiler Layer

**File**: `src/talkpipe/chatterlang/compiler.py`

The compiler transforms the AST into executable Python objects using the Pipe API.

#### Compilation Process

1. **Parse Script**: Convert text to AST using `script_parser`
2. **Resolve Constants**: Substitute constant values 
3. **Create Runtime**: Initialize shared state component
4. **Compile Components**: Transform AST nodes to Pipe API objects
5. **Build Pipeline**: Connect components using `|` operator

The compiler uses Python's `@singledispatch` to route different AST node types (pipelines, loops, etc.) to specialized compilation functions. A `RuntimeComponent` holds shared state such as variables and constants across the pipeline.

### 3. Registry System

**File**: `src/talkpipe/chatterlang/registry.py`

The registry maps ChatterLang identifiers to Python implementation classes. It supports both decorator-based registration and entry point discovery for plugins.

#### Registration Decorators

Components register themselves using decorators, so adding a new source or segment is trivial — in a new module or in a Jupyter notebook:

```python
from talkpipe.chatterlang import registry
from talkpipe.pipe.core import source, AbstractSegment

@registry.register_source("example_echo")
@source(delimiter=',')
def example_echo(data, delimiter):
    """Generate input from a string."""
    if delimiter is None:
        yield data
    else:
        for item in data.split(delimiter):
            yield item

@registry.register_segment("example_print")
class ExamplePrint(AbstractSegment):
    """Print and pass through each item."""
    def transform(self, input_iter):
        for x in input_iter:
            print(x)
            yield x
```

### 4. Variable Management

ChatterLang handles variables for storing and reusing intermediate data.

#### Variable Sources

```python
from talkpipe.pipe.core import AbstractSource

class VariableSource(AbstractSource):
    """Sources data from a runtime variable."""
    def __init__(self, variable_name: str):
        self.variable_name = variable_name
        self.runtime = type("Runtime", (), {"variable_store": {variable_name: []}})()

    def generate(self):
        yield from self.runtime.variable_store[self.variable_name]
```

#### Variable Assignment

```python
from talkpipe.pipe.core import AbstractSegment

class VariableSetSegment(AbstractSegment):
    """Stores pipeline data in a runtime variable."""
    def __init__(self, variable_name: str):
        self.variable_name = variable_name
        self.runtime = type("Runtime", (), {"variable_store": {}})()

    def transform(self, items):
        list_of_items = list(items)
        self.runtime.variable_store[self.variable_name] = list_of_items
        yield from list_of_items
```

#### Variable Accumulation

```python
from talkpipe.chatterlang import registry
from talkpipe.pipe.core import AbstractSegment

@registry.register_segment("example_accum")
class ExampleAccum(AbstractSegment):
    """Accumulates data across multiple pipeline runs."""
    def __init__(self, variable_name=None):
        super().__init__()
        self.accumulator = []
        self.variable_name = variable_name
        self.runtime = type("Runtime", (), {"variable_store": {}})()

    def transform(self, items):
        for item in self.accumulator:
            yield item
        for item in items:
            self.accumulator.append(item)
            if self.variable_name:
                self.runtime.variable_store.setdefault(self.variable_name, []).append(item)
            yield item
```

## Advanced Features

### 1. Comment Processing

The compiler preprocesses scripts to remove comments (text after `#` on a line) while preserving string literals.

### 2. Parameter Resolution

The compiler resolves segment and source parameters from constants and runtime variables before passing them to the underlying Pipe API components.

## Applications and Tools

### 1. Command-Line Script Runner

**File**: `src/talkpipe/app/chatterlang_script.py`

Executes ChatterLang scripts from command line:

```bash
python -m talkpipe.app.chatterlang_script --script "INPUT FROM echo[data='Hello'] | print"
```

**Features**:
- Script loading from files, configuration, or inline
- Custom module loading
- Logger configuration
- Error handling and reporting

### 2. Web-Based Workbench

**File**: `src/talkpipe/app/chatterlang_workbench.py`

Interactive development environment with:

**Features**:
- Script editor with syntax highlighting
- Real-time compilation and execution
- Interactive mode for pipeline input
- Example script library
- System logging panel
- Responsive web interface

**Example Integration**:
```python
from talkpipe.chatterlang import compile

script_text = "INPUT FROM echo[data='Hello'] | print"
compiled_instance = compile(script_text)

# Execute non-interactive scripts
is_interactive = False
if not is_interactive:
    output_iterator = compiled_instance([])
    output_text = "\n".join(str(chunk) for chunk in output_iterator)

# Handle interactive scripts
user_input = "Hello"
if is_interactive:
    output_iterator = compiled_instance([user_input])
    # Stream results back to client
```

### 3. HTTP Server for Data Processing

**File**: `src/talkpipe/app/chatterlang_serve.py`

FastAPI server that processes JSON data through ChatterLang scripts:

**Features**:
- Multi-user session management
- Configurable web forms
- Real-time streaming output
- API authentication
- Script compilation per session

**Session Integration**:
```python
from talkpipe.chatterlang import compile

class UserSession:
    def compile_script(self, script_content: str):
        """Compile ChatterLang script for this session."""
        self.compiled_script = compile(script_content)
        self.compiled_script = self.compiled_script.as_function(
            single_in=True, single_out=False
        )
```

## Example Scripts

To try ChatterLang scripts and explore examples interactively, use the **ChatterLang Workbench** (`chatterlang_workbench`), whose built-in example library and editor are described in [ChatterLang Workbench](../api-reference/chatterlang-workbench.md).

## Key Benefits

### 1. Accessibility

ChatterLang makes data pipeline creation accessible to users without Python programming experience.

### 2. Rapid Prototyping

The declarative syntax enables quick iteration and experimentation with different pipeline configurations.

### 3. Component Reusability

Registered components can be reused across different scripts and applications.

### 4. Integration Flexibility

ChatterLang scripts can be embedded in web applications, command-line tools, and automated workflows.

### 5. Debugging Support

The compilation process provides clear error messages and the workbench offers interactive debugging capabilities.

## Implementation Patterns

### 1. Decorator-Based Registration

Components self-register using decorators:

```python
from talkpipe.chatterlang import registry
from talkpipe.pipe.core import AbstractSegment

@registry.register_segment("myTransform")
class MyTransform(AbstractSegment):
    def __init__(self, param1=None):
        super().__init__()
        self.param1 = param1
    
    def transform(self, input_iter):
        for item in input_iter:
            yield f"{self.param1}: {item}"
```

### 2. Error Propagation

Compilation and runtime errors are properly handled and reported:

```python
import logging
from talkpipe.chatterlang import compile
from fastapi import HTTPException

logger = logging.getLogger(__name__)
script_text = "INPUT FROM echo[data='Hello'] | print"

try:
    compiled = compile(script_text)
    results = list(compiled([]))
except Exception as e:
    logger.error(f"Script execution failed: {e}")
    raise HTTPException(status_code=400, detail=f"Error: {e}")
```

## Conclusion

ChatterLang bridges ease of use and computational power: a natural
language-inspired syntax that compiles to the Pipe API. Its layered
design—parser, compiler, registry, and applications—keeps the system
maintainable, extensible, and backward compatible as it evolves, and its
integration with web applications, command-line tools, and interactive
environments lets TalkPipe's data processing reach a wide range of use cases.

---
Last Reviewed: 20261111