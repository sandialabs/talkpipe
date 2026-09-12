# TalkPipe Reference Tools

**`chatterlang_reference_generator`** and **`chatterlang_reference_browser`** - Automated documentation generation and interactive reference browsing for TalkPipe components.

## Overview

These two tools discover every registered source, segment, and field segment in the TalkPipe ecosystem and document it, so you can see what is available and how to use it:

- **Reference Generator** - Scans Python code to automatically extract and document TalkPipe components
- **Reference Browser** - Interactive terminal-based browser for exploring generated documentation

## ChatterLang Reference Generator

**`chatterlang_reference_generator`** - Automated tool that documents every source and segment registered with TalkPipe — built-ins and installed plugins alike — as HTML and text.

### Usage

#### Command Line Interface

```bash
chatterlang_reference_generator [html_output text_output]
```

Provide both output paths or neither. Components are discovered through the TalkPipe registry (including `talkpipe.segments` / `talkpipe.sources` entry points), so components from any installed plugin package appear automatically — there is no argument for selecting a package or directory.

#### Default Behavior

When run without arguments, uses sensible defaults:

```bash
chatterlang_reference_generator
# Equivalent to:
# chatterlang_reference_generator ./chatterlang_ref.html ./chatterlang_ref.txt
```

#### Custom Output

```bash
chatterlang_reference_generator ./docs/reference.html ./docs/reference.txt
```

#### Include Your Own Components

Install the package that registers them (see [Extending TalkPipe](../architecture/extending-talkpipe.md)), then rerun the generator; its components are picked up through their entry points:

```bash
pip install my-talkpipe-plugin
chatterlang_reference_generator ./custom_ref.html ./custom_ref.txt
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

**HTML Output (`chatterlang_ref.html` by default)**:
- Styled, responsive web interface
- Table of contents with quick navigation
- Searchable content (browser search)
- Organized by package with collapsible sections
- Parameter lists with type annotations
- Preserved HTML formatting in docstrings

**Text Output (`chatterlang_ref.txt` by default)**:
- Plain text format for terminal viewing
- Package-organized structure
- Complete parameter documentation
- Compatible with text search tools
- Used by the reference browser

### Component Analysis

#### Parameter Processing

The generator processes function parameters as follows:

- **Excludes common parameters**: `self`, `items`, `item` 
- **Segment function handling**: Skips first parameter after `self` for segment functions
- **Type annotation extraction**: Captures Python type hints
- **Default value extraction**: Documents parameter defaults
- **Complex type handling**: Safely unparsers complex AST nodes

#### Registry-Based Analysis

Components are discovered by introspecting the live TalkPipe registry:
- **Always in sync** with what ChatterLang can actually resolve
- **Entry-point aware** — `talkpipe.segments` / `talkpipe.sources` groups are loaded first, so plugin components are included
- **Grouped aliases** — a component registered under several ChatterLang names appears once with all its names

## ChatterLang Reference Browser

**`chatterlang_reference_browser`** - Interactive terminal application for browsing TalkPipe component documentation with search, filtering, and detailed component inspection.

### Usage

#### Command Line Interface

```bash
chatterlang_reference_browser
```

The browser takes no arguments. On startup it loads component information live from the TalkPipe registry (including installed plugins), the same way the reference generator does — no documentation files are read or required.

### Interactive Commands

Once launched, the browser provides a command-line interface:

```
🔧 TalkPipe Documentation Browser
==================================================
Commands:
  list                - List all modules
  list <module>       - List components in module
  show <component>    - Show detailed component info
  search <term>       - Search components and descriptions
  help                - Show this help
  quit                - Exit browser
```

#### Module Exploration

The module list, and the counts in it, depend on what is installed — plugins add
their own modules — so treat the transcripts below as the shape of the output
rather than an inventory.

**List all modules**:
```
talkpipe> list

