"""
FastAPI JSON Receiver Server with Configurable Form UI
Receives JSON data via HTTP and processes it with a configurable function
Multi-user support with session isolation
"""

import argparse
import asyncio
import functools
import html
import json
import logging
import secrets
import socket
import string
import sys
import threading
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from datetime import datetime, timedelta
from pathlib import Path
from queue import Empty, Queue
from typing import Annotated, Any

import uvicorn
import yaml
from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from pydantic import BaseModel

from talkpipe.app.server_common import (
    STATIC_DIR,
    add_host_port_args,
    add_load_module_arg,
    api_key_matches,
    apply_cli_constants,
    is_output_stream,
    load_module_files_or_exit,
    mount_static,
)
from talkpipe.chatterlang import compile, register_source
from talkpipe.chatterlang.compiler import CompileError
from talkpipe.pipe.core import AbstractSource
from talkpipe.util.config import get_config, load_script
from talkpipe.util.constants import ALLOWED_ORIGINS, API_KEY

logger = logging.getLogger(__name__)

#: Page templates (``string.Template`` syntax); their CSS and JavaScript are
#: static files under ``static/serve/``, served at ``/static/serve/``.
TEMPLATE_DIR = Path(__file__).parent / "templates" / "chatterlang_serve"

_FORM_POSITIONS = ("bottom", "top", "left", "right")

_AUTH_SECTION_HTML = """
            <div class="auth-section">
                <label for="apiKey">API Key:</label>
                <input type="password" id="apiKey" placeholder="Enter API key">
            </div>
"""


@functools.cache
def _load_template(name: str) -> string.Template:
    return string.Template((TEMPLATE_DIR / name).read_text(encoding="utf-8"))


def _render_template(name: str, **values: str) -> str:
    """Fill the named page template. Callers pass already-escaped values."""
    return _load_template(name).substitute(values)


# User Session Management
class UserSession:
    """Encapsulates per-user session state"""

    def __init__(
        self,
        session_id: str,
        script_content: str | None = None,
        history_length: int = 1000,
    ):
        self.session_id = session_id
        self.history: list[dict[str, Any]] = []
        self.history_length = history_length
        self.output_queue: Queue[Any] = Queue(maxsize=1000)
        self.compiled_script: Callable[..., Any] | None = None
        self.last_activity = datetime.now()
        # Scratch space for processor functions that keep per-session objects
        # (e.g. a built pipeline whose LLM adapter carries conversation memory).
        self.state: dict[str, Any] = {}
        # Held while this session's processor runs, so a stateful per-session
        # pipeline is never entered by two requests at once.
        self.lock = threading.Lock()

        # Compile script for this session if provided
        if script_content:
            self.compile_script(script_content)

    def compile_script(self, script_content: str) -> None:
        """Compile a Chatterlang script for this session"""
        # Compile script - configuration values are accessible via $key syntax
        self.compiled_script = compile(script_content)
        self.compiled_script = self.compiled_script.as_function(
            single_in=True, single_out=False
        )
        logger.info(f"Session {self.session_id}: Script compiled successfully")

    def add_to_history(self, entry: dict[str, Any]) -> None:
        """Add entry to session history"""
        self.history.append(entry)
        if len(self.history) > self.history_length:
            self.history = self.history[-self.history_length :]

    def add_output(self, output: str, message_type: str = "response") -> None:
        """Add output to session's output queue"""
        try:
            timestamped_output = {
                "timestamp": datetime.now().isoformat(),
                "output": output,
                "type": message_type,
            }
            self.output_queue.put(timestamped_output, block=False)
        except Exception as e:
            # Queue is full, remove oldest item
            logger.warning(f"Output queue full, attempting to remove oldest item: {e}")
            try:
                self.output_queue.get_nowait()
                self.output_queue.put(timestamped_output, block=False)
            except Exception as e2:
                logger.warning(
                    f"Failed to add output to queue even after removing oldest item: {e2}"
                )

    def update_activity(self) -> None:
        """Update last activity timestamp"""
        self.last_activity = datetime.now()


