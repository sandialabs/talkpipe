"""
FastAPI JSON Receiver Server with Configurable Form UI
Receives JSON data via HTTP and processes it with a configurable function
"""
from typing import Union
import logging
import argparse
import yaml
import asyncio
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import Optional, List, Any, Dict, Callable
from datetime import datetime
import uvicorn
import json
from pathlib import Path
import threading
from queue import Queue, Empty
from talkpipe.pipe.core import AbstractSource
from talkpipe.chatterlang import register_source
from talkpipe.chatterlang import compile
from talkpipe.util.config import get_config
from talkpipe.util.config import load_module_file


logger = logging.getLogger(__name__)

# Models
class DataResponse(BaseModel):
    status: str
    message: str
    data: Dict[str, Any]
    timestamp: datetime

class DataHistory(BaseModel):
    entries: List[dict]
    count: int

# Configuration Models
class FormField(BaseModel):
    name: str
    type: str = "text"  # text, number, select, checkbox, textarea, date, email, etc.
    label: Optional[str] = None
    placeholder: Optional[str] = None
    required: bool = False
    default: Optional[Any] = None
    options: Optional[List[str]] = None  # For select fields
    min: Optional[Union[int, float]] = None  # For number fields
    max: Optional[Union[int, float]] = None  # For number fields
    rows: Optional[int] = None  # For textarea

class FormConfig(BaseModel):
    title: str = "Data Input Form"
    fields: List[FormField] = []
    position: str = "bottom"  # bottom, top, left, right
    height: str = "300px"  # CSS height for the form panel
    theme: str = "dark"  # dark, light

