# ChatterLang Workbench

**`chatterlang_workbench`** - Browser-based IDE for writing, testing, and running ChatterLang pipelines.

## Overview

The ChatterLang Workbench provides a development environment for TalkPipe's external DSL. It features a code editor with syntax highlighting, context-aware autocomplete, hover help, and live error checking; real-time script execution (including interactive, chat-style scripts); a pipeline workspace for saving and reloading scripts; and a suggestions sidebar that recommends the next pipeline component. This tool is perfect for experimenting with ChatterLang syntax, prototyping pipelines, and learning TalkPipe concepts interactively.

## Usage

### Command Line Interface

```bash
chatterlang_workbench [options]
```

Then open the printed URL (default `http://127.0.0.1:4143`) in a browser.

### Command Line Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--host` | string | `127.0.0.1` | Server host address |
| `--port` | integer | `4143` | Server port number |
| `--reload` | flag | `false` | Enable auto-reload for development |
| `--load-module` | string | | Path to custom module file to import (can be used multiple times) |
| `--workspace` | string | `~/.talkpipe/workbench` | Directory for saved pipelines and workbench settings |
| `--suggest-source` | string | | LLM source for the suggestions sidebar (e.g. `ollama`) |
| `--suggest-model` | string | | LLM model name for the suggestions sidebar |
| `--no-llm-suggestions` | flag | `false` | Disable LLM-driven suggestions entirely (heuristic suggestions remain) |

### Examples

```bash
# Start server with default settings
chatterlang_workbench

# Start on custom host and port
chatterlang_workbench --host 0.0.0.0 --port 8080

# Enable development mode with auto-reload
chatterlang_workbench --reload

# Load custom modules before starting
chatterlang_workbench --load-module /path/to/custom_segments.py

# Keep saved pipelines in a project directory
chatterlang_workbench --workspace ./my_pipelines

# Use a specific model for the suggestions sidebar
chatterlang_workbench --suggest-source ollama --suggest-model llama3.2

# Heuristic suggestions only, no LLM calls
chatterlang_workbench --no-llm-suggestions
```

## Web Interface Features

### Script Editor

The editor understands ChatterLang:

- **Syntax highlighting** for keywords, components, parameters, strings, variables (`@name`), and constants (`$name`).
- **Autocomplete** appears as you type (or on `Ctrl-Space`): sources after `INPUT FROM`/`NEW`, segments after `|`, and parameter names inside `[...]` — each with its documentation.
- **Hover help**: hover any component name for its description and parameter table.
- **Lint as you type**: unknown components, bad parameter names, and syntax errors are underlined with precise positions and "did you mean" hints.
- **Check button**: runs a full compile of the script server-side (instantiates components without executing them) and reports any errors with line/column positions.
- `Ctrl-Enter` runs the script; `Ctrl-S` saves the current pipeline.

### Interactive Execution

The workbench supports two execution modes:

#### Non-Interactive Scripts
Scripts that start with `INPUT FROM` or other source commands execute immediately when run, displaying all output at once.

**Example:**
```
INPUT FROM echo[data="Hello World"] | print
```

#### Interactive Scripts
Scripts that start with `|` (pipe) require user input and support multi-turn interactions. An input box appears below the output pane.

**Example:**
```
| llmPrompt[model="llama3.2", source="ollama", multi_turn=True]
```

### Pipeline Workspace

Use **Save** / **Save As…** to store the current script as a named pipeline; saved pipelines appear in the left sidebar, where they can be reopened, renamed, or deleted. Pipelines are stored as plain `.script` files in the workspace directory (default `~/.talkpipe/workbench`, override with `--workspace`). Metadata lives in a `#%` comment header, so the files remain directly runnable with `chatterlang_script` and friendly to version control:

```
#% name: Daily article summarizer
#% description: Downloads a URL list and summarizes each page
#% created: 2026-07-16T12:00:00+00:00
INPUT FROM ...
```

### Suggestions Sidebar

The right sidebar recommends what to add next:

- **Likely next**: instant, heuristic rankings mined from the built-in examples and your saved pipelines (the `×N` counts show how often a component appears in that corpus). Click a suggestion to insert it.
- **AI suggestions**: an LLM proposes the next component with a short rationale. Click the ✨ button to ask, or enable "Suggest automatically while typing" in Settings (⚙).

The suggestion LLM is resolved in this order:

1. The workbench **Settings dialog** (⚙), persisted to `<workspace>/settings.json` — this takes precedence over the flags below once saved.
2. The `--suggest-source` / `--suggest-model` command-line flags.
3. The standard TalkPipe model configuration (`TALKPIPE_default_model_source` / `TALKPIPE_default_model_name` or `~/.talkpipe.toml`).

