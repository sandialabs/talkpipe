import argparse
import asyncio
import atexit
import contextlib
import logging
import os
import queue
import sys
import threading
import uuid
from collections import OrderedDict
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    StreamingResponse,
)
from pydantic import BaseModel

from talkpipe.app.chatterlang_reference_generator import (
    analyze_registered_items,
    generate_html,
    generate_text,
)
from talkpipe.app.server_common import (
    STATIC_DIR,
    add_host_port_args,
    add_load_module_arg,
    api_key_matches,
    apply_cli_constants,
    is_interactive_script,
    is_loopback_host,
    iter_output_text,
    mount_static,
)
from talkpipe.app.workbench import reference_api, suggest_api, workspace_api
from talkpipe.chatterlang.compiler import compile
from talkpipe.util.config import add_config_values, load_module_file
from talkpipe.util.constants import WORKBENCH_API_KEY, WORKBENCH_LOAD_MODULES

__all__ = ["app", "is_loopback_host", "main"]

logger = logging.getLogger(__name__)


def _load_configured_modules() -> None:
    """Import custom module files listed in the workbench configuration.

    ``main()`` records ``--load-module`` paths in the
    ``TALKPIPE_workbench_load_modules`` environment variable rather than
    importing them directly: with ``--reload``, uvicorn re-imports the app
    in a subprocess where only the environment survives, so importing here
    (at app startup) makes custom modules work in both modes.
    """
    from talkpipe.util.config import get_config

    configured = get_config().get(WORKBENCH_LOAD_MODULES)
    if not configured:
        return
    import os

    for module_file in configured.split(os.pathsep):
        if module_file:
            load_module_file(fname=module_file, fail_on_missing=False)


