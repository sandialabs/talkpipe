import uuid
import argparse
import logging
import queue
from pathlib import Path
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import StreamingResponse, HTMLResponse, JSONResponse, FileResponse
from pydantic import BaseModel
from talkpipe.pipe import core
from talkpipe.pipe.core import RuntimeComponent
from talkpipe.chatterlang import registry
from talkpipe.chatterlang.compiler import compile
from talkpipe.util.config import load_module_file, parse_unknown_args, add_config_values
from talkpipe.app.chatterlang_reference_generator import analyze_registered_items, generate_html, generate_text
from talkpipe.app.workbench import reference_api, workspace_api, suggest_api

logger = logging.getLogger(__name__)

from contextlib import asynccontextmanager


def _load_configured_modules():
    """Import custom module files listed in the workbench configuration.

    ``main()`` records ``--load-module`` paths in the
    ``TALKPIPE_workbench_load_modules`` environment variable rather than
    importing them directly: with ``--reload``, uvicorn re-imports the app
    in a subprocess where only the environment survives, so importing here
    (at app startup) makes custom modules work in both modes.
    """
    from talkpipe.util.config import get_config
    configured = get_config().get("workbench_load_modules")
    if not configured:
        return
    import os
    for module_file in configured.split(os.pathsep):
        if module_file:
            load_module_file(fname=module_file, fail_on_missing=False)


@asynccontextmanager
async def _lifespan(app):
    _load_configured_modules()
    # Building the component reference imports every registered component
    # (seconds); do it in the background so the first browser fetch is fast.
    reference_api.warm_reference_cache_async()
    yield


app = FastAPI(lifespan=_lifespan)
# Since we're adding static files, set up the directory for serving them
# Note: You'll need to create this directory when deploying
app.mount("/static", StaticFiles(directory=Path(__file__).parent / 'static'), name="static")

WORKBENCH_STATIC_DIR = Path(__file__).parent / 'static' / 'workbench'

app.include_router(reference_api.router)
app.include_router(workspace_api.router)
app.include_router(suggest_api.router)

# Configure logging
log_queue = queue.Queue()
log_handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
log_handler.setFormatter(formatter)

# Custom handler to capture logs
class QueueHandler(logging.Handler):
    def emit(self, record):
        log_entry = self.formatter.format(record)
        log_queue.put(log_entry)

queue_handler = QueueHandler()
queue_handler.setFormatter(formatter)

# Add handlers to root logger
logging.getLogger().addHandler(queue_handler)
logging.getLogger().setLevel(logging.INFO)

# Global in-memory store for compiled script instances
compiled_scripts = {}

