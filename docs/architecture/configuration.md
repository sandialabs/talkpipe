# TalkPipe Configuration Architecture

This document describes how TalkPipe manages configuration across different environments, including configuration file formats, environment variable handling, and precedence rules.

## Overview

TalkPipe uses a layered configuration system that supports multiple sources with clear precedence rules. Configuration can come from:

1. **Command-line arguments** (including unknown arguments that get added to the configuration)
2. **Environment variables** (with `TALKPIPE_` prefix)
3. **Configuration files** (TOML format)
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
default_model_name = "llama3.2"
default_model_source = "ollama"
OLLAMA_SERVER_URL = "http://localhost:11434"

# HTTP servers (chatterlang_serve, serverag): key checked when --require_auth is set
API_KEY = "change-me"

# chatterlang_workbench
workbench_workspace = "~/talkpipe-workbench"
workbench_api_key = "change-me-too"

# Database connections (example)
mongo_connection_string = "mongodb://localhost:27017/talkpipe"
vector_db_path = "/path/to/vector/db"
```

### Configuration File Location

The configuration system loads a single TOML file from:

1. The path specified in the `path` parameter to `get_config()` 
2. Default: `~/.talkpipe.toml` (user home directory)

## Environment Variable Handling

### Environment Variable Format

All TalkPipe environment variables use the prefix `TALKPIPE_` followed by the configuration key name. Convention is to write the key in uppercase after the prefix (e.g. `TALKPIPE_DEFAULT_MODEL_NAME`), but key matching against TOML file settings is case-insensitive, so `TALKPIPE_default_model_name` and `TALKPIPE_DEFAULT_MODEL_NAME` both set the same `default_model_name` config value.

Provider SDK credentials are separate from TalkPipe config keys:
- OpenAI SDK reads `OPENAI_API_KEY`
- Anthropic SDK reads `ANTHROPIC_API_KEY`

#### Environment Variable Examples

```bash
# Logging configuration
export TALKPIPE_LOGGER_LEVELS="root:INFO,talkpipe:DEBUG"
export TALKPIPE_LOGGER_FILES="talkpipe:/tmp/talkpipe.log"

# LLM defaults
export TALKPIPE_DEFAULT_MODEL_NAME="llama3.2"
export TALKPIPE_DEFAULT_MODEL_SOURCE="ollama"
export TALKPIPE_OLLAMA_SERVER_URL="http://localhost:11434"

# HTTP server API key (chatterlang_serve / serverag with --require_auth)
export TALKPIPE_API_KEY="change-me"
```

### Environment Variable Processing

1. **Prefix Removal**: The `TALKPIPE_` prefix is stripped from the environment variable name
2. **Key Normalization**: The remaining name becomes the configuration key (matched case-insensitively against other config sources)
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

### Embedding and LLM defaults: `serverag` vs segment keys

See [Model and source configuration](../guides/model-and-source-configuration.md) for a user-focused guide to `model`, `source`, and related config keys.

Several components resolve embedding and chat model defaults from `get_config()`, all under the same four keys (see `talkpipe.util.constants`): `default_embedding_model_name`, `default_embedding_model_source`, `default_model_name`, and `default_model_source`.

- **Segment defaults** — `LLMEmbed` and `LLMPrompt` fall back to these keys when `model` / `source` arguments are omitted.
- **`serverag` / `makevectordatabase` defaults** — When you omit `--embedding_model`, `--embedding_source`, `--completion_model`, and `--completion_source`, these commands read the same four keys from the merged config.

Set them once in `~/.talkpipe.toml` (or as `TALKPIPE_*` environment variables) for one consistent set of defaults across every pipeline and CLI. Environment variables use the usual `TALKPIPE_` prefix and map to the key name after the prefix, case-insensitively (for example, `TALKPIPE_default_model_name` or `TALKPIPE_DEFAULT_MODEL_NAME` both work).

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
export OPENAI_API_KEY="sk-your-secret-key"
export ANTHROPIC_API_KEY="your-anthropic-key"

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
from talkpipe.util.config import get_config

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
export OPENAI_API_KEY="sk-dev-key"
export TALKPIPE_OLLAMA_SERVER_URL="http://localhost:11434"

# Use local configuration file for persistent settings
cat > ~/.talkpipe.toml << EOF
# Development configuration
logger_levels = "root:DEBUG"
default_model_name = "llama3.2"
default_model_source = "ollama"
workbench_load_modules = "/home/user/talkpipe-modules/my_segments.py"
EOF
```

