// TalkPipe Workbench frontend bootstrap: editor wiring, run/interactive
// flows, logs, examples menu, and bottom output/log tabs.

import { createEditor, runFullCheck } from "./editor.js";
import { initWorkspace, markDirty } from "./workspace.js";
import { initSuggestions, notifyScriptChanged } from "./suggest.js";

let scriptId = null;
let isProcessing = false;

const $ = (id) => document.getElementById(id);

// --- Editor ---------------------------------------------------------------

export const editor = createEditor($("editor"), {
  onCursor(line, column) {
    $("cursorPosition").textContent = `Line: ${line}, Column: ${column}`;
  },
  onChange() {
    markDirty();
    notifyScriptChanged(editor);
  },
  onRun: runScript,
});

// --- Bottom tabs ----------------------------------------------------------

const tabPanes = { output: $("output"), logs: $("log-content") };

for (const tab of document.querySelectorAll("#bottom-tabs .tab")) {
  tab.addEventListener("click", () => selectTab(tab.dataset.tab));
}

function selectTab(name) {
  for (const tab of document.querySelectorAll("#bottom-tabs .tab")) {
    tab.classList.toggle("active", tab.dataset.tab === name);
  }
  for (const [paneName, pane] of Object.entries(tabPanes)) {
    pane.classList.toggle("hidden", paneName !== name);
  }
}

$("clearOutput").addEventListener("click", () => {
  const active = document.querySelector("#bottom-tabs .tab.active").dataset.tab;
  tabPanes[active].textContent = "";
});

function scrollToBottom(element) {
  element.scrollTop = element.scrollHeight;
  setTimeout(() => { element.scrollTop = element.scrollHeight; }, 50);
}

export function appendOutput(text, className = "output-item") {
  const outputDiv = $("output");
  const item = document.createElement("div");
  item.className = className;
  item.textContent = text;
  outputDiv.appendChild(item);
  scrollToBottom(outputDiv);
}

// --- Run / interactive flows (legacy /compile and /go endpoints) ----------

function setBusy(busy, message) {
  const indicator = $("statusIndicator");
  indicator.textContent = message || "Working…";
  indicator.classList.toggle("hidden", !busy);
  $("runButton").disabled = busy;
}

async function runScript() {
  setBusy(true, "Compiling…");
  selectTab("output");
  try {
    const response = await fetch("/compile", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ script: editor.getValue() }),
    });
    if (!response.ok) {
      const errorData = await response.json();
      throw new Error(errorData.detail || "Unknown error");
    }
    const data = await response.json();
    $("output").textContent = "";
    scriptId = data.id;

    const interactiveSection = $("interactive-section");
    if (data.interactive) {
      interactiveSection.classList.remove("hidden");
      $("interactiveInput").focus();
    } else {
      interactiveSection.classList.add("hidden");
      if (data.output) {
        for (const line of data.output.split("\n")) {
          if (line.trim()) appendOutput(line);
        }
      }
    }
  } catch (error) {
    appendOutput("Error: " + error.message, "output-item output-error");
  } finally {
    setBusy(false);
  }
}

$("runButton").addEventListener("click", runScript);

async function processInteractiveInput() {
  if (!scriptId || isProcessing) return;
  const inputElem = $("interactiveInput");
  const userInput = inputElem.value;
  if (!userInput.trim()) return;

  inputElem.value = "";
  isProcessing = true;
  $("loadingIndicator").classList.remove("hidden");
  $("goButton").disabled = true;
  inputElem.disabled = true;

  appendOutput("> " + userInput, "user-input");

  try {
    const response = await fetch("/go", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: scriptId, user_input: userInput }),
    });
    if (!response.ok) {
      const errorData = await response.json();
      throw new Error(errorData.detail || "Unknown error");
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder("utf-8");
    let buffer = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop();
      for (const line of lines) {
        if (line.trim()) appendOutput(line);
      }
    }
    if (buffer.trim()) appendOutput(buffer);
  } catch (error) {
    appendOutput("Error: " + error.message, "output-item output-error");
  } finally {
    isProcessing = false;
    $("loadingIndicator").classList.add("hidden");
    $("goButton").disabled = false;
    inputElem.disabled = false;
    inputElem.focus();
  }
}

$("goButton").addEventListener("click", processInteractiveInput);
$("interactiveInput").addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    event.preventDefault();
    processInteractiveInput();
  }
});

// --- Full compile check ---------------------------------------------------

$("checkButton").addEventListener("click", async () => {
  setBusy(true, "Checking…");
  try {
    const diagnostics = await runFullCheck(editor.view);
    if (diagnostics.length === 0) {
      appendOutput("Check passed: script compiles.");
    } else {
      selectTab("output");
      for (const d of diagnostics) {
        appendOutput(`line ${d.line}, col ${d.column}: ${d.message}`, "output-item output-error");
      }
    }
  } catch (e) {
    appendOutput("Check failed: " + e.message, "output-item output-error");
  } finally {
    setBusy(false);
  }
});

// Show the Check button only once the lint endpoint is known to exist.
fetch("/api/lint", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ script: "", mode: "parse" }),
})
  .then((r) => { if (r.ok) $("checkButton").hidden = false; })
  .catch(() => {});

// --- Examples menu ---------------------------------------------------------

async function loadExamples() {
  try {
    const response = await fetch("/examples");
    const data = await response.json();
    const menu = $("examplesMenu");
    menu.textContent = "";
    for (const [category, examples] of Object.entries(data.examples)) {
      const header = document.createElement("div");
      header.className = "dropdown-category";
      header.textContent = category;
      menu.appendChild(header);
      for (const example of examples) {
        const item = document.createElement("div");
        item.className = "dropdown-item";
        const name = document.createElement("div");
        name.className = "item-name";
        name.textContent = example.name;
        const description = document.createElement("div");
        description.className = "item-description";
        description.textContent = example.description;
        item.append(name, description);
        item.addEventListener("click", () => {
          editor.setValue(example.code);
          menu.classList.add("hidden");
          editor.focus();
        });
        menu.appendChild(item);
      }
    }
  } catch (error) {
    console.error("Error loading examples:", error);
  }
}

$("examplesButton").addEventListener("click", (event) => {
  event.stopPropagation();
  $("examplesMenu").classList.toggle("hidden");
});
document.addEventListener("click", (event) => {
  if (!event.target.closest(".dropdown")) $("examplesMenu").classList.add("hidden");
});

loadExamples();

// --- Logs -------------------------------------------------------------------

let logInterval = null;

function getLogLevel(logEntry) {
  if (logEntry.includes("ERROR")) return "log-error";
  if (logEntry.includes("WARNING")) return "log-warning";
  return "log-info";
}

async function fetchLogs() {
  try {
    const response = await fetch("/logs");
    const data = await response.json();
    if (data.logs.length > 0) {
      const logContent = $("log-content");
      for (const log of data.logs) {
        const entry = document.createElement("div");
        entry.className = "log-entry " + getLogLevel(log);
        entry.textContent = log;
        logContent.appendChild(entry);
      }
      scrollToBottom(logContent);
    }
  } catch (error) {
    console.error("Error fetching logs:", error);
  }
}

$("logButton").addEventListener("click", () => {
  selectTab("logs");
  fetchLogs();
  if (!logInterval) logInterval = setInterval(fetchLogs, 2000);
});

// --- Optional feature modules (each hides its UI if the API is absent) ----

initWorkspace(editor);
initSuggestions(editor);
