"""
FastAPI JSON Receiver Server
Receives JSON data via HTTP and processes it with a configurable function
"""

import logging
import argparse
from fastapi.responses import FileResponse
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
from queue import Queue
from talkpipe.pipe.core import AbstractSource
from talkpipe.chatterlang import register_source
from talkpipe.chatterlang import compile
from talkpipe.util.config import get_config

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

class JSONReceiver:
    """JSON Data Receiver Server Class - supports multiple instances"""
    
    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 9999,
        api_key: str = "your-secret-key-here",
        require_auth: bool = False,
        processor_func: Callable[[Dict[str, Any]], Any] = None,
        title: str = "JSON Data Receiver",
        history_length: int = 1000
    ):
        self.host = host
        self.port = port
        self.api_key = api_key
        self.require_auth = require_auth
        self.history = []
        self.title = title
        self.history_length = history_length
        
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
    
    async def _verify_api_key(self, x_api_key: Optional[str] = Header(None)):
        """Dependency for API key validation"""
        if self.require_auth and x_api_key != self.api_key:
            raise HTTPException(status_code=403, detail="Invalid API key")
        return x_api_key
    
    def _default_print_processor(self, data: Dict[str, Any]) -> str:
        """Default processor: print JSON data to stdout"""
        try:
            print(f"[Port {self.port}] Received JSON: {json.dumps(data, indent=2, default=str)}")
            return "Data printed successfully"
        except Exception as e:
            logger.error(f"Error processing data: {e}")
            raise HTTPException(status_code=500, detail=f"Processing error: {e}")
    
    def _save_to_history(self, data: Dict[str, Any]):
        self.history.append(data)
        while len(self.history) > self.history_length:
            self.history.pop(0)
    
    async def _process_json(self, data: Dict[str, Any]) -> DataResponse:
        """Process JSON data with the configured processor function"""
        
        # Log the request
        logger.info(f"[{datetime.now().strftime('%H:%M:%S')}] Port {self.port}: Processing JSON data")
        
        try:
            # Process the data
            result = self.processor_function(data)
            
            # Save to history
            self._save_to_history(data)
            
            # Determine message based on result
            if isinstance(result, str):
                message = result
            else:
                message = "Data processed successfully"
            
            return DataResponse(
                status="success",
                message=message,
                data=data,
                timestamp=datetime.now()
            )
            
        except HTTPException:
            # Re-raise HTTP exceptions from the processor
            raise
        except Exception as e:
            logger.error(f"Error processing data: {e}")
            raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")
    
    def _get_history(self, limit: int) -> DataHistory:
        """Get processing history"""
        return DataHistory(entries=self.history, count=len(self.history))
    
    def _clear_history(self):
        """Clear processing history"""
        self.history.clear()
        logger.info(f"Port {self.port}: History cleared")
        return {"status": "success", "message": "History cleared", "timestamp": datetime.now()}
    
    def _get_html_interface(self) -> str:
        """Get the HTML interface with port-specific URLs"""
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>{self.title} - Port {self.port}</title>
            <link rel="icon" type="image/ico" href="/favicon.ico">
            <style>
                body {{ font-family: Arial, sans-serif; max-width: 800px; margin: 50px auto; padding: 20px; }}
                input, button, textarea {{ font-size: 16px; padding: 10px; margin: 5px; }}
                textarea {{ width: 500px; height: 150px; font-family: monospace; }}
                .status {{ margin-top: 20px; padding: 10px; border-radius: 5px; }}
                .success {{ background-color: #d4edda; color: #155724; }}
                .error {{ background-color: #f8d7da; color: #721c24; }}
                .history {{ margin-top: 30px; }}
                .history-item {{ padding: 5px; border-bottom: 1px solid #ddd; }}
                code {{ background-color: #f4f4f4; padding: 2px 5px; border-radius: 3px; }}
                .port-info {{ background-color: #e3f2fd; padding: 10px; border-radius: 5px; margin-bottom: 20px; }}
            </style>
        </head>
        <body>
            <div class="port-info">
                <h1>{self.title}</h1>
                <p><strong>Server Port:</strong> {self.port}</p>
                <p><strong>History Length:</strong> {len(self.history)}, max length={self.history_length}</p>
            </div>
            
            <p>Send JSON data to process it on this machine:</p>
            
            <div>
                <textarea id="jsonData" placeholder='{{"example": "data", "number": 42}}'></textarea><br>
                <button onclick="sendData()">Send JSON Data</button>
            </div>
            
            <div id="status"></div>
            
            <div class="history">
                <h3>API Endpoints:</h3>
                <ul>
                    <li><code>POST /process</code> - Send JSON data for processing</li>
                    <li><code>GET /history</code> - Get processing history</li>
                    <li><code>DELETE /history</code> - Clear processing history</li>
                    <li><code>GET /health</code> - Health check</li>
                    <li><code>GET /docs</code> - API documentation</li>
                </ul>
                
                <h3>Usage Examples:</h3>
                <pre>
# Using curl:
curl -X POST http://localhost:{self.port}/process \\
  -H "Content-Type: application/json" \\
  -d '{{"message": "hello", "value": 123}}'

# Using PowerShell:
Invoke-RestMethod -Uri http://localhost:{self.port}/process \\
  -Method POST -ContentType "application/json" \\
  -Body '{{"key": "value", "number": 42}}'

# Using Python:
import requests
response = requests.post('http://localhost:{self.port}/process', 
  json={{'key': 'value', 'number': 42}})
print(response.json())</pre>
            </div>
            
            <script>
                async function sendData() {{
                    const jsonText = document.getElementById('jsonData').value;
                    const status = document.getElementById('status');
                    
                    try {{
                        const data = JSON.parse(jsonText);
                        
                        const response = await fetch('/process', {{
                            method: 'POST',
                            headers: {{'Content-Type': 'application/json'}},
                            body: JSON.stringify(data)
                        }});
                        
                        const result = await response.json();
                        
                        if (response.ok) {{
                            status.className = 'status success';
                            status.textContent = 'JSON data processed successfully on port {self.port}!';
                        }} else {{
                            status.className = 'status error';
                            status.textContent = 'Error: ' + result.detail;
                        }}
                    }} catch (error) {{
                        status.className = 'status error';
                        status.textContent = 'Error: ' + error.message;
                    }}
                    
                    setTimeout(() => status.textContent = '', 3000);
                }}
            </script>
        </body>
        </html>
        """
    
    def set_processor_function(self, func: Callable[[Dict[str, Any]], Any]):
        """Set the function used to process incoming JSON data"""
        self.processor_function = func
        logger.info(f"Port {self.port}: Processor function set to: {func.__name__}")
    
    def start(self, background: bool = False):
        """Start the FastAPI server"""
        logger.info(f"Starting JSON Data Receiver on http://{self.host}:{self.port}")
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

@register_source("jsonReceiver")
class JSONReceiverSegment(AbstractSource):
    """Segment for receiving JSON data via FastAPI"""
    
    def __init__(self, port: int = 9999, host: str = "0.0.0.0", 
                 api_key: str = None, require_auth: bool = False):
        super().__init__()
        self.port = port
        self.host = host
        self.api_key = api_key
        self.require_auth = require_auth
        self.queue = Queue(maxsize=1000)
        
        self.receiver = JSONReceiver(
            host=host,
            port=port,
            api_key=api_key,
            require_auth=require_auth,
            title=f"JSON Receiver Segment (Port {port})",
            processor_func=self.process_data
        )
        self.receiver.start(background=True)
        logger.info(f"Finished initializing JSONReceiverSegment on port {port}")

    def process_data(self, data: Dict[str, Any]) -> str:
        """Process incoming JSON data and add it to the queue"""
        try:
            self.queue.put(data, block=True, timeout=60)
            return f"Data received and queued: {data}"
        except Exception as e:
            logger.error(f"Error processing data: {e}")
            return f"Error processing data: {str(e)}"
        
    def generate(self):
        print("Starting JSONReceiverSegment generator...")
        while True:
            # Wait for data to be available in the queue
            print("Waiting for data...")
            # This will block until data is available
            yield self.queue.get(block=True, timeout=None)

def go():
    
    parser = argparse.ArgumentParser(description='FastAPI JSON Data Receiver')
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
    
    args = parser.parse_args()
    

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

    receiver = JSONReceiver(
        host=args.host,
        port=args.port,
        api_key=args.api_key,
        require_auth=args.require_auth,
        title=args.title,
        processor_func=compiled_script,
    )

    # Start the server
    receiver.start(background=False)

if __name__ == "__main__":
    go()
