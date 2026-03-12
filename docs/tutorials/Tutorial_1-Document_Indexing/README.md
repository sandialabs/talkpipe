# Tutorial 1: Document Indexing and Search

**Build a full document search system in under 30 minutes—from zero to a working web interface and API.**

TalkPipe lets you prototype searchable document systems without external databases or custom code. This tutorial shows how: you’ll generate test content, index it with full-text search, and expose it via a web UI and REST API—all using TalkPipe’s built-in components.

---

## Why This Tutorial?

- **Start fast**: No database setup—Whoosh is included with TalkPipe.
- **Real results**: You get a working search UI and API, not just a demo.
- **Learn the basics**: Foundation for Tutorials 2 (semantic search) and 3 (report generation).
- **Reuse it**: The same patterns work for docs, wikis, tickets, and other text collections.

---

## What You'll Build

| Step | Goal | Outcome |
|------|------|---------|
| **1** | Create content | 50 AI-generated stories in `stories.json` |
| **2** | Build the index | Full-text search index in `full_text_index/` |
| **3** | Add search | Web form + REST API for searching |

---

## Prerequisites

- **TalkPipe** installed: See [Getting Started](../../quickstart.md) for installation. For this tutorial: `pip install talkpipe[ollama]` or `talkpipe[all]`
- **Step 1 only**: Ollama installed locally with the `llama3.2` model (or adjust the script to use another model)

> **Tip:** If you skip Step 1, you can use the included `stories.json` and go straight to Step 2.

---

## Quick Start

All commands must be run from the tutorial directory:

```bash
cd docs/tutorials/Tutorial_1-Document_Indexing
```

| Step | Command | Time |
|------|---------|------|
| 1 | `./Step_1_CreateSyntheticData.sh` or `chatterlang_script --script Step_1_CreateSyntheticData.script` | ~5–10 min |
| 2 | `./Step_2_IndexStories.sh` or `chatterlang_script --script Step_2_IndexStories.script` | ~5 sec |
| 3 | `./Step_3_SearchStories.sh` or `chatterlang_serve --form-config story_search_ui.yml --title "Story Search" --display-property query --script Step_3_SearchStories.script` | Starts server |

Step 3 starts a web server. Use the URL printed in the terminal—append `/stream` for the search form, or POST to the base URL for the REST API.

---

## Step 1: Creating Synthetic Data

*Generating realistic test content for indexing*

### The Problem

You need documents to search. In real projects you might use papers, wikis, or tickets. For prototyping, synthetic data is safer and easier to control.

### The Solution

A ChatterLang pipeline in `Step_1_CreateSyntheticData.script` generates 50 short stories using an LLM:

```chatterlang
INPUT FROM "Generating 50 synthetic stories into stories.json" | print;
INPUT FROM echo[data="Write a fictitious five sentence story about technology development in an imaginary country.", n=50]
| llmPrompt[source="ollama", model="llama3.2", multi_turn=False]
| toDict[field_list="_:content"]
| llmPrompt[source="ollama", model="llama3.2", system_prompt="Write exactly one title for this story in plain text with no markdown", field="content", set_as="title", multi_turn=False]
| progressTicks[tick_count=1, eol_count=10, print_count=true]
| dumpsJsonl 
| writeString[fname="stories.json"];
```

**Expected result:** `stories.json` is created with 50 JSONL entries (one story per line). Progress ticks appear in the terminal.

**Run it:**

```bash
chatterlang_script --script Step_1_CreateSyntheticData.script
```

### Pipeline Breakdown

| Segment | Purpose |
|---------|---------|
| `echo[data="...", n=50]` | Sends 50 copies of the prompt to the pipeline |
| `llmPrompt[source="ollama", model="llama3.2", multi_turn=False]` | Generates 50 different stories (no context between calls) |
| `toDict[field_list="_:content"]` | Puts each story into a dict with a `content` field |
| `llmPrompt[..., field="content", set_as="title", ...]` | Adds a title for each story |
| `dumpsJsonl` \| `writeString[fname="stories.json"]` | Writes JSONL to `stories.json` |

---

## Step 2: Indexing the Stories

*Making documents searchable with full-text indexing*

### The Problem

Raw text files don’t support queries like “find stories about quantum computing.” You need an index: terms → documents, with relevance scoring.

### The Solution

Whoosh creates a full-text index from `stories.json`:

```chatterlang
INPUT FROM "stories.json"
| readJsonl
| progressTicks[tick_count=1, print_count=True]
| indexWhoosh[index_path="./full_text_index", field_list="content,title", overwrite=True]
```

**Expected result:** Directory `full_text_index/` is created. Progress output shows 50 items indexed.

**Run it:**

```bash
chatterlang_script --script Step_2_IndexStories.script
```

### What Whoosh Provides

- Full-text search, phrase search, wildcards (`*`, `?`)
- Boolean queries (AND, OR, NOT)
- Relevance scoring

TalkPipe includes Whoosh, so there’s no extra install. For larger deployments, you can swap in Elasticsearch or Solr and keep the rest of the pipeline.

### Data Flow

- **Input**: Filename `"stories.json"`
- **After `readJsonl`**: One JSON object per story
- **After `indexWhoosh`**: Same objects, plus searchable index in `full_text_index/`

---

## Step 3: Implementing Search

*Web interface and REST API*

### The Problem

You need both a UI for humans and an API for other systems. TalkPipe provides both from one configuration.

### The Solution

`chatterlang_serve` starts a server with a search form and JSON API. Pipeline segment from `Step_3_SearchStories.script` (receives query from form/API):

```chatterlang
| searchWhoosh[index_path="full_text_index", field="query"]
| formatItem[field_list="document.title:Title,document.content:Content,score:Score"]
```

**Run it:**

```bash
chatterlang_serve --form-config story_search_ui.yml --title "Story Search" --display-property query --script Step_3_SearchStories.script
```

### What You Get

| Interface | Path | Use |
|-----------|------|-----|
| **Web form** | `{base_url}/stream` | Search in a browser |
| **REST API** | `{base_url}/process` (POST) | Use from other apps |

The server prints the base URL when it starts (default: `http://localhost:2025`).

**Example API call:**

```bash
curl -X POST http://localhost:2025/process \
  -H "Content-Type: application/json" \
  -d '{"query": "quantum energy"}'
```

### Form Configuration

`story_search_ui.yml` defines the web form (fields, layout, theme). You can change the UI without touching the search logic.

**Expected result:** Server starts and prints a URL (e.g. `http://localhost:2025`). Open `{url}/stream` for the search form. Searching returns matching stories with title, content, and score.

---

## Troubleshooting

| Issue | Cause | Fix |
|-------|-------|-----|
| Connection refused / Ollama error | Ollama not running | Start Ollama: `ollama serve` (or launch the Ollama app) |
| Model not found | `llama3.2` not installed | Run `ollama pull llama3.2` |
| File not found / path errors | Wrong working directory | Run all commands from `docs/tutorials/Tutorial_1-Document_Indexing` |
| Port already in use | Another process on 2025 | Use `--port 2026` (or another port) with `chatterlang_serve` |

---

## Next Steps

- Add semantic search and RAG: [Tutorial 2: Search by Example and RAG](../Tutorial_2-Search_by_Example_and_RAG/)
- Build report generation: [Tutorial 3](../Tutorial_3_Report_Writing/)
- **Customize**: Swap prompts, models, or indexes; the pipeline structure stays the same.

**Next:** [Tutorial 2: Search by Example and RAG](../Tutorial_2-Search_by_Example_and_RAG/)

---

*Last reviewed: 20260219*
