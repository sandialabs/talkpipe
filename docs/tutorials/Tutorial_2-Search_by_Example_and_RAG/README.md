# Tutorial 2: Search by Example and RAG

**Go beyond keyword search—find documents by meaning and generate answers from your content.**

Keyword search breaks when users ask "find documents similar to this" or "show me content with the same concepts." This tutorial adds semantic search and RAG: embed documents as vectors, search by example, and let an LLM synthesize answers from retrieved context.

---

## Why This Tutorial?

- **Semantic search**: Find by meaning, not just matching words ("car" ≈ "automobile" ≈ "vehicle")
- **Example-based queries**: Users paste text and find similar content—no keyword crafting
- **RAG in practice**: Combine retrieval + generation for contextual answers
- **Builds on Tutorial 1**: Reuses the same stories; no data re-creation

---

## What You'll Build

| Step | Goal | Outcome |
|------|------|---------|
| **1** | Create vector index | LanceDB index in `vector_index/` with embeddings |
| **2** | Search by example | Web interface for semantic similarity search |
| **3** | RAG pipeline | AI-generated answers grounded in retrieved documents |

---

## Prerequisites

- **Tutorial 1 completed**: `stories.json` must exist at `../Tutorial_1-Document_Indexing/stories.json`
- **TalkPipe** installed: `pip install talkpipe[ollama]` (or `talkpipe[all]`)
- **Ollama** with these models:
  - `mxbai-embed-large` (embeddings): `ollama pull mxbai-embed-large`
  - `llama3.2` (Step 3 only): `ollama pull llama3.2`

---

## Quick Start

All commands must be run from the tutorial directory:

```bash
cd docs/tutorials/Tutorial_2-Search_by_Example_and_RAG
```

| Step | Command | Time |
|------|---------|------|
| 1 | `./Step_1_CreateVectorDatabase.sh` or `chatterlang_script --script Step_1_CreateVectorDatabase.script` | ~15–30 sec |
| 2 | `./Step_2_SearchByExample.sh` or `chatterlang_serve --form-config story_by_example_ui.yml --display-property example --script Step_2_SearchByExample.script` | Starts server |
| 3 | `./Step_3_SpecializedRag.sh` or `chatterlang_serve --form-config story_by_example_ui.yml --load-module step_3_extras.py --display-property example --script Step_3_SpecializedRag.script` | Starts server |

Steps 2 and 3 start web servers. Open the URL shown—append `/stream` for the form, or POST to the base URL for the API.

---

## Step 1: Creating a Vector Database

*Transforming text into searchable embeddings*

### The Problem

Traditional search matches words. "car" won't find "automobile"; "running quickly" won't match "sprinting." Vector embeddings map text into a space where similar meanings are close together.

### The Solution

Embed each story with `llmEmbed` and store vectors in LanceDB:

```
INPUT FROM "../Tutorial_1-Document_Indexing/stories.json"
| readJsonl
| progressTicks[tick_count=1, print_count=True]
| llmEmbed[field="content", source="ollama", model="mxbai-embed-large", set_as="vector"]
| addToLanceDB[path="./vector_index", table_name="stories", vector_field="vector", metadata_field_list="title,content", overwrite=True]
```

**Run it:**

```bash
chatterlang_script --script Step_1_CreateVectorDatabase.script
```

### Pipeline Breakdown

| Segment | Purpose |
|---------|---------|
| `INPUT FROM "../Tutorial_1-Document_Indexing/stories.json"` | Reuses stories from Tutorial 1 |
| `llmEmbed[field="content", ..., set_as="vector"]` | Generates embeddings for each story's content |
| `addToLanceDB` | Stores vectors in LanceDB; keeps title and content for retrieval |

---

## Step 2: Search by Example

*Finding documents through semantic similarity*

### The Problem

Users often have an example and want similar content—a support agent pasting an error, a researcher with one relevant paper, a writer with a paragraph.

### The Solution

Embed the user's example, search the vector index, format results:

```
| copy
| llmEmbed[field="example", source="ollama", model="mxbai-embed-large", set_as="vector"]
| searchLanceDB[field="vector", path="./vector_index", table_name="stories", limit=10]
| formatItem[field_list="document.title:Title, document.content:Content, score:Score"]
```

**Run it:**

```bash
chatterlang_serve --form-config story_by_example_ui.yml --display-property example --script Step_2_SearchByExample.script
```

### Pipeline Breakdown

| Segment | Purpose |
|---------|---------|
| `copy` | Defensive copy for web endpoints—avoids mutating shared input |
| `llmEmbed[field="example", ...]` | Embeds the user's example with the same model used for indexing |
| `searchLanceDB[..., limit=10]` | Returns the 10 nearest documents by vector similarity |
| `formatItem` | Maps internal fields to display labels (Title, Content, Score) |

---

## Step 3: Specialized RAG (Retrieval-Augmented Generation)

*Combining search with AI to generate answers*

### The Problem

Finding relevant documents is useful, but users often want a synthesized answer—not just a list of matches.

### The Solution

Retrieve documents, build a RAG prompt with context, and generate an answer:

```
| copy
| llmEmbed[field="example", source="ollama", model="mxbai-embed-large", set_as="vector"]
| searchLanceDB[field="vector", path="./vector_index", table_name="stories", all_results_at_once=True, set_as="results"]
| ragPrompt
| llmPrompt[source="ollama", model="llama3.2"]
```

**Run it:**

```bash
chatterlang_serve --form-config story_by_example_ui.yml --load-module step_3_extras.py --display-property example --script Step_3_SpecializedRag.script
```

### Pipeline Breakdown

| Segment | Purpose |
|---------|---------|
| `searchLanceDB[..., all_results_at_once=True, set_as="results"]` | Collects all matches into one item for the LLM |
| `ragPrompt` | Custom segment (in `step_3_extras.py`) that builds a prompt from query + retrieved docs |
| `llmPrompt` | Generates the answer from the RAG prompt |

### The Custom RAG Segment

`step_3_extras.py` defines `ragPrompt`, which formats the user's example and retrieved documents into a prompt:

```python
@register_segment("ragPrompt")
@field_segment()
def rag_prompt_segment(item):
    query = extract_property(item, "example", fail_on_missing=True)
    results = extract_property(item, "results", fail_on_missing=True)
    context_text = "\n\n".join([
        f"Title: {result.document['title']}\nContent: {result.document['content']}"
        for result in results
    ])
    return f"""
    You are a helpful assistant. Your task is to answer the question based on the provided context.
    Answer the question as accurately as possible. At the end of your answer, provide a list of
    sources used to answer the question and list the names of technologies listed in the sources.

    Context:
    {context_text}

    Question:
    {query}
    """
```

The `--load-module step_3_extras.py` flag registers this segment so the script can use it.

---

## Key Takeaways

- **Vector search captures meaning**: Same concepts map close together even with different wording
- **Example-based search improves discovery**: Users find content they couldn't reach with keywords
- **Pipelines are composable**: Combine keyword search (Tutorial 1) with vector search in one app
- **RAG adds value**: Retrieval + generation yields answers grounded in your documents

---

## Next Steps

- **Tutorial 3**: Use this vector index for report generation and summaries
- **Customize**: Swap embedding models, adjust the RAG prompt, or add filters

---

*Last reviewed: 20260212*