# Models
class DataResponse(BaseModel):
    status: str
    message: str
    data: dict[str, Any]
    timestamp: datetime


class DataHistory(BaseModel):
    entries: list[dict[str, Any]]
    count: int


# Configuration Models
class FormField(BaseModel):
    name: str
    type: str = "text"  # text, number, select, checkbox, textarea, date, email, etc.
    label: str | None = None
    placeholder: str | None = None
    required: bool = False
    default: Any | None = None
    options: list[str] | None = None  # For select fields
    min: int | float | None = None  # For number fields
    max: int | float | None = None  # For number fields
    rows: int | None = None  # For textarea
    persist: bool = False  # If True, field values will not be reset after submission


class FormConfig(BaseModel):
    title: str = "Data Input Form"
    fields: list[FormField] = []
    position: str = "bottom"  # bottom, top, left, right
    height: str = "150px"  # CSS height for the form panel
    theme: str = "dark"  # dark, light


class ChatterlangServer:
    """ChatterLang Server Class with configurable form UI and multi-user support"""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 9999,
        api_key: str | None = None,
        require_auth: bool = False,
        processor_func: Callable[..., Any] | None = None,
        title: str | None = None,
        history_length: int = 1000,
        form_config: dict[str, Any] | None = None,
        display_property: str | None = None,
        script_content: str | None = None,
        secure_cookies: bool = False,
    ):
        """Create the server.

        ``api_key`` has no default: when ``require_auth`` is set and no key is
        given, a random one is generated so the server never runs behind a
        guessable, published default. The generated key is deliberately not
        logged (clear-text logging of a credential); an embedding application
        can read it from ``self.api_key`` and distribute it out of band. The
        CLI (``go``) refuses to start in this state instead, since its
        operator would have no way to learn the key.
        ``secure_cookies`` marks the session cookie ``Secure`` (HTTPS only);
        leave it off for plain-HTTP localhost use.
        """
        self.host = host
        self.port = port
        self.require_auth = require_auth
        if require_auth and not api_key:
            api_key = secrets.token_urlsafe(32)
            logger.warning(
                "require_auth is set but no API key was given; generated a "
                "random one for this run. It is deliberately not logged: read "
                "it from this server's api_key attribute and provide it to "
                "clients as X-API-Key."
            )
        self.api_key = api_key
        self.secure_cookies = secure_cookies
        if title is None:
            # No explicit title: use the form config's title so the browser tab
            # matches what the page shows, rather than a generic default.
            if form_config and form_config.get("title"):
                title = form_config["title"]
            else:
                title = "ChatterLang Server"
        self.title = title
        self.history_length = history_length
        self.display_property = display_property
        self.script_content = script_content

        # Session management
        self.sessions: dict[str, UserSession] = {}
        self.session_lock = threading.Lock()

        # Parse form configuration
        if form_config:
            self.form_config = FormConfig(**form_config)
        else:
            # Default form configuration
            self.form_config = FormConfig(
                title="Data Input Form",
                fields=[
                    FormField(
                        name="prompt",
                        type="text",
                        label="Prompt",
                        placeholder="Enter prompt",
                        required=True,
                    ),
                ],
            )

        # Set up processor function
        self.processor_function = processor_func or self._default_print_processor

        # Create FastAPI app instance
        self.app = FastAPI(title=f"{title} (Port {port})", version="1.0.0")

        # Mount favicon.ico directly to root
        @self.app.get("/favicon.ico")
        async def favicon() -> FileResponse:
            favicon_path = STATIC_DIR / "favicon.ico"
            if favicon_path.exists():
                return FileResponse(favicon_path)
            raise HTTPException(status_code=404, detail="Favicon not found")

        # Configure middleware
        self._setup_middleware()

        # Add security headers middleware
        self._setup_security_headers()

        # Configure routes
        self._setup_routes()

        # The pages' CSS and JavaScript (including the vendored Markdown
        # renderer), so the UI works with no internet access.
        mount_static(self.app)

        # Server instance for stopping
        self.server = None
        self.server_thread: threading.Thread | None = None
        self._uvicorn_server: uvicorn.Server | None = None

        # Start session cleanup task
        self._start_cleanup_task()

    def _create_session(self, session_id: str) -> UserSession:
        """Create a session, reporting script compile errors to the client rather
        than letting them surface as an opaque 500 with no detail."""
        try:
            return UserSession(
                session_id=session_id,
                script_content=self.script_content,
                history_length=self.history_length,
            )
        except CompileError as exc:
            raise HTTPException(
                status_code=500, detail=f"ChatterLang script failed to compile: {exc}"
            ) from exc

    def get_or_create_session(
        self, request: Request, response: Response
    ) -> UserSession:
        """Get existing session or create new one based on session cookie"""
        session_id = request.cookies.get("talkpipe_session_id")

        with self.session_lock:
            if session_id and session_id in self.sessions:
                # Update activity for existing session
                session = self.sessions[session_id]
                session.update_activity()
                return session

            # A cookie we don't recognise (server restarted, or a value the
            # client made up) is never adopted as-is: the id is what keys the
            # session table, so it is always minted here.
            if session_id:
                logger.info("Unknown session cookie presented; issuing a new session")

            # Create new session
            session_id = str(uuid.uuid4())
            session = self._create_session(session_id)
            self.sessions[session_id] = session

            # Set session cookie (expires in 24 hours) with security attributes
            response.set_cookie(
                key="talkpipe_session_id",
                value=session_id,
                max_age=86400,  # 24 hours
                httponly=True,  # Prevent JavaScript access
                samesite="lax",  # CSRF protection
                secure=self.secure_cookies,
                path="/",  # Restrict cookie path
            )

            logger.info(f"Created new session: {session_id}")
            return session

    def cleanup_expired_sessions(self, max_age_hours: int = 24) -> None:
        """Clean up sessions that haven't been active for max_age_hours"""
        cutoff_time = datetime.now() - timedelta(hours=max_age_hours)

        with self.session_lock:
            expired_sessions = [
                session_id
                for session_id, session in self.sessions.items()
                if session.last_activity < cutoff_time
            ]

            for session_id in expired_sessions:
                del self.sessions[session_id]
                logger.info(f"Cleaned up expired session: {session_id}")

    def get_session_by_id(self, session_id: str) -> UserSession | None:
        """Get session by ID, return None if not found"""
        with self.session_lock:
            return self.sessions.get(session_id)

    def _start_cleanup_task(self) -> None:
        """Start background task to cleanup expired sessions"""

        def cleanup_worker() -> None:
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

    def _setup_middleware(self) -> None:
        """Configure CORS middleware with security restrictions"""
        # Define allowed origins - never use "*" in production
        allowed_origins = [
            "http://localhost:3000",
            "http://localhost:8000",
            "http://127.0.0.1:3000",
            "http://127.0.0.1:8000",
            f"http://localhost:{self.port}",
            f"http://127.0.0.1:{self.port}",
        ]

        # Add environment-specific origins if configured
        import os

        env_origins = os.getenv(f"TALKPIPE_{ALLOWED_ORIGINS}", "").split(",")
        allowed_origins.extend(
            [origin.strip() for origin in env_origins if origin.strip()]
        )

        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=allowed_origins,  # Specific origins only - never "*"
            allow_credentials=True,
            allow_methods=[
                "GET",
                "POST",
                "PUT",
                "DELETE",
                "OPTIONS",
            ],  # Specific methods only
            allow_headers=[
                "Content-Type",
                "Authorization",
                "X-API-Key",
            ],  # Specific headers only
            expose_headers=["Content-Type"],
            max_age=86400,  # Cache preflight requests for 24 hours
        )

    def _setup_security_headers(self) -> None:
        """Add security headers to all responses"""

        @self.app.middleware("http")
        async def add_security_headers(
            request: Request, call_next: Callable[[Request], Awaitable[Response]]
        ) -> Response:
            response = await call_next(request)

            # Security headers
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-XSS-Protection"] = "1; mode=block"
            response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
            # Scripts come only from this server (no inline handlers, no CDN);
            # styles allow inline because the pages set layout variables in a
            # style attribute.
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "script-src 'self'; "
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

    def _setup_routes(self) -> None:
        """Configure all API routes"""

        @self.app.get("/", response_class=HTMLResponse)
        async def root(request: Request, response: Response) -> Any:
            return self._get_html_interface()

        @self.app.get("/stream", response_class=HTMLResponse)
        async def stream_page(request: Request, response: Response) -> Any:
            return self._get_stream_interface()

        # Plain ``def`` handlers on purpose: they drive synchronous pipelines
        # (LLM calls, HTTP fetches), so Starlette must run them in its
        # threadpool rather than on the event loop.
        @self.app.post("/process", response_model=DataResponse)
        def process_json(
            data: dict[str, Any],
            request: Request,
            response: Response,
            api_key: str = Depends(self._verify_api_key),
        ) -> DataResponse:
            session = self.get_or_create_session(request, response)
            return self._process_json(data, session)

        @self.app.get("/history", response_model=DataHistory)
        def get_history(
            request: Request,
            response: Response,
            limit: int = 50,
            api_key: str = Depends(self._verify_api_key),
        ) -> DataHistory:
            session = self.get_or_create_session(request, response)
            return self._get_history(limit, session)

        @self.app.delete("/history")
        def clear_history(
            request: Request,
            response: Response,
            api_key: str = Depends(self._verify_api_key),
        ) -> dict[str, str]:
            session = self.get_or_create_session(request, response)
            return self._clear_history(session)

        @self.app.get("/health")
        async def health_check() -> dict[str, Any]:
            return {"status": "healthy", "timestamp": datetime.now(), "port": self.port}

        @self.app.get("/form-config")
        async def get_form_config() -> dict[str, Any]:
            return self.form_config.model_dump()

        @self.app.get("/output-stream")
        async def output_stream(
            request: Request,
            response: Response,
            api_key: str = Depends(self._verify_api_key),
        ) -> StreamingResponse:
            """Server-Sent Events endpoint for streaming output"""
            session = self.get_or_create_session(request, response)
            return StreamingResponse(
                self._generate_output_stream(session),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Content-Type-Options": "nosniff",
                },
            )

    async def _verify_api_key(self, x_api_key: str | None = Header(None)) -> str | None:
        """Dependency for API key validation"""
        if self.require_auth and not api_key_matches(x_api_key, self.api_key):
            raise HTTPException(status_code=403, detail="Invalid API key")
        return x_api_key

    def _default_print_processor(
        self, data: dict[str, Any], session: UserSession
    ) -> str:
        """Default processor function that just prints the data"""
        logger.info(
            f"Port {self.port} Session {session.session_id}: Processing data with default handler"
        )
        logger.info(
            f"Port {self.port} Session {session.session_id}: Received data: {json.dumps(data, indent=2)}"
        )
        return f"Data received: {data}"

    async def _generate_output_stream(self, session: UserSession) -> AsyncIterator[str]:
        """Generate Server-Sent Events stream for a specific session"""
        while True:
            try:
                # Non-blocking check so the event loop is never stalled
                output = session.output_queue.get_nowait()
                yield f"data: {json.dumps(output)}\n\n"
            except Empty:
                # Send heartbeat to keep connection alive
                yield ": heartbeat\n\n"

            await asyncio.sleep(0.1)

    def _process_json(self, data: dict[str, Any], session: UserSession) -> DataResponse:
        """Process JSON data and return response"""
        try:
            with session.lock:
                output_items = self._run_processor(data, session)

            # Do not add response items to output_queue - the stream UI displays from the
            # /process response to avoid duplicates. SSE output_queue is only used for errors.

            # Store in session history
            session.add_to_history(
                {
                    "timestamp": datetime.now(),
                    "input": data,
                    "output": output_items if output_items else "No output",
                }
            )

            return DataResponse(
                status="success",
                message="Data processed successfully",
                data={
                    "input": data,
                    "output": output_items,
                    "count": len(output_items),
                },
                timestamp=datetime.now(),
            )
        except Exception as e:
            error_msg = f"Error processing data: {e!s}"
            session.add_output(error_msg, "error")
            logger.error(f"Port {self.port} Session {session.session_id}: {error_msg}")
            raise HTTPException(status_code=500, detail=error_msg) from e

    def _run_processor(self, data: dict[str, Any], session: UserSession) -> list[Any]:
        """Run the session's script (or the processor function) and collect its output."""
        if session.compiled_script:
            result = session.compiled_script(data)
        else:
            result = self.processor_function(data, session)

        output_items: list[Any] = []
        if is_output_stream(result):
            try:
                output_items.extend(item for item in result if item is not None)
            except Exception as e:
                error_msg = f"Error processing iterator: {e!s}"
                session.add_output(error_msg, "error")
                output_items.append({"error": error_msg})
        elif result is not None:
            output_items.append(result)
        return output_items

    def _get_history(self, limit: int, session: UserSession) -> DataHistory:
        """Get processing history for a session"""
        entries = session.history[-limit:] if limit > 0 else session.history
        return DataHistory(entries=entries, count=len(entries))

    def _clear_history(self, session: UserSession) -> dict[str, str]:
        """Clear processing history for a session"""
        session.history.clear()
        logger.info(f"Port {self.port} Session {session.session_id}: History cleared")
        return {"status": "success", "message": "History cleared"}

    def _generate_form_fields(self) -> str:
        """Generate HTML for form fields based on configuration.

        Every configured value that lands in the markup is HTML-escaped: the
        form config is operator-supplied, but a stray quote in a label must not
        break (or script) the page.
        """
        fields_html = []
        esc = html.escape

        for field in self.form_config.fields:
            name = esc(field.name)
            label = esc(field.label or field.name.capitalize())
            required = "required" if field.required else ""
            persist_attr = 'data-persist="true"' if field.persist else ""
            placeholder = esc(str(field.placeholder or ""))
            input_type = esc(field.type)

            if field.type == "select" and field.options:
                options = "".join(
                    f'<option value="{esc(str(opt))}">{esc(str(opt))}</option>'
                    for opt in field.options
                )
                field_html = f'''
                <div class="form-group">
                    <label for="{name}">{label}:</label>
                    <select name="{name}" id="{name}" {required} {persist_attr}>
                        <option value="">Choose...</option>
                        {options}
                    </select>
                </div>
                '''
            elif field.type == "textarea":
                rows = int(field.rows or 3)
                default_text = esc(str(field.default or ""))
                field_html = f'''
                <div class="form-group">
                    <label for="{name}">{label}:</label>
                    <textarea name="{name}" id="{name}" rows="{rows}"
                              placeholder="{placeholder}" {required} {persist_attr}>{default_text}</textarea>
                </div>
                '''
            elif field.type == "checkbox":
                checked = "checked" if field.default else ""
                field_html = f'''
                <div class="form-group checkbox-group">
                    <label>
                        <input type="checkbox" name="{name}" id="{name}" {checked} {persist_attr}>
                        {label}
                    </label>
                </div>
                '''
            else:
                # Default input types (text, number, date, email, etc.)
                min_attr = (
                    f'min="{esc(str(field.min))}"' if field.min is not None else ""
                )
                max_attr = (
                    f'max="{esc(str(field.max))}"' if field.max is not None else ""
                )
                default_val = (
                    f'value="{esc(str(field.default))}"'
                    if field.default is not None
                    else ""
                )

                field_html = f'''
                <div class="form-group">
                    <label for="{name}">{label}:</label>
                    <input type="{input_type}" name="{name}" id="{name}"
                           placeholder="{placeholder}" {required} {min_attr} {max_attr} {default_val} {persist_attr}>
                </div>
                '''

            fields_html.append(field_html)

        return "\n".join(fields_html)

    def _page_context(self) -> dict[str, str]:
        """Values every page template takes. All operator-supplied text is
        HTML-escaped here; the templates never escape on their own."""
        position = self.form_config.position
        if position not in _FORM_POSITIONS:
            position = "bottom"
        theme = "dark" if self.form_config.theme == "dark" else "light"
        return {
            "title": html.escape(self.title),
            "form_title": html.escape(self.form_config.title),
            "theme": theme,
            "position": position,
            "height": html.escape(self.form_config.height),
            "auth_section": _AUTH_SECTION_HTML if self.require_auth else "",
            "form_fields": self._generate_form_fields(),
        }

    def _get_stream_interface(self) -> str:
        """The chat-style page at ``/stream`` (templates/chatterlang_serve/stream.html)."""
        return _render_template(
            "stream.html",
            **self._page_context(),
            display_property=html.escape(self.display_property or ""),
        )

    def _get_html_interface(self) -> str:
        """The form-and-history page at ``/`` (templates/chatterlang_serve/index.html)."""
        return _render_template(
            "index.html",
            **self._page_context(),
            host=html.escape(self.host),
            port=html.escape(str(self.port)),
            auth_note=(
                "<p>Authentication required: Include 'X-API-Key' header</p>"
                if self.require_auth
                else ""
            ),
        )

    def set_processor_function(self, func: Callable[..., Any]) -> None:
        """Set the function used to process incoming JSON data"""
        self.processor_function = func
        logger.info(f"Port {self.port}: Processor function set to: {func.__name__}")

    def _check_port_available(self) -> None:
        """Verify the host/port can be bound before announcing the server.

        uvicorn reports a failed bind as a logged ERROR and returns, which
        previously left our success banner on screen next to dead URLs. A
        pre-flight bind turns that into a clear fatal error instead. (There
        is a small window between this check and uvicorn's own bind, but a
        port grabbed in that window still surfaces as uvicorn's ERROR.)
        """
        try:
            infos = socket.getaddrinfo(self.host, self.port, type=socket.SOCK_STREAM)
        except socket.gaierror as exc:
            raise RuntimeError(f"Cannot resolve host '{self.host}': {exc}") from exc
        family, socktype, proto, _, sockaddr = infos[0]
        with socket.socket(family, socktype, proto) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(sockaddr)
            except OSError as exc:
                raise RuntimeError(
                    f"Cannot start ChatterLang server: failed to bind "
                    f"http://{self.host}:{self.port} ({exc}). Is the port "
                    f"already in use, or blocked? Try a different port."
                ) from exc

    def start(self, background: bool = False) -> None:
        """Start the FastAPI server"""
        self._check_port_available()
        print(f"\n{'=' * 60}")
        print("ChatterLang Server Started")
        print(f"{'=' * 60}")
        print(f"User Interface:     http://{self.host}:{self.port}/stream")
        print(f"API Endpoint:       http://{self.host}:{self.port}/process")
        print(f"API Documentation:  http://{self.host}:{self.port}/docs")
        if self.require_auth:
            print("Authentication:     ENABLED (API key required)")
        print(f"{'=' * 60}\n")

        # Also log for debugging purposes
        logger.info(f"Starting JSON Data Receiver on http://{self.host}:{self.port}")
        processor_name = self.processor_function.__name__
        logger.info(f"Port {self.port}: Using processor function: {processor_name}")

        # Drive uvicorn through a Server object rather than uvicorn.run() so
        # stop() can ask it to exit; uvicorn.run() offers no handle at all.
        config = uvicorn.Config(self.app, host=self.host, port=self.port)
        self._uvicorn_server = uvicorn.Server(config)
        if background:
            self.server_thread = threading.Thread(
                target=self._uvicorn_server.run,
                daemon=True,
            )
            self.server_thread.start()
            logger.info(f"Port {self.port}: Server started in background thread")
        else:
            self._uvicorn_server.run()

    def stop(self, timeout: float = 10.0) -> None:
        """Stop a server started with ``start(background=True)``.

        Signals uvicorn to exit and waits up to ``timeout`` seconds for the
        server thread to finish. A no-op if the server is not running.
        """
        if self._uvicorn_server is not None:
            logger.info(f"Port {self.port}: Stopping server...")
            self._uvicorn_server.should_exit = True
        if self.server_thread and self.server_thread.is_alive():
            self.server_thread.join(timeout)
            if self.server_thread.is_alive():
                logger.warning(
                    f"Port {self.port}: server thread did not stop within {timeout}s"
                )


