"""
FastAPI JSON Receiver Server with Configurable Form UI
Receives JSON data via HTTP and processes it with a configurable function
Multi-user support with session isolation
"""
from typing import Union, Annotated, Optional
import logging
import argparse
import yaml
import html
import asyncio
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi import FastAPI, HTTPException, Depends, Header, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import Optional, List, Any, Dict, Callable
from datetime import datetime, timedelta
import uvicorn
import json
from pathlib import Path
import threading
from queue import Queue, Empty
import uuid
from talkpipe.pipe.core import AbstractSource, RuntimeComponent
from talkpipe.chatterlang import register_source
from talkpipe.chatterlang import compile
from talkpipe.util.config import get_config, load_script
from talkpipe.util.config import load_module_file, parse_unknown_args, add_config_values
from talkpipe.util.data_manipulation import extract_property


logger = logging.getLogger(__name__)

# User Session Management
class UserSession:
    """Encapsulates per-user session state"""
    
    def __init__(self, session_id: str, script_content: str = None, history_length: int = 1000):
        self.session_id = session_id
        self.history = []
        self.history_length = history_length
        self.output_queue = Queue(maxsize=1000)
        self.compiled_script = None
        self.last_activity = datetime.now()
        
        # Compile script for this session if provided
        if script_content:
            self.compile_script(script_content)
    
    def compile_script(self, script_content: str):
        """Compile a Chatterlang script for this session"""
        # Compile script - configuration values are accessible via $key syntax
        self.compiled_script = compile(script_content)
        self.compiled_script = self.compiled_script.as_function(single_in=True, single_out=False)
        logger.info(f"Session {self.session_id}: Script compiled successfully")
    
    def add_to_history(self, entry: dict):
        """Add entry to session history"""
        self.history.append(entry)
        if len(self.history) > self.history_length:
            self.history = self.history[-self.history_length:]
    
    def add_output(self, output: str, message_type: str = "response"):
        """Add output to session's output queue"""
        try:
            timestamped_output = {
                "timestamp": datetime.now().isoformat(),
                "output": output,
                "type": message_type
            }
            self.output_queue.put(timestamped_output, block=False)
        except Exception as e:
            # Queue is full, remove oldest item
            logger.warning(f"Output queue full, attempting to remove oldest item: {e}")
            try:
                self.output_queue.get_nowait()
                self.output_queue.put(timestamped_output, block=False)
            except Exception as e2:
                logger.warning(f"Failed to add output to queue even after removing oldest item: {e2}")
    
    def update_activity(self):
        """Update last activity timestamp"""
        self.last_activity = datetime.now()

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
    persist: bool = False  # If True, field values will not be reset after submission

class FormConfig(BaseModel):
    title: str = "Data Input Form"
    fields: List[FormField] = []
    position: str = "bottom"  # bottom, top, left, right
    height: str = "150px"  # CSS height for the form panel
    theme: str = "dark"  # dark, light

