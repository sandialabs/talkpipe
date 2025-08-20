# ChatterlangServer Documentation

ChatterlangServer is TalkPipe's web API endpoint system that allows you to create interactive web interfaces and REST APIs for processing JSON data through ChatterLang pipelines. It provides both a user-friendly web form and a REST API endpoint that can integrate with external systems.

## Overview

ChatterlangServer creates a FastAPI-based web service that:
- Accepts JSON data via HTTP POST requests 
- Processes data through configurable ChatterLang scripts
- Provides real-time streaming output via Server-Sent Events
- Offers customizable web forms for user interaction
- Supports API key authentication for secure access

## Getting Started

### Using chatterlang_serve Command

The `chatterlang_serve` command is the primary way to launch ChatterlangServer:

```bash
# Basic usage - starts server on port 2025
chatterlang_serve

# Custom port and host
chatterlang_serve --port 8080 --host localhost

# With authentication
chatterlang_serve --api-key mysecretkey --require-auth

# With a ChatterLang script
chatterlang_serve --script '| lambda[expression="item.upper()", field="prompt"]'

# With form configuration
chatterlang_serve --form-config config.yaml
```

## Configuration Options

### Command Line Arguments

| Argument | Description | Default |
|----------|-------------|---------|
| `--script` | ChatterLang script to process data or and environment variable or path to a file containing the script. | None, required |
| `-p, --port` | Port to listen on | 2025 |
| `-o, --host` | Host to bind to | 0.0.0.0 |
| `--api-key` | Set API key for authentication | None |
| `--require-auth` | Require API key authentication | False |
| `--title` | Title for the web interface | "ChatterLang Server" |
| `--form-config` | Path to form configuration file | None, result is a single text property called "query" |
| `--load-module` | Path to custom module to import | None |
| `--display-property` | Property to display as user input | None, result is to display the whole JSON input |

### Form Configuration YAML/JSON Syntax

The form configuration file defines the web interface layout and form fields. It supports both YAML and JSON formats.

#### Basic Structure

```yaml
title: "My Custom Interface"
position: "bottom"           # bottom, top, left, right
height: "200px"             # CSS height value
theme: "dark"               # dark, light

fields:
  - name: "field_name"      # Required: JSON property name
    type: "text"            # Field type (see below)
    label: "Display Label"  # Optional: display label
    placeholder: "hint..."  # Optional: placeholder text
    required: true          # Optional: required field
    default: "value"        # Optional: default value
```

#### Field Types

**Text Input:**
```yaml
- name: message
  type: text                # Default type
  label: "Message"
  placeholder: "Enter your message"
  required: true
  persist: false            # Don't preserve value after submission
```

**Number Input:**
```yaml
- name: count
  type: number
  label: "Count"
  min: 1
  max: 100
  default: 10
```

**Textarea:**
```yaml
- name: description
  type: textarea
  label: "Description"
  rows: 4
  placeholder: "Enter detailed description"
```

**Select Dropdown:**
```yaml
- name: category
  type: select
  label: "Category"
  required: true
  options:
    - "Option 1"
    - "Option 2"
    - "Option 3"
```

**Checkbox:**
```yaml
- name: enabled
  type: checkbox
  label: "Enable feature"
  default: true
```

**Other Input Types:**
- `email` - Email input with validation
- `date` - Date picker
- `password` - Password input (hidden text)

#### Field Persistence

**Persistent Fields:**
By default, form fields are cleared after each submission in the streaming interface. Use the `persist` option to preserve field values:

```yaml
- name: api_model
  type: select
  label: "AI Model"
  persist: true             # Keep selected value after submission
  options:
    - "gpt-4"
    - "claude-3"
    - "gemini-pro"
    
- name: temperature
  type: number
  label: "Temperature"
  min: 0.0
  max: 2.0
  default: 0.7
  persist: true             # Keep temperature setting
  
- name: prompt
  type: textarea
  label: "Your Prompt"
  persist: false            # Clear prompt after each submission (default)
```

**Use Cases for Persistent Fields:**
- Configuration settings (model selection, parameters)
- User preferences (output format, language)
- Context that remains constant across queries
- API keys or connection settings

**Note:** The regular interface (non-streaming) preserves all field values by default. The `persist` option primarily affects the streaming chat interface.

#### Layout Positions

- `bottom` - Form at bottom, chat above (default)
- `top` - Form at top, chat below  
- `left` - Form on left side, chat on right
- `right` - Form on right side, chat on left

#### Complete Example

```yaml
title: "AI Content Generator"
position: "bottom"
height: "250px"
theme: "dark"

fields:
  - name: topic
    type: textarea
    label: "Content Topic"
    placeholder: "Describe what you want to generate content about"
    required: true
    rows: 3
    persist: false          # Clear topic after each generation
    
  - name: style
    type: select
    label: "Writing Style"
    required: true
    persist: true           # Remember selected style
    options:
      - "Professional"
      - "Casual"
      - "Technical"
      - "Creative"
      
  - name: word_count
    type: number
    label: "Target Word Count"
    min: 50
    max: 2000
    default: 500
    persist: true           # Remember word count preference
    
  - name: include_citations
    type: checkbox
    label: "Include citations"
    default: false
    persist: true           # Remember citation preference
```

