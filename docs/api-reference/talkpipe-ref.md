# TalkPipe Reference Tools

**`chatterlang_reference_generator`** and **`chatterlang_reference_browser`** - Automated documentation generation and interactive reference browsing for TalkPipe components.

## Overview

The TalkPipe reference tools provide comprehensive documentation generation and browsing capabilities for TalkPipe's library of sources, segments, and field segments. These tools automatically discover and document all registered components in the TalkPipe ecosystem, making it easy to explore available functionality and understand how to use each component.

- **Reference Generator** - Scans Python code to automatically extract and document TalkPipe components
- **Reference Browser** - Interactive terminal-based browser for exploring generated documentation

## ChatterLang Reference Generator

**`chatterlang_reference_generator`** - Automated tool that scans TalkPipe source code to generate comprehensive HTML and text documentation for all registered components.

### Usage

#### Command Line Interface

```bash
chatterlang_reference_generator [root_or_package] [html_output] [text_output]
```

#### Default Behavior

When run without arguments, uses sensible defaults:

```bash
chatterlang_reference_generator
# Equivalent to:
# chatterlang_reference_generator talkpipe ./talkpipe_ref.html ./talkpipe_ref.txt
```

#### Custom Output

```bash
chatterlang_reference_generator talkpipe ./docs/reference.html ./docs/reference.txt
```

#### Analyze Custom Package

```bash
chatterlang_reference_generator my_custom_package ./custom_ref.html ./custom_ref.txt
```

#### Analyze Directory

```bash
chatterlang_reference_generator ./src/my_talkpipe_extensions ./extensions.html ./extensions.txt
```

### Features

#### Automatic Component Discovery

The generator automatically detects and analyzes:

**Registered Segments**: Classes and functions decorated with:
- `@register_segment("name")`
- `@registry.register_segment("name")`
- `@segment`

**Registered Sources**: Classes and functions decorated with:
- `@register_source("name")`  
- `@registry.register_source("name")`
- `@source`

**Field Segments**: Functions decorated with:
- `@field_segment`
- `@core.field_segment()`

#### Documentation Extraction

For each discovered component, extracts:

- **Component Name**: Python class/function name
- **ChatterLang Name**: Name used in pipeline scripts
- **Component Type**: Source, Segment, or Field Segment
- **Package Location**: Dotted module path
- **Base Classes**: For class-based components
- **Parameters**: Function/constructor arguments with types and defaults
- **Docstrings**: Complete documentation with HTML formatting preserved

#### Output Formats

**HTML Output (`talkpipe_ref.html`)**:
- Styled, responsive web interface
- Table of contents with quick navigation
- Searchable content (browser search)
- Organized by package with collapsible sections
- Parameter lists with type annotations
- Preserved HTML formatting in docstrings

**Text Output (`talkpipe_ref.txt`)**:
- Plain text format for terminal viewing
- Package-organized structure
- Complete parameter documentation
- Compatible with text search tools
- Used by the reference browser

### Component Analysis

#### Parameter Processing

The generator intelligently processes function parameters:

- **Excludes common parameters**: `self`, `items`, `item` 
- **Segment function handling**: Skips first parameter after `self` for segment functions
- **Type annotation extraction**: Captures Python type hints
- **Default value extraction**: Documents parameter defaults
- **Complex type handling**: Safely unparsers complex AST nodes

#### AST-Based Analysis

Uses Python's Abstract Syntax Tree (AST) parsing for:
- **Accurate code analysis** without importing modules
- **Safe processing** of potentially problematic code
- **Cross-version compatibility** with Python 3.9+ unparse support
- **Decorator pattern recognition** across different syntax styles

## ChatterLang Reference Browser

**`chatterlang_reference_browser`** - Interactive terminal application for browsing TalkPipe component documentation with search, filtering, and detailed component inspection.

### Usage

#### Command Line Interface

```bash
chatterlang_reference_browser [doc_path]
```

#### Auto-Discovery Mode

```bash
# Automatically finds or generates documentation
chatterlang_reference_browser
```

**Discovery Process**:
1. Looks for `talkpipe_ref.txt` in current directory
2. Falls back to `unit-docs.txt` in installation directory static folder
3. Attempts to run `chatterlang_reference_generator` to create files
4. Displays error if documentation cannot be found or generated

#### Explicit Path Mode

```bash
# Use documentation from specific directory
chatterlang_reference_browser /path/to/docs/
```

### Interactive Commands

Once launched, the browser provides a command-line interface:

```
🔧 TalkPipe Documentation Browser
==================================================
Commands:
  list                - List all packages
  list <package>      - List components in package  
  show <component>    - Show detailed component info
  search <term>       - Search components and descriptions
  help                - Show this help
  quit                - Exit browser
```

#### Package Exploration

**List all packages**:
```
talkpipe> list

Available Packages (15):
------------------------------
📦 talkpipe.data.email        (3 components)
📦 talkpipe.data.html         (4 components)  
📦 talkpipe.data.mongo        (2 components)
📦 talkpipe.llm.chat          (6 components)
📦 talkpipe.pipe.basic        (12 components)
```

**List package contents**:
```
talkpipe> list talkpipe.data.email

Components in talkpipe.data.email (3):
--------------------------------------------------
🔌 readEmail             (EmailReader)
⚙️ filterEmails          (FilterEmails)  
⚙️ extractAttachments    (ExtractAttachments)
```

#### Component Details

**Show detailed component information**:
```
talkpipe> show readEmail

============================================================
📋 readEmail
============================================================
Class/Function: EmailReader
Type:           Source Class
Package:        talkpipe.data.email
Base Classes:   io.AbstractSource

Description:
------------
  Read emails from IMAP server with optional filtering.
  
  Supports both IMAP and IMAPS protocols with various
  authentication methods including OAuth2.

Parameters:
-----------
  server                   = "imap.gmail.com"
  port                     = 993
  username
  password                 = None
  use_ssl                  = True
  folder                   = "INBOX"
```