> **Remote Ollama:** the workbench server talks to Ollama directly, so if your Ollama server runs on another machine, set `TALKPIPE_OLLAMA_SERVER_URL` (e.g. `export TALKPIPE_OLLAMA_SERVER_URL=http://your-ollama-host:11434`) **before starting** `chatterlang_workbench`. The same applies to `llmPrompt` and friends inside scripts you run from the workbench.

### Built-in Examples

The **Examples** menu provides categorized example scripts (basic data flows, LLM chat and agent conversations, image/vision, loops, scoring, and RAG). Loading an example replaces the editor content as an unsaved scratch buffer — use **Save As…** to keep your own copy.

### Built-in Documentation

The **Docs** links in the header serve the full component reference (HTML and text) generated live from the installed components — including any custom components loaded with `--load-module`.

### System Logging

- **Logs tab / Logs button**: live system and execution logs, color-coded by level.
- Logs refresh every couple of seconds while the tab is open; use the trash icon to clear.

## Development Features

### Custom Module Loading

Load custom TalkPipe components before starting the server:

```bash
chatterlang_workbench --load-module ./my_custom_segments.py
```

This allows you to:
- Test custom sources and segments
- Prototype new functionality
- Integrate domain-specific components

Custom components participate fully in the workbench: they compile and run, and they appear in autocomplete, hover help, lint, and the generated documentation.

### Auto-reload Mode

Enable development mode for automatic server restarts:

```bash
chatterlang_workbench --reload
```

**Note**: Only use `--reload` in development environments.

## HTTP API

Everything the UI does is available over HTTP on the same port:

| Endpoint | Method | Purpose and request body |
|----------|--------|--------------------------|
| `/compile` | POST | Compile (and, for non-interactive scripts, run) `{"script": ...}`; returns `{"id", "interactive", "output"?}` |
| `/go` | POST | Send input to a compiled interactive script: `{"id": <from /compile>, "user_input": ...}` |
| `/api/lint` | POST | Diagnostics for a script: `{"script": ..., "mode": "parse" \| "full"}` |
| `/api/reference` | GET | Component reference (names, types, parameters, docs) |
| `/api/pipelines` | GET/POST | List / create (`{"name", "description"?, "script"}`) saved pipelines (`PUT`/`DELETE`/`POST .../rename` per id) |
| `/api/suggest` | POST | LLM next-component suggestions: `{"script": ..., "cursor_offset": ...}` |
| `/api/suggest/stats` | GET | Heuristic co-occurrence tables |
| `/api/settings` | GET/PUT | Suggestion settings (per workspace): `{"suggest_source", "suggest_model", "auto_suggest"}` |

## Troubleshooting

### Common Issues

**Server won't start**
- Check if port is already in use
- Verify TalkPipe installation
- Check for missing dependencies

**Scripts fail to compile**
- Verify ChatterLang syntax (the lint underlines and the Check button give positions and hints)
- Check for missing LLM configurations
- Review system logs for detailed errors

**Interactive mode not working**
- Ensure script starts with `|` character
- Verify LLM connectivity (Ollama/OpenAI)
- Check API key configuration

**AI suggestions say no LLM endpoint is configured**
- Suggestions work with any supported provider (such as ollama, openai, or anthropic — plugins can register additional sources), not just Ollama
- Pick a provider and model in the Settings dialog (⚙), start the workbench with `--suggest-source` / `--suggest-model`, or set the TalkPipe default model configuration

**AI suggestions say the model is not reachable**
- If the message instead says a provider is *not installed* (e.g. "Ollama is not installed. Please install it with: `pip install talkpipe[ollama]`"), install that extra and restart — the model was never the problem
- If Ollama runs on another machine, set `TALKPIPE_OLLAMA_SERVER_URL` and restart the workbench
- Verify the model is pulled on the Ollama server (`ollama pull <model>`)
- If you started with `--no-llm-suggestions`, LLM suggestions stay off regardless of Settings

**Interactive chat shows "Error: …" in the output pane**
- The message is the real error from the provider (e.g. a missing model with a `ollama pull` hint); the bottom **Logs** tab has the full detail and stack context

**My `--suggest-model` flag seems ignored**
- A model saved in the Settings dialog (stored in `<workspace>/settings.json`) takes precedence over the CLI flags; clear the fields in Settings (choose "(default)") or remove `settings.json` to fall back to the flags

**Custom components missing under `--reload`**
- Upgrade TalkPipe: older versions lost `--load-module` components when the auto-reloader restarted the server

**Examples not loading**
- Check browser console for JavaScript errors
- Restart server if needed

---

*For conceptual information about ChatterLang, see [ChatterLang Architecture](../architecture/chatterlang.md).*

---
Last Reviewed: 20260716
