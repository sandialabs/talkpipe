# API Reference

Complete technical reference for all TalkPipe commands, components, and APIs.

## Command-Line Tools

### [ChatterlangServer / talkpipe_endpoint](chatterlang-server.md)
Create web APIs and interactive forms for processing JSON data through ChatterLang pipelines.
- REST API endpoints
- Configurable web forms  
- Real-time streaming output
- Authentication support

### [ChatterLang Workbench](chatterlang-server.md)
Interactive web interface for writing, testing, and running ChatterLang scripts.
- Real-time script execution
- Built-in documentation
- Logging and debugging tools

### [ChatterLang Script Runner](chatterlang-script.md)
Command-line tool for executing ChatterLang scripts from files or command line.
- Batch script execution
- Environment variable support
- Pipeline automation

### [Documentation Generator](talkpipe-ref.md)
Generate HTML and text documentation for all available sources and segments.
- Auto-generated reference docs
- Custom module documentation
- Export formats: HTML, text

## Core APIs

### Pipe API (Internal DSL)
Python-based pipeline construction using the `|` operator.
- Source and segment decorators
- Custom component creation
- Type safety and IDE support

### ChatterLang (External DSL)
Text-based domain-specific language for defining data processing pipelines.
- Unix-like syntax
- Variables and constants
- Loop constructs
- Multi-pipeline support

## Component Types

### Sources
Generate data at the start of pipelines:
- `echo` - Static data output
- `jsonReceiver` - Web API data input
- `rss` - RSS feed processing
- File readers (CSV, JSON, etc.)

### Segments  
Transform data within pipelines:
- `llmPrompt` - LLM interaction
- `filter` - Data filtering
- `map` - Data transformation
- `print` - Output display

### Sinks
Consume data at the end of pipelines:
- File writers
- Database connectors
- Email senders
- Web API clients

---

*For conceptual overviews and guides, see the [guides](../guides/) and [architecture](../architecture/) sections. For working examples, see the [tutorials](../tutorials/) directory.*