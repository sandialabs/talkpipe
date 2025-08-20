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

The parser converts ChatterLang text into an Abstract Syntax Tree (AST) using the Parsy parsing library.

#### Core Data Structures

```python
@dataclass
class ParsedScript:
    """A parsed script containing pipelines and constants."""
    pipelines: List[Union[ParsedPipeline, ParsedLoop]]
    constants: Dict[str, Any] = field(default_factory=dict)

@dataclass  
class ParsedPipeline:
    """A pipeline with input source and transform chain."""
    input_node: Optional[InputNode]
    transforms: List[Union[SegmentNode, VariableName, ForkNode]]

@dataclass
class InputNode:
    """Represents input sources like 'INPUT FROM source'."""
    source: Union[VariableName, Identifier, str]
    params: Dict[Identifier, Any]

@dataclass
class SegmentNode:
    """Represents transform operations with parameters."""
    operation: str
    params: Dict[Identifier, Any]
```

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

#### Single Dispatch Pattern

The compiler uses Python's `@singledispatch` decorator to handle different AST node types:

```python
@singledispatch
def compile(script: ParsedScript, runtime: RuntimeComponent = None) -> Callable:
    """Compile a parsed script into executable Pipeline."""

@compile.register(ParsedPipeline)
def _(pipeline: ParsedPipeline, runtime: RuntimeComponent) -> Pipeline:
    """Compile a pipeline into Pipeline object."""

@compile.register(ParsedLoop)
def _(loop: ParsedLoop, runtime: RuntimeComponent) -> Loop:
    """Compile a loop into Loop object."""
```

#### Runtime Component Integration

The compiler creates a `RuntimeComponent` that provides shared state across the pipeline:

```python
class RuntimeComponent:
    def __init__(self):
        self._variable_store = {}  # Mutable runtime variables
        self._const_store = {}     # Immutable constants
```

### 3. Registry System

**File**: `src/talkpipe/chatterlang/registry.py`

The registry maps ChatterLang identifiers to Python implementation classes.

#### Registry Structure

```python
class Registry(Generic[T]):
    def __init__(self):
        self._registry: Dict[str, Type[T]] = {}
    
    def register(self, cls: Type[T], name: str) -> None:
        self._registry[name] = cls

input_registry = Registry()    # Sources
segment_registry = Registry()  # Segments
```

#### Registration Decorators

Components register themselves using decorators.  This makes it trivial to add new sources and segments to TalkPipe, whether in new modules or in a jupyter notebook:

```python
@registry.register_source("echo")
@source(delimiter=',')
def echo(data, delimiter):
    """Generate input from a string."""
    if delimiter is None:
        yield data
    else:
        for item in data.split(delimiter):
            yield item

@registry.register_segment("print")
class Print(AbstractSegment):
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
class VariableSource(AbstractSource):
    """Sources data from a runtime variable."""
    def __init__(self, variable_name: str):
        self.variable_name = variable_name
    
    def generate(self):
        yield from self.runtime.variable_store[self.variable_name]
```

#### Variable Assignment

```python
class VariableSetSegment(AbstractSegment):
    """Stores pipeline data in a runtime variable."""
    def transform(self, items):
        list_of_items = list(items)
        self.runtime.variable_store[self.variable_name] = list_of_items
        yield from list_of_items
```

#### Variable Accumulation

```python
@registry.register_segment("accum")
class Accum(AbstractSegment):
    """Accumulates data across multiple pipeline runs."""
    def transform(self, items):
        for item in self.accumulator:
            yield item
        for item in items:
            self.accumulator.append(item)
            if self.variable_name:
                self.runtime.variable_store[self.variable_name].append(item)
            yield item
```

## Advanced Features

### 1. Script Composition

### 2. Comment Processing

The compiler includes a preprocessing step to remove comments while preserving string literals.  Any text on a line after a hash mark is considered a comment:

```python
def remove_comments(text: str) -> str:
    """Remove comments starting with # outside quoted strings."""
    result = []
    in_quotes = False
    i = 0
    while i < len(text):
        char = text[i]
        if char == '"':
            in_quotes = not in_quotes
            result.append(char)
        elif char == '#' and not in_quotes:
            # Skip to end of line
            while i < len(text) and text[i] != "\n":
                i += 1
            if i < len(text) and text[i] == "\n":
                result.append("\n")
        else:
            result.append(char)
        i += 1
    return "".join(result)
```