class JSONReceiver:
    """JSON Data Receiver Server Class with configurable form UI"""
    
    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 9999,
        api_key: str = "your-secret-key-here",
        require_auth: bool = False,
        processor_func: Callable[[Dict[str, Any]], Any] = None,
        title: str = "JSON Data Receiver",
        history_length: int = 1000,
        form_config: Optional[Dict[str, Any]] = None
    ):
        self.host = host
        self.port = port
        self.api_key = api_key
        self.require_auth = require_auth
        self.history = []
        self.title = title
        self.history_length = history_length
        
        # Output streaming queue
        self.output_queue = Queue(maxsize=1000)
        self.output_clients = []
        
        # Parse form configuration
        if form_config:
            self.form_config = FormConfig(**form_config)
        else:
            # Default form configuration
            self.form_config = FormConfig(
                title="Data Input Form",
                fields=[
                    FormField(name="message", type="text", label="Message", placeholder="Enter message", required=True),
                    FormField(name="value", type="number", label="Value", placeholder="Enter numeric value")
                ]
            )
        
        # Set up processor function
        self.processor_function = processor_func or self._default_print_processor
        
        # Create FastAPI app instance
        self.app = FastAPI(title=f"{title} (Port {port})", version="1.0.0")

        # Mount favicon.ico directly to root
        @self.app.get("/favicon.ico")
        async def favicon():
            favicon_path = Path(__file__).parent / 'static' / 'favicon.ico'
            if favicon_path.exists():
                return FileResponse(favicon_path)
            else:
                raise HTTPException(status_code=404, detail="Favicon not found")
        
        # Configure middleware
        self._setup_middleware()
        
        # Configure routes
        self._setup_routes()
        
        # Server instance for stopping
        self.server = None
        self.server_thread = None
    
    def _setup_middleware(self):
        """Configure CORS middleware"""
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    
    def _setup_routes(self):
        """Configure all API routes"""
        
        @self.app.get("/", response_class=HTMLResponse)
        async def root():
            return self._get_html_interface()
        
        @self.app.get("/stream", response_class=HTMLResponse)
        async def stream_page():
            return self._get_stream_interface()
        
        @self.app.post("/process", response_model=DataResponse)
        async def process_json(data: Dict[str, Any], api_key: str = Depends(self._verify_api_key)):
            return await self._process_json(data)
        
        @self.app.get("/history", response_model=DataHistory)
        async def get_history(limit: int = 50, api_key: str = Depends(self._verify_api_key)):
            return self._get_history(limit)
        
        @self.app.delete("/history")
        async def clear_history(api_key: str = Depends(self._verify_api_key)):
            return self._clear_history()
        
        @self.app.get("/health")
        async def health_check():
            return {"status": "healthy", "timestamp": datetime.now(), "port": self.port}
        
        @self.app.get("/form-config")
        async def get_form_config():
            return self.form_config.dict()
        
        @self.app.get("/output-stream")
        async def output_stream():
            """Server-Sent Events endpoint for streaming output"""
            return StreamingResponse(
                self._generate_output_stream(),
                media_type="text/event-stream"
            )
    
    async def _verify_api_key(self, x_api_key: Optional[str] = Header(None)):
        """Dependency for API key validation"""
        if self.require_auth and x_api_key != self.api_key:
            raise HTTPException(status_code=403, detail="Invalid API key")
        return x_api_key
    
    def _default_print_processor(self, data: Dict[str, Any]) -> str:
        """Default processor function that just prints the data"""
        logger.info(f"Port {self.port}: Processing data with default handler")
        logger.info(f"Port {self.port}: Received data: {json.dumps(data, indent=2)}")
        output = f"Data received: {data}"
        self._add_output(output)
        return output
    
    def _add_output(self, output: str, message_type: str = "response"):
        """Add output to the streaming queue with message type"""
        try:
            # Add timestamp to output
            timestamped_output = {
                "timestamp": datetime.now().isoformat(),
                "output": output,
                "type": message_type  # "response", "user", "error"
            }
            self.output_queue.put(timestamped_output, block=False)
        except:
            # Queue is full, remove oldest item
            try:
                self.output_queue.get_nowait()
                self.output_queue.put(timestamped_output, block=False)
            except:
                pass

    def _add_user_message(self, data: Dict[str, Any]):
        """Add user message to the streaming queue"""
        user_message = {
            "timestamp": datetime.now().isoformat(),
            "output": json.dumps(data, indent=2),
            "type": "user"
        }
        try:
            self.output_queue.put(user_message, block=False)
        except:
            # Queue is full, remove oldest item
            try:
                self.output_queue.get_nowait()
                self.output_queue.put(user_message, block=False)
            except:
                pass

    async def _generate_output_stream(self):
        """Generate Server-Sent Events stream"""
        while True:
            try:
                # Check for new output
                output = self.output_queue.get(timeout=0.1)
                yield f"data: {json.dumps(output)}\n\n"
            except Empty:
                # Send heartbeat to keep connection alive
                yield f": heartbeat\n\n"
            
            await asyncio.sleep(0.1)
   
    async def _process_json(self, data: Dict[str, Any]) -> DataResponse:
        """Process JSON data and return response"""
        try:
            # Add user message to stream
            self._add_user_message(data)
            
            # Process the data
            result = self.processor_function(data)
            
            # Collect all output items for the API response
            output_items = []
            
            # If result is iterable (like a generator), process each item
            if hasattr(result, '__iter__') and not isinstance(result, (str, bytes, dict)):
                try:
                    for item in result:
                        if item is not None:
                            self._add_output(str(item), "response")
                            output_items.append(item)
                except Exception as e:
                    error_msg = f"Error processing iterator: {str(e)}"
                    self._add_output(error_msg, "error")
                    output_items.append({"error": error_msg})
            else:
                # Single result
                if result is not None:
                    self._add_output(str(result), "response")
                    output_items.append(result)
            
            # Store in history
            self.history.append({
                "timestamp": datetime.now(),
                "input": data,
                "output": output_items if output_items else "No output"
            })
            
            # Limit history length
            if len(self.history) > self.history_length:
                self.history = self.history[-self.history_length:]
            
            return DataResponse(
                status="success",
                message="Data processed successfully",
                data={
                    "input": data,
                    "output": output_items,
                    "count": len(output_items)
                },
                timestamp=datetime.now()
            )
        except Exception as e:
            error_msg = f"Error processing data: {str(e)}"
            self._add_output(error_msg, "error")
            logger.error(f"Port {self.port}: {error_msg}")
            raise HTTPException(status_code=500, detail=error_msg)
    
    def _get_history(self, limit: int) -> DataHistory:
        """Get processing history"""
        entries = self.history[-limit:] if limit > 0 else self.history
        return DataHistory(entries=entries, count=len(entries))
    
    def _clear_history(self):
        """Clear processing history"""
        self.history.clear()
        logger.info(f"Port {self.port}: History cleared")
        return {"status": "success", "message": "History cleared"}
    
    def _generate_form_fields(self) -> str:
        """Generate HTML for form fields based on configuration"""
        fields_html = []
        
        for field in self.form_config.fields:
            label = field.label or field.name.capitalize()
            required = "required" if field.required else ""
            
            if field.type == "select" and field.options:
                field_html = f'''
                <div class="form-group">
                    <label for="{field.name}">{label}:</label>
                    <select name="{field.name}" id="{field.name}" {required}>
                        <option value="">Choose...</option>
                        {"".join(f'<option value="{opt}">{opt}</option>' for opt in field.options)}
                    </select>
                </div>
                '''
            elif field.type == "textarea":
                rows = field.rows or 3
                field_html = f'''
                <div class="form-group">
                    <label for="{field.name}">{label}:</label>
                    <textarea name="{field.name}" id="{field.name}" rows="{rows}" 
                              placeholder="{field.placeholder or ''}" {required}>{field.default or ''}</textarea>
                </div>
                '''
            elif field.type == "checkbox":
                checked = "checked" if field.default else ""
                field_html = f'''
                <div class="form-group checkbox-group">
                    <label>
                        <input type="checkbox" name="{field.name}" id="{field.name}" {checked}>
                        {label}
                    </label>
                </div>
                '''
            else:
                # Default input types (text, number, date, email, etc.)
                min_attr = f'min="{field.min}"' if field.min is not None else ""
                max_attr = f'max="{field.max}"' if field.max is not None else ""
                default_val = f'value="{field.default}"' if field.default is not None else ""
                
                field_html = f'''
                <div class="form-group">
                    <label for="{field.name}">{label}:</label>
                    <input type="{field.type}" name="{field.name}" id="{field.name}" 
                           placeholder="{field.placeholder or ''}" {required} {min_attr} {max_attr} {default_val}>
                </div>
                '''
            
            fields_html.append(field_html)
        
        return "\n".join(fields_html)
    
    def _get_stream_interface(self) -> str:
        """Generate streaming HTML interface with chat-like layout"""
        position = self.form_config.position
        height = self.form_config.height
        theme = self.form_config.theme
        
        # Theme colors
        if theme == "dark":
            bg_color = "#1e1e1e"
            text_color = "#ffffff"
            input_bg = "#2d2d2d"
            border_color = "#444"
            button_bg = "#0066cc"
            button_hover = "#0052a3"
            output_bg = "#0a0a0a"
            output_text = "#00ff00"
            user_msg_bg = "#2d4a87"
            response_msg_bg = "#2d2d2d"
            error_msg_bg = "#8b2635"
        else:
            bg_color = "#f5f5f5"
            text_color = "#333333"
            input_bg = "#ffffff"
            border_color = "#ddd"
            button_bg = "#0066cc"
            button_hover = "#0052a3"
            output_bg = "#ffffff"
            output_text = "#333333"
            user_msg_bg = "#e3f2fd"
            response_msg_bg = "#f5f5f5"
            error_msg_bg = "#ffebee"
        
        auth_header = '''
            <div class="auth-section">
                <label for="apiKey">API Key:</label>
                <input type="password" id="apiKey" placeholder="Enter API key">
            </div>
        ''' if self.require_auth else ''
        
        form_fields = self._generate_form_fields()
        
        return f'''
        <!DOCTYPE html>
        <html>
        <head>
            <title>{self.title} - Stream</title>
            <style>
                * {{
                    margin: 0;
                    padding: 0;
                    box-sizing: border-box;
                }}
                
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                    background-color: {bg_color};
                    color: {text_color};
                    height: 100vh;
                    display: flex;
                    flex-direction: column;
                }}
                
                .header {{
                    background-color: {input_bg};
                    border-bottom: 1px solid {border_color};
                    padding: 1rem;
                    text-align: center;
                }}
                
                .main-container {{
                    display: flex;
                    flex: 1;
                    overflow: hidden;
                }}
                
                .form-panel {{
                    width: 350px;
                    background-color: {input_bg};
                    border-right: 1px solid {border_color};
                    padding: 1rem;
                    overflow-y: auto;
                }}
                
                .chat-panel {{
                    flex: 1;
                    display: flex;
                    flex-direction: column;
                    background-color: {output_bg};
                }}
                
                .chat-messages {{
                    flex: 1;
                    padding: 1rem;
                    overflow-y: auto;
                    display: flex;
                    flex-direction: column;
                    gap: 0.5rem;
                }}
                
                .message {{
                    max-width: 70%;
                    padding: 0.75rem 1rem;
                    border-radius: 1rem;
                    margin: 0.25rem 0;
                    word-wrap: break-word;
                    position: relative;
                }}
                
                .message.user {{
                    background-color: {user_msg_bg};
                    color: white;
                    align-self: flex-end;
                    margin-left: auto;
                }}
                
                .message.response {{
                    background-color: {response_msg_bg};
                    color: {output_text};
                    align-self: flex-start;
                    margin-right: auto;
                }}
                
                .message.error {{
                    background-color: {error_msg_bg};
                    color: white;
                    align-self: flex-start;
                    margin-right: auto;
                }}
                
                .message-timestamp {{
                    font-size: 0.75rem;
                    opacity: 0.7;
                    margin-bottom: 0.25rem;
                }}
                
                .message-content {{
                    white-space: pre-wrap;
                    font-family: 'Segoe UI', system-ui, sans-serif;
                }}
                
                .message.user .message-content {{
                    font-family: 'SF Mono', Monaco, 'Cascadia Code', 'Roboto Mono', Consolas, 'Courier New', monospace;
                    font-size: 0.9rem;
                }}
                
                .form-group {{
                    margin-bottom: 1rem;
                }}
                
                .form-group label {{
                    display: block;
                    margin-bottom: 0.5rem;
                    font-weight: 500;
                }}
                
                .form-group input,
                .form-group textarea,
                .form-group select {{
                    width: 100%;
                    padding: 0.75rem;
                    border: 1px solid {border_color};
                    border-radius: 0.5rem;
                    background-color: {input_bg};
                    color: {text_color};
                    font-size: 1rem;
                }}
                
                .form-group input:focus,
                .form-group textarea:focus,
                .form-group select:focus {{
                    outline: none;
                    border-color: {button_bg};
                    box-shadow: 0 0 0 2px {button_bg}33;
                }}
                
                .submit-btn {{
                    width: 100%;
                    padding: 0.75rem;
                    background-color: {button_bg};
                    color: white;
                    border: none;
                    border-radius: 0.5rem;
                    font-size: 1rem;
                    cursor: pointer;
                    transition: background-color 0.2s;
                }}
                
                .submit-btn:hover {{
                    background-color: {button_hover};
                }}
                
                .submit-btn:disabled {{
                    background-color: #666;
                    cursor: not-allowed;
                }}
                
                .controls {{
                    padding: 1rem;
                    border-top: 1px solid {border_color};
                    background-color: {input_bg};
                    display: flex;
                    gap: 1rem;
                    align-items: center;
                }}
                
                .control-btn {{
                    padding: 0.5rem 1rem;
                    background-color: {button_bg};
                    color: white;
                    border: none;
                    border-radius: 0.25rem;
                    cursor: pointer;
                    font-size: 0.9rem;
                }}
                
                .control-btn:hover {{
                    background-color: {button_hover};
                }}
                
                .status {{
                    padding: 0.75rem;
                    margin: 1rem 0;
                    border-radius: 0.5rem;
                    display: none;
                }}
                
                .status.success {{
                    background-color: #d4edda;
                    color: #155724;
                    border: 1px solid #c3e6cb;
                }}
                
                .status.error {{
                    background-color: #f8d7da;
                    color: #721c24;
                    border: 1px solid #f5c6cb;
                }}
                
                .auth-section {{
                    margin-bottom: 1rem;
                    padding-bottom: 1rem;
                    border-bottom: 1px solid {border_color};
                }}
                
                .initial-message {{
                    text-align: center;
                    padding: 2rem;
                    color: {text_color};
                    opacity: 0.6;
                    font-style: italic;
                }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>{self.form_config.title}</h1>
            </div>
            
            <div class="main-container">
                <div class="form-panel">
                    {auth_header}
                    
                    <form id="dataForm">
                        {form_fields}
                        <button type="submit" class="submit-btn" id="submitBtn">Send Message</button>
                    </form>
                    
                    <div id="status" class="status"></div>
                </div>
                
                <div class="chat-panel">
                    <div class="chat-messages" id="chatMessages">
                        <div class="initial-message">
                            Welcome! Send a message to start the conversation.
                        </div>
                    </div>
                    
                    <div class="controls">
                        <button class="control-btn" onclick="clearChat()">Clear Chat</button>
                        <button class="control-btn" onclick="toggleAutoScroll()" id="autoScrollBtn">Auto-scroll: ON</button>
                        <span id="connectionStatus">Connecting...</span>
                    </div>
                </div>
            </div>
            
            <script>
                let eventSource = null;
                let autoScroll = true;
                
                function initSSE() {{
                    eventSource = new EventSource('/output-stream');
                    
                    eventSource.onopen = function(event) {{
                        document.getElementById('connectionStatus').textContent = 'Connected';
                        document.getElementById('connectionStatus').style.color = 'green';
                    }};
                    
                    eventSource.onmessage = function(event) {{
                        try {{
                            const data = JSON.parse(event.data);
                            addMessage(data.output, data.type || 'response', data.timestamp);
                        }} catch (e) {{
                            console.error('Error parsing SSE data:', e);
                        }}
                    }};
                    
                    eventSource.onerror = function(event) {{
                        document.getElementById('connectionStatus').textContent = 'Connection error';
                        document.getElementById('connectionStatus').style.color = 'red';
                    }};
                }}
                
                function addMessage(content, type, timestamp) {{
                    const messagesContainer = document.getElementById('chatMessages');
                    
                    // Remove initial message if it exists
                    const initialMessage = messagesContainer.querySelector('.initial-message');
                    if (initialMessage) {{
                        initialMessage.remove();
                    }}
                    
                    const messageDiv = document.createElement('div');
                    messageDiv.className = `message ${{type}}`;
                    
                    const timestampDiv = document.createElement('div');
                    timestampDiv.className = 'message-timestamp';
                    const time = new Date(timestamp).toLocaleTimeString();
                    timestampDiv.textContent = time;
                    
                    const contentDiv = document.createElement('div');
                    contentDiv.className = 'message-content';
                    contentDiv.textContent = content;
                    
                    messageDiv.appendChild(timestampDiv);
                    messageDiv.appendChild(contentDiv);
                    
                    messagesContainer.appendChild(messageDiv);
                    
                    // Remove old messages if too many (keep last 1000)
                    while (messagesContainer.children.length > 1000) {{
                        messagesContainer.removeChild(messagesContainer.firstChild);
                    }}
                    
                    if (autoScroll) {{
                        messagesContainer.scrollTop = messagesContainer.scrollHeight;
                    }}
                }}
                
                function clearChat() {{
                    const messagesContainer = document.getElementById('chatMessages');
                    messagesContainer.innerHTML = '<div class="initial-message">Chat cleared. Send a message to continue.</div>';
                }}
                
                function toggleAutoScroll() {{
                    autoScroll = !autoScroll;
                    document.getElementById('autoScrollBtn').textContent = `Auto-scroll: ${{autoScroll ? 'ON' : 'OFF'}}`;
                }}
                
                async function submitForm(event) {{
                    event.preventDefault();
                    const form = document.getElementById('dataForm');
                    const status = document.getElementById('status');
                    const submitBtn = document.getElementById('submitBtn');
                    const formData = new FormData(form);
                    
                    // Build JSON object from form data
                    const data = {{}};
                    for (const [key, value] of formData.entries()) {{
                        // Skip API key field
                        if (key === 'apiKey') continue;
                        
                        // Handle different input types
                        const input = form.elements[key];
                        if (input.type === 'number') {{
                            data[key] = value ? parseFloat(value) : null;
                        }} else if (input.type === 'checkbox') {{
                            data[key] = input.checked;
                        }} else {{
                            data[key] = value;
                        }}
                    }}
                    
                    const headers = {{
                        'Content-Type': 'application/json'
                    }};
                    
                    {("if (document.getElementById('apiKey')?.value) {" + 
                      "headers['X-API-Key'] = document.getElementById('apiKey').value;" + 
                      "}") if self.require_auth else ""}
                    
                    submitBtn.disabled = true;
                    submitBtn.textContent = 'Sending...';
                    
                    try {{
                        const response = await fetch('/process', {{
                            method: 'POST',
                            headers: headers,
                            body: JSON.stringify(data)
                        }});
                        
                        const result = await response.json();
                        
                        status.style.display = 'block';
                        if (response.ok) {{
                            status.className = 'status success';
                            status.textContent = 'Message sent successfully';
                        }} else {{
                            status.className = 'status error';
                            status.textContent = 'Error: ' + result.detail;
                        }}
                    }} catch (error) {{
                        status.style.display = 'block';
                        status.className = 'status error';
                        status.textContent = 'Error: ' + error.message;
                    }}
                    
                    submitBtn.disabled = false;
                    submitBtn.textContent = 'Send Message';
                    
                    setTimeout(() => {{
                        status.style.display = 'none';
                    }}, 3000);
                }}
                
                // Event listeners
                document.getElementById('dataForm').addEventListener('submit', submitForm);
                
                // Initialize SSE on page load
                initSSE();
            </script>
        </body>
        </html>
        '''
    
    def _get_html_interface(self) -> str:
        """Generate HTML interface with configurable form"""
        position = self.form_config.position
        height = self.form_config.height
        theme = self.form_config.theme
        
        # CSS for different positions
        position_styles = {
            "bottom": f"bottom: 0; left: 0; right: 0; height: {height};",
            "top": f"top: 0; left: 0; right: 0; height: {height};",
            "left": f"top: 0; left: 0; bottom: 0; width: {height};",
            "right": f"top: 0; right: 0; bottom: 0; width: {height};"
        }
        
        form_style = position_styles.get(position, position_styles["bottom"])
        
        # Theme colors
        if theme == "dark":
            bg_color = "#1e1e1e"
            text_color = "#ffffff"
            input_bg = "#2d2d2d"
            border_color = "#444"
            button_bg = "#0066cc"
            button_hover = "#0052a3"
        else:
            bg_color = "#f5f5f5"
            text_color = "#333333"
            input_bg = "#ffffff"
            border_color = "#ddd"
            button_bg = "#0066cc"
            button_hover = "#0052a3"
        
        auth_header = '''
            <div class="auth-section">
                <label for="apiKey">API Key:</label>
                <input type="password" id="apiKey" placeholder="Enter API key">
            </div>
        ''' if self.require_auth else ''
        
        form_fields = self._generate_form_fields()
        
        return f'''
        <!DOCTYPE html>
        <html>
        <head>
            <title>{self.title}</title>
            <style>
                * {{
                    margin: 0;
                    padding: 0;
                    box-sizing: border-box;
                }}
                
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                    background-color: #f0f0f0;
                    color: #333;
                    height: 100vh;
                    overflow: hidden;
                }}
                
                .main-content {{
                    height: calc(100vh - {height});
                    padding: 20px;
                    overflow-y: auto;
                    background-color: #f8f9fa;
                }}
                
                .info-section {{
                    background-color: white;
                    border-radius: 8px;
                    padding: 20px;
                    margin-bottom: 20px;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                }}
                
                .endpoint-info {{
                    background-color: #f8f9fa;
                    padding: 10px;
                    border-radius: 4px;
                    font-family: monospace;
                    font-size: 14px;
                    margin: 10px 0;
                    border: 1px solid #dee2e6;
                }}
                
                .history-section {{
                    background-color: white;
                    border-radius: 8px;
                    padding: 20px;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                }}
                
                .history-item {{
                    background-color: #f8f9fa;
                    padding: 10px;
                    margin: 5px 0;
                    border-radius: 4px;
                    font-family: monospace;
                    font-size: 12px;
                    white-space: pre-wrap;
                }}
                
                .form-panel {{
                    position: fixed;
                    {form_style}
                    background-color: {input_bg};
                    border: 1px solid {border_color};
                    padding: 20px;
                    box-shadow: 0 -2px 10px rgba(0,0,0,0.1);
                    overflow-y: auto;
                }}
                
                .form-container {{
                    display: flex;
                    flex-direction: column;
                    height: 100%;
                }}
                
                .form-header {{
                    margin-bottom: 15px;
                }}
                
                .form-header h3 {{
                    color: {text_color};
                    margin: 0;
                }}
                
                .form-content {{
                    flex: 1;
                    display: flex;
                    flex-wrap: wrap;
                    gap: 15px;
                    overflow-y: auto;
                    margin-bottom: 15px;
                }}
                
                .form-group {{
                    min-width: 200px;
                    flex: 1;
                }}
                
                .form-group label {{
                    display: block;
                    margin-bottom: 5px;
                    font-weight: 500;
                    color: {text_color};
                }}
                
                .form-group input,
                .form-group textarea,
                .form-group select {{
                    width: 100%;
                    padding: 8px 12px;
                    border: 1px solid {border_color};
                    border-radius: 4px;
                    background-color: {input_bg};
                    color: {text_color};
                    font-size: 14px;
                }}
                
                .form-group input:focus,
                .form-group textarea:focus,
                .form-group select:focus {{
                    outline: none;
                    border-color: {button_bg};
                    box-shadow: 0 0 0 2px {button_bg}33;
                }}
                
                .form-actions {{
                    display: flex;
                    gap: 10px;
                    align-items: center;
                }}
                
                .submit-btn {{
                    padding: 10px 20px;
                    background-color: {button_bg};
                    color: white;
                    border: none;
                    border-radius: 4px;
                    cursor: pointer;
                    font-size: 14px;
                    transition: background-color 0.2s;
                }}
                
                .submit-btn:hover {{
                    background-color: {button_hover};
                }}
                
                .submit-btn:disabled {{
                    background-color: #6c757d;
                    cursor: not-allowed;
                }}
                
                .status {{
                    padding: 8px 12px;
                    border-radius: 4px;
                    font-size: 14px;
                    display: none;
                }}
                
                .status.success {{
                    background-color: #d4edda;
                    color: #155724;
                    border: 1px solid #c3e6cb;
                }}
                
                .status.error {{
                    background-color: #f8d7da;
                    color: #721c24;
                    border: 1px solid #f5c6cb;
                }}
                
                .auth-section {{
                    margin-bottom: 15px;
                    padding-bottom: 15px;
                    border-bottom: 1px solid {border_color};
                }}
                
                .checkbox-group {{
                    display: flex;
                    align-items: center;
                }}
                
                .checkbox-group input {{
                    width: auto;
                    margin-right: 8px;
                }}
                
                .form-minimized {{
                    height: 50px !important;
                    overflow: hidden;
                }}
                
                .form-minimized .form-content,
                .form-minimized .form-actions {{
                    display: none;
                }}
                
                @media (max-width: 768px) {{
                    .form-content {{
                        flex-direction: column;
                    }}
                    
                    .form-group {{
                        min-width: 100%;
                    }}
                }}
            </style>
        </head>
        <body>
            <div class="main-content">
                <div class="info-section">
                    <h1>{self.title}</h1>
                    <p>Submit JSON data using the form below or send POST requests to:</p>
                    <div class="endpoint-info">POST http://{self.host}:{self.port}/process</div>
                    {"<p>Authentication required: Include 'X-API-Key' header</p>" if self.require_auth else ""}
                    <p>View API documentation at: <a href="/docs">/docs</a></p>
                    <p>View streaming interface at: <a href="/stream">/stream</a></p>
                </div>
                
                <div class="history-section">
                    <h2>Recent Submissions</h2>
                    <button onclick="fetchHistory()">Refresh History</button>
                    <button onclick="clearHistory()">Clear History</button>
                    <div id="history"></div>
                </div>
            </div>
            
            <div class="form-panel" id="formPanel">
                <div class="form-container">
                    <div class="form-header">
                        <h3>{self.form_config.title}</h3>
                    </div>
                    
                    {auth_header}
                    
                    <form id="dataForm">
                        <div class="form-content">
                            {form_fields}
                        </div>
                        
                        <div class="form-actions">
                            <button type="submit" class="submit-btn" id="submitBtn">Submit</button>
                            <div id="status" class="status"></div>
                        </div>
                    </form>
                </div>
            </div>
            
            <script>
                async function submitForm(event) {{
                    event.preventDefault();
                    const form = document.getElementById('dataForm');
                    const status = document.getElementById('status');
                    const submitBtn = document.getElementById('submitBtn');
                    const formData = new FormData(form);
                    
                    // Build JSON object from form data
                    const data = {{}};
                    for (const [key, value] of formData.entries()) {{
                        // Skip API key field
                        if (key === 'apiKey') continue;
                        
                        // Handle different input types
                        const input = form.elements[key];
                        if (input.type === 'number') {{
                            data[key] = value ? parseFloat(value) : null;
                        }} else if (input.type === 'checkbox') {{
                            data[key] = input.checked;
                        }} else {{
                            data[key] = value;
                        }}
                    }}
                    
                    const headers = {{
                        'Content-Type': 'application/json'
                    }};
                    
                    {("if (document.getElementById('apiKey')?.value) {" + 
                      "headers['X-API-Key'] = document.getElementById('apiKey').value;" + 
                      "}") if self.require_auth else ""}
                    
                    submitBtn.disabled = true;
                    submitBtn.textContent = 'Submitting...';
                    
                    try {{
                        const response = await fetch('/process', {{
                            method: 'POST',
                            headers: headers,
                            body: JSON.stringify(data)
                        }});
                        
                        const result = await response.json();
                        
                        status.style.display = 'block';
                        if (response.ok) {{
                            status.className = 'status success';
                            status.textContent = 'Success: ' + result.message;
                            fetchHistory();
                        }} else {{
                            status.className = 'status error';
                            status.textContent = 'Error: ' + result.detail;
                        }}
                    }} catch (error) {{
                        status.style.display = 'block';
                        status.className = 'status error';
                        status.textContent = 'Error: ' + error.message;
                    }}
                    
                    submitBtn.disabled = false;
                    submitBtn.textContent = 'Submit';
                    
                    setTimeout(() => {{
                        status.style.display = 'none';
                    }}, 3000);
                }}
                
                async function fetchHistory() {{
                    const headers = {{}};
                    {("if (document.getElementById('apiKey')?.value) {" + 
                      "headers['X-API-Key'] = document.getElementById('apiKey').value;" + 
                      "}") if self.require_auth else ""}
                    
                    try {{
                        const response = await fetch('/history?limit=10', {{ headers }});
                        const data = await response.json();
                        
                        const historyDiv = document.getElementById('history');
                        if (data.entries && data.entries.length > 0) {{
                            historyDiv.innerHTML = data.entries
                                .reverse()
                                .map(entry => `<div class="history-item">${{JSON.stringify(entry, null, 2)}}</div>`)
                                .join('');
                        }} else {{
                            historyDiv.innerHTML = '<p>No history available</p>';
                        }}
                    }} catch (error) {{
                        console.error('Error fetching history:', error);
                    }}
                }}
                
                async function clearHistory() {{
                    const headers = {{}};
                    {("if (document.getElementById('apiKey')?.value) {" + 
                      "headers['X-API-Key'] = document.getElementById('apiKey').value;" + 
                      "}") if self.require_auth else ""}
                    
                    try {{
                        await fetch('/history', {{ method: 'DELETE', headers }});
                        fetchHistory();
                    }} catch (error) {{
                        console.error('Error clearing history:', error);
                    }}
                }}
                
                // Handle Enter key to submit form
                document.getElementById('dataForm').addEventListener('keypress', function(event) {{
                    if (event.key === 'Enter' && !event.shiftKey && event.target.tagName !== 'TEXTAREA') {{
                        event.preventDefault();
                        submitForm(event);
                    }}
                }});
                
                // Attach event listener to form
                document.getElementById('dataForm').addEventListener('submit', submitForm);
                
                // Load history on page load
                fetchHistory();
            </script>
        </body>
        </html>
        '''
    
    def set_processor_function(self, func: Callable[[Dict[str, Any]], Any]):
        """Set the function used to process incoming JSON data"""
        self.processor_function = func
        logger.info(f"Port {self.port}: Processor function set to: {func.__name__}")
    
    def start(self, background: bool = False):
        """Start the FastAPI server"""
        logger.info(f"Starting JSON Data Receiver on http://{self.host}:{self.port}")
        logger.info(f"Main interface: http://{self.host}:{self.port}/")
        logger.info(f"Streaming interface: http://{self.host}:{self.port}/stream")
        logger.info(f"API documentation: http://{self.host}:{self.port}/docs")
        if self.require_auth:
            logger.info(f"Port {self.port}: API key authentication: ENABLED")
        
        processor_name = self.processor_function.__name__ 
        logger.info(f"Port {self.port}: Using processor function: {processor_name}")
        
        if background:
            self.server_thread = threading.Thread(
                target=lambda: uvicorn.run(self.app, host=self.host, port=self.port),
                daemon=True
            )
            self.server_thread.start()
            logger.info(f"Port {self.port}: Server started in background thread")
        else:
            uvicorn.run(self.app, host=self.host, port=self.port)
    
    def stop(self):
        """Stop the server (only works if started in background)"""
        if self.server_thread and self.server_thread.is_alive():
            logger.info(f"Port {self.port}: Stopping server...")
            # Note: uvicorn doesn't provide a clean stop method when run this way
            # For production use, consider using uvicorn.Server with proper lifecycle management

