# ChatterLang Script

**`chatterlang_script`** - Command-line utility for executing ChatterLang pipeline scripts from the terminal or as batch processes.

## Overview

ChatterLang Script is TalkPipe's command-line interface for running ChatterLang pipeline scripts. It compiles and executes scripts written in TalkPipe's external DSL, making it ideal for automation, data processing workflows, and integration into larger systems. The tool supports inline scripts, file-based scripts, configuration-based scripts, and custom module loading.

## Usage

### Command Line Interface

```bash
chatterlang_script --script "script_content" [options]
```

### Command Line Options

| Option | Type | Description |
|--------|------|-------------|
| `--script` | string | **Required.** The ChatterLang script to execute. Can be a file path, configuration key, or inline script content |
| `--load-module` | string | Path to custom module file to import before execution (can be specified multiple times) |
| `--logger_levels` | string | Logger level configuration in format 'logger:level,logger:level,...' |
| `--logger_files` | string | Logger file output configuration in format 'logger:file,logger:file,...' |

## Script Sources

The `--script` parameter supports three input methods, checked in this order:

### 1. File Path
If the script value is an existing file path, the file contents will be loaded and executed:

```bash
chatterlang_script --script "/path/to/my_pipeline.txt"
```

### 2. Configuration Key
If the script value exists as a key in your TalkPipe configuration (`~/.talkpipe.toml`), that configuration value will be used:

**~/.talkpipe.toml:**
```toml
data_processor = 'INPUT FROM echo[data="1,2,3,4,5"] | cast[cast_type="int"] | scale[multiplier=2] | print'
web_scraper = 'INPUT FROM "http://www.example.com" | downloadURL | htmlToText | print'
```

```bash
chatterlang_script --script data_processor
```

### 3. Inline Script
If neither file nor configuration key exists, the value is treated as inline script content:

```bash
chatterlang_script --script 'INPUT FROM "Hello World" | print'
```

## Troubleshooting

### Common Issues

**Script not found:**
- Verify file path exists and is readable
- Check configuration key spelling in `~/.talkpipe.toml`
- Ensure inline script has proper syntax

**Module import failures:**
- Verify Python module syntax
- Check that required dependencies are installed
- Ensure TalkPipe registry decorators are used correctly

**Runtime errors:**
- Check input data format matches expected types
- Verify external service connectivity (APIs, URLs)
- Review ChatterLang syntax for typos

**Performance issues:**
- Monitor memory usage with large datasets
- Consider data chunking strategies
- Profile LLM API response times

### Debug Mode

Enable comprehensive logging:

```bash
chatterlang_script \
    --logger_levels "root:DEBUG" \
    --script 'your_script_here'
```

---

*For interactive development and testing of ChatterLang scripts, see [ChatterLang Workbench](chatterlang-workbench.md). For web API integration, see [ChatterLang Server](chatterlang-server.md).*

Last Reviewed: 20250808