class ChatterlangServer:
    """ChatterLang Server Class with configurable form UI and multi-user support"""
    
    def __init__(
        self,
        host: str = "localhost",
        port: int = 9999,
        api_key: str = "your-secret-key-here",
        require_auth: bool = False,
        processor_func: Callable[[Dict[str, Any]], Any] = None,
        title: str = "ChatterLang Server",
        history_length: int = 1000,
        form_config: Optional[Dict[str, Any]] = None,
        display_property: Optional[str] = None,
        script_content: Optional[str] = None
    ):
        self.host = host
        self.port = port
        self.api_key = api_key
        self.require_auth = require_auth
        self.title = title
        self.history_length = history_length
        self.display_property = display_property
        self.script_content = script_content
        
        # Session management
        self.sessions: Dict[str, UserSession] = {}
        self.session_lock = threading.Lock()
        
        # Parse form configuration
        if form_config:
            self.form_config = FormConfig(**form_config)
        else:
            # Default form configuration
            self.form_config = FormConfig(
                title="Data Input Form",
                fields=[
                    FormField(name="prompt", type="text", label="Prompt", placeholder="Enter prompt", required=True),
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
        
        # Add security headers middleware
        self._setup_security_headers()
        
        # Configure routes
        self._setup_routes()
        
        # Server instance for stopping
        self.server = None
        self.server_thread = None
        
        # Start session cleanup task
        self._start_cleanup_task()
    
    def get_or_create_session(self, request: Request, response: Response) -> UserSession:
        """Get existing session or create new one based on session cookie"""
        session_id = request.cookies.get("talkpipe_session_id")
        
        with self.session_lock:
            if session_id and session_id in self.sessions:
                # Update activity for existing session
                session = self.sessions[session_id]
                session.update_activity()
                return session
            
            # If session_id exists but not in memory (after restart), 
            # recreate the session with the same ID
            if session_id:
                session = UserSession(
                    session_id=session_id,  # Keep the same ID
                    script_content=self.script_content,
                    history_length=self.history_length
                )
                self.sessions[session_id] = session
                logger.info(f"Recreated session after restart: {session_id}")
                return session
            
            # Create new session
            session_id = str(uuid.uuid4())
            session = UserSession(
                session_id=session_id,
                script_content=self.script_content,
                history_length=self.history_length
            )
            self.sessions[session_id] = session
            
            # Set session cookie (expires in 24 hours) with security attributes
            response.set_cookie(
                key="talkpipe_session_id",
                value=session_id,
                max_age=86400,  # 24 hours
                httponly=True,  # Prevent JavaScript access
                samesite="lax",  # CSRF protection
                secure=False,    # Set to True in production with HTTPS
                path="/"         # Restrict cookie path
            )
            
            logger.info(f"Created new session: {session_id}")
            return session
    
    def cleanup_expired_sessions(self, max_age_hours: int = 24):
        """Clean up sessions that haven't been active for max_age_hours"""
        cutoff_time = datetime.now() - timedelta(hours=max_age_hours)
        
        with self.session_lock:
            expired_sessions = [
                session_id for session_id, session in self.sessions.items()
                if session.last_activity < cutoff_time
            ]
            
            for session_id in expired_sessions:
                del self.sessions[session_id]
                logger.info(f"Cleaned up expired session: {session_id}")
    
    def get_session_by_id(self, session_id: str) -> Optional[UserSession]:
        """Get session by ID, return None if not found"""
        with self.session_lock:
            return self.sessions.get(session_id)
    
    def _start_cleanup_task(self):
        """Start background task to cleanup expired sessions"""
        def cleanup_worker():
            while True:
                try:
                    self.cleanup_expired_sessions()
                    threading.Event().wait(300)  # Wait 5 minutes
                except Exception as e:
                    logger.error(f"Error in session cleanup: {e}")
                    threading.Event().wait(60)  # Wait 1 minute on error
        
        cleanup_thread = threading.Thread(target=cleanup_worker, daemon=True)
        cleanup_thread.start()
        logger.info("Started session cleanup background task")
    
    def _setup_middleware(self):
        """Configure CORS middleware with security restrictions"""
        # Define allowed origins - never use "*" in production
        allowed_origins = [
            "http://localhost:3000",
            "http://localhost:8000", 
            "http://127.0.0.1:3000",
            "http://127.0.0.1:8000",
            f"http://localhost:{self.port}",
            f"http://127.0.0.1:{self.port}"
        ]
        
        # Add environment-specific origins if configured
        import os
        env_origins = os.getenv('TALKPIPE_ALLOWED_ORIGINS', '').split(',')
        allowed_origins.extend([origin.strip() for origin in env_origins if origin.strip()])
        
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=allowed_origins,  # Specific origins only - never "*"
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],  # Specific methods only
            allow_headers=["Content-Type", "Authorization", "X-API-Key"],  # Specific headers only
            expose_headers=["Content-Type"],
            max_age=86400,  # Cache preflight requests for 24 hours
        )
    
    def _setup_security_headers(self):
        """Add security headers to all responses"""
        @self.app.middleware("http")
        async def add_security_headers(request, call_next):
            response = await call_next(request)
            
            # Security headers
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-XSS-Protection"] = "1; mode=block"
            response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline'; "
                "style-src 'self' 'unsafe-inline'; "
                "img-src 'self' data:; "
                "connect-src 'self'; "
                "font-src 'self'; "
                "object-src 'none'; "
                "media-src 'self'; "
                "child-src 'none';"
            )
            response.headers["Permissions-Policy"] = (
                "camera=(), microphone=(), geolocation=(), payment=(), "
                "usb=(), magnetometer=(), gyroscope=(), speaker=()"
            )
            
            return response
    
    def _setup_routes(self):
        """Configure all API routes"""
        
        @self.app.get("/", response_class=HTMLResponse)
        async def root(request: Request, response: Response):
            return self._get_html_interface()
        
        @self.app.get("/stream", response_class=HTMLResponse)
        async def stream_page(request: Request, response: Response):
            return self._get_stream_interface()
        
        @self.app.post("/process", response_model=DataResponse)
        async def process_json(
            data: Dict[str, Any], 
            request: Request, 
            response: Response,
            api_key: str = Depends(self._verify_api_key)
        ):
            session = self.get_or_create_session(request, response)
            return await self._process_json(data, session)
        
        @self.app.get("/history", response_model=DataHistory)
        async def get_history(
            request: Request, 
            response: Response,
            limit: int = 50, 
            api_key: str = Depends(self._verify_api_key)
        ):
            session = self.get_or_create_session(request, response)
            return self._get_history(limit, session)
        
        @self.app.delete("/history")
        async def clear_history(
            request: Request, 
            response: Response,
            api_key: str = Depends(self._verify_api_key)
        ):
            session = self.get_or_create_session(request, response)
            return self._clear_history(session)
        
        @self.app.get("/health")
        async def health_check():
            return {"status": "healthy", "timestamp": datetime.now(), "port": self.port}
        
        @self.app.get("/form-config")
        async def get_form_config():
            return self.form_config.model_dump()
        
        @self.app.get("/output-stream")
        async def output_stream(
            request: Request, 
            response: Response,
            api_key: str = Depends(self._verify_api_key)
        ):
            """Server-Sent Events endpoint for streaming output"""
            session = self.get_or_create_session(request, response)
            return StreamingResponse(
                self._generate_output_stream(session),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Content-Type-Options": "nosniff"
                }
            )
    
    async def _verify_api_key(self, x_api_key: Optional[str] = Header(None)):
        """Dependency for API key validation"""
        if self.require_auth and x_api_key != self.api_key:
            raise HTTPException(status_code=403, detail="Invalid API key")
        return x_api_key
    
    def _default_print_processor(self, data: Dict[str, Any], session: UserSession) -> str:
        """Default processor function that just prints the data"""
        logger.info(f"Port {self.port} Session {session.session_id}: Processing data with default handler")
        logger.info(f"Port {self.port} Session {session.session_id}: Received data: {json.dumps(data, indent=2)}")
        output = f"Data received: {data}"
        return output
    

    async def _generate_output_stream(self, session: UserSession):
        """Generate Server-Sent Events stream for a specific session"""
        while True:
            try:
                # Check for new output in this session's queue
                output = session.output_queue.get(timeout=0.1)
                yield f"data: {json.dumps(output)}\n\n"
            except Empty:
                # Send heartbeat to keep connection alive
                yield f": heartbeat\n\n"
            
            await asyncio.sleep(0.1)
   
    async def _process_json(self, data: Dict[str, Any], session: UserSession) -> DataResponse:
        """Process JSON data and return response"""
        try:
            # Determine which processor to use
            processor = session.compiled_script if session.compiled_script else self._default_print_processor
            
            # Process the data
            if session.compiled_script:
                result = processor(data)
            else:
                result = processor(data, session)
            
            # Collect all output items for the API response
            output_items = []
            
            # If result is iterable (like a generator), process each item
            if hasattr(result, '__iter__') and not isinstance(result, (str, bytes, dict)):
                try:
                    for item in result:
                        if item is not None:
                            session.add_output(str(item), "response")
                            output_items.append(item)
                except Exception as e:
                    error_msg = f"Error processing iterator: {str(e)}"
                    session.add_output(error_msg, "error")
                    output_items.append({"error": error_msg})
            else:
                # Single result
                if result is not None:
                    session.add_output(str(result), "response")
                    output_items.append(result)
            
            # Store in session history
            session.add_to_history({
                "timestamp": datetime.now(),
                "input": data,
                "output": output_items if output_items else "No output"
            })
            
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
            session.add_output(error_msg, "error")
            logger.error(f"Port {self.port} Session {session.session_id}: {error_msg}")
            raise HTTPException(status_code=500, detail=error_msg)
    
    def _get_history(self, limit: int, session: UserSession) -> DataHistory:
        """Get processing history for a session"""
        entries = session.history[-limit:] if limit > 0 else session.history
        return DataHistory(entries=entries, count=len(entries))
    
    def _clear_history(self, session: UserSession):
        """Clear processing history for a session"""
        session.history.clear()
        logger.info(f"Port {self.port} Session {session.session_id}: History cleared")
        return {"status": "success", "message": "History cleared"}
    
    def _generate_form_fields(self) -> str:
        """Generate HTML for form fields based on configuration"""
        fields_html = []
        
        for field in self.form_config.fields:
            label = field.label or field.name.capitalize()
            required = "required" if field.required else ""
            persist_attr = 'data-persist="true"' if field.persist else ""
            
            if field.type == "select" and field.options:
                field_html = f'''
                <div class="form-group">
                    <label for="{field.name}">{label}:</label>
                    <select name="{field.name}" id="{field.name}" {required} {persist_attr}>
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
                              placeholder="{field.placeholder or ''}" {required} {persist_attr}>{field.default or ''}</textarea>
                </div>
                '''
            elif field.type == "checkbox":
                checked = "checked" if field.default else ""
                field_html = f'''
                <div class="form-group checkbox-group">
                    <label>
                        <input type="checkbox" name="{field.name}" id="{field.name}" {checked} {persist_attr}>
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
                           placeholder="{field.placeholder or ''}" {required} {min_attr} {max_attr} {default_val} {persist_attr}>
                </div>
                '''
            
            fields_html.append(field_html)
        
        return "\n".join(fields_html)
    
    def _get_stream_interface(self) -> str:
        """Generate streaming HTML interface with chat-like layout that respects position configuration"""
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
        
        # Generate position-specific CSS and classes
        form_panel_class = "form-panel"
        if position in ["bottom", "top"]:
            # Horizontal layouts - form at bottom/top, chat fills remaining space
            form_panel_class += " horizontal"
            if position == "bottom":
                main_container_style = "flex-direction: column;"
                form_panel_style = f"order: 2; height: {height}; border-top: 1px solid {border_color}; border-right: none;"
                chat_panel_style = f"order: 1; flex: 1; height: calc(100vh - {height} - 140px);"  # 80px header + 60px controls
                controls_style = "order: 3;"
            else:  # top
                main_container_style = "flex-direction: column;"
                form_panel_style = f"order: 1; height: {height}; border-bottom: 1px solid {border_color}; border-right: none;"
                chat_panel_style = f"order: 2; flex: 1; height: calc(100vh - {height} - 140px);"  # 80px header + 60px controls
                controls_style = "order: 3;"
            form_panel_width = "width: 100%;"
            
        else:
            # Vertical layouts - form at left/right, chat fills remaining space
            main_container_style = "flex-direction: row;"
            form_panel_width = f"width: {height};"  # Use height as width for vertical layouts
            chat_panel_style = "flex: 1;"
            controls_style = ""
            
            if position == "left":
                form_panel_style = f"order: 1; border-right: 1px solid {border_color};"
                chat_panel_style += " order: 2;"
            else:  # right
                form_panel_style = f"order: 2; border-left: 1px solid {border_color};"
                chat_panel_style += " order: 1;"
        
        # Generate controls HTML based on position
        if position in ["bottom", "top"]:
            # Controls outside chat panel for bottom/top positions
            chat_controls = ""
            standalone_controls = '''
                <div class="controls">
                    <button class="control-btn" onclick="clearChat()">Clear Chat</button>
                    <button class="control-btn" onclick="toggleAutoScroll()" id="autoScrollBtn">Auto-scroll: ON</button>
                    <span id="connectionStatus">Connecting...</span>
                </div>
            '''
        else:
            # Controls inside chat panel for left/right positions
            chat_controls = '''
                    <div class="controls">
                        <button class="control-btn" onclick="clearChat()">Clear Chat</button>
                        <button class="control-btn" onclick="toggleAutoScroll()" id="autoScrollBtn">Auto-scroll: ON</button>
                        <span id="connectionStatus">Connecting...</span>
                    </div>
            '''
            standalone_controls = ""
        
        auth_header = '''
            <div class="auth-section">
                <label for="apiKey">API Key:</label>
                <input type="password" id="apiKey" placeholder="Enter API key">
            </div>
        ''' if self.require_auth else ''
        
        form_fields = self._generate_form_fields()
        
        return f'''<!DOCTYPE html> 
        <html>
        <head>
            <title>{html.escape(self.title)} - Stream</title>
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
                    flex-shrink: 0;
                    height: 80px;
                }}
                
                .main-container {{
                    display: flex;
                    flex: 1;
                    overflow: hidden;
                    {main_container_style}
                }}
                
                .form-panel {{
                    {form_panel_width}
                    background-color: {input_bg};
                    padding: 1rem;
                    overflow-y: auto;
                    {form_panel_style}
                }}
                
                .chat-panel {{
                    display: flex;
                    flex-direction: column;
                    background-color: {output_bg};
                    {chat_panel_style}
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
                
                .copy-btn {{
                    position: absolute;
                    top: 0.5rem;
                    right: 0.5rem;
                    background: rgba(255, 255, 255, 0.1);
                    border: none;
                    border-radius: 0.25rem;
                    color: currentColor;
                    cursor: pointer;
                    padding: 0.25rem;
                    opacity: 0;
                    transition: opacity 0.2s;
                    font-size: 0.75rem;
                    backdrop-filter: blur(10px);
                }}
                
                .message:hover .copy-btn {{
                    opacity: 1;
                }}
                
                .copy-btn:hover {{
                    background: rgba(255, 255, 255, 0.2);
                }}
                
                .copy-btn.copied {{
                    background: rgba(34, 197, 94, 0.2);
                    color: #22c55e;
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
                
                /* Make submit button narrower for horizontal layouts */
                .form-panel.horizontal .submit-btn {{
                    width: auto;
                    min-width: 120px;
                    max-width: 200px;
                    margin: 0 auto;
                    display: block;
                }}
                
                /* Organize form fields in horizontal layouts */
                .form-panel.horizontal {{
                    display: flex;
                    flex-direction: column;
                }}
                
                .form-panel.horizontal form {{
                    display: flex;
                    flex-direction: row;
                    align-items: flex-end;
                    gap: 1rem;
                    flex-wrap: wrap;
                }}
                
                .form-panel.horizontal .form-fields {{
                    display: flex;
                    flex-direction: row;
                    gap: 1rem;
                    flex-wrap: wrap;
                    flex: 1;
                }}
                
                .form-panel.horizontal .form-group {{
                    flex: 1;
                    min-width: 200px;
                    margin-bottom: 0;
                }}
                
                .form-panel.horizontal .submit-btn {{
                    margin: 0;
                    align-self: flex-end;
                    height: fit-content;
                }}
                
                .form-panel.horizontal .status {{
                    width: 100%;
                    margin: 0.5rem 0 0 0;
                }}
                
                .form-panel.horizontal .auth-section {{
                    width: 100%;
                    margin-bottom: 1rem;
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
                    flex-wrap: wrap;
                    flex-shrink: 0;
                    height: 60px;
                    {controls_style}
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
                
                /* Responsive adjustments */
                @media (max-width: 768px) {{
                    .main-container {{
                        flex-direction: column !important;
                    }}
                    
                    .form-panel {{
                        order: 2 !important;
                        width: 100% !important;
                        height: {height} !important;
                        border-right: none !important;
                        border-left: none !important;
                        border-top: 1px solid {border_color} !important;
                        border-bottom: none !important;
                    }}
                    
                    .form-panel form {{
                        flex-direction: column !important;
                    }}
                    
                    .form-panel .form-fields {{
                        flex-direction: column !important;
                    }}
                    
                    .form-panel .form-group {{
                        margin-bottom: 1rem !important;
                    }}
                    
                    .form-panel .submit-btn {{
                        width: 100% !important;
                        margin: 0 !important;
                    }}
                    
                    .chat-panel {{
                        order: 1 !important;
                        height: calc(100vh - {height} - 140px) !important;
                    }}
                    
                    .controls {{
                        order: 3 !important;
                    }}
                }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>{html.escape(self.form_config.title)}</h1>
            </div>
            
            <div class="main-container">
                <div class="{form_panel_class}">
                    {auth_header}
                    
                    <form id="dataForm">
                        <div class="form-fields">
                            {form_fields}
                        </div>
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
                    {chat_controls}
                </div>
                {standalone_controls}
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
                            // Skip user messages from server since we display them immediately on client
                            if (data.type === 'user' && data.output === lastUserMessage) {{
                                return;
                            }}
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
                
                function resetFormSelectively(form) {{
                    const formElements = form.querySelectorAll('input, select, textarea');
                    formElements.forEach(element => {{
                        if (!element.hasAttribute('data-persist')) {{
                            // Reset non-persistent fields
                            if (element.type === 'checkbox' || element.type === 'radio') {{
                                element.checked = false;
                            }} else {{
                                element.value = '';
                            }}
                        }}
                    }});
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
                    timestampDiv.textContent = new Date(timestamp).toLocaleTimeString();
                    
                    const contentDiv = document.createElement('div');
                    contentDiv.className = 'message-content';
                    contentDiv.textContent = content;
                    
                    messageDiv.appendChild(timestampDiv);
                    messageDiv.appendChild(contentDiv);
                    
                    // Add copy button for response and error messages
                    if (type === 'response' || type === 'error') {{
                        const copyBtn = document.createElement('button');
                        copyBtn.className = 'copy-btn';
                        copyBtn.innerHTML = '📋';
                        copyBtn.title = 'Copy message';
                        copyBtn.onclick = function() {{
                            copyToClipboard(content, copyBtn);
                        }};
                        messageDiv.appendChild(copyBtn);
                    }}
                    messagesContainer.appendChild(messageDiv);
                    
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
                    const btn = document.getElementById('autoScrollBtn');
                    btn.textContent = `Auto-scroll: ${{autoScroll ? 'ON' : 'OFF'}}`;
                }}
                
                function copyToClipboard(text, button) {{
                    navigator.clipboard.writeText(text).then(function() {{
                        // Visual feedback
                        const originalContent = button.innerHTML;
                        button.innerHTML = '✓';
                        button.classList.add('copied');
                        
                        setTimeout(function() {{
                            button.innerHTML = originalContent;
                            button.classList.remove('copied');
                        }}, 2000);
                    }}).catch(function(err) {{
                        console.error('Failed to copy text: ', err);
                        // Fallback for older browsers
                        const textArea = document.createElement('textarea');
                        textArea.value = text;
                        document.body.appendChild(textArea);
                        textArea.select();
                        try {{
                            document.execCommand('copy');
                            // Same visual feedback as above
                            const originalContent = button.innerHTML;
                            button.innerHTML = '✓';
                            button.classList.add('copied');
                            
                            setTimeout(function() {{
                                button.innerHTML = originalContent;
                                button.classList.remove('copied');
                            }}, 2000);
                        }} catch (err) {{
                            console.error('Fallback copy failed: ', err);
                        }}
                        document.body.removeChild(textArea);
                    }});
                }}
                
                let lastUserMessage = null; // Track last user message to avoid duplicates
                
                async function submitForm(event) {{
                    event.preventDefault();
                    const form = document.getElementById('dataForm');
                    const status = document.getElementById('status');
                    const submitBtn = document.getElementById('submitBtn');
                    const formData = new FormData(form);
                    
                    // Build JSON object from form data
                    const data = {{}};
                    for (const [key, value] of formData.entries()) {{
                        if (key === 'apiKey') continue;
                        
                        const input = form.elements[key];
                        if (input.type === 'number') {{
                            data[key] = value ? parseFloat(value) : null;
                        }} else if (input.type === 'checkbox') {{
                            data[key] = input.checked;
                        }} else {{
                            data[key] = value;
                        }}
                    }}
                    
                    // Add user message to chat immediately for instant feedback
                    const displayProperty = '{html.escape(str(self.display_property))}' || Object.keys(data)[0];
                    const userMessage = data[displayProperty] || JSON.stringify(data);
                    lastUserMessage = userMessage; // Store to detect duplicates from server
                    addMessage(userMessage, 'user', new Date().toISOString());
                    
                    // Clear form, but preserve persistent fields
                    resetFormSelectively(form);
                    
                    submitBtn.disabled = true;
                    submitBtn.textContent = 'Sending...';
                    
                    try {{
                        const headers = {{'Content-Type': 'application/json'}};
                        const apiKey = document.getElementById('apiKey')?.value;
                        if (apiKey) {{
                            headers['X-API-Key'] = apiKey;
                        }}
                        
                        const response = await fetch('/process', {{
                            method: 'POST',
                            headers: headers,
                            body: JSON.stringify(data)
                        }});
                        
                        if (!response.ok) {{
                            throw new Error(`HTTP ${{response.status}}: ${{response.statusText}}`);
                        }}
                        
                        status.textContent = 'Message sent successfully!';
                        status.className = 'status success';
                        status.style.display = 'block';
                        
                        setTimeout(() => {{
                            status.style.display = 'none';
                            lastUserMessage = null; // Clear after a delay
                        }}, 3000);
                        
                    }} catch (error) {{
                        status.textContent = `Error: ${{error.message}}`;
                        status.className = 'status error';
                        status.style.display = 'block';
                        
                        addMessage(`Error: ${{error.message}}`, 'error', new Date().toISOString());
                        lastUserMessage = null; // Clear on error
                    }} finally {{
                        submitBtn.disabled = false;
                        submitBtn.textContent = 'Send Message';
                    }}
                }}
                
                // Event listeners
                document.getElementById('dataForm').addEventListener('submit', submitForm);
                
                // Initialize SSE on page load
                initSSE();
            </script>
        </body>
        </html>
        '''  # nosec B608 
    
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
        
        # nosec B608 - HTML template with proper escaping, not SQL injection
        return f'''<!DOCTYPE html>
        <html>
        <head>
            <title>{html.escape(self.title)}</title>
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
                    height: calc(100vh - {html.escape(height)});
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
                    {html.escape(form_style)}
                    background-color: {html.escape(input_bg)};
                    border: 1px solid {html.escape(border_color)};
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
                    color: {html.escape(text_color)};
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
                    <h1>{html.escape(self.title)}</h1>
                    <p>Submit JSON data using the form below or send POST requests to:</p>
                    <div class="endpoint-info">POST http://{html.escape(self.host)}:{html.escape(str(self.port))}/process</div>
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
                        <h3>{html.escape(self.form_config.title)}</h3>
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
        '''  # nosec B608

    def set_processor_function(self, func: Callable[[Dict[str, Any]], Any]):
        """Set the function used to process incoming JSON data"""
        self.processor_function = func
        logger.info(f"Port {self.port}: Processor function set to: {func.__name__}")
    
    def start(self, background: bool = False):
        """Start the FastAPI server"""
        print(f"\n{'='*60}")
        print(f"ChatterLang Server Started")
        print(f"{'='*60}")
        print(f"User Interface:     http://{self.host}:{self.port}/stream")
        print(f"API Endpoint:       http://{self.host}:{self.port}/process")
        print(f"API Documentation:  http://{self.host}:{self.port}/docs")
        if self.require_auth:
            print(f"Authentication:     ENABLED (API key required)")
        print(f"{'='*60}\n")

        # Also log for debugging purposes
        logger.info(f"Starting JSON Data Receiver on http://{self.host}:{self.port}")
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