def load_form_config(config_path: str) -> Dict[str, Any]:
    """Load form configuration from YAML or JSON file"""
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")
    
    with open(path, 'r') as f:
        if path.suffix in ['.yaml', '.yml']:
            return yaml.safe_load(f)
        elif path.suffix == '.json':
            return json.load(f)
        else:
            raise ValueError(f"Unsupported configuration file format: {path.suffix}")

@register_source("jsonReceiver")
class JSONReceiverSegment(AbstractSource):
    """Segment for receiving JSON data via FastAPI with configurable form"""
    
    def __init__(self, port: Union[int,str] = 9999, host: str = "0.0.0.0", 
                 api_key: str = None, require_auth: bool = False,
                 form_config: Union[str, Dict[str, Any]] = None):
        super().__init__()
        self.port = int(port)
        self.host = host
        self.api_key = api_key
        self.require_auth = require_auth
        self.queue = Queue(maxsize=1000)
        
        # Load form configuration if provided
        if isinstance(form_config, str):
            # Check if it's a config variable
            if form_config.startswith('$'):
                config_data = get_config(form_config[1:])
                if config_data:
                    form_config = json.loads(config_data) if isinstance(config_data, str) else config_data
                else:
                    # Try loading as file path
                    form_config = load_form_config(form_config[1:])
            else:
                # Load from file
                form_config = load_form_config(form_config)
        
        self.receiver = JSONReceiver(
            host=host,
            port=self.port,
            api_key=api_key,
            require_auth=require_auth,
            title=f"JSON Receiver Segment (Port {port})",
            processor_func=self.process_data,
            form_config=form_config
        )
        self.receiver.start(background=True)
        logger.info(f"Finished initializing JSONReceiverSegment on port {port}")

    def process_data(self, data: Dict[str, Any]) -> str:
        """Process incoming JSON data and add it to the queue"""
        try:
            self.queue.put(data, block=True, timeout=60)
            result = f"Data received and queued: {data}"
            # Add to output stream if receiver has the method
            if hasattr(self.receiver, '_add_output'):
                self.receiver._add_output(result)
            return result
        except Exception as e:
            logger.error(f"Error processing data: {e}")
            error_msg = f"Error processing data: {str(e)}"
            if hasattr(self.receiver, '_add_output'):
                self.receiver._add_output(error_msg)
            return error_msg
        
    def generate(self):
        print("Starting JSONReceiverSegment generator...")
        while True:
            # Wait for data to be available in the queue
            print("Waiting for data...")
            # This will block until data is available
            yield self.queue.get(block=True, timeout=None)

