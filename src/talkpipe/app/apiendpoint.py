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
    
    def _add_output(self, output: str):
        """Add output to the streaming queue"""
        try:
            # Add timestamp to output
            timestamped_output = {
                "timestamp": datetime.now().isoformat(),
                "output": output
            }
            self.output_queue.put(timestamped_output, block=False)
        except:
            # Queue is full, remove oldest item
            try:
                self.output_queue.get_nowait()
                self.output_queue.put(timestamped_output, block=False)
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
        """Process incoming JSON data"""
        import sys
        from io import StringIO
        
        try:
            # Add timestamp
            data['_received_at'] = datetime.now().isoformat()
            
            # Store in history
            self.history.append(data)
            if len(self.history) > self.history_length:
                self.history.pop(0)
            
            # Capture stdout during processing
            old_stdout = sys.stdout
            sys.stdout = captured_output = StringIO()
            
            try:
                # Process with configured function
                result = self.processor_function(data)
                
                # Get captured output
                output = captured_output.getvalue()
                if output:
                    # Split by newlines and add each line to output
                    for line in output.strip().split('\n'):
                        if line:
                            self._add_output(line)
                
                # Convert result to string if needed
                if not isinstance(result, str):
                    result = str(result)
                
                # Add the result itself as output
                if result and result != output.strip():
                    self._add_output(f"Result: {result}")
                
            finally:
                sys.stdout = old_stdout
            
            logger.info(f"Port {self.port}: Successfully processed data")
            
            return DataResponse(
                status="success",
                message=result,
                data=data,
                timestamp=datetime.now()
            )
            
        except Exception as e:
            logger.error(f"Port {self.port}: Error processing data: {str(e)}")
            self._add_output(f"Error: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))
    
    def _get_history(self, limit: int) -> DataHistory:
        """Get processing history"""
        entries = self.history[-limit:] if limit > 0 else self.history
        return DataHistory(entries=entries, count=len(entries))
    
    def _clear_history(self):
        """Clear processing history"""
        self.history.clear()
        logger.info(f"Port {self.port}: History cleared")
        return {"status": "success", "message": "History cleared"}
    
    def _generate_form_fields_html(self) -> str:
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
        """Generate streaming HTML interface with form and output"""
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
        else:
            bg_color = "#f5f5f5"
            text_color = "#333333"
            input_bg = "#ffffff"
            border_color = "#ddd"
            button_bg = "#0066cc"
            button_hover = "#0052a3"
            output_bg = "#ffffff"
            output_text = "#333333"
        
        auth_header = '''
            <div class="auth-section">
                <label for="apiKey">API Key:</label>
                <input type="password" id="apiKey" placeholder="Enter API key">
            </div>
        ''' if self.require_auth else ''
        
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
                    background-color: {output_bg};
                    color: {text_color};
                    height: 100vh;
                    display: flex;
                    flex-direction: column;
                    overflow: hidden;
                }}
                
                .output-section {{
                    flex: 1;
                    padding: 20px;
                    overflow-y: auto;
                    background-color: {output_bg};
                    font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
                }}
                
                .output-line {{
                    color: {output_text};
                    margin: 2px 0;
                    padding: 2px 5px;
                    white-space: pre-wrap;
                    word-wrap: break-word;
                }}
                
                .output-line.error {{
                    color: #ff6b6b;
                }}
                
                .output-line .timestamp {{
                    color: #666;
                    margin-right: 10px;
                }}
                
                .form-panel {{
                    height: {height};
                    background-color: {bg_color};
                    color: {text_color};
                    border-top: 2px solid {border_color};
                    box-shadow: 0 -2px 10px rgba(0,0,0,0.1);
                    padding: 20px;
                    overflow-y: auto;
                }}
                
                .form-container {{
                    max-width: 1200px;
                    margin: 0 auto;
                }}
                
                .form-header {{
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    margin-bottom: 20px;
                }}
                
                .form-title {{
                    font-size: 18px;
                    font-weight: 600;
                }}
                
                .control-buttons {{
                    display: flex;
                    gap: 10px;
                }}
                
                .control-btn {{
                    background: none;
                    border: 1px solid {border_color};
                    color: {text_color};
                    cursor: pointer;
                    padding: 5px 10px;
                    border-radius: 4px;
                    font-size: 12px;
                }}
                
                .form-content {{
                    display: flex;
                    flex-wrap: wrap;
                    gap: 15px;
                    align-items: flex-end;
                }}
                
                .form-group {{
                    flex: 1;
                    min-width: 200px;
                }}
                
                .form-group label {{
                    display: block;
                    margin-bottom: 5px;
                    font-size: 14px;
                    font-weight: 500;
                }}
                
                .form-group input,
                .form-group select,
                .form-group textarea {{
                    width: 100%;
                    padding: 8px 12px;
                    background-color: {input_bg};
                    color: {text_color};
                    border: 1px solid {border_color};
                    border-radius: 4px;
                    font-size: 14px;
                }}
                
                .checkbox-group {{
                    display: flex;
                    align-items: center;
                }}
                
                .checkbox-group label {{
                    display: flex;
                    align-items: center;
                    margin-bottom: 0;
                }}
                
                .checkbox-group input[type="checkbox"] {{
                    width: auto;
                    margin-right: 8px;
                }}
                
                .form-actions {{
                    display: flex;
                    gap: 10px;
                    align-items: center;
                }}
                
                button {{
                    padding: 8px 20px;
                    background-color: {button_bg};
                    color: white;
                    border: none;
                    border-radius: 4px;
                    cursor: pointer;
                    font-size: 14px;
                    font-weight: 500;
                    transition: background-color 0.2s;
                }}
                
                button:hover {{
                    background-color: {button_hover};
                }}
                
                .status {{
                    padding: 8px 15px;
                    border-radius: 4px;
                    font-size: 14px;
                    margin-left: 10px;
                }}
                
                .status.success {{
                    background-color: #4caf50;
                    color: white;
                }}
                
                .status.error {{
                    background-color: #f44336;
                    color: white;
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
            <div class="output-section" id="outputSection">
                <div class="output-line">Waiting for output...</div>
            </div>
            
            <div class="form-panel" id="formPanel">
                <div class="form-container">
                    <div class="form-header">
                        <h2 class="form-title">{self.form_config.title}</h2>
                        <div class="control-buttons">
                            <button class="control-btn" onclick="clearOutput()">Clear Output</button>
                            <button class="control-btn" onclick="toggleAutoScroll()">Auto-scroll: ON</button>
                        </div>
                    </div>
                    
                    <form id="dataForm" onsubmit="submitForm(event)">
                        {auth_header}
                        <div class="form-content">
                            {self._generate_form_fields_html()}
                            <div class="form-actions">
                                <button type="submit">Submit</button>
                                <div id="status" class="status" style="display: none;"></div>
                            </div>
                        </div>
                    </form>
                </div>
            </div>
            
            <script>
                let autoScroll = true;
                let eventSource = null;
                const outputSection = document.getElementById('outputSection');
                
                // Initialize SSE connection
                function initSSE() {{
                    eventSource = new EventSource('/output-stream');
                    
                    eventSource.onmessage = function(event) {{
                        const data = JSON.parse(event.data);
                        addOutput(data.output, data.timestamp);
                    }};
                    
                    eventSource.onerror = function(error) {{
                        console.error('SSE error:', error);
                        addOutput('Connection error - retrying...', new Date().toISOString(), true);
                        // Reconnect after error
                        setTimeout(initSSE, 5000);
                    }};
                }}
                
                // Add output line
                function addOutput(text, timestamp, isError = false) {{
                    const line = document.createElement('div');
                    line.className = 'output-line' + (isError ? ' error' : '');
                    
                    const time = new Date(timestamp).toLocaleTimeString();
                    line.innerHTML = `<span class="timestamp">${{time}}</span>${{escapeHtml(text)}}`;
                    
                    outputSection.appendChild(line);
                    
                    // Remove old lines if too many (keep last 1000)
                    while (outputSection.children.length > 1000) {{
                        outputSection.removeChild(outputSection.firstChild);
                    }}
                    
                    if (autoScroll) {{
                        outputSection.scrollTop = outputSection.scrollHeight;
                    }}
                }}
                
                function escapeHtml(text) {{
                    const div = document.createElement('div');
                    div.textContent = text;
                    return div.innerHTML;
                }}
                
                function clearOutput() {{
                    outputSection.innerHTML = '<div class="output-line">Output cleared. Waiting for new data...</div>';
                }}
                
                function toggleAutoScroll() {{
                    autoScroll = !autoScroll;
                    event.target.textContent = `Auto-scroll: ${{autoScroll ? 'ON' : 'OFF'}}`;
                }}
                
                async function submitForm(event) {{
                    event.preventDefault();
                    const form = document.getElementById('dataForm');
                    const status = document.getElementById('status');
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
                            status.textContent = 'Submitted successfully';
                        }} else {{
                            status.className = 'status error';
                            status.textContent = 'Error: ' + result.detail;
                        }}
                    }} catch (error) {{
                        status.style.display = 'block';
                        status.className = 'status error';
                        status.textContent = 'Error: ' + error.message;
                    }}
                    
                    setTimeout(() => {{
                        status.style.display = 'none';
                    }}, 3000);
                }}
                
                // Handle Enter key to submit form
                document.getElementById('dataForm').addEventListener('keypress', function(event) {{
                    if (event.key === 'Enter' && !event.shiftKey && event.target.tagName !== 'TEXTAREA') {{
                        event.preventDefault();
                        submitForm(event);
                    }}
                }});
                
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
                    overflow-y: auto;
                    padding: 20px;
                }}
                
                .form-panel {{
                    position: fixed;
                    {form_style}
                    background-color: {bg_color};
                    color: {text_color};
                    border-top: 2px solid {border_color};
                    box-shadow: 0 -2px 10px rgba(0,0,0,0.1);
                    padding: 20px;
                    overflow-y: auto;
                    z-index: 1000;
                }}
                
                .form-container {{
                    max-width: 1200px;
                    margin: 0 auto;
                }}
                
                .form-header {{
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    margin-bottom: 20px;
                }}
                
                .form-title {{
                    font-size: 18px;
                    font-weight: 600;
                }}
                
                .minimize-btn {{
                    background: none;
                    border: none;
                    color: {text_color};
                    cursor: pointer;
                    font-size: 20px;
                    padding: 5px 10px;
                }}
                
                .form-content {{
                    display: flex;
                    flex-wrap: wrap;
                    gap: 15px;
                    align-items: flex-end;
                }}
                
                .form-group {{
                    flex: 1;
                    min-width: 200px;
                }}
                
                .form-group label {{
                    display: block;
                    margin-bottom: 5px;
                    font-size: 14px;
                    font-weight: 500;
                }}
                
                .form-group input,
                .form-group select,
                .form-group textarea {{
                    width: 100%;
                    padding: 8px 12px;
                    background-color: {input_bg};
                    color: {text_color};
                    border: 1px solid {border_color};
                    border-radius: 4px;
                    font-size: 14px;
                }}
                
                .checkbox-group {{
                    display: flex;
                    align-items: center;
                }}
                
                .checkbox-group label {{
                    display: flex;
                    align-items: center;
                    margin-bottom: 0;
                }}
                
                .checkbox-group input[type="checkbox"] {{
                    width: auto;
                    margin-right: 8px;
                }}
                
                .form-actions {{
                    display: flex;
                    gap: 10px;
                    align-items: center;
                }}
                
                button {{
                    padding: 8px 20px;
                    background-color: {button_bg};
                    color: white;
                    border: none;
                    border-radius: 4px;
                    cursor: pointer;
                    font-size: 14px;
                    font-weight: 500;
                    transition: background-color 0.2s;
                }}
                
                button:hover {{
                    background-color: {button_hover};
                }}
                
                .status {{
                    padding: 8px 15px;
                    border-radius: 4px;
                    font-size: 14px;
                    margin-left: 10px;
                }}
                
                .status.success {{
                    background-color: #4caf50;
                    color: white;
                }}
                
                .status.error {{
                    background-color: #f44336;
                    color: white;
                }}
                
                .info-section {{
                    background-color: white;
                    border-radius: 8px;
                    padding: 30px;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                    margin-bottom: 20px;
                }}
                
                .endpoint-info {{
                    background-color: #f8f9fa;
                    padding: 15px;
                    border-radius: 4px;
                    font-family: monospace;
                    margin: 10px 0;
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
                        <h2 class="form-title">{self.form_config.title}</h2>
                        <button class="minimize-btn" onclick="toggleForm()">−</button>
                    </div>
                    
                    <form id="dataForm" onsubmit="submitForm(event)">
                        {auth_header}
                        <div class="form-content">
                            {self._generate_form_fields_html()}
                            <div class="form-actions">
                                <button type="submit">Submit</button>
                                <div id="status" class="status" style="display: none;"></div>
                            </div>
                        </div>
                    </form>
                </div>
            </div>
            
            <script>
                let isMinimized = false;
                
                function toggleForm() {{
                    const panel = document.getElementById('formPanel');
                    const btn = document.querySelector('.minimize-btn');
                    isMinimized = !isMinimized;
                    
                    if (isMinimized) {{
                        panel.classList.add('form-minimized');
                        btn.textContent = '+';
                    }} else {{
                        panel.classList.remove('form-minimized');
                        btn.textContent = '−';
                    }}
                }}
                
                async function submitForm(event) {{
                    event.preventDefault();
                    const form = document.getElementById('dataForm');
                    const status = document.getElementById('status');
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