class _DropCancelledRequestTracebacks(logging.Filter):
    """Hide uvicorn's "Exception in ASGI application" report for cancelled requests.

    Installed once the app has shut down (see the Shutdown section below): the
    only requests still running then are the ones uvicorn cancelled because
    the grace period expired, and it reports each of them with a full
    ``CancelledError`` traceback although nothing went wrong.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        exc = record.exc_info[1] if record.exc_info else None
        return not isinstance(exc, asyncio.CancelledError)


_cancelled_request_filter = _DropCancelledRequestTracebacks()


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    _load_configured_modules()
    # Building the component reference imports every registered component
    # (seconds); do it in the background so the first browser fetch is fast.
    reference_api.warm_reference_cache_async()
    yield
    logging.getLogger("uvicorn.error").addFilter(_cancelled_request_filter)


app = FastAPI(lifespan=_lifespan)
mount_static(app)

WORKBENCH_STATIC_DIR = STATIC_DIR / "workbench"

app.include_router(reference_api.router)
app.include_router(workspace_api.router)
app.include_router(suggest_api.router)


# --- Access control -----------------------------------------------------------
#
# The workbench compiles and RUNS whatever chatterlang it is sent, as the user
# who started it, and a script can read any configuration value (including
# API keys) via ``$name``. It is meant for one developer on their own machine,
# so it binds to loopback by default and refuses other hosts unless asked.
# Optionally a token protects every route that does work; the UI shell and its
# static assets stay open so the page can load and prompt for the token.

_PROTECTED_PREFIXES = ("/api/", "/compile", "/go", "/logs", "/examples", "/docs/")

WORKBENCH_BANNER = (
    "ChatterLang Workbench executes arbitrary chatterlang scripts as your user\n"
    "and exposes your TalkPipe configuration (including any API keys) to those\n"
    "scripts. Keep it bound to a loopback address; if you must expose it, set\n"
    "--api-key and put it behind TLS."
)


def _configured_api_key() -> str | None:
    """The workbench token, if one is configured (``workbench_api_key``)."""
    from talkpipe.util.config import get_config

    value = get_config().get(WORKBENCH_API_KEY)
    return str(value) if value else None


def _is_protected(path: str) -> bool:
    return any(
        path == prefix.rstrip("/") or path.startswith(prefix)
        for prefix in _PROTECTED_PREFIXES
    )


@app.middleware("http")
async def _require_api_key(request: Request, call_next: Any) -> Any:
    key = _configured_api_key()
    if (
        key
        and _is_protected(request.url.path)
        and not api_key_matches(request.headers.get("x-api-key"), key)
    ):
        return JSONResponse({"detail": "Missing or invalid X-API-Key"}, status_code=401)
    return await call_next(request)


# Log capture for the UI's log panel. The queue is bounded: nothing drains it
# unless a browser polls GET /logs, so an unbounded queue would grow for the
# life of the process. When full, the oldest entry is dropped.
LOG_QUEUE_MAXSIZE = 10_000
log_queue: queue.Queue[str] = queue.Queue(maxsize=LOG_QUEUE_MAXSIZE)
log_handler = logging.StreamHandler()
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
log_handler.setFormatter(formatter)


# Custom handler to capture logs
class QueueHandler(logging.Handler):
    """Append formatted records to ``log_queue``, dropping the oldest when full."""

    def emit(self, record: logging.LogRecord) -> None:
        log_entry = self.format(record)
        while True:
            try:
                log_queue.put_nowait(log_entry)
                return
            except queue.Full:
                with contextlib.suppress(queue.Empty):
                    log_queue.get_nowait()


queue_handler = QueueHandler()
queue_handler.setFormatter(formatter)


def configure_logging() -> None:
    """Attach the UI log capture to the root logger.

    Called from ``main()`` rather than at import time so that merely importing
    this module (e.g. from tests or another application) does not reconfigure
    the host process's logging.
    """
    root = logging.getLogger()
    if queue_handler not in root.handlers:
        root.addHandler(queue_handler)
    root.setLevel(logging.INFO)


class _CompiledScriptStore(OrderedDict[str, dict[str, Any]]):
    """Bounded, insertion-ordered store of compiled script instances.

    Every POST /compile creates a live pipeline; without a bound the store grows
    for the life of the process. Once ``maxsize`` entries exist, the least
    recently used one is evicted; a later /go for it returns 404.
    """

    def __init__(self, maxsize: int = 100):
        super().__init__()
        self.maxsize = maxsize

    def __setitem__(self, key: str, value: dict[str, Any]) -> None:
        super().__setitem__(key, value)
        self.move_to_end(key)
        while len(self) > self.maxsize:
            self.popitem(last=False)

    def get(self, key: str, default: Any = None) -> Any:
        if key in self:
            self.move_to_end(key)
        return super().get(key, default)


COMPILED_SCRIPTS_MAXSIZE = 100
# Global in-memory store for compiled script instances
compiled_scripts: _CompiledScriptStore = _CompiledScriptStore(COMPILED_SCRIPTS_MAXSIZE)

# Define example scripts to display in the UI
EXAMPLE_SCRIPTS = {
    "Basic Examples": [
        {
            "name": "Hello World",
            "description": "Print a message (echo splits comma-separated data into items)",
            "code": 'INPUT FROM echo[data="Hello, ChatterLang World!"] | print',
        },
        {
            "name": "Data Transformation",
            "description": "Convert strings to integers",
            "code": 'INPUT FROM echo[data="1|2|hello|3", delimiter="|"] | cast[cast_type="int"] | print',
        },
        {
            "name": "Using Variables",
            "description": "Store data in a variable and reuse it",
            "code": 'INPUT FROM echo[data="1,2,3,4,5"] | @numbers; INPUT FROM @numbers | print',
        },
    ],
    "LLM Examples": [
        {
            "name": "Simple Chat",
            "description": "Interactive conversation with an LLM",
            "code": '| llmPrompt[model="llama3.2", source="ollama", multi_turn=True]',
        },
        {
            "name": "Agent Conversation",
            "description": "Two agents debating a topic",
            "code": 'CONST economist_prompt = "You are an economist debating a proposition. Reply in one sentence.";\nCONST theologian_prompt="You are a reformed theologian debating a proposition. Reply in one sentence.";\nINPUT FROM echo[data="The US should give free puppies to all children."] | @next_utterance | accum[variable=@conv] | print;\nLOOP 3 TIMES {\n    INPUT FROM @next_utterance | llmPrompt[system_prompt=economist_prompt] | @next_utterance | accum[variable=@conv] | print;\n    INPUT FROM @next_utterance | llmPrompt[system_prompt=theologian_prompt] | @next_utterance | accum[variable=@conv] | print;\n};\nINPUT FROM @conv',
        },
        {
            "name": "Web Page Summarizer",
            "description": "Download and summarize a web page",
            "code": '| downloadURL | htmlToText | llmPrompt[system_prompt="Summarize the following text in 3-5 sentences:"]',
        },
    ],
    "Image Examples": [
        {
            "name": "Describe the TalkPipe Logo",
            "description": "Fetch the workbench's own logo image and ask a vision LLM to describe it",
            "code": '# Pulls the logo image from this running TalkPipe workbench server.\n# $workbench_logo_url is populated by chatterlang_workbench at startup\n# based on the --host and --port arguments.\n# Example assumes that ollama is installed and the gemma4:31b-cloud has been pulled.\nINPUT FROM echo[data=$workbench_logo_url]\n    | toDict[field_list="_:image"]\n    | llmVisionPrompt[\n        image_field="image",\n        model="gemma4:31b-cloud",\n        source="ollama",\n        prompt="Describe what you see in this image in two or three sentences.",\n        set_as="answer"\n      ]\n    | print',
        }
    ],
    "Advanced Examples": [
        {
            "name": "Data Analysis Loop",
            "description": "Process data in multiple iterations",
            "code": "INPUT FROM range[lower=0, upper=5] | @data;\nLOOP 3 TIMES {\n    INPUT FROM @data | scale[multiplier=2] | @data\n};\nINPUT FROM @data | print",
        },
        {
            "name": "Document Evaluation",
            "description": "Score a document on relevance to a topic",
            "code": 'CONST scorePrompt = "On a scale of 1 to 10, rate how relevant the following text is to artificial intelligence. Provide a score and brief explanation.";\n| llmScore[system_prompt=scorePrompt] | print',
        },
        {
            "name": "RAG Pipeline with Vector Database",
            "description": "Build a complete RAG system with document indexing and querying",
            "code": '# This example demonstrates a complete RAG (Retrieval-Augmented Generation) workflow.\n# It indexes documents into a vector database and then queries them with an LLM.\n\n# Sample knowledge base documents (in a real scenario, these would be from files or a database)\nCONST docs = "TalkPipe is a Python toolkit for building AI workflows. It provides a Unix-like pipeline syntax for chaining data transformations and LLM operations.|TalkPipe supports multiple LLM providers including OpenAI, Ollama, and Anthropic. You can switch between providers easily using configuration.|With TalkPipe, you can build RAG systems, multi-agent debates, and document processing pipelines. It uses Python generators for memory-efficient streaming.";\n\n# Step 1: Index documents into a vector database\nINPUT FROM echo[data=docs, delimiter="|"] \n    | toDict[field_list="_:text"] \n    | makeVectorDatabase[\n        path="tmp://demo_knowledge_base",\n        embedding_model="nomic-embed-text",\n        embedding_source="ollama",\n        embedding_field="text"\n      ] \n    | print;\n\n# Step 2: Query the knowledge base with RAG\nINPUT FROM echo[data="What are the key benefits of using TalkPipe?"] \n    | toDict[field_list="_:text"] \n    | ragToText[\n        path="tmp://demo_knowledge_base",\n        embedding_model="nomic-embed-text",\n        embedding_source="ollama",\n        completion_model="llama3.2",\n        completion_source="ollama",\n        content_field="text",\n        prompt_directive="Answer the question based on the background information provided.",\n        limit=3\n      ] \n    | print',
        },
    ],
}


class ScriptRequest(BaseModel):
    script: str


class InteractiveRequest(BaseModel):
    id: str
    user_input: str


@app.get("/examples")
def get_examples() -> JSONResponse:
    """Endpoint to return all example scripts"""
    return JSONResponse(content={"examples": EXAMPLE_SCRIPTS})


@app.get("/docs/html")
def get_docs_html() -> HTMLResponse:
    """Generate and return HTML documentation using live introspection"""
    import os
    import tempfile

    try:
        # Generate documentation using the shared extraction mechanism
        analyzed_items = analyze_registered_items()

        # Create temporary file for HTML output
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".html", delete=False
        ) as temp_file:
            temp_path = temp_file.name

        try:
            generate_html(analyzed_items, temp_path)

            # Read the generated HTML
            with open(temp_path, encoding="utf-8") as f:
                html_content = f.read()

            return HTMLResponse(content=html_content)
        finally:
            # Clean up temporary file
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    except Exception as e:
        logger.exception("Error generating HTML documentation")
        raise HTTPException(
            status_code=500,
            detail="Documentation generation failed; details are in the "
            "workbench server log.",
        ) from e


@app.get("/docs/text", response_class=HTMLResponse)
def get_docs_text() -> HTMLResponse:
    """Generate and return text documentation using live introspection"""
    import html
    import os
    import tempfile

    try:
        # Generate documentation using the shared extraction mechanism
        analyzed_items = analyze_registered_items()

        # Create temporary file for text output
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False
        ) as temp_file:
            temp_path = temp_file.name

        try:
            generate_text(analyzed_items, temp_path)

            # Read the generated text and wrap in HTML for browser display
            with open(temp_path, encoding="utf-8") as f:
                text_content = f.read()

            # Wrap text content in a simple HTML page for better browser display
            html_wrapped = f"""<!DOCTYPE html>
