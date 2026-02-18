# ChatterLang Architecture

## Overview

ChatterLang is TalkPipe's external Domain-Specific Language (DSL) that provides a high-level, declarative syntax for building data processing pipelines. It abstracts away Python implementation details and allows users to express complex workflows using simple, human-readable commands.

While the Pipe API requires Python programming knowledge, ChatterLang enables data analysts, researchers, and non-programmers to create sophisticated pipelines through text-based scripts.

## Design Philosophy

### Human-Readable Syntax

ChatterLang uses Unix-inspired syntax that makes data pipelines easier to read and write:

```chatterlang
INPUT FROM echo[data="Hello, World!"] | print
```

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

**Sources**: Define where data comes from
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

**Variables**: Store intermediate results
```chatterlang
| @my_variable    # Store results in variable
INPUT FROM @my_variable  # Use stored results as input
```

**Constants**: Define reusable values (the following are equivalent)
```chatterlang
CONST multiplier = 5
SET api_key = "sk-123456"
```

**Loops**: Repeat operations multiple times
```chatterlang
LOOP 3 TIMES {
    INPUT FROM @data | scale[multiplier=2] | @data
}
```

**Forking**: Parallel processing branches
```chatterlang
| fork(
    | scale[multiplier=2] | print,
    | toUpperCase | print
)
```

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

Components register themselves using decorators.  This makes it trivial to add new sources and segments to TalkPipe, whether in new modules or in a jupyter notebook:

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

ChatterLang provides sophisticated variable handling for intermediate data storage and reuse.

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

### 1. Script Composition

### 2. Comment Processing

The compiler preprocesses scripts to remove comments (text after `#` on a line) while preserving string literals.

### 3. Parameter Resolution

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

To try ChatterLang scripts and explore examples interactively, use the **ChatterLang Workbench** (`chatterlang_workbench`). It provides a script editor with syntax highlighting, real-time execution, and an example script library. See [ChatterLang Workbench](../api-reference/chatterlang-workbench.md) for details.

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

### 3. Error Propagation

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

ChatterLang demonstrates how a well-designed DSL can make powerful functionality accessible to a broader audience. By providing a natural language-inspired syntax that compiles to the robust Pipe API, it bridges the gap between ease of use and computational power.

The architecture's layered design—parser, compiler, registry, and applications—creates a maintainable and extensible system that can evolve with user needs while maintaining backward compatibility.

Through its integration with web applications, command-line tools, and interactive environments, ChatterLang enables TalkPipe's data processing capabilities to be deployed across diverse use cases and user scenarios.

---
Last Reviewed: 20250817