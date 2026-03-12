# Tutorial 3: Report Generation

**Turn search results into structured reports—executive summaries, multi-section analyses, and audience-specific formats.**

Tutorial 2 showed how to answer questions with RAG. This tutorial goes further: generate full documents from retrieved content. Enter a topic, retrieve relevant stories, and produce exec summaries, detailed reports, or format-specific outputs (technical report, client summary, research memo, etc.).

---

## Why This Tutorial?

- **Document generation, not just Q&A**: Synthesize multiple sources into coherent reports
- **Structured output**: Executive summaries, multi-section analyses, audience-specific formats
- **One topic, many formats**: Same research → executive brief, technical report, client summary, research memo, or presentation outline
- **Builds on Tutorial 2**: Uses the same vector index; no re-indexing

---

## What You'll Build

| Step | Goal | Outcome |
|------|------|---------|
| **1** | Executive summaries | 500–750 word summaries with key findings and strategic implications |
| **2** | Detailed reports | Multi-section reports (intro, analysis, tech deep-dive, future, recommendations) |
| **3** | Multi-format reports | Same content in 5 formats chosen by the user |

---

## Prerequisites

- **Tutorials 1 and 2 completed**: Vector index must exist at `../Tutorial_2-Search_by_Example_and_RAG/vector_index`
- **TalkPipe** installed: See [Getting Started](../../quickstart.md). For this tutorial: `pip install talkpipe[ollama]` or `talkpipe[all]`
- **Ollama** with these models:
  - `mxbai-embed-large` (embeddings): `ollama pull mxbai-embed-large`
  - `llama3.2` (generation): `ollama pull llama3.2`

---

## Quick Start

All commands must be run from the tutorial directory:

```bash
cd docs/tutorials/Tutorial_3_Report_Writing
```

| Step | Command | Time |
|------|---------|------|
| 1 | `./Step_1_ExecutiveSummaryGeneration.sh` or `chatterlang_serve --form-config report_topic_ui.yml --load-module step_1_extras.py --display-property topic --script Step_1_ExecutiveSummaryGeneration.script` | Starts server |
| 2 | `./Step_2_DetailedAnalysisReportGeneration.sh` or `chatterlang_serve --form-config report_topic_ui.yml --load-module step_2_extras.py --display-property topic --script Step_2_DetailedAnalysisReportGeneration.script` | Starts server |
| 3 | `./Step_3_MultiFormatReportGeneration.sh` or `chatterlang_serve --form-config multi_format_ui.yml --load-module step3_extras.py --display-property topic --script Step_3_MultiFormatReportGeneration.script` | Starts server |

Each step starts a web server. Open the URL shown—append `/stream` for the form. Try topics like "quantum computing innovations" or "renewable energy technologies."

---

## Step 1: Executive Summary Generation

*Structured summaries from retrieved documents*

### The Problem

Executives need concise overviews that synthesize multiple documents. Manual summarization is slow and can miss connections across sources.

### The Solution

Pipeline segment from `Step_1_ExecutiveSummaryGeneration.script` (receives `topic` from form):

```chatterlang
| copy
| llmEmbed[field="topic", source="ollama", model="mxbai-embed-large", set_as="vector"]
| searchLanceDB[field="vector", path="../Tutorial_2-Search_by_Example_and_RAG/vector_index", table_name="stories", all_results_at_once=True, set_as="results"]
| executiveSummaryPrompt
| llmPrompt[source="ollama", model="llama3.2"]
```

**Expected result:** Server starts. Enter a topic (e.g. "quantum computing"); receive a 500–750 word executive summary with key findings and strategic implications.

**Run it:**

```bash
chatterlang_serve --form-config report_topic_ui.yml --load-module step_1_extras.py --display-property topic --script Step_1_ExecutiveSummaryGeneration.script
```

### Pipeline Breakdown

| Segment | Purpose |
|---------|---------|
| `llmEmbed[field="topic", ...]` | Converts the user's topic into a vector for semantic search |
| `searchLanceDB[..., all_results_at_once=True, set_as="results"]` | Retrieves all matching documents into one item |
| `executiveSummaryPrompt` | Custom segment (in `step_1_extras.py`) that builds a prompt with Executive Overview, Key Findings, Technology Highlights, Strategic Implications |
| `llmPrompt` | Generates the summary from the prompt |

---

## Step 2: Detailed Analysis Reports

*Multi-section reports with in-depth coverage*

### The Problem

Executive summaries give overviews; stakeholders often need full reports with multiple sections, evidence, and recommendations.

### The Solution

Pipeline segment from `Step_2_DetailedAnalysisReportGeneration.script`:

```chatterlang
| copy
| llmEmbed[field="topic", source="ollama", model="mxbai-embed-large", set_as="vector"]
| searchLanceDB[field="vector", path="../Tutorial_2-Search_by_Example_and_RAG/vector_index", table_name="stories", limit=10, all_results_at_once=True, set_as="results"]
| generateReportSectionPrompts
| generateDetailedReport[source="ollama", model="llama3.2"]
```

**Expected result:** Server starts. Enter a topic; receive a multi-section report (intro, analysis, tech deep-dive, future implications, recommendations, sources).

**Run it:**

```bash
chatterlang_serve --form-config report_topic_ui.yml --load-module step_2_extras.py --display-property topic --script Step_2_DetailedAnalysisReportGeneration.script
```

### Pipeline Breakdown

| Segment | Purpose |
|---------|---------|
| `generateReportSectionPrompts` | Creates prompts for Introduction, Analysis, Technology, Future, Recommendations |
| `generateDetailedReport` | Runs each section through the LLM and assembles a formatted report |

### Section Structure

The report includes: Introduction and Background, Detailed Analysis, Technology Deep Dive, Future Implications, Recommendations, and Sources Referenced.

---

## Step 3: Multi-Format Report Pipeline

*Same content, different formats for different audiences*

### The Problem

Different audiences need different presentations—execs want briefs, technical teams want specs, clients want accessible summaries.

### The Solution

Pipeline segment from `Step_3_MultiFormatReportGeneration.script` (receives `topic` and `format` from form):

```chatterlang
| copy
| llmEmbed[field="topic", source="ollama", model="mxbai-embed-large", set_as="vector"]
| searchLanceDB[field="vector", path="../Tutorial_2-Search_by_Example_and_RAG/vector_index", table_name="stories", limit=10, all_results_at_once=True, set_as="results"]
| generateMultiFormatReport[source="ollama", model="llama3.2"]
```

**Expected result:** Server starts. Enter a topic and choose a format (Executive Brief, Technical Report, etc.); receive a report tailored to that format.

**Run it:**

```bash
chatterlang_serve --form-config multi_format_ui.yml --load-module step3_extras.py --display-property topic --script Step_3_MultiFormatReportGeneration.script
```

### Pipeline Breakdown

| Segment | Purpose |
|---------|---------|
| `generateMultiFormatReport` | Reads `format` from the input, builds a format-specific prompt, and generates the report |

### Format Options

| Format | Description |
|--------|-------------|
| **Executive Brief** | 1-page strategic overview (400–500 words) |
| **Technical Report** | Detailed technical analysis (600–800 words) |
| **Client Summary** | Accessible overview for non-technical stakeholders |
| **Research Memo** | Academic-style analysis with citations |
| **Presentation Outline** | Slide-by-slide talking points for a 15–20 min presentation |

Step 3 uses `multi_format_ui.yml`, which adds a `format` dropdown to the topic field.

---

## Custom Segments

Each step uses custom segments defined in Python:

| File | Segments | Purpose |
|------|----------|---------|
| `step_1_extras.py` | `executiveSummaryPrompt` | Structures retrieved docs into an exec summary prompt |
| `step_2_extras.py` | `generateReportSectionPrompts`, `generateDetailedReport` | Creates section prompts and assembles the full report |
| `step3_extras.py` | `generateMultiFormatReport` | Applies format-specific prompts and generates output |

The `--load-module` flag registers these so the scripts can use them.

---

## Troubleshooting

| Issue | Cause | Fix |
|-------|-------|-----|
| Connection refused / Ollama error | Ollama not running | Start Ollama: `ollama serve` |
| Model not found | Embedding or LLM model not installed | Run `ollama pull mxbai-embed-large` and `ollama pull llama3.2` |
| vector_index not found | Tutorial 2 not completed | Complete Tutorial 2 first; run from `docs/tutorials/Tutorial_3_Report_Writing` |
| Port already in use | Another process on default port | Use `--port 2026` with `chatterlang_serve` |

---

## Key Takeaways

- **RAG scales to document generation**: Retrieval + generation can produce full reports, not just Q&A
- **Custom segments extend pipelines**: Add domain-specific logic in Python and plug it into ChatterLang
- **Same data, multiple outputs**: One vector index supports summaries, detailed reports, and format-specific documents
- **Progression**: Tutorial 1 (search) → Tutorial 2 (Q&A) → Tutorial 3 (report generation)

---

## File Structure

See [file_structure.md](file_structure.md) for a complete list of files in this tutorial.

**Previous:** [Tutorial 2: Search by Example and RAG](../Tutorial_2-Search_by_Example_and_RAG/)

---

*Last reviewed: 20260219*
