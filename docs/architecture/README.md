# Architecture Documentation

Deep technical documentation covering TalkPipe's design, concepts, and implementation details.

## Core Concepts

### [Pipe API](pipe-api.md)
TalkPipe's internal Python DSL for building data processing pipelines.
- Pipeline construction with `|` operator
- Source and segment lifecycle
- Generator-based streaming architecture
- Component composition patterns

### [Data Protocol](protocol.md)
Conventions and protocols for data flowing through TalkPipe pipelines.
- Core principles: generators, arbitrary objects, cardinality
- Dictionary convention for higher-level pipelines
- Field access utilities and patterns
- Protocol layers and best practices

### [ChatterLang](chatterlang.md)
TalkPipe's external domain-specific language for defining workflows.
- Language syntax and grammar
- Compiler implementation
- Variable and constant handling
- Control flow constructs

### [Streaming Architecture](streaming.md)
How TalkPipe processes data efficiently using Python generators.
- Memory-efficient data processing
- Lazy evaluation principles
- Backpressure handling
- Error propagation

### [Metadata Stream](metadata-stream.md)
How TalkPipe handles control signals and metadata alongside regular data items.
- Metadata objects for control signals
- Opt-in metadata processing
- Flush signals and end-of-stream markers
- Backward compatibility

## Extension Points

### [Extending TalkPipe](extending-talkpipe.md)
Comprehensive guide to extending TalkPipe with custom functionality.
- Creating custom sources and segments
- Plugin architecture
- Module loading and registration
- API compatibility guidelines

### [Configuration System](configuration.md)
How TalkPipe manages configuration across different environments.
- Configuration file formats
- Environment variable handling
- Precedence rules
- Security considerations

---

*For API details, see [API Reference](../api-reference/). For working examples, see the [tutorials](../tutorials/) directory.*