@register_source("chatterlangServer")
class ChatterlangServerSegment(AbstractSource):
    """Segment for receiving JSON data via FastAPI with configurable form"""
    
    def __init__(self, port: Annotated[Union[int,str], "Port number for the server"] = 9999, host: Annotated[str, "Host address to bind to"] = "localhost", 
                 api_key: Annotated[Optional[str], "API key for authentication"] = None, require_auth: Annotated[bool, "Whether to require authentication"] = False,
                 form_config: Annotated[Union[str, Dict[str, Any], None], "Form configuration as dict, config variable, or file path"] = None):
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
        
        # Create a custom script that forwards data to our queue
        script_content = f"""
        def process_data(data):
            # This will be replaced by the segment's process_data method
            return "Data queued for processing"
        
        process_data
        """
        
        self.receiver = ChatterlangServer(
            host=host,
            port=self.port,
            api_key=api_key,
            require_auth=require_auth,
            title=f"JSON Receiver Segment (Port {port})",
            form_config=form_config,
            script_content=script_content
        )
        
        # Override the processor for each new session to use our queue
        original_get_or_create_session = self.receiver.get_or_create_session
        
        def patched_get_or_create_session(request, response):
            session = original_get_or_create_session(request, response)
            # Replace the compiled script with our custom processor
            session.compiled_script = lambda data: self.process_data(data)
            return session
        
        self.receiver.get_or_create_session = patched_get_or_create_session
        self.receiver.start(background=True)
        logger.info(f"Finished initializing ChatterlangServer on port {port}")

    def process_data(self, data: Dict[str, Any]) -> str:
        """Process incoming JSON data and add it to the queue"""
        try:
            self.queue.put(data, block=True, timeout=60)
            result = f"Data received and queued: {data}"
            return result
        except Exception as e:
            logger.error(f"Error processing data: {e}")
            error_msg = f"Error processing data: {str(e)}"
            return error_msg
        
    def generate(self):
        print("Starting ChatterlangServer generator...")
        while True:
            # Wait for data to be available in the queue
            print("Waiting for data...")
            # This will block until data is available
            yield self.queue.get(block=True, timeout=None)