# Define example scripts to display in the UI
EXAMPLE_SCRIPTS = {
    "Basic Examples": [
        {
            "name": "Hello World",
            "description": "Print a message (echo splits comma-separated data into items)",
            "code": 'INPUT FROM echo[data="Hello, ChatterLang World!"] | print'
        },
        {
            "name": "Data Transformation",
            "description": "Convert strings to integers",
            "code": 'INPUT FROM echo[data="1|2|hello|3", delimiter="|"] | cast[cast_type="int"] | print'
        },
        {
            "name": "Using Variables",
            "description": "Store data in a variable and reuse it",
            "code": 'INPUT FROM echo[data="1,2,3,4,5"] | @numbers; INPUT FROM @numbers | print'
        }
    ],
    "LLM Examples": [
        {
            "name": "Simple Chat",
            "description": "Interactive conversation with an LLM",
            "code": '| llmPrompt[model="llama3.2", source="ollama", multi_turn=True]'
        },
        {
            "name": "Agent Conversation",
            "description": "Two agents debating a topic",
            "code": 'CONST economist_prompt = "You are an economist debating a proposition. Reply in one sentence.";\nCONST theologian_prompt="You are a reformed theologian debating a proposition. Reply in one sentence.";\nINPUT FROM echo[data="The US should give free puppies to all children."] | @next_utterance | accum[variable=@conv] | print;\nLOOP 3 TIMES {\n    INPUT FROM @next_utterance | llmPrompt[system_prompt=economist_prompt] | @next_utterance | accum[variable=@conv] | print;\n    INPUT FROM @next_utterance | llmPrompt[system_prompt=theologian_prompt] | @next_utterance | accum[variable=@conv] | print;\n};\nINPUT FROM @conv'
        },
        {
            "name": "Web Page Summarizer",
            "description": "Download and summarize a web page",
            "code": '| downloadURL | htmlToText | llmPrompt[system_prompt="Summarize the following text in 3-5 sentences:"]'
        }
    ],
    "Image Examples": [
        {
            "name": "Describe the TalkPipe Logo",
            "description": "Fetch the workbench's own logo image and ask a vision LLM to describe it",
            "code": '# Pulls the logo image from this running TalkPipe workbench server.\n# $workbench_logo_url is populated by chatterlang_workbench at startup\n# based on the --host and --port arguments.\n# Example assumes that ollama is installed and the gemma4:31b-cloud has been pulled.\nINPUT FROM echo[data=$workbench_logo_url]\n    | toDict[field_list="_:image"]\n    | llmVisionPrompt[\n        image_field="image",\n        model="gemma4:31b-cloud",\n        source="ollama",\n        prompt="Describe what you see in this image in two or three sentences.",\n        set_as="answer"\n      ]\n    | print'
        }
    ],
    "Advanced Examples": [
        {
            "name": "Data Analysis Loop",
            "description": "Process data in multiple iterations",
            "code": 'INPUT FROM range[lower=0, upper=5] | @data;\nLOOP 3 TIMES {\n    INPUT FROM @data | scale[multiplier=2] | @data\n};\nINPUT FROM @data | print'
        },
        {
            "name": "Document Evaluation",
            "description": "Score a document on relevance to a topic",
            "code": 'CONST scorePrompt = "On a scale of 1 to 10, rate how relevant the following text is to artificial intelligence. Provide a score and brief explanation.";\n| llmScore[system_prompt=scorePrompt] | print'
        },
        {
            "name": "RAG Pipeline with Vector Database",
            "description": "Build a complete RAG system with document indexing and querying",
            "code": '# This example demonstrates a complete RAG (Retrieval-Augmented Generation) workflow.\n# It indexes documents into a vector database and then queries them with an LLM.\n\n# Sample knowledge base documents (in a real scenario, these would be from files or a database)\nCONST docs = "TalkPipe is a Python toolkit for building AI workflows. It provides a Unix-like pipeline syntax for chaining data transformations and LLM operations.|TalkPipe supports multiple LLM providers including OpenAI, Ollama, and Anthropic. You can switch between providers easily using configuration.|With TalkPipe, you can build RAG systems, multi-agent debates, and document processing pipelines. It uses Python generators for memory-efficient streaming.";\n\n# Step 1: Index documents into a vector database\nINPUT FROM echo[data=docs, delimiter="|"] \n    | toDict[field_list="_:text"] \n    | makeVectorDatabase[\n        path="tmp://demo_knowledge_base",\n        embedding_model="nomic-embed-text",\n        embedding_source="ollama",\n        embedding_field="text"\n      ] \n    | print;\n\n# Step 2: Query the knowledge base with RAG\nINPUT FROM echo[data="What are the key benefits of using TalkPipe?"] \n    | toDict[field_list="_:text"] \n    | ragToText[\n        path="tmp://demo_knowledge_base",\n        embedding_model="nomic-embed-text",\n        embedding_source="ollama",\n        completion_model="llama3.2",\n        completion_source="ollama",\n        content_field="text",\n        prompt_directive="Answer the question based on the background information provided.",\n        limit=3\n      ] \n    | print'
        }
    ]
}

class ScriptRequest(BaseModel):
    script: str

class InteractiveRequest(BaseModel):
    id: str
    user_input: str