### 3. Parameter Resolution

The compiler resolves parameters from constants and runtime variables:

```python
def _resolve_params(params, runtime):
    """Resolve parameters using constants and variables."""
    return {
        k: runtime.const_store[params[k].name] 
           if isinstance(params[k], Identifier) 
           else params[k] 
        for k in params
    }
```

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
# Compile script
compiled_instance = compile(script_text)

# Execute non-interactive scripts
if not is_interactive:
    output_iterator = compiled_instance([])
    output_text = "\n".join(str(chunk) for chunk in output_iterator)

# Handle interactive scripts  
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
class UserSession:
    def compile_script(self, script_content: str):
        """Compile ChatterLang script for this session."""
        self.compiled_script = compile(script_content)
        self.compiled_script = self.compiled_script.asFunction(
            single_in=True, single_out=False
        )
```

## Example Scripts

All examples below are self-contained and can be pasted directly into the ChatterLang workbench to run.

### Basic Data Processing

```chatterlang
# Generate and process sample data
INPUT FROM echo[data="Alice,25,85|Bob,30,92|Charlie,22,78", delimiter="|"]
| lambda[expression="item.split(',')"]
| lambda[expression="{'name':item[0], 'age':item[1], 'score':item[2]}"]
| toDict[field_list="name:Name,age:Age,score:Score"]
| formatItem[field_list="Name,Age,Score"]
| print
```

### Variable Storage and Reuse

```chatterlang
# Demonstrate variable storage
INPUT FROM echo[data="apple,banana,cherry,date", delimiter=","]
| @fruits
| print;

INPUT FROM @fruits
| lambda[expression="len(item)"]
| formatItem[field_list="_:Length"]
| print;

INPUT FROM @fruits
| lambda[expression="item.upper()"]
| print
```

### Data Filtering and Analysis

```chatterlang
# Filter and analyze numerical data
INPUT FROM range[lower=1, upper=20]
| lambda[expression="{'number': item, 'is_even': item % 2 == 0, 'square': item ** 2}"]
| lambdaFilter[expression="item['is_even']"]
| formatItem[field_list="number:Number,square:Square"]
| print
```

### Conditional Processing

```chatterlang
# Process data with conditions
INPUT FROM echo[data="5,15,25,35,45", delimiter=","]
| cast[cast_type="int"]
| lambda[expression="{'value': item, 'category': 'small' if item < 20 else 'large'}"]
| formatItem[field_list="value:Value,category:Category"]
| print
```

### String Manipulation

```chatterlang
# Advanced string processing
INPUT FROM echo[data="The quick brown fox jumps over the lazy dog"]
| lambda[expression="item.split()"]
| flatten
| lambda[expression="{'word': item, 'length': len(item), 'vowels': sum(1 for c in item.lower() if c in 'aeiou')}"]
| lambdaFilter[expression="item['length'] > 3"]
| formatItem[field_list="word:Word,length:Length,vowels:Vowels"]
| firstN[n=5]
| print
```

### Data Aggregation

```chatterlang
# Aggregate and summarize data
INPUT FROM echo[data="10,20,30,40,50", delimiter=","]
| cast[cast_type="int"]
| toList
| @numbers;

INPUT FROM @numbers
| lambda[expression="{'count': len(item), 'sum': sum(item), 'avg': sum(item)/len(item), 'max': max(item), 'min': min(item)}"]
| formatItem[field_list="count:Count,sum:Sum,avg:Average,max:Maximum,min:Minimum"]
| print
```

### Loop Processing

```chatterlang
# Use loops to process data multiple times
INPUT FROM range[lower=1, upper=5]
| @numbers;

LOOP 3 TIMES {
    INPUT FROM @numbers
    | scale[multiplier=2]
    | @numbers
    | formatItem[field_list="_:Iteration Values"]
    | print
}
```

### Hash and Unique Processing

```chatterlang
# Demonstrate hashing and data transformation
INPUT FROM echo[data="apple,banana,apple,cherry,banana,date", delimiter=","]
| toDict[field_list="_:item"]
| hash[field_list="item", algorithm="MD5", append_as="hash_value"]
| formatItem[field_list="_:Fruit,hash_value:Hash"]
| print
```

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