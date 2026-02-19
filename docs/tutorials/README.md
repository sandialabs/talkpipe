# TalkPipe Tutorials

Three progressive tutorials for building data processing pipelines with minimal code: document search, semantic search with RAG, and AI-powered report generation.

## Learning Path

```mermaid
flowchart LR
    T1[Tutorial 1: Document Indexing ~30 min]
    T2[Tutorial 2: Search & RAG ~25 min]
    T3[Tutorial 3: Report Generation ~25 min]
    T1 --> T2 --> T3
```

Each tutorial builds on the previous. Tutorial 1's index feeds Tutorial 2; Tutorial 2's vector search powers Tutorial 3.

## Get Started in 5 Minutes

1. **Install**: See [Getting Started](../quickstart.md) for installation. For tutorials: `pip install talkpipe[ollama]` or `talkpipe[all]`
2. **Run Tutorial 1** (from `docs/tutorials/Tutorial_1-Document_Indexing`):
   - `./Step_1_CreateSyntheticData.sh` — creates `stories.json` (~5–10 min)
   - `./Step_2_IndexStories.sh` — builds search index (~5 sec)
   - `./Step_3_SearchStories.sh` — starts the search web UI and API
3. **See results**: Open the URL printed by Step 3; append `/stream` for the search form

## Tutorial Overview

| Tutorial | What You Build | Time |
|----------|----------------|------|
| [**1: Document Indexing**](Tutorial_1-Document_Indexing/) | Full-text search: synthetic data, Whoosh index, web UI + REST API | ~30 min |
| [**2: Search & RAG**](Tutorial_2-Search_by_Example_and_RAG/) | Vector embeddings, semantic search, RAG answers | ~25 min |
| [**3: Report Generation**](Tutorial_3_Report_Writing/) | Executive summaries, multi-section reports, format-specific outputs | ~25 min |

## Getting Started

1. **Choose a tutorial**: Start with [Tutorial 1](Tutorial_1-Document_Indexing/) if you're new
2. **Run the steps**: Each tutorial has step-by-step bash scripts
3. **Experiment**: Change prompts, models, parameters; test with your own data
4. **Build your own**: Use the patterns for custom pipelines

## Key Concepts

- **Composability**: Each tutorial reuses the previous one's output. Tutorial 1's index → Tutorial 2's corpus → Tutorial 3's report source.
- **Segment isolation**: Built-in segments (Whoosh, LanceDB, Ollama) can be replaced with custom segments or plugins (e.g. Elasticsearch, cloud vector DBs, OpenAI) when you scale—pipeline logic stays the same.
- **Streaming**: Process large files, see results as they generate, chain without intermediate storage.
- **Configuration over code**: YAML defines UIs; pipeline logic stays separate.

## Beyond the Web Interface

- **REST API**: Every `chatterlang_serve` exposes `POST /process` for JSON requests
- **Embed in code**: Use `compiler.compile(script).as_function()` to call pipelines from Python
- **Scale**: Write custom segments or use plugins for Elasticsearch, cloud vector DBs, etc., when you outgrow built-in Whoosh and LanceDB

## Advanced Tips

- Use `progressTicks` to identify bottlenecks
- Swap segments incrementally when scaling (Whoosh for metadata + cloud vectors is a common hybrid)
- See [Extending TalkPipe](../architecture/extending-talkpipe.md) for custom segments and plugins

---
Last Reviewed: 20260219