@app.get("/examples")
def get_examples():
    """Endpoint to return all example scripts"""
    return JSONResponse(content={"examples": EXAMPLE_SCRIPTS})

@app.get("/docs/html")
def get_docs_html():
    """Generate and return HTML documentation using live introspection"""
    import tempfile
    import os
    
    try:
        # Generate documentation using the shared extraction mechanism
        analyzed_items = analyze_registered_items()
        
        # Create temporary file for HTML output
        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as temp_file:
            temp_path = temp_file.name
        
        try:
            generate_html(analyzed_items, temp_path)
            
            # Read the generated HTML
            with open(temp_path, 'r', encoding='utf-8') as f:
                html_content = f.read()
            
            return HTMLResponse(content=html_content)
        finally:
            # Clean up temporary file
            if os.path.exists(temp_path):
                os.unlink(temp_path)
                
    except Exception as e:
        logger.error(f"Error generating HTML documentation: {e}")
        raise HTTPException(status_code=500, detail=f"Documentation generation failed: {e}")

@app.get("/docs/text", response_class=HTMLResponse)
def get_docs_text():
    """Generate and return text documentation using live introspection"""
    import tempfile
    import os
    import html
    
    try:
        # Generate documentation using the shared extraction mechanism
        analyzed_items = analyze_registered_items()
        
        # Create temporary file for text output
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as temp_file:
            temp_path = temp_file.name
        
        try:
            generate_text(analyzed_items, temp_path)
            
            # Read the generated text and wrap in HTML for browser display
            with open(temp_path, 'r', encoding='utf-8') as f:
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
        logger.error(f"Error generating text documentation: {e}")
        raise HTTPException(status_code=500, detail=f"Documentation generation failed: {e}")


@app.get("/logs")
async def get_logs():
    logs = []
    while not log_queue.empty():
        try:
            logs.append(log_queue.get_nowait())
        except queue.Empty:
            break
    return JSONResponse(content={"logs": logs})

@app.post("/compile")
def compile_script(request: ScriptRequest):
    if not request.script:
        logging.error("Empty script submitted")
        raise HTTPException(status_code=400, detail="Script content is required")
    if len(request.script) > 10000:
        logging.error("Script too long")
        raise HTTPException(status_code=413, detail="Script is too long, maximum length is 10,000 characters")
    try:
        logging.info("Compiling new script")
        
        # Compile script - configuration values are accessible via $key syntax
        compiled_instance = compile(request.script)
        logging.info("Script compiled successfully")
    except Exception as e:
        logging.error(f"Script compilation failed: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Compilation error: {e}")
    
    is_interactive = False
    for line in request.script.splitlines():
        line = line.strip()
        if not line or line.startswith('CONST') or line.startswith('#'):
            continue
        is_interactive = line[0] == '|'
        break
    
    script_id = str(uuid.uuid4())
    compiled_scripts[script_id] = {"instance": compiled_instance, "interactive": is_interactive}
    logging.info(f"Created new script instance with ID: {script_id}")
    
    if not is_interactive:
        try:
            logging.info("Executing non-interactive script")
            output_iterator = compiled_instance([])
            output_chunks = [chunk for chunk in output_iterator]
            output_text = "\n".join(str(chunk) for chunk in output_chunks)
            logging.info("Non-interactive script execution completed")
            return {"id": script_id, "interactive": is_interactive, "output": output_text}
        except Exception as e:
            logging.error(f"Script execution failed: {str(e)}")
            raise HTTPException(status_code=400, detail=f"Execution error: {e}")
    
    return {"id": script_id, "interactive": is_interactive}

