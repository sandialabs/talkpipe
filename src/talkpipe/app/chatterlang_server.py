import uuid
import argparse
import logging
import queue
from pathlib import Path
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import StreamingResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel
from talkpipe.pipe import core
from talkpipe.chatterlang import registry
from talkpipe.chatterlang.compiler import compile
from talkpipe.util.config import load_module_file

logger = logging.getLogger(__name__)

app = FastAPI()
# Since we're adding static files, set up the directory for serving them
# Note: You'll need to create this directory when deploying
app.mount("/static", StaticFiles(directory=Path(__file__).parent / 'static'), name="static")

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
            "description": "Simple example to print a message",
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
            "code": '| llmPrompt[name="llama3.2", source="ollama", multi_turn=True]'
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
    "Advanced Examples": [
        {
            "name": "Data Analysis Loop",
            "description": "Process data in multiple iterations",
            "code": 'INPUT FROM range[lower=0, upper=5] | @data;\nLOOP 3 TIMES {\n    INPUT FROM @data | scale[multiplier=2] | @data\n};\nINPUT FROM @data | print'
        },
        {
            "name": "Document Evaluation",
            "description": "Score a document on relevance to a topic",
            "code": 'CONST scorePrompt = "On a scale of 1 to 10, rate how relevant the following text is to artificial intelligence. Provide a score and brief explanation.";\n| llmScore[system_prompt=scorePrompt, append_as="ai_relevance"] | print'
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
    try:
        logging.info("Compiling new script")
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
    html_content = """<!DOCTYPE html>
<html>
<head>
  <title>TalkPipe</title>
  <link rel="icon" type="image/ico" href="/static/favicon.ico">
  <style>
    /* Base styles and reset */
    html, body {
      margin: 0;
      padding: 0;
      height: 100%;
      font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
      color: #333;
      background-color: #f5f7fa;
    }
    
    * {
      box-sizing: border-box;
    }
    
    /* Main layout */
    #container {
      display: flex;
      flex-direction: column;
      height: 100vh;
      max-width: 1200px;
      margin: 0 auto;
      box-shadow: 0 0 20px rgba(0,0,0,0.05);
      background: white;
    }
    
    /* Header styles */
    header {
      background: linear-gradient(135deg, #4a6baf 0%, #1e3a8a 100%);
      color: white;
      padding: 15px 20px;
      border-bottom: 1px solid #e0e0e0;
    }
    
    header h1 {
      margin: 0;
      font-size: 24px;
      font-weight: 500;
    }
    
    .subtitle {
      font-size: 14px;
      opacity: 0.8;
      margin-top: 4px;
    }
    
    .topmaterial {
      font-size: 14px;
      opacity: 0.8;
      margin-top: 4px;
    }

    /* Section containers */
    #compile-section, #interactive-section {
      flex: none;
      padding: 20px;
      background: white;
      border-bottom: 1px solid #e0e0e0;
    }
    
    /* Main workspace */
    .workspace-container {
      display: flex;
      flex: 1;
      overflow: hidden;
    }
    
    /* Examples panel */
    #examples-panel {
      width: 300px;
      background: #f0f4f8;
      border-right: 1px solid #ddd;
      padding: 0;
      overflow-y: auto;
      flex-shrink: 0;
      display: flex;
      flex-direction: column;
    }
    
    .examples-header {
      padding: 15px;
      background: #e0e7ef;
      border-bottom: 1px solid #d0d7df;
      font-weight: 500;
    }
    
    /* Editor container */
    .editor-container {
      position: relative;
      margin-bottom: 15px;
      border-radius: 6px;
      overflow: hidden;
      border: 1px solid #ddd;
      background: #f8f9fa;
    }
    
    #scriptInput {
      width: 100%;
      height: 300px;
      box-sizing: border-box;
      font-family: 'Consolas', 'Monaco', monospace;
      padding: 15px;
      line-height: 1.5;
      tab-size: 4;
      resize: vertical;
      border: none;
      background: #f8f9fa;
      color: #333;
      font-size: 14px;
    }
    
    #scriptInput:focus {
      outline: none;
      box-shadow: inset 0 0 0 2px #4a6baf;
    }
    
    #cursorPosition {
      display: block;
      text-align: right;
      padding: 5px 10px;
      background: #eaeaea;
      color: #666;
      font-family: monospace;
      font-size: 12px;
      user-select: none;
    }
    
    /* Output section */
    .main-panel {
      flex: 1;
      display: flex;
      flex-direction: column;
      overflow: hidden;
    }
    
    #output-section {
      flex: 1;
      overflow-y: auto;
      padding: 20px;
      background: #f8f9fa;
      display: flex;
      flex-direction: column;
      border-radius: 6px;
      margin: 0 20px 20px 20px;
    }
    
    #output-section h2 {
      margin-top: 0;
      font-size: 18px;
      color: #4a6baf;
      font-weight: 500;
    }
    
    #output {
      flex: 1;
      white-space: pre-wrap;
      font-family: 'Consolas', 'Monaco', monospace;
      background: white;
      padding: 15px;
      border-radius: 6px;
      border: 1px solid #e0e0e0;
      overflow-y: auto;
      font-size: 14px;
    }
    
    /* Button styles */
    button {
      background: #4a6baf;
      color: white;
      border: none;
      padding: 8px 16px;
      border-radius: 4px;
      cursor: pointer;
      font-weight: 500;
      transition: background-color 0.2s;
    }
    
    button:hover {
      background: #3a5b9f;
    }
    
    button:disabled {
      background: #9eabc9;
      cursor: not-allowed;
      opacity: 0.7;
    }
    
    /* Interactive section */
    #interactive-container {
      display: flex;
      align-items: center;
      gap: 12px;
    }
    
    #interactiveInput {
      flex: 1;
      padding: 10px 12px;
      border: 1px solid #ddd;
      border-radius: 4px;
      font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
      font-size: 14px;
    }
    
    #interactiveInput:focus {
      outline: none;
      border-color: #4a6baf;
      box-shadow: 0 0 0 2px rgba(74, 107, 175, 0.2);
    }
    
    .hidden {
      display: none !important;
    }
    
    /* Output formatting */
    .user-input {
      color: #4a6baf;
      font-weight: bold;
      margin-top: 12px;
      margin-bottom: 6px;
      border-left: 3px solid #4a6baf;
      padding-left: 8px;
    }
    
    .output-item {
      margin-bottom: 10px;
      padding: 8px;
      border-left: 3px solid #e0e0e0;
      font-size: 14px;
      background: rgba(248, 249, 250, 0.5);
    }
    
    /* Loading animation */
    @keyframes pulse {
      0% { opacity: 1; }
      50% { opacity: 0.3; }
      100% { opacity: 1; }
    }
    
    .loading {
      color: #666;
      animation: pulse 1.5s infinite;
      margin-left: 10px;
      font-style: italic;
    }
    
    #log-panel {
      position: fixed;
      bottom: 0;
      right: 0;
      width: 50%;
      height: 400px;
      background: #1e293b;
      color: #f8f9fa;
      padding: 20px;
      box-shadow: -2px -2px 10px rgba(0,0,0,0.2);
      z-index: 999;
      display: flex;
      flex-direction: column;
      border-top-left-radius: 8px;
    }
    
    #log-content {
      flex: 1;
      overflow-y: auto;
      font-family: 'Consolas', 'Monaco', monospace;
      white-space: pre-wrap;
      padding: 15px;
      background: #0f172a;
      margin-bottom: 10px;
      border-radius: 4px;
      font-size: 13px;
    }
    
    .log-entry {
      margin-bottom: 5px;
      padding: 4px 8px;
      border-left: 3px solid #666;
      font-size: 12px;
    }
    
    .log-error { border-left-color: #f87171; color: #fca5a5; }
    .log-info { border-left-color: #4ade80; color: #86efac; }
    .log-warning { border-left-color: #facc15; color: #fde68a; }
    
    #log-controls {
      display: flex;
      gap: 10px;
    }
    
    #log-controls button {
      padding: 5px 10px;
      background: #334155;
      border: none;
      border-radius: 3px;
      cursor: pointer;
      font-size: 13px;
    }
    
    #log-controls button:hover {
      background: #475569;
    }
    
    .close-button {
      position: absolute;
      top: 15px;
      right: 15px;
      background: none;
      border: none;
      color: white;
      cursor: pointer;
      font-size: 20px;
      opacity: 0.7;
    }
    
    .close-button:hover {
      opacity: 1;
    }
    
    /* Title & section headings */
    h2 {
      font-size: 18px;
      margin-bottom: 15px;
      color: #4a6baf;
      font-weight: 500;
    }
    
    h3 {
      font-size: 16px;
      color: #4a6baf;
      font-weight: 500;
    }
    
    /* Example accordion styles */
    .accordion {
      background-color: #e0e7ef;
      color: #333;
      cursor: pointer;
      padding: 15px;
      width: 100%;
      text-align: left;
      border: none;
      outline: none;
      transition: 0.3s;
      font-weight: 500;
      font-size: 15px;
      border-bottom: 1px solid #d0d7df;
    }

    .accordion:hover {
      background-color: #d0d7ef;
    }

    .accordion:after {
      content: '\\002B'; /* Unicode for plus sign (+) */
      color: #4a6baf;
      font-weight: bold;
      float: right;
      margin-left: 5px;
    }

    .active:after {
      content: '\\2212'; /* Unicode for minus sign (-) */
    }

    .panel {
      padding: 0;
      background-color: #f0f4f8;
      overflow: hidden;
      max-height: 0;
      transition: max-height 0.2s ease-out;
    }
    
    .example-item {
      padding: 10px 15px 10px 30px;
      border-bottom: 1px solid #e0e7ef;
      cursor: pointer;
      transition: background-color 0.2s;
    }
    
    .example-item:hover {
      background-color: #e0e7ef;
    }
    
    .example-name {
      font-weight: 500;
      margin-bottom: 3px;
    }
    
    .example-description {
      font-size: 12px;
      color: #666;
    }

    /* Only affects links inside elements with the header-links class */
    .header-links a {
      color: #4ade80; /* Bright green to match the "Pipe" styling */
      text-decoration: underline;
      font-weight: 500;
      transition: color 0.2s;
    }

    .header-links a:hover {
      color: #a7f3d0; /* Lighter green on hover */
      text-decoration: underline;
    }

    .button-group {
      display: flex;
      gap: 12px;
      align-items: center;
      margin-bottom: 15px;
    }

    /* Make all buttons in the group consistent */
    .button-group button {
      padding: 8px 16px;
      border-radius: 4px;
      font-weight: 500;
      transition: background-color 0.2s;
    }
    
  </style>
</head>
<body>
  <div id="container">
    <header>
      <h1>Talk<span style="color: #4ade80;">Pipe</span></h1>
      <div class="subtitle">Write and execute ChatterLang scripts interactively</div>
      <span class="header-links">
      <div class="topmaterial">Source and Segment documentation: (<a href="static/unit-docs.html" target="_blank">html</a>) (<a href="static/unit-docs.txt" target="_blank">text</a>)</div>
      </span>
    </header>
    <div id="compile-section">
      <h2>Script Editor</h2>
      <div class="editor-container">
        <textarea id="scriptInput" placeholder="Enter your ChatterLang script here..."></textarea>
        <div id="cursorPosition">Line: 0, Column: 0</div>
      </div>
      <div class="button-group">
        <button id="compileButton">Compile Script</button>
        <button id="toggle-examples">Toggle Examples</button>
        <button id="log-button">Toggle Logs</button>
        <span id="compileLoadingIndicator" class="loading hidden">Compiling script...</span>
      </div>    </div>
    <div class="workspace-container">
      <div id="examples-panel">
        <div class="examples-header">Example Scripts</div>
        <!-- Example categories will be populated here -->
      </div>
      <div class="main-panel">
        <div id="output-section">
          <h2>Output:</h2>
          <div id="output"></div>
        </div>
        <div id="interactive-section" class="hidden">
          <div id="interactive-container">
            <input type="text" id="interactiveInput" placeholder="Enter your input here...">
            <button id="goButton">Submit</button>
            <span id="loadingIndicator" class="loading hidden">Processing...</span>
          </div>
        </div>
      </div>
    </div>
  </div>
    
  <div id="log-panel" class="hidden">
    <button class="close-button">&times;</button>
    <h3>System Logs</h3>
    <div id="log-content"></div>
    <div id="log-controls">
      <button id="clear-logs">Clear Logs</button>
      <button id="refresh-logs">Refresh Logs</button>
    </div>
  </div>

  <script>
    let scriptId = null;
    let interactiveMode = false;
    let isProcessing = false;
    let isExamplesPanelVisible = true;

    // Cursor position tracking
    const scriptInput = document.getElementById('scriptInput');
    const cursorPosition = document.getElementById('cursorPosition');
    const examplesPanel = document.getElementById('examples-panel');

    // Load examples when the page loads
    document.addEventListener('DOMContentLoaded', loadExamples);

    // Toggle examples panel
    document.getElementById('toggle-examples').addEventListener('click', toggleExamplesPanel);

    function toggleExamplesPanel() {
      isExamplesPanelVisible = !isExamplesPanelVisible;
      examplesPanel.style.display = isExamplesPanelVisible ? 'flex' : 'none';
    }

    async function loadExamples() {
      try {
        const response = await fetch('/examples');
        const data = await response.json();
        
        if (data.examples) {
          const examplesPanel = document.getElementById('examples-panel');
          
          // Clear existing content
          while (examplesPanel.children.length > 1) {
            examplesPanel.removeChild(examplesPanel.lastChild);
          }
          
          // Add each category and its examples
          Object.entries(data.examples).forEach(([category, examples]) => {
            // Create category button (accordion)
            const categoryBtn = document.createElement('button');
            categoryBtn.className = 'accordion';
            categoryBtn.textContent = category;
            examplesPanel.appendChild(categoryBtn);
            
            // Create panel for examples
            const panel = document.createElement('div');
            panel.className = 'panel';
            examplesPanel.appendChild(panel);
            
            // Add examples to panel
            examples.forEach(example => {
              const exampleItem = document.createElement('div');
              exampleItem.className = 'example-item';
              exampleItem.innerHTML = `
                <div class="example-name">${example.name}</div>
                <div class="example-description">${example.description}</div>
              `;
              exampleItem.addEventListener('click', () => insertExample(example.code));
              panel.appendChild(exampleItem);
            });
            
            // Add accordion functionality
            categoryBtn.addEventListener('click', function() {
              this.classList.toggle('active');
              const panel = this.nextElementSibling;
              if (panel.style.maxHeight) {
                panel.style.maxHeight = null;
              } else {
                panel.style.maxHeight = panel.scrollHeight + "px";
              }
            });
          });
        }
      } catch (error) {
        console.error('Error loading examples:', error);
      }
    }

    function insertExample(code) {
      scriptInput.value = code;
      updateCursorPosition();
      // Focus and scroll to the editor
      scriptInput.focus();
    }

    function updateCursorPosition() {
      const pos = scriptInput.selectionStart;
      const text = scriptInput.value.substring(0, pos);
      const lines = text.split('\\n');
      const currentLine = lines.length - 1;
      const currentColumn = lines[lines.length - 1].length;
      cursorPosition.textContent = `Line: ${currentLine}, Column: ${currentColumn}`;
    }

    scriptInput.addEventListener('mouseup', updateCursorPosition);
    scriptInput.addEventListener('keyup', updateCursorPosition);
    scriptInput.addEventListener('input', updateCursorPosition);

    function scrollToBottom(element) {
      // Force scroll to bottom with multiple approaches for cross-browser compatibility
      if (element) {
        // Immediately try to scroll
        element.scrollTop = element.scrollHeight;
        
        // Then use multiple techniques with increasing delays to ensure it works
        setTimeout(() => { element.scrollTop = element.scrollHeight; }, 10);
        setTimeout(() => { element.scrollTop = element.scrollHeight; }, 50);
        setTimeout(() => { element.scrollTop = element.scrollHeight; }, 100);
      }
    }

    function setProcessingState(processing) {
      isProcessing = processing;
      const loadingIndicator = document.getElementById('loadingIndicator');
      const goButton = document.getElementById('goButton');
      const interactiveInput = document.getElementById('interactiveInput');
      
      loadingIndicator.classList.toggle('hidden', !processing);
      goButton.disabled = processing;
      interactiveInput.disabled = processing;
      
      if (!processing) {
        interactiveInput.focus();
      }
    }

    function setCompileState(compiling) {
      const compileButton = document.getElementById('compileButton');
      const compileLoadingIndicator = document.getElementById('compileLoadingIndicator');
      
      compileButton.disabled = compiling;
      compileLoadingIndicator.classList.toggle('hidden', !compiling);
      scriptInput.disabled = compiling;
    }

    function appendOutput(text) {
      const outputDiv = document.getElementById("output");
      const outputItem = document.createElement('div');
      outputItem.className = 'output-item';
      outputItem.textContent = text;
      outputDiv.appendChild(outputItem);
      
      // Scroll the OUTPUT SECTION (parent container) to bottom
      const outputSection = document.getElementById("output-section");
      scrollToBottom(outputSection);
      scrollToBottom(outputDiv);
    }

    // Logging functionality
    let isLogPanelVisible = false;
    let logUpdateInterval = null;

    document.getElementById('log-button').addEventListener('click', toggleLogPanel);
    document.querySelector('#log-panel .close-button').addEventListener('click', toggleLogPanel);
    document.getElementById('clear-logs').addEventListener('click', clearLogs);
    document.getElementById('refresh-logs').addEventListener('click', fetchLogs);

    function toggleLogPanel() {
      const logPanel = document.getElementById('log-panel');
      isLogPanelVisible = !isLogPanelVisible;
      logPanel.classList.toggle('hidden');
      
      if (isLogPanelVisible) {
        fetchLogs();
        logUpdateInterval = setInterval(fetchLogs, 2000);
      } else {
        clearInterval(logUpdateInterval);
      }
    }

    function clearLogs() {
      document.getElementById('log-content').innerHTML = '';
    }

    async function fetchLogs() {
      try {
        const response = await fetch('/logs');
        const data = await response.json();
        
        if (data.logs.length > 0) {
          const logContent = document.getElementById('log-content');
          data.logs.forEach(log => {
            const logEntry = document.createElement('div');
            logEntry.className = 'log-entry ' + getLogLevel(log);
            logEntry.textContent = log;
            logContent.appendChild(logEntry);
          });
          logContent.scrollTop = logContent.scrollHeight;
        }
      } catch (error) {
        console.error('Error fetching logs:', error);
      }
    }

    function getLogLevel(logEntry) {
      if (logEntry.includes('ERROR')) return 'log-error';
      if (logEntry.includes('WARNING')) return 'log-warning';
      return 'log-info';
    }

    document.getElementById("compileButton").addEventListener("click", async function() {
      setCompileState(true);
      const script = document.getElementById("scriptInput").value;
      try {
        const response = await fetch("/compile", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ script })
        });
        
        if (!response.ok) {
          const errorData = await response.json();
          throw new Error(errorData.detail || "Unknown error");
        }
        
        const data = await response.json();
        const outputDiv = document.getElementById("output");
        outputDiv.textContent = "";
        
        scriptId = data.id;
        interactiveMode = data.interactive;
        
        if (interactiveMode) {
          document.getElementById("interactive-section").classList.remove("hidden");
          document.getElementById("interactiveInput").focus();
        } else {
          document.getElementById("interactive-section").classList.add("hidden");
          if (data.output) {
            const outputs = data.output.split('\\n');
            outputs.forEach(output => {
              if (output.trim()) {
                appendOutput(output);
              }
            });
          }
        }
      } catch (error) {
        console.error('Error:', error);
        appendOutput("Error: " + error.message);
      } finally {
        setCompileState(false);
      }
    });

    async function processInteractiveInput() {
      if (!scriptId || isProcessing) {
        return;
      }

      const interactiveInputElem = document.getElementById("interactiveInput");
      const userInput = interactiveInputElem.value;
      
      if (!userInput.trim()) {
        return;
      }
      
      interactiveInputElem.value = "";
      setProcessingState(true);

      const outputDiv = document.getElementById("output");
      const userInputDiv = document.createElement('div');
      userInputDiv.className = 'user-input';
      userInputDiv.textContent = '> ' + userInput;
      outputDiv.appendChild(userInputDiv);

      try {
        const response = await fetch("/go", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ id: scriptId, user_input: userInput })
        });
        
        if (!response.ok) {
          const errorData = await response.json();
          throw new Error(errorData.detail || "Unknown error");
        }
        
        const reader = response.body.getReader();
        const decoder = new TextDecoder("utf-8");
        let buffer = '';
        
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\\n');
          buffer = lines.pop();
          
          lines.forEach(line => {
            if (line.trim()) {
              appendOutput(line);
            }
          });
        }
        
        if (buffer.trim()) {
          appendOutput(buffer);
        }
        
      } catch (error) {
        console.error('Error:', error);
        const errorDiv = document.createElement('div');
        errorDiv.style.color = 'red';
        errorDiv.textContent = 'Error: ' + error.message;
        outputDiv.appendChild(errorDiv);
      } finally {
        setProcessingState(false);
        // Force scroll to bottom after processing completes
        const outputDiv = document.getElementById("output");
        const outputSection = document.getElementById("output-section");
        scrollToBottom(outputSection);
        scrollToBottom(outputDiv);
      }
    }

    document.getElementById("goButton").addEventListener("click", processInteractiveInput);

    document.getElementById("interactiveInput").addEventListener("keydown", function(event) {
      if (event.key === "Enter") {
        event.preventDefault();
        processInteractiveInput();
      }
    });
  </script>
</body>
</html>"""
    return HTMLResponse(content=html_content)

def main():
    parser = argparse.ArgumentParser(
        description="Run the Talkpipe server with uvicorn"
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
        "--load_module", action='append', default=[], type=str, help="Path to a custom module file to import before running the script."
    )

    # Add more uvicorn options as needed
    args = parser.parse_args()

    if args.load_module:
        for module_file in args.load_module:
            load_module_file(fname=module_file, fail_on_missing=False)

    print(f"Starting TalkPipe server at http://{args.host}:{args.port}")
    uvicorn.run(
        "talkpipe.app.chatterlang_server:app",
        host=args.host,
        port=args.port,
        reload=args.reload
    )

if __name__ == "__main__":
    main()