<html>
<head>
    <title>TalkPipe Documentation (Text)</title>
    <style>
        body {{
            font-family: 'Consolas', 'Monaco', monospace;
            white-space: pre-wrap;
            margin: 20px;
            line-height: 1.4;
            background-color: #f5f5f5;
        }}
        .content {{
            background-color: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
    </style>
</head>
<body>
    <div class="content">{html.escape(text_content)}</div>
</body>
</html>"""

            return HTMLResponse(content=html_wrapped)
        finally:
            # Clean up temporary file
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    except Exception as e:
        logger.exception("Error generating text documentation")
        raise HTTPException(
            status_code=500,
            detail="Documentation generation failed; details are in the "
            "workbench server log.",
        ) from e


@app.get("/logs")
async def get_logs() -> JSONResponse:
    logs = []
    while not log_queue.empty():
        try:
            logs.append(log_queue.get_nowait())
        except queue.Empty:
            break
    return JSONResponse(content={"logs": logs})


@app.post("/compile")
def compile_script(request: ScriptRequest) -> dict[str, Any]:
    if not request.script:
        logger.error("Empty script submitted")
        raise HTTPException(status_code=400, detail="Script content is required")
    if len(request.script) > 10000:
        logger.error("Script too long")
        raise HTTPException(
            status_code=413,
            detail="Script is too long, maximum length is 10,000 characters",
        )
    try:
        logger.info("Compiling new script")

        # Compile script - configuration values are accessible via $key syntax
        compiled_instance = compile(request.script)
        logger.info("Script compiled successfully")
    except Exception as e:
        logger.error(f"Script compilation failed: {e!s}")
        raise HTTPException(status_code=400, detail=f"Compilation error: {e}") from e

    is_interactive = is_interactive_script(request.script)

    script_id = str(uuid.uuid4())
    compiled_scripts[script_id] = {
        "instance": compiled_instance,
        "interactive": is_interactive,
    }
    logger.info(f"Created new script instance with ID: {script_id}")

    if not is_interactive:
        try:
            logger.info("Executing non-interactive script")
            output_iterator = compiled_instance([])
            output_chunks = list(output_iterator)
            output_text = "\n".join(str(chunk) for chunk in output_chunks)
            logger.info("Non-interactive script execution completed")
            return {
                "id": script_id,
                "interactive": is_interactive,
                "output": output_text,
            }
        except Exception as e:
            logger.error(f"Script execution failed: {e!s}")
            raise HTTPException(status_code=400, detail=f"Execution error: {e}") from e

    return {"id": script_id, "interactive": is_interactive}


@app.post("/go")
def interactive_go(request: InteractiveRequest) -> StreamingResponse:
    script_info = compiled_scripts.get(request.id)
    if not script_info:
        logger.error(f"Script not found: {request.id}")
        raise HTTPException(status_code=404, detail="Script instance not found")
    if not script_info["interactive"]:
        logger.error(f"Non-interactive script called with /go: {request.id}")
        raise HTTPException(status_code=400, detail="This script is not interactive")
    logger.info(f"Processing interactive input for script: {request.id}")

    # Create a wrapper generator that ensures all items are string-serializable.
    # The pipeline is lazy (e.g. the LLM call in llmPrompt happens as items are
    # consumed here), so a failure typically occurs *after* the StreamingResponse
    # has already sent HTTP 200 and its headers. We therefore cannot switch to an
    # error status code; if we let the exception propagate, the connection aborts
    # and the browser reports a meaningless "network error". Instead, catch it and
    # yield an error line into the stream body so it shows up in the output pane.
    # Only the exception class name is streamed: runtime exception text can carry
    # file paths, URLs, and library internals (information exposure through an
    # exception), so the full error and traceback go to the server log instead.
    def ensure_serializable() -> Iterator[str]:
        try:
            yield from iter_output_text(script_info["instance"]([request.user_input]))
        except Exception as e:
            logger.exception("Interactive execution failed")
            yield (
                f"\nError: the pipeline failed while running "
                f"({type(e).__name__}). Check the segment parameters and "
                "input values; the full error and traceback are in the "
                "workbench server log."
            )

    return StreamingResponse(ensure_serializable(), media_type="text/plain")


@app.get("/", response_class=HTMLResponse)
def get_ui() -> FileResponse:
    """Serve the workbench UI (static files under static/workbench/)."""
    return FileResponse(WORKBENCH_STATIC_DIR / "index.html", media_type="text/html")


# --- Shutdown ----------------------------------------------------------------
#
# Ctrl-C must stop the workbench promptly even while a request is still
# running. Two things otherwise keep it alive for as long as that request
# takes (an LLM call for the suggestions sidebar, or a script run via
# /compile or /go, can run for minutes):
#
# 1. uvicorn's graceful shutdown waits for in-flight requests with no time
#    limit unless ``timeout_graceful_shutdown`` is set. After the grace period
#    it cancels the request tasks and returns from ``uvicorn.run``.
# 2. Cancelling a task does not stop the code it was running: the sync
#    endpoints execute on anyio worker threads, which are not daemon threads,
#    and Python's interpreter shutdown joins every non-daemon thread before the
#    process can exit. A second Ctrl-C ("force quit") does not help with this
#    part either.
#
# So after a short grace period the process is ended with ``os._exit`` when
# request threads are still running. Registered ``atexit`` handlers (talkpipe's
# temp-directory cleanup, ``logging.shutdown``) are run explicitly first,
# because ``os._exit`` skips them. With ``--reload`` the app runs in uvicorn's
# reloader subprocess, which only the grace period reaches.

SHUTDOWN_GRACE_SECONDS = 2


def _lingering_request_threads() -> list[threading.Thread]:
    """Non-daemon threads (other than the main thread) that are still alive."""
    return [
        thread
        for thread in threading.enumerate()
        if thread is not threading.main_thread() and not thread.daemon
    ]


def _exit_without_waiting_for_requests() -> None:
    """Exit the process now if request threads survived uvicorn's shutdown.

    Called after ``uvicorn.run`` returns. When nothing is running this is a
    no-op and the interpreter exits normally; otherwise interpreter shutdown
    would block until the running script or LLM call finishes.
    """
    lingering = _lingering_request_threads()
    if not lingering:
        return
    # print, not logger: the module logger feeds the UI log panel, not the
    # console, and the UI is gone by now.
    print(
        f"Exiting without waiting for {len(lingering)} running request(s) to finish",
        file=sys.stderr,
    )
    atexit._run_exitfuncs()
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0)


def main() -> None:
    configure_logging()
    parser = argparse.ArgumentParser(
        description="Start the ChatterLang Workbench, a browser-based IDE "
        "for developing and testing ChatterLang pipelines."
    )
    add_host_port_args(parser, default_host="127.0.0.1", default_port=4143)
    parser.add_argument(
        "--reload", action="store_true", help="Enable auto-reload (default: off)"
    )
    add_load_module_arg(parser)
    parser.add_argument(
        "--workspace",
        type=str,
        default=None,
        help="Directory for saved pipelines (default: ~/.talkpipe/workbench)",
    )
    parser.add_argument(
        "--suggest-source",
        type=str,
        default=None,
        help="LLM source for the suggestions sidebar (e.g. ollama); defaults to the standard "
        "TalkPipe model configuration. A source saved in the workbench Settings dialog "
        "takes precedence over this flag.",
    )
    parser.add_argument(
        "--suggest-model",
        type=str,
        default=None,
        help="LLM model name for the suggestions sidebar; defaults to the standard "
        "TalkPipe model configuration. A model saved in the workbench Settings dialog "
        "takes precedence over this flag.",
    )
    parser.add_argument(
        "--no-llm-suggestions",
        action="store_true",
        help="Disable LLM-driven suggestions entirely (heuristic suggestions remain)",
    )
    parser.add_argument(
        "--allow-remote",
        action="store_true",
        help="Permit binding to a non-loopback --host. The workbench runs arbitrary "
        "scripts as your user; only do this behind TLS and with --api-key.",
    )
    parser.add_argument(
        "--api-key",
        type=str,
        default=None,
        help="Require this token (X-API-Key header) on every API call. Also settable "
        "as TALKPIPE_WORKBENCH_API_KEY. Open the UI with ?key=<token> once; the "
        "browser keeps it for the session.",
    )

    # Add more uvicorn options as needed
    args, unknown_args = parser.parse_known_args()

    # Leftover --key value arguments become configuration values ($key in scripts)
    apply_cli_constants(unknown_args)

    # Expose the workbench's own logo URL so example scripts can fetch it from
    # the running server via $workbench_logo_url.
    logo_host = (
        "localhost"
        if args.host in ("0.0.0.0", "::")  # nosec B104 - compare bind host, not binding here
        else args.host
    )
    add_config_values(
        {
            "workbench_logo_url": f"http://{logo_host}:{args.port}/static/talkpipe_logo.png"
        },
        override=True,
    )

    # Propagate workbench settings via TALKPIPE_* environment variables in
    # addition to add_config_values: with --reload, uvicorn re-imports the app
    # in a subprocess, where only the environment survives (get_config() reads
    # TALKPIPE_* variables on load).
    workbench_settings = {}
    if args.workspace:
        workbench_settings["workbench_workspace"] = args.workspace
    if args.suggest_source:
        workbench_settings["workbench_suggest_source"] = args.suggest_source
    if args.suggest_model:
        workbench_settings["workbench_suggest_model"] = args.suggest_model
    if args.no_llm_suggestions:
        workbench_settings["workbench_llm_suggestions"] = "false"
    if workbench_settings:
        import os

        for key, value in workbench_settings.items():
            os.environ[f"TALKPIPE_{key}"] = value
        add_config_values(workbench_settings, override=True)

    if args.load_module:
        # Recorded in the environment and imported at app startup (see
        # _load_configured_modules) so custom modules survive --reload.
        import os

        os.environ["TALKPIPE_WORKBENCH_LOAD_MODULES"] = os.pathsep.join(
            args.load_module
        )
        add_config_values(
            {"workbench_load_modules": os.pathsep.join(args.load_module)},
            override=True,
        )

    if args.api_key:
        import os

        os.environ["TALKPIPE_WORKBENCH_API_KEY"] = args.api_key
        add_config_values({"workbench_api_key": args.api_key}, override=True)

    print(WORKBENCH_BANNER, file=sys.stderr)
    logger.warning("Workbench starting: it executes arbitrary scripts as this user")
    if not is_loopback_host(args.host):
        if not args.allow_remote:
            print(
                f"Refusing to bind to non-loopback host {args.host!r}. Pass "
                f"--allow-remote (and --api-key) if you really mean to expose "
                f"the workbench.",
                file=sys.stderr,
            )
            sys.exit(2)
        print(
            f"WARNING: binding to {args.host!r} exposes script execution to the "
            f"network{'' if args.api_key else ' with NO authentication'}.",
            file=sys.stderr,
        )
        logger.warning("Workbench bound to non-loopback host %s", args.host)

    print(f"Starting ChatterLang Workbench at http://{args.host}:{args.port}")
    uvicorn.run(
        "talkpipe.app.chatterlang_workbench:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        timeout_graceful_shutdown=SHUTDOWN_GRACE_SECONDS,
    )
    _exit_without_waiting_for_requests()


if __name__ == "__main__":
    main()