def load_form_config(config_path: str) -> dict[str, Any]:
    """Load form configuration from YAML or JSON file"""
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    with open(path) as f:
        config: dict[str, Any]
        if path.suffix in [".yaml", ".yml"]:
            config = yaml.safe_load(f)
        elif path.suffix == ".json":
            config = json.load(f)
        else:
            raise ValueError(f"Unsupported configuration file format: {path.suffix}")
    return config


def resolve_form_config(
    form_config: str | dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Resolve a form configuration given as a dict, a file path, or ``$name``.

    ``$name`` is looked up in the configuration (a JSON string or a table);
    if it is not set there, ``name`` is tried as a file path.
    """
    if not isinstance(form_config, str):
        return form_config
    if form_config.startswith("$"):
        name = form_config[1:]
        config_data: Any = get_config().get(name)
        if config_data:
            resolved: dict[str, Any] = (
                json.loads(config_data) if isinstance(config_data, str) else config_data
            )
            return resolved
        return load_form_config(name)
    return load_form_config(form_config)


@register_source("chatterlangServer")
class ChatterlangServerSegment(AbstractSource[Any]):
    """Segment for receiving JSON data via FastAPI with configurable form"""

    def __init__(
        self,
        port: Annotated[int | str, "Port number for the server"] = 9999,
        host: Annotated[str, "Host address to bind to"] = "localhost",
        api_key: Annotated[str | None, "API key for authentication"] = None,
        require_auth: Annotated[bool, "Whether to require authentication"] = False,
        form_config: Annotated[
            str | dict[str, Any] | None,
            "Form configuration as dict, config variable, or file path",
        ] = None,
        secure_cookies: Annotated[
            bool, "Mark the session cookie Secure (HTTPS deployments only)"
        ] = False,
    ):
        super().__init__()
        self.port = int(port)
        self.host = host
        self.api_key = api_key
        self.require_auth = require_auth
        self.secure_cookies = secure_cookies
        self.queue: Queue[Any] = Queue(maxsize=1000)

        form_config_dict = resolve_form_config(form_config)

        # Create a custom script that forwards data to our queue
        script_content = """
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
            form_config=form_config_dict,
            script_content=script_content,
            secure_cookies=secure_cookies,
        )

        # Override the processor for each new session to use our queue
        original_get_or_create_session = self.receiver.get_or_create_session

        def patched_get_or_create_session(
            request: Request, response: Response
        ) -> UserSession:
            session = original_get_or_create_session(request, response)
            # Replace the compiled script with our custom processor
            session.compiled_script = lambda data: self.process_data(data)
            return session

        self.receiver.get_or_create_session = patched_get_or_create_session  # type: ignore[method-assign]  # per-instance hook; the server has no injection point for it
        self.receiver.start(background=True)
        logger.info(f"Finished initializing ChatterlangServer on port {port}")

    def process_data(self, data: dict[str, Any]) -> str:
        """Process incoming JSON data and add it to the queue"""
        try:
            self.queue.put(data, block=True, timeout=60)
            return f"Data received and queued: {data}"
        except Exception as e:
            logger.error(f"Error processing data: {e}")
            return f"Error processing data: {e!s}"

    def generate(self) -> Iterator[Any]:
        print("Starting ChatterlangServer generator...")
        while True:
            # Wait for data to be available in the queue
            print("Waiting for data...")
            # This will block until data is available
            yield self.queue.get(block=True, timeout=None)