def go():
    
    parser = argparse.ArgumentParser(description='FastAPI JSON Data Receiver with Configurable Form')
    parser.add_argument('-p', '--port', type=int, default=9999,
                        help='Port to listen on (default: 9999)')
    parser.add_argument('-o', '--host', default='0.0.0.0',
                        help='Host to bind to (default: 0.0.0.0)')
    parser.add_argument('--api-key', help='Set API key for authentication')
    parser.add_argument('--require-auth', action='store_true',
                        help='Require API key authentication')
    parser.add_argument('--title', default='JSON Data Receiver',
                        help='Title for the FastAPI application')
    parser.add_argument('--script-var', default=None, 
                        help='Configuration key containing script to run')
    parser.add_argument('--script', default=None,
                        help='Chatterlang script to run on received data')
    parser.add_argument('--form-config', default=None,
                        help='Path to form configuration file (YAML or JSON) or config variable ($VAR_NAME)')
    parser.add_argument("--load_module", action='append', default=[], type=str, 
                        help="Path to a custom module file to import before running the script.")

    
    args = parser.parse_args()
    
    if args.load_module:
        for module_file in args.load_module:
            load_module_file(fname=module_file, fail_on_missing=False)

    script = None
    if args.script_var and args.script:
        raise ValueError("Cannot specify both --script-var and --script. Use one or the other.")
    if args.script_var:
        script = get_config(args.script_var)
        if not script:
            raise ValueError(f"No script found for variable '{args.script_var}' in configuration.")
    else:
        script = args.script
    
    if script:
        # Compile the Chatterlang script
        compiled_script = compile(script)
        compiled_script = compiled_script.asFunction(single_in=True, single_out=False)
    else:
        # Default processor function if no script is provided
        compiled_script = None
    
    # Load form configuration if provided
    form_config = None
    if args.form_config:
        if args.form_config.startswith('$'):
            # Try to load from config variable
            config_data = get_config(args.form_config[1:])
            if config_data:
                form_config = json.loads(config_data) if isinstance(config_data, str) else config_data
            else:
                # Try loading as file path
                form_config = load_form_config(args.form_config[1:])
        else:
            # Load from file
            form_config = load_form_config(args.form_config)

    receiver = JSONReceiver(
        host=args.host,
        port=args.port,
        api_key=args.api_key,
        require_auth=args.require_auth,
        title=args.title,
        processor_func=compiled_script,
        form_config=form_config
    )

    # Start the server
    receiver.start(background=False)

if __name__ == "__main__":
    go()