#### Search Functionality

**Search by name or description**:
```
talkpipe> search mongodb

Search Results for 'mongodb' (2 found):
------------------------------------------------------------
🔌 mongoConnect          (talkpipe.data.mongo)
   Connect to MongoDB database with authentication

⚙️ mongoQuery            (talkpipe.data.mongo)  
   Execute MongoDB queries with result processing
```

**Search examples**:
```
talkpipe> search llm        # Find LLM-related components
talkpipe> search email      # Find email processing tools  
talkpipe> search pdf        # Find PDF handling components
talkpipe> search filter     # Find filtering operations
```

### Browser Features

#### Intelligent Component Matching

**Case-insensitive search**:
- `show reademail` matches `readEmail`
- `show READEMAIL` matches `readEmail`

**Partial name suggestions**:
```
talkpipe> show email

Component 'email' not found. Did you mean:
  readEmail
  filterEmails  
  parseEmailHeaders
```

#### Component Type Icons

- **🔌 Sources** - Data input components (e.g., `readEmail`, `mongoConnect`)
- **⚙️ Segments** - Data transformation components (e.g., `filterEmails`, `scale`)

#### Smart Navigation

**Tab completion support** (where available):
- Package names in `list` commands
- Component names in `show` commands
- Common search terms

**Command shortcuts**:
- `q` or `quit` or `exit` - Exit browser
- `h` or `help` - Show help
- `l` - Shorthand for `list`  
- `s` - Shorthand for `search`

### File Format Compatibility

#### Supported Documentation Formats

**Primary Format** (`talkpipe_ref.txt`):
```text
PACKAGE: package.name
---------------------

Source Class: ComponentName
  ChatterLang Name: chatterlangName
  Docstring:
    Component description...
  Parameters:
    param1: str = "default"
    param2: int
```

**Installation Format** (`unit-docs.txt`):
- Same structure as `talkpipe_ref.txt`  
- Typically found in TalkPipe installation directory
- Used when local documentation not available

#### Parsing Capabilities

The browser handles:
- **Multi-line docstrings** with proper formatting
- **Complex parameter signatures** with type annotations
- **Nested package structures** with hierarchical organization
- **Mixed component types** (classes, functions, field segments)

### Advanced Usage

#### Development Workflow Integration

**Local Development**:
```bash
# In your TalkPipe extension project
chatterlang_reference_generator ./src/ ./ref.html ./ref.txt
chatterlang_reference_browser ./
```

**Component Discovery**:
```bash
# Find all components related to a specific domain
chatterlang_reference_browser
# Then in browser:
# > search data
# > search transform  
# > search llm
```

#### Documentation Validation

**Check component registration**:
```python
# After adding new components, verify they appear
chatterlang_reference_generator
chatterlang_reference_browser
# > list your.package.name
# > show yourNewComponent
```

## Error Handling and Troubleshooting

### Reference Generator Issues

**Package/Directory Not Found**:
```bash
$ chatterlang_reference_generator nonexistent_package
Error: Cannot find package or directory 'nonexistent_package'
```

**AST Parsing Errors**:
- Invalid Python syntax in source files
- Incompatible Python version for AST features
- File encoding issues

**Solutions**:
- Verify package installation: `python -c "import package_name"`
- Check Python version: `python --version` (3.11+ recommended)
- Validate file encoding: ensure UTF-8 encoding

### Reference Browser Issues

**Documentation Files Not Found**:
```bash
$ chatterlang_reference_browser
Error: Could not find talkpipe_ref.txt or unit-docs.txt in /current/directory
```

**Auto-Generation Failure**:
```bash
Reference files not found in current directory or installation directory.
Attempting to run 'chatterlang_reference_generator' command to generate them...
Error running talkpipe_ref command: [Errno 2] No such file or directory
```

**Solutions**:
- Ensure TalkPipe is properly installed: `pip install talkpipe`
- Verify PATH includes TalkPipe commands: `which chatterlang_reference_generator`
- Manually generate documentation: `chatterlang_reference_generator`
- Check current directory permissions for file creation

## Best Practices

### Component Development

**Documentation Standards**:
```python
@registry.register_segment("mySegment")
@core.field_segment()
def my_segment(item: str, multiplier: int = 1, 
              enabled: bool = True) -> str:
    """
    Process text items with configurable multiplication.
    
    This segment repeats input text a specified number of times,
    optionally with transformation applied.
    
    Args:
        item: Input text to process
        multiplier: Number of repetitions (default: 1)  
        enabled: Whether processing is active (default: True)
        
    Returns:
        Processed text string
        
    Examples:
        | mySegment[multiplier=3] -> repeats text 3 times
        | mySegment[enabled=false] -> passes through unchanged
    """
    if not enabled:
        return item
    return item * multiplier
```

### Browser Usage

**Effective Search Strategies**:
1. **Start broad**: `search llm` to find all LLM components
2. **Narrow down**: `search openai` for specific providers  
3. **Explore packages**: `list talkpipe.llm` to see organization
4. **Check details**: `show llmPrompt` for usage information

**Documentation Workflow**:
1. **Discovery**: Use search to find relevant components
2. **Investigation**: Use show to understand parameters and usage
3. **Implementation**: Apply knowledge in ChatterLang scripts
4. **Validation**: Return to browser to verify understanding

---

*For ChatterLang script development, see [ChatterLang Script](chatterlang-script.md). For interactive script development, see [ChatterLang Workbench](chatterlang-workbench.md).*

---
Last Reviewed: 20250814