def go():
    
    parser = argparse.ArgumentParser(description='FastAPI JSON Data Receiver with Configurable Form')
    parser.add_argument('-p', '--port', type=int, default=2025,
                        help='Port to listen on (default: 2025)')
    parser.add_argument('-o', '--host', default='localhost',
                        help='Host to bind to (default: localhost)')
    parser.add_argument('--api-key', help='Set API key for authentication')
    parser.add_argument('--require-auth', action='store_true',
                        help='Require API key authentication')
    parser.add_argument('--title', default='JSON Data Receiver',
                        help='Title for the FastAPI application')
    parser.add_argument('--script', default=None,
                        help='Chatterlang script to run on received data: file path, configuration key, or inline script content')
    parser.add_argument('--form-config', default=None,
                        help='Path to form configuration file (YAML or JSON) or config variable ($VAR_NAME)')
    parser.add_argument("--load-module", action='append', default=[], type=str, 
                        help="Path to a custom module file to import before running the script.")
    parser.add_argument('--display-property', default=None, 
                        help='Property of the input json to display in the stream interface as user input.')

    args, unknown_args = parser.parse_known_args()

    # Parse unknown arguments and add to configuration so they're accessible via $key syntax
    constants = parse_unknown_args(unknown_args)

    # Add command-line constants to the configuration
    if constants:
        add_config_values(constants, override=True)
        print(f"Added command-line values to configuration: {list(constants.keys())}")

    if args.load_module:
        for module_file in args.load_module:
            load_module_file(fname=module_file, fail_on_missing=False)

    # Get API key from command line, or fall back to configuration (which checks environment variable)
    api_key = args.api_key
    if api_key is None:
        api_key = get_config().get('API_KEY')

    script_content = None
    if args.script:
        script_content = load_script(args.script)
    
    # Load form configuration if provided
    form_config = None
    if args.form_config:
        if args.form_config.startswith('$'):
            # Try to load from config variable
            config_data = get_config()[args.form_config[1:]]
            if config_data:
                form_config = json.loads(config_data) if isinstance(config_data, str) else config_data
            else:
                # Try loading as file path
                form_config = load_form_config(args.form_config[1:])
        else:
            # Load from file
            form_config = load_form_config(args.form_config)

    receiver = ChatterlangServer(
        host=args.host,
        port=args.port,
        api_key=api_key,
        require_auth=args.require_auth,
        title=args.title,
        form_config=form_config,
        display_property=args.display_property,
        script_content=script_content
    )

    # Start the server
    receiver.start(background=False)

if __name__ == "__main__":
    go()