Available Modules (31):
------------------------------
📦 talkpipe.data.email                 (2 components)
📦 talkpipe.data.extraction            (10 components)
📦 talkpipe.data.mongo                 (2 components)
📦 talkpipe.llm.chat                   (4 components)
📦 talkpipe.pipe.fields                (13 components)
```

**List module contents** (partial module names match if unambiguous):
```
talkpipe> list talkpipe.data.email

Components in talkpipe.data.email (2):
--------------------------------------------------
🔌 readEmail                      (readEmail)
⚙️ sendEmail                      (sendEmail)
```

#### Component Details

**Show detailed component information**:
```
talkpipe> show readEmail

============================================================
📋 readEmail
============================================================
Class/Function: readEmail
Type:           Source
Module:         talkpipe.data.email
Base Classes:   AbstractSource

Description:
------------
  A source that monitors an email inbox and yields new unread emails.

  This source periodically checks for new unread emails, marks them as read,
  and yields their content and metadata. It connects using IMAP and can be
  configured to poll at specific intervals.
  ...

Parameters:
-----------
  poll_interval_minutes: int          = 10     // Minutes between email checks
  folder               : str          = INBOX  // Mailbox folder to check
  mark_as_read         : bool         = True   // Whether to mark emails as read
  limit                : int          = 100    // Maximum number of emails to fetch per check. If -1, fetch all
  unseen_only          : bool         = True   // Whether to only fetch unseen emails
  imap_server          : str | None   = None   // IMAP server address. If None, uses config
  email_address        : str | None   = None   // Email address. If None, uses config
  password             : str | None   = None   // Password. If None, uses config
  timeout              : float | None = None   // IMAP socket timeout in seconds
```

#### Search Functionality

**Search by name or description**:
```
talkpipe> search mongodb

Search Results for 'mongodb' (2 found):
------------------------------------------------------------
⚙️ mongoInsert                    (talkpipe.data.mongo)
   Insert items from the input stream into a MongoDB collect...

⚙️ mongoSearch                    (talkpipe.data.mongo)
   Search a MongoDB collection and yield results.
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
  sendEmail
```

#### Component Type Icons

- **🔌 Sources** - Data input components (e.g., `readEmail`, `rss`)
- **⚙️ Segments** - Data transformation components (e.g., `mongoSearch`, `scale`)
- **🔧 Field Segments** - Per-field transformation components

Exit with `quit` or `exit` (or Ctrl-D / Ctrl-C).

### Advanced Usage

#### Development Workflow Integration

**Local Development**:
```bash
# In your TalkPipe extension project (install it so its entry points register)
pip install -e .
chatterlang_reference_generator ./ref.html ./ref.txt
chatterlang_reference_browser
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
```
# After adding new components, verify they appear
chatterlang_reference_browser
# > list your.package.name
# > show yourNewComponent
```

## Error Handling and Troubleshooting

### Reference Generator Issues

**Wrong number of output paths** (provide both or neither):
```bash
$ chatterlang_reference_generator only.html
chatterlang_reference_generator: error: provide both html_out and text_out, or neither
```

**Unrecognized options** are rejected rather than treated as filenames:
```bash
$ chatterlang_reference_generator --output_dir ./refdocs
chatterlang_reference_generator: error: unrecognized arguments: --output_dir
```

### Reference Browser Issues

**No components found**:
```bash
$ chatterlang_reference_browser
No TalkPipe components found. Make sure plugins are properly installed.
```

**Solutions**:
- Ensure TalkPipe is properly installed: `pip install talkpipe`
- If a plugin's components are missing, reinstall the plugin package so its `talkpipe.segments` / `talkpipe.sources` entry points register

## Best Practices

### Component Development

**Documentation Standards**:
```python
from talkpipe.chatterlang import registry
from talkpipe.pipe import core

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

**Documentation workflow**: `search` to find a component, `show` it to learn its
parameters and usage, apply it in a ChatterLang script, then come back to the
browser to check anything that surprised you.

---

*For ChatterLang script development, see [ChatterLang Script](chatterlang-script.md). For interactive script development, see [ChatterLang Workbench](chatterlang-workbench.md).*

---
Last Reviewed: 20260710