@app.post("/go")
def interactive_go(request: InteractiveRequest):
    script_info = compiled_scripts.get(request.id)
    if not script_info:
        logging.error(f"Script not found: {request.id}")
        raise HTTPException(status_code=404, detail="Script instance not found")
    if not script_info["interactive"]:
        logging.error(f"Non-interactive script called with /go: {request.id}")
        raise HTTPException(status_code=400, detail="This script is not interactive")
    try:
        logging.info(f"Processing interactive input for script: {request.id}")
        output_iterator = script_info["instance"]([request.user_input])
        # Create a wrapper generator that ensures all items are string-serializable
        def ensure_serializable():
            for item in output_iterator:
                # Handle Pydantic models and other complex objects
                if hasattr(item, 'model_dump_json'):
                    # If it's a Pydantic model, use its JSON serialization
                    yield item.model_dump_json()
                elif hasattr(item, '__dict__'):
                    # For other objects with __dict__
                    yield str(item)
                else:
                    # Pass through strings and other basic types
                    yield str(item)
        return StreamingResponse(ensure_serializable(), media_type="text/plain")
    except Exception as e:
        logging.error(f"Interactive execution failed: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Interactive execution error: {e}")

@app.get("/", response_class=HTMLResponse)
def get_ui():
    """Serve the workbench UI (static files under static/workbench/)."""
    return FileResponse(WORKBENCH_STATIC_DIR / "index.html", media_type="text/html")

def main():
    parser = argparse.ArgumentParser(
        description="Start the ChatterLang Workbench, a browser-based IDE "
                    "for developing and testing ChatterLang pipelines."
    )
    parser.add_argument(
        "--host", type=str, default="127.0.0.1", help="Server host (default: 127.0.0.1)"
    )
    parser.add_argument(
        "--port", type=int, default=4143, help="Server port (default: 4143)"
    )
    parser.add_argument(
        "--reload", action="store_true", help="Enable auto-reload (default: off)"
    )
    parser.add_argument(
        "--load-module", action='append', default=[], type=str, help="Path to a custom module file to import before running the script."
    )
    parser.add_argument(
        "--workspace", type=str, default=None,
        help="Directory for saved pipelines (default: ~/.talkpipe/workbench)"
    )
    parser.add_argument(
        "--suggest-source", type=str, default=None,
        help="LLM source for the suggestions sidebar (e.g. ollama); defaults to the standard "
             "TalkPipe model configuration. A source saved in the workbench Settings dialog "
             "takes precedence over this flag."
    )
    parser.add_argument(
        "--suggest-model", type=str, default=None,
        help="LLM model name for the suggestions sidebar; defaults to the standard "
             "TalkPipe model configuration. A model saved in the workbench Settings dialog "
             "takes precedence over this flag."
    )
    parser.add_argument(
        "--no-llm-suggestions", action="store_true",
        help="Disable LLM-driven suggestions entirely (heuristic suggestions remain)"
    )

    # Add more uvicorn options as needed
    args, unknown_args = parser.parse_known_args()
    
    # Parse unknown arguments and add to configuration so they're accessible via $key syntax
    constants = parse_unknown_args(unknown_args)
    
    # Add command-line constants to the configuration
    if constants:
        add_config_values(constants, override=True)
        print(f"Added command-line values to configuration: {list(constants.keys())}")

    # Expose the workbench's own logo URL so example scripts can fetch it from
    # the running server via $workbench_logo_url.
    logo_host = (
        "localhost"
        if args.host in ("0.0.0.0", "::")  # nosec B104 - compare bind host, not binding here
        else args.host
    )
    add_config_values(
        {"workbench_logo_url": f"http://{logo_host}:{args.port}/static/talkpipe_logo.png"},
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
        os.environ["TALKPIPE_workbench_load_modules"] = os.pathsep.join(args.load_module)
        add_config_values(
            {"workbench_load_modules": os.pathsep.join(args.load_module)},
            override=True,
        )

    print(f"Starting ChatterLang Workbench at http://{args.host}:{args.port}")
    uvicorn.run(
        "talkpipe.app.chatterlang_workbench:app",
        host=args.host,
        port=args.port,
        reload=args.reload
    )

if __name__ == "__main__":
    main()