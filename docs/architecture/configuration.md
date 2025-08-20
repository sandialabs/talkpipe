# TalkPipe Configuration Architecture

This document describes how TalkPipe manages configuration across different environments, including configuration file formats, environment variable handling, and precedence rules.

## Overview

TalkPipe uses a layered configuration system that supports multiple sources with clear precedence rules. Configuration can come from:

3. **Command-line arguments** (including unknown arguments that get added to the configuration)
2. **Environment variables** (with `TALKPIPE_` prefix)
1. **Configuration files** (TOML format)
4. **Default values** (hard-coded in the application)

## Configuration File Formats

### TOML Configuration Files

TalkPipe primarily uses TOML (Tom's Obvious, Minimal Language) files for configuration. The default configuration file location is `~/.talkpipe.toml`.

#### Example Configuration File

```toml
# ~/.talkpipe.toml

# Logging configuration
logger_levels = "root:INFO,talkpipe:DEBUG"
logger_files = "talkpipe:/tmp/talkpipe.log,root:/tmp/app.log"

# LLM Configuration
openai_api_key = "your-api-key-here"
ollama_base_url = "http://localhost:11434"

# Server Configuration
default_port = 8080
default_host = "0.0.0.0"

# Security
api_keys = ["key1", "key2", "key3"]

# Custom scripts and modules
custom_script_path = "/path/to/your/scripts"

# Database connections (example)
mongo_uri = "mongodb://localhost:27017/talkpipe"
vector_db_path = "/path/to/vector/db"
```

### Configuration File Location

The configuration system loads a single TOML file from:

1. The path specified in the `path` parameter to `get_config()` 
2. Default: `~/.talkpipe.toml` (user home directory)

## Environment Variable Handling

### Environment Variable Format

All TalkPipe environment variables use the prefix `TALKPIPE_` followed by the configuration key name in uppercase.

#### Environment Variable Examples

```bash
# Logging configuration
export TALKPIPE_LOGGER_LEVELS="root:INFO,talkpipe:DEBUG"
export TALKPIPE_LOGGER_FILES="talkpipe:/tmp/talkpipe.log"

# Server Configuration
export TALKPIPE_DEFAULT_PORT="8080"
export TALKPIPE_DEFAULT_HOST="127.0.0.1"

# Custom scripts
export TALKPIPE_WELCOME_SCRIPT='INPUT FROM echo[data="Hello from env!"] | print'
```

### Environment Variable Processing

1. **Prefix Removal**: The `TALKPIPE_` prefix is stripped from the environment variable name
2. **Key Normalization**: The remaining name becomes the configuration key (case-sensitive)
3. **Type Preservation**: Values remain as strings and are converted by consuming code as needed

## Command-Line Arguments

### Standard Arguments

Each TalkPipe application accepts standard command-line arguments:

```bash
# Common arguments across applications
--logger_levels "root:INFO,talkpipe:DEBUG"
--logger_files "talkpipe:/tmp/talkpipe.log"
--load-module "/path/to/custom/module.py"

# Application-specific arguments
--port 8080
--host "127.0.0.1"
--script "/path/to/script.tp"
```

### Unknown Arguments as Constants

TalkPipe applications support passing arbitrary constants via unknown command-line arguments:

```bash
# These become available as constants in ChatterLang scripts
python -m talkpipe.app.chatterlang_script --script "my_script.tp" \
    --debug true \
    --api_key "my-key" \
    --timeout 30 \
    --base_url "https://api.example.com"
```

#### Constant Type Inference

The `parse_unknown_args` function automatically infers types:

- **Booleans**: `true`, `false` (case-insensitive) → `bool`
- **Integers**: Numeric strings (including negative) → `int`
- **Floats**: Strings containing decimal points → `float` (with fallback to `str`)
- **Strings**: Everything else → `str`

#### Using Constants in Scripts

Constants are available directly by name in ChatterLang scripts:

```chatterlang
# All configuration values use $key syntax
# From command line: --debug true --base_url "https://example.com"
INPUT FROM echo[data=$debug] | print
INPUT FROM echo[data=$base_url] | downloadURL | print

# From config file or environment variables
INPUT FROM echo[data=$api_key] | print
INPUT FROM echo[data=$ollama_base_url] | downloadURL | print
```

## Configuration Precedence Rules

TalkPipe has two distinct systems with different precedence rules:

### Application Configuration Precedence
For application settings (logging, server ports, etc.):

1. **Standard command-line arguments** (`--logger_levels "..."`)
2. **Environment variables** (`TALKPIPE_KEY`)
3. **Configuration file values** (`~/.talkpipe.toml`)
4. **Application defaults** (hard-coded values)

### ChatterLang Script Variable Access

**Configuration Variables** (accessed with `$key` syntax in scripts):
- Configuration file: `key = "value"` in `~/.talkpipe.toml`
- Environment variables: `TALKPIPE_key`
- Command-line arguments: `--key value`
- Precedence: Command-line > Environment variables > Configuration file values

### Example Precedence Resolution

**Application Configuration:**
```bash
# Configuration file ~/.talkpipe.toml
logger_levels = "root:WARNING"

# Environment variable
export TALKPIPE_LOGGER_LEVELS="root:INFO"

# Command line
python -m talkpipe.app.chatterlang_script --logger_levels "root:DEBUG"
```
Result: `"root:DEBUG"` (command-line argument wins)

**Script Variables:**
```bash
# Configuration file ~/.talkpipe.toml
api_key = "config-key"

# Environment variable  
export TALKPIPE_API_KEY="env-key"

# Command line argument
python -m talkpipe.app.chatterlang_script --script "test.tp" --api_key "cmd-key" --my_constant "cmd-value"
```

In the script:
- `$api_key` → `"cmd-key"` (command-line overrides environment and config)
- `$my_constant` → `"cmd-value"` (command-line argument)

### Configuration Inheritance

- Applications inherit base configuration from the config file and environment
- Each application can override specific values with its command-line arguments
- Runtime constants are application-specific and don't affect other processes

## Security Considerations

### Sensitive Data Handling

#### API Keys and Credentials

**Best Practices:**
```bash
# ✅ Use environment variables for secrets
export TALKPIPE_OPENAI_API_KEY="sk-your-secret-key"

# ❌ Avoid putting secrets in config files
# ~/.talkpipe.toml
# openai_api_key = "sk-your-secret-key"  # Don't do this

# ❌ Avoid secrets in command-line arguments (visible in process list)
# python script.py --api_key "secret"  # Don't do this
```

**Recommended Secret Management:**
- Store secrets in environment variables only
- Use secure secret management systems (HashiCorp Vault, AWS Secrets Manager, etc.)
- Rotate API keys regularly
- Use least-privilege principles

#### File Permissions

```bash
# Secure configuration file permissions
chmod 600 ~/.talkpipe.toml
chown $USER:$USER ~/.talkpipe.toml

# Secure log file permissions
chmod 640 /var/log/talkpipe.log
```

### Configuration Validation

TalkPipe applications perform validation on configuration values:

1. **Type Checking**: Ensures values match expected types
2. **Range Validation**: Validates numeric ranges (e.g., port numbers)
3. **Path Validation**: Checks file and directory existence where required
4. **Format Validation**: Validates structured data (JSON, YAML within TOML)

## Configuration Loading Process

### Startup Sequence

1. **Initialize Defaults**: Load hard-coded default values
2. **Load Configuration File**: Read and parse TOML configuration file
3. **Process Environment Variables**: Override with `TALKPIPE_*` environment variables
4. **Parse Command Line**: Process standard arguments and unknown arguments
5. **Validate Configuration**: Check required values and validate formats
6. **Cache Configuration**: Store final configuration for runtime use

### Configuration Caching

Configuration is cached after first load to improve performance:

```python
# Configuration is cached globally
config = get_config()  # Loads from file/env first time
config = get_config()  # Returns cached version

# Force reload when needed
config = get_config(reload=True)  # Re-reads from sources
```


## Configuration Best Practices

### Development Environment

```bash
# Use environment variables for local development
export TALKPIPE_LOGGER_LEVELS="root:DEBUG,talkpipe:DEBUG"
export TALKPIPE_OPENAI_API_KEY="sk-dev-key"
export TALKPIPE_DEFAULT_PORT="8080"

# Use local configuration file for persistent settings
cat > ~/.talkpipe.toml << EOF
# Development configuration
logger_levels = "root:DEBUG"
custom_modules = ["/home/user/talkpipe-modules"]
default_host = "127.0.0.1"
EOF
```

## Troubleshooting Configuration

### Common Issues

1. **Configuration Not Loading**
   ```bash
   # Check file permissions
   ls -la ~/.talkpipe.toml
   
   # Check TOML syntax
   python -c "import tomllib; print(tomllib.load(open('/path/to/home/.talkpipe.toml', 'rb')))"
   ```

2. **Environment Variables Not Working**
   ```bash
   # Check environment variables
   env | grep TALKPIPE_
   
   # Verify prefix and naming
   export TALKPIPE_LOGGER_LEVELS="root:DEBUG"  # Correct
   export LOGGER_LEVELS="root:DEBUG"           # Won't work - missing prefix
   ```

3. **Constants Not Available in Scripts**
   ```bash
   # Check that constants are being parsed
   python -m talkpipe.app.chatterlang_script --script "test.tp" --debug true
   ```

### Configuration Debugging

Enable debug logging to see configuration loading:

```bash
export TALKPIPE_LOGGER_LEVELS="talkpipe.util.config:DEBUG"
python -m talkpipe.app.chatterlang_script --script "test.tp"
```

This will show detailed information about:
- Configuration file discovery and loading
- Environment variable processing
- Argument parsing and constant extraction
- Final merged configuration values

## API Reference

### Configuration Functions

#### `get_config(reload=False, path="~/.talkpipe.toml", ignore_env=False)`
Load configuration from file and environment variables.

**Parameters:**
- `reload` (bool): Force reload from sources
- `path` (str): Configuration file path
- `ignore_env` (bool): Skip environment variable processing

**Returns:**
- `dict`: Merged configuration dictionary

#### `parse_unknown_args(unknown_args)`
Parse unknown command-line arguments as constants.

**Parameters:**
- `unknown_args` (List[str]): List of unknown arguments

**Returns:**
- `Dict[str, Any]`: Parsed constants with type inference

#### `configure_logger(logger_levels=None, base_level="WARNING", logger_files=None)`
Configure logging based on configuration values.

**Parameters:**
- `logger_levels` (str): Logger level configuration string
- `base_level` (str): Default logging level
- `logger_files` (str): File logging configuration string

This comprehensive configuration system provides flexibility for different deployment scenarios while maintaining security and ease of use.

---
Last Reviewed: 20250820