def go() -> None:

    parser = argparse.ArgumentParser(
        description="FastAPI JSON Data Receiver with Configurable Form"
    )
    add_host_port_args(parser, default_host="localhost", default_port=2025)
    parser.add_argument("--api-key", help="Set API key for authentication")
    parser.add_argument(
        "--require-auth",
        action="store_true",
        help="Require API key authentication; supply the key with --api-key "
        "or the TALKPIPE_API_KEY configuration",
    )
    parser.add_argument(
        "--secure-cookies",
        action="store_true",
        help="Mark the session cookie Secure; only for HTTPS deployments "
        "(behind a TLS-terminating proxy)",
    )
    parser.add_argument(
        "--title",
        default=None,
        help="Title for the web pages and FastAPI application "
        "(default: the form config title if it sets one, "
        "else 'JSON Data Receiver')",
    )
    parser.add_argument(
        "--script",
        default=None,
        help="Chatterlang script to run on received data: file path, configuration key, or inline script content",
    )
    parser.add_argument(
        "--form-config",
        default=None,
        help="Path to form configuration file (YAML or JSON) or config variable ($VAR_NAME)",
    )
    add_load_module_arg(parser)
    parser.add_argument(
        "--display-property",
        default=None,
        help="Property of the input json to display in the stream interface as user input.",
    )

    args, unknown_args = parser.parse_known_args()

    # Leftover --key value arguments become configuration values ($key in scripts)
    apply_cli_constants(unknown_args)
    load_module_files_or_exit(args.load_module)

    # Get API key from command line, or fall back to configuration (which checks environment variable)
    api_key = args.api_key
    if api_key is None:
        api_key = get_config().get(API_KEY)
    if args.require_auth and not api_key:
        # ChatterlangServer would generate a random key, but it is
        # deliberately never logged or printed (clear-text logging of a
        # credential), so a server started this way could not be
        # authenticated to by anyone. Refuse to start instead of silently
        # locking the operator out.
        print(
            "ERROR: --require-auth needs an API key. Pass --api-key or set "
            "TALKPIPE_API_KEY; generate one with e.g.\n"
            "  python3 -c 'import secrets; print(secrets.token_urlsafe(32))'",
            file=sys.stderr,
        )
        sys.exit(1)

    script_content = None
    if args.script:
        script_content = load_script(args.script)
        # Fail at startup on an uncompilable script instead of surfacing the
        # error only when the first request arrives.
        try:
            compile(script_content)
        except CompileError as exc:
            print(
                f"ERROR: Cannot start ChatterLang server: the script failed to "
                f"compile.\n{exc}",
                file=sys.stderr,
            )
            sys.exit(1)

    # Load form configuration if provided
    form_config = None
    if args.form_config:
        try:
            form_config = resolve_form_config(args.form_config)
        except FileNotFoundError as exc:
            print(
                f"ERROR: {exc}. Relative paths are resolved against the current "
                f"directory; run the command from the directory containing the "
                f"form config or pass an absolute path.",
                file=sys.stderr,
            )
            sys.exit(1)

    # Explicit --title wins; otherwise fall back to the form config's title so
    # the browser tab matches the page, and finally to the historical default.
    title = args.title
    if title is None:
        title = (form_config or {}).get("title") or "JSON Data Receiver"

    receiver = ChatterlangServer(
        host=args.host,
        port=args.port,
        api_key=api_key,
        require_auth=args.require_auth,
        title=title,
        form_config=form_config,
        display_property=args.display_property,
        script_content=script_content,
        secure_cookies=args.secure_cookies,
    )

    # Start the server
    try:
        receiver.start(background=False)
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    go()
