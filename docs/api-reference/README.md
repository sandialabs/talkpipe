# API Reference

Complete technical reference for all TalkPipe commands, components, and APIs.

## Command-Line Tools

### [makevectordatabase & serverag](../guides/makevectordatabase-and-serverag.md)
Create vector databases from documents and run RAG web servers. Minimal two-command workflow for document Q&A.
- `makevectordatabase` — Index files into LanceDB
- `serverag` — Web UI or CLI for querying

### [chatterlang_serve](chatterlang-server.md)
Create web APIs and interactive forms for processing JSON data through ChatterLang pipelines.
- REST API endpoints
- Configurable web forms  
- Real-time streaming output
- Authentication support

### [ChatterLang Workbench](chatterlang-workbench.md)
Browser-based IDE for writing, testing, and running ChatterLang scripts.
- Editor with autocomplete, hover help, and live error checking
- Real-time script execution
- Pipeline save/load workspace and next-component suggestions
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

### [Plugin Manager](talkpipe-plugin-manager.md)
Manage and inspect TalkPipe plugins installed via Python entry points.
- List installed plugins
- Plugin status monitoring
- Development workflow support

## Performance Optimization

### [Lazy Loading](lazy-loading.md)
How the registry loads components on demand (always on — no switch to flip).
- Name lookups import only the component that was asked for
- Catalogue-wide operations (`.all`, reference browser) load everything once
- How to keep your own components cheap to load
- Status of the historical `LAZY_IMPORT` flag

---

*For conceptual overviews, see the [architecture](../architecture/) sections. For working examples, see the [tutorials](../tutorials/) directory.*

Last Reviewed: 20250814