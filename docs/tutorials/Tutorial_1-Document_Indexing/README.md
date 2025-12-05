# Prototyping a Searchable Document System with TalkPipe

This tutorial walks through building a document indexing and search system using TalkPipe. You'll learn how to rapidly prototype and experiment with different approaches to make large collections of text searchable and retrievable.

## What You'll Build

A complete document search system in three steps:
1. **Creating the Content** - Generate synthetic test documents using LLMs
2. **Building the Index** - Make documents searchable with full-text indexing
3. **Implementing Search** - Create web and API interfaces for searching

This tutorial uses minimal LLM integration (only for test data generation) to demonstrate TalkPipe's core pipeline concepts. The actual search functionality uses Whoosh, a pure-Python full-text search library included with TalkPipe - no external databases or services required.

**Use Cases**: These three steps might be your complete solution for small projects, or your proof-of-concept phase for larger deployments where you'll extract the proven pipelines into custom applications.

---

## Step 1: Creating Synthetic Data
*Generating realistic test content for our indexing system*

### The Challenge
Before we can build a search system, we need documents to search through. In real-world scenarios, you might be working with existing content like:
- Research papers and articles
- Company documentation and wikis
- Customer support tickets
- Product descriptions
- Legal documents

However, for testing and development purposes, we often need synthetic data that mimics real content patterns without using sensitive or copyrighted material.

### The Solution: AI-Generated Stories

The first step uses TalkPipe's ChatterLang scripting language to generate 50 fictional stories about technology development. The pipeline is defined in `Step_1_CreateSyntheticData.script`:

```
INPUT FROM "Generating 50 synthetic stories into stories.json" | print;
INPUT FROM echo[data="Write a fictitious five sentence story about technology development in an imaginary country.", n=50]
| llmPrompt[source="ollama", model="llama3.2", multi_turn=False]
| toDict[field_list="_:content"]
| llmPrompt[source="ollama", model="llama3.2", system_prompt="Write exactly one title for this story in plain text with no markdown", field="content", set_as="title", multi_turn=False]
| progressTicks[tick_count=1, eol_count=10, print_count=true]
| dumpsJsonl
| writeString[fname="stories.json"];
```

To run this script (from the `Tutorial_1-Document_Indexing` directory):

```bash
chatterlang_script --script Step_1_CreateSyntheticData.script
```

### Breaking Down the Pipeline

Let's understand what each part of this pipeline accomplishes:

**1. Status Message**
```
INPUT FROM "Generating 50 synthetic stories into stories.json" | print;
```
This prints a status message to let the user know what's happening.

**2. Content Generation with Repetition**
```
INPUT FROM echo[data="Write a fictitious five sentence story about technology development in an imaginary country.", n=50]
| llmPrompt[source="ollama", model="llama3.2", multi_turn=False]
```
The `echo` source generates 50 copies of the prompt, which are then sent to the LLM to generate 50 different stories. The `multi_turn=False` parameter ensures each story is independent, preventing the AI from building on previous stories.

**3. Data Structuring**
```
| toDict[field_list="_:content"]
```
This transforms the generated text into a structured format, creating a dictionary with the story content in a "content" field. This structure is crucial for later indexing.

**4. Title Generation**
```
| llmPrompt[system_prompt="Write exactly one title for this story in plain text with no markdown", field="content", set_as="title", multi_turn=False]
```
This step generates appropriate titles for each story. Notice how it:
- Uses the story content as input (`field="content"`)
- Adds the title to the existing data (`set_as="title"`)
- Ensures clean output with specific formatting instructions

**5. Progress Tracking and Output**
```
| progressTicks[tick_count=1, eol_count=10, print_count=true]
| dumpsJsonl
| writeString[fname="stories.json"];
```
The `progressTicks` segment provides visual feedback during processing. Finally, each complete document (with both content and title) is formatted as JSON Lines (JSONL) format and written directly to `stories.json` using `writeString`.


---

## Step 2: Indexing the Stories
*Making documents searchable through full-text indexing*

### The Challenge
Having documents isn't enough – we need to make them searchable. Raw text files can't efficiently answer queries like "find all stories about artificial intelligence" or "show me documents mentioning quantum computing." We need an index.

Think of an index like the index at the back of a book, but much more sophisticated. Instead of just noting page numbers for specific terms, a full-text search index:
- Breaks down every document into searchable terms
- Creates reverse mappings from terms to documents
- Enables complex queries with multiple terms
- Provides relevance scoring for search results

### The Solution: Whoosh Indexing

Step 2 takes our generated stories and creates a searchable index using the Whoosh library. The pipeline is defined in `Step_2_IndexStories.script`:

```
INPUT FROM "stories.json"
| readJsonl
| progressTicks[tick_count=1, print_count=True]
| indexWhoosh[index_path="./full_text_index", field_list="content,title", overwrite=True]
```

To run this script (from the `Tutorial_1-Document_Indexing` directory):

```bash
chatterlang_script --script Step_2_IndexStories.script
```

### Understanding the Indexing Pipeline

**1. Reading the Data**
```
INPUT FROM "stories.json"
| readJsonl
```
This reads our generated stories file and converts each line from JSON format back into Python objects that can be processed.

