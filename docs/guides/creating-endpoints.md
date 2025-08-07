# Creating Web Endpoints

Learn how to build web APIs and interactive interfaces using `talkpipe_endpoint`.

## Overview

`talkpipe_endpoint` creates FastAPI-based web services that:
- Accept JSON data via HTTP POST requests
- Process data through ChatterLang pipelines
- Provide real-time streaming output
- Offer customizable web forms

## Basic Usage

### Simple API Endpoint

```bash
# Start a basic endpoint that echoes input
talkpipe_endpoint --port 8080 --script "| print"
```

Test with curl:
```bash
curl -X POST http://localhost:8080/process \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello World"}'
```

### With Processing Pipeline

```bash
# Process text through an LLM
talkpipe_endpoint --port 8080 \
  --script "| llmPrompt[model='gpt-4', system_prompt='Summarize this text'] | print"
```

## Form Configuration

Create custom web forms using YAML configuration:

**simple-form.yaml:**
```yaml
title: "Text Processor"
position: "bottom"
height: "150px"
theme: "dark"

fields:
  - name: text
    type: textarea
    label: "Input Text"
    placeholder: "Enter text to process..."
    required: true
```

```bash
talkpipe_endpoint --form-config simple-form.yaml \
  --script "| llmPrompt[model='gpt-4'] | print"
```

## Advanced Examples

### Multi-Field Form

**analysis-form.yaml:**
```yaml
title: "Content Analysis"
position: "bottom"
height: "200px"
theme: "light"

fields:
  - name: content
    type: textarea
    label: "Content"
    required: true
    rows: 4
    
  - name: analysis_type
    type: select
    label: "Analysis Type"
    required: true
    options:
      - "Summary"
      - "Key Points"
      - "Sentiment Analysis"
      - "Topic Extraction"
      
  - name: max_length
    type: number
    label: "Max Length"
    min: 50
    max: 1000
    default: 200
```

**Corresponding script:**
```bash
talkpipe_endpoint --form-config analysis-form.yaml \
  --script """
  | lambda[expression="f'{item[\"analysis_type\"]}: {item[\"content\"][:100]}...'", append_as="prompt"]
  | llmPrompt[model='gpt-4', field="prompt", system_prompt="Provide the requested analysis in the specified format"]
  | print
  """
```

### Document Processing Endpoint

```bash
talkpipe_endpoint --port 9000 \
  --script """
  | downloadURL[field="url"]
  | htmlToText  
  | llmPrompt[model='gpt-4', system_prompt="Extract key information and create a structured summary"]
  | print
  """ \
  --form-config document-form.yaml
```

**document-form.yaml:**
```yaml
title: "Document Processor"
fields:
  - name: url
    type: text
    label: "Document URL"
    placeholder: "https://example.com/document.html"
    required: true
```

## Authentication

### Enable API Key Authentication

```bash
talkpipe_endpoint --api-key "your-secret-key" --require-auth \
  --script "| llmPrompt[model='gpt-4'] | print"
```

Test with authentication:
```bash
curl -X POST http://localhost:2025/process \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-secret-key" \
  -d '{"message": "Authenticated request"}'
```

## Real-Time Streaming

### Streaming Interface

Access the streaming interface at `/stream`:
```bash
talkpipe_endpoint --script "| llmPrompt[model='gpt-4'] | print"
# Open http://localhost:2025/stream
```

Features:
- Real-time output display
- Chat-like interface
- Auto-scroll toggle
- Clear chat history

### Custom Display Property

Control what appears as user input in the stream:
```bash
talkpipe_endpoint --display-property "title" \
  --script "| llmPrompt[model='gpt-4', field='content'] | print"
```

## Configuration Management

### Using Configuration Variables

Store scripts in `~/.talkpipe.toml`:
```toml
summarizer_script = "| llmPrompt[model='gpt-4', system_prompt='Create a concise summary'] | print"
```

Reference in command:
```bash
talkpipe_endpoint --script-var summarizer_script
```

### Loading Custom Modules

```bash
talkpipe_endpoint --load-module ./my_segments.py \
  --script "| myCustomProcessor | print"
```

## Error Handling

### Graceful Error Handling

```bash
talkpipe_endpoint --script """
| llmPrompt[model='gpt-4', fail_on_error=false]
| lambda[expression="item if item else 'Processing failed'"]  
| print
"""
```

### Custom Error Messages

```python
# In custom module
@core.segment()
def safeProcessor(items):
    for item in items:
        try:
            # Process item
            result = process_item(item)
            yield result
        except Exception as e:
            yield {"error": f"Processing failed: {str(e)}", "original": item}
```

## Production Considerations

### Docker Deployment

```dockerfile
FROM python:3.11-slim
RUN pip install talkpipe
COPY config.yaml /app/
WORKDIR /app
CMD ["talkpipe_endpoint", "--form-config", "config.yaml", "--script", "| llmPrompt[model='gpt-4'] | print"]
```

### Reverse Proxy Setup

**nginx.conf:**
```nginx
location /api/ {
    proxy_pass http://localhost:2025/;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
}
```

### Environment Variables

```bash
export TALKPIPE_openai_api_key="sk-..."
export TALKPIPE_default_model_name="gpt-4"

talkpipe_endpoint --script "| llmPrompt[model='gpt-4'] | print"
```

## Monitoring and Logging

### Enable Debug Logging

```bash
export TALKPIPE_logger_levels="talkpipe.app.apiendpoint:DEBUG"
talkpipe_endpoint --script "| print"
```

### Health Checks

```bash
# Check endpoint health
curl http://localhost:2025/health
```

## Best Practices

1. **Input Validation**: Use form field validation and script-level checks
2. **Error Handling**: Always include `fail_on_error=false` for robust pipelines
3. **Security**: Use API keys in production and HTTPS for sensitive data
4. **Performance**: Keep pipelines simple and use streaming for large datasets
5. **Monitoring**: Implement health checks and logging for production deployments

## Next Steps

- [Form Configuration Guide](form-configuration.md) - Advanced form design
- [Authentication & Security](authentication.md) - Secure your endpoints  
- [Deployment Guide](deployment.md) - Production deployment strategies