## API Usage

### REST API Endpoints

**POST /process** - Submit data for processing
- Content-Type: `application/json`
- Optional Header: `X-API-Key` (if authentication enabled)
- Body: JSON object matching your form fields

**GET /history** - Retrieve processing history
- Optional Query: `?limit=10` 
- Optional Header: `X-API-Key`

**DELETE /history** - Clear processing history
- Optional Header: `X-API-Key`

**GET /health** - Health check endpoint

**GET /output-stream** - Server-Sent Events stream for real-time output

### curl Examples

**Basic POST request:**
```bash
curl -X POST http://localhost:2025/process \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello world", "value": 42}'
```

**With API key authentication:**
```bash
curl -X POST http://localhost:2025/process \
  -H "Content-Type: application/json" \
  -H "X-API-Key: mysecretkey" \
  -d '{"topic": "AI developments", "style": "Professional"}'
```

**Get processing history:**
```bash
curl http://localhost:2025/history?limit=5 \
  -H "X-API-Key: mysecretkey"
```

**Health check:**
```bash
curl http://localhost:2025/health
```

## Web Interface Workflow

### 1. Access the Interface

Navigate to `http://localhost:2025/` in your browser to access the main interface, or `http://localhost:2025/stream` for the real-time streaming interface.

### 2. Configure Authentication (if enabled)

If authentication is required, enter your API key in the provided field in the form.

### 3. Fill Out the Form

Complete the form fields based on your configuration:
- **Required fields** are marked and must be filled
- **Select fields** provide dropdown options
- **Number fields** enforce min/max constraints
- **Textarea fields** allow multi-line input

### 4. Submit Data

Click "Submit" or "Send Message" to process your data. The interface will:
- Validate required fields
- Send data to the processing endpoint
- Display success/error status
- Show real-time output in the streaming interface

### 5. View Results

- **Main interface**: Shows processing history and status messages
- **Streaming interface**: Real-time chat-like view with user messages and AI responses
- **Browser developer tools**: Network tab shows raw API responses

### 6. Stream Interface Features

The `/stream` interface provides:
- **Real-time output**: See results as they're generated
- **Chat history**: Conversation-style display of interactions
- **Auto-scroll**: Automatically scrolls to new messages (toggleable)
- **Clear chat**: Reset the conversation history
- **Responsive design**: Works on desktop and mobile

## Integration Examples

### Basic AI Chat Interface

```bash
# Start server with simple chat script
chatterlang_serve --port 8080 \
  --script '| llmPrompt[source="ollama", model="llama3.2", field="prompt"]' --display-property prompt 
```

## Advanced Features

### Custom Display Properties

Use `--display-property` to control what appears as user input in the stream interface:

```bash
chatterlang_serve --display-property "prompt" \
  --script "| llmPrompt"
```

This will show the `title` field value instead of the full JSON in the chat.

### Loading Custom Modules

Import custom Python modules before starting:

```bash
chatterlang_serve --load-module ./my_segments.py \
  --script "| myCustomSegment"
```

### Configuration Variables

Store scripts and configs in `~/.talkpipe.toml`:

```toml
my_script = "| llmPrompt[system_prompt='You are a helpful assistant']"
```

Then reference them:

```bash
chatterlang_serve --script my_script 
```

## Troubleshooting

### Common Issues

**Port already in use:**
```bash
# Try a different port
chatterlang_serve --port 8081
```

**Module not found:**
```bash
# Ensure TalkPipe is properly installed
pip install talkpipe
```

**Authentication errors:**
- Verify API key matches between client and server
- Check that `X-API-Key` header is included in requests

**Form not displaying:**
- Validate YAML/JSON syntax in form configuration
- Check browser console for JavaScript errors

### Logging

Enable detailed logging for debugging:

```bash
export TALKPIPE_logger_levels="talkpipe.app.chatterlang_serve:DEBUG"
chatterlang_serve --script "| print"
```

## Security Considerations

- **API Keys**: Use strong, unique API keys for authentication
- **Network**: Consider running behind a reverse proxy (nginx, Apache)
- **HTTPS**: Use HTTPS in production environments
- **CORS**: The server allows all origins by default - restrict in production
- **Input Validation**: Form fields provide basic validation, but validate data in your scripts
- **File Access**: Scripts can access the file system - be cautious with user inputs

## Performance Notes

- **Queue Size**: Output queue is limited to 1000 items
- **History**: Processing history is limited to 1000 entries by default
- **Connections**: Each streaming client maintains a Server-Sent Events connection
- **Memory**: Large responses are truncated in the web interface
- **Concurrency**: FastAPI handles multiple concurrent requests automatically

---
Last Reviewed: 20250813