## Troubleshooting Configuration

### Common Issues

1. **Configuration Not Loading**
   ```bash
   # Check file permissions
   ls -la ~/.talkpipe.toml
   
   # Check TOML syntax
   python -c "import tomllib; from pathlib import Path; print(tomllib.load(open(Path.home() / '.talkpipe.toml', 'rb')))"
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

## Recognized Configuration Keys

Every key TalkPipe itself reads is named in `talkpipe.util.constants` (import
the constant rather than repeating the string). Keys are matched
case-insensitively; set any of them as `key = ...` in `~/.talkpipe.toml` or as
`TALKPIPE_KEY` in the environment.

| Key | Used by |
|-----|---------|
| `default_model_name`, `default_model_source` | `llmPrompt`, `llmVisionPrompt`, `serverag`, workbench suggestions |
| `default_embedding_model_name`, `default_embedding_model_source` | `llmEmbed`, `makevectordatabase`, `serverag` |
| `OLLAMA_SERVER_URL` | every `source="ollama"` adapter |
| `MODEL2VEC_REVISION`, `MODEL2VEC_CACHE_DIR` | `source="model2vec"` embeddings |
| `llm_timeout`, `email_timeout`, `mongo_timeout` | network timeouts (seconds) for LLM, SMTP/IMAP, and MongoDB clients |
| `logger_levels`, `logger_files` | `configureLogger` / `configure_logger` |
| `API_KEY` | `chatterlang_serve` and `serverag` when `--require_auth` is set |
| `TALKPIPE_ALLOWED_ORIGINS` (environment only) | extra CORS origins for `chatterlang_serve` |
| `user_agent` | `downloadURL` and other HTTP fetches |
| `rss_url` | the `rss` source |
| `smtp_server`, `smtp_port`, `sender_email`, `recipient_email`, `email_password` | `sendEmail` |
| `imap_server`, `email_address`, `email_password` | `readEmail` |
| `mongo_connection_string` | the MongoDB segments |
| `workbench_workspace`, `workbench_load_modules`, `workbench_api_key`, `workbench_llm_suggestions`, `workbench_suggest_source`, `workbench_suggest_model` | `chatterlang_workbench` |
| `LAZY_IMPORT` | registry diagnostics only (see [Lazy loading](../api-reference/lazy-loading.md)) |

Any other key is stored and available to scripts as `$key`, but nothing in
TalkPipe reads it. A test in the repository (`tests/test_config_keys_documented.py`)
checks that every `TALKPIPE_*` variable mentioned in this document corresponds
to a key TalkPipe actually reads.

## API Reference

### Configuration Functions

#### `get_config(reload=False, path="~/.talkpipe.toml", ignore_env=False)`

```python
from talkpipe.util.config import get_config
```

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

**Note — this reconfigures the host process's logging.** `configure_logger`
(and the `configureLogger` segment, which calls it) invokes
`logging.basicConfig(level=base_level)` and, for every logger named in
`logger_levels`, clears that logger's existing handlers before attaching a
console handler. That is what you want in a script or a `chatterlang_script`
run, but if you embed talkpipe in an application that has already configured
logging, either leave `configureLogger` out of the pipeline or accept that it
replaces the handlers on the loggers it names. talkpipe itself installs only a
`logging.NullHandler` on the `talkpipe` logger at import time and never
touches the root logger unless you call this function.

This comprehensive configuration system provides flexibility for different deployment scenarios while maintaining security and ease of use.

---
Last Reviewed: 20250820