**2. Progress Monitoring**
```
| progressTicks[tick_count=1, print_count=True]
```
This provides feedback during processing, showing how many documents have been indexed. For larger datasets, this helps track progress and identify any bottlenecks.

**3. The Indexing Engine**
```
| indexWhoosh[index_path="./full_text_index", field_list="content,title", overwrite=True]
```
This is where the magic happens. The `indexWhoosh` segment:
- **Creates the index structure** in the `./full_text_index` directory
- **Indexes specified fields** - both "content" and "title" become searchable
- **Overwrites existing indexes** if they exist (`overwrite=True`)

### Why Whoosh?

Whoosh is a pure-Python search library that provides:
- **Full-text search capabilities** - Find documents containing specific terms
- **Boolean queries** - Combine terms with AND, OR, NOT operators
- **Phrase searching** - Find exact phrases within documents
- **Wildcard support** - Search with partial matches using * and ?
- **Relevance scoring** - Rank results by how well they match queries

Whoosh is included with TalkPipe, providing access to full-text search capabilities without additional setup, configuration, or external dependencies. This makes it possible to start experimenting with search functionality quickly.

For production deployments that need to scale beyond Whoosh's capabilities, TalkPipe's modular design allows you to replace the Whoosh components with enterprise search engines like Elasticsearch or Solr while keeping the rest of your pipeline unchanged.

### What Happens During Indexing

The indexing process:

1. **Tokenization** - Breaks text into individual terms and phrases
2. **Normalization** - Converts terms to lowercase, removes punctuation
3. **Term Analysis** - Identifies important terms and their frequencies
4. **Inverse Mapping** - Creates mappings from terms to documents containing them
5. **Storage** - Saves the index structure to disk for fast retrieval

After this step, you'll have a `full_text_index` directory containing the searchable index of all your stories.

### The Data Flow Transformation

Notice how the data changes as it flows through the pipeline:
- **Input**: A filename string (`"stories.json"`)
- **After readJsonl**: Individual JSON objects (one per story)
- **After indexWhoosh**: The same objects, but now also stored in a searchable index

This demonstrates TalkPipe's power in transforming data while maintaining its flow through the pipeline.

---

## Step 3: Implementing Search
*Creating user interfaces for finding and retrieving documents*

### The Challenge
We now have a searchable index, but we need a way for users to actually search it. The challenge is providing both:
- **Programmatic access** - APIs that other systems can call
- **Human-friendly interfaces** - Web forms that people can use directly

Most search implementations require significant custom development, but TalkPipe provides built-in solutions for both needs.

### The Solution: Dual Interface Search

Step 3 creates both an API endpoint and a web interface using a single command. The pipeline is defined in `Step_3_SearchStories.script`:

```
| searchWhoosh[index_path="full_text_index", field="query"]
| formatItem[field_list="document.title:Title,document.content:Content,score:Score"]
```

To run this script (from the `Tutorial_1-Document_Indexing` directory):

```bash
chatterlang_serve --form-config story_search_ui.yml --title "Story Search" --display-property query --script Step_3_SearchStories.script
```

### Understanding the Search System

**1. The Endpoint Architecture**
```
chatterlang_serve --form-config story_search_ui.yml --title "Story Search"
```
This creates a web server that provides:
- **An API endpoint** for programmatic access
- **A web form interface** configured by `story_search_ui.yml`
- **Automatic JSON handling** for both input and output

**2. The Search Pipeline**
```
| searchWhoosh[index_path="full_text_index", field="query"]
```
This segment:
- **Connects to our index** created in Step 2
- **Accepts search queries** from the "query" field in incoming requests
- **Returns matching documents** with relevance scores

**3. Result Formatting**
```
| formatItem[field_list="document.title:Title,document.content:Content,score:Score"]
```
This formats the search results for display:
- **Maps internal fields** to user-friendly labels
- **Selects relevant information** (title, content, and relevance score)
- **Prepares data** for both API responses and web display

### How Users Interact with the System

When you run the `chatterlang_serve` command, it will start a web server and display the URL to access it. Visiting that URL directly will show you the raw API endpoint interface, while adding `/stream` to the URL will bring up the user-friendly web form interface.

**Web Interface Users** can:
1. Navigate to the `/stream` URL in their browser
2. Enter search terms in a simple form
3. View formatted results with titles, content, and relevance scores
4. Refine their searches and try different terms

**API Users** can:
1. Send POST requests to the base URL with JSON payloads containing queries
2. Receive structured JSON responses with search results
3. Integrate search functionality into their own applications
4. Build more complex interfaces on top of the search API

### Configuring chatterlang_serve

The `story_search_ui.yml` file (included in the tutorial directory) contains configuration for the web interface:
- **Form field definitions** - What search options to present
- **Styling configuration** - How the interface should look
- **Validation rules** - What types of queries are allowed
- **Response formatting** - How results should be displayed

This separation of configuration from code means you can:
- **Modify the interface** without changing the underlying search logic
- **Customize for different use cases** with different YAML files
- **Maintain consistency** across multiple search interfaces

---
Last Reviewed: 20251128