# Tutorial 2: Search by Example and RAG - Going Beyond Keyword Search

Imagine you're building a knowledge management system for your team. You've already created a traditional keyword search (as shown in Tutorial 1), but your users keep saying things like:

- "I want to find documents similar to this one"
- "Show me all content that talks about the same concepts as this paragraph"
- "Can you find articles with similar themes to what I'm writing?"

Traditional keyword search falls short here. What you need is **semantic search** - the ability to find documents based on meaning and context, not just matching words. Even better, you want to use those search results to generate intelligent summaries and answers. That's where this tutorial comes in.

In Tutorial 1, we built a document system using traditional full-text search. Now we'll enhance it with AI-powered capabilities:

1. **Step 1: Create a Vector Database** - Transform documents into mathematical representations that capture meaning
2. **Step 2: Search by Example** - Find similar documents using semantic similarity instead of keywords
3. **Step 3: Specialized RAG** - Combine search results with AI to generate contextual answers

---

## Step 1: Creating a Vector Database
*Transforming text into searchable mathematical representations*

### Why Vector Search?

Traditional search looks for exact word matches. But consider these queries:
- "car" vs "automobile" vs "vehicle" - same concept, different words
- "running quickly" vs "sprinting" - similar meaning, no shared words
- "The product exceeded expectations" vs "Customers were delighted" - same sentiment, completely different phrasing

Vector embeddings solve this by converting text into high-dimensional mathematical representations where similar meanings are numerically close together. Think of it as mapping words and phrases into a space where distance represents semantic similarity.

### The Implementation

The pipeline is defined in `Step_1_CreateVectorDatabase.script`:

```
INPUT FROM "../Tutorial_1-Document_Indexing/stories.json"
| readJsonl
| progressTicks[tick_count=1, print_count=True]
| llmEmbed[field="content", source="ollama", model="mxbai-embed-large", set_as="vector"]
| addToLanceDB[path="./vector_index", table_name="stories", vector_field="vector", metadata_field_list="title,content", overwrite=True]
```

To run this script:

```bash
chatterlang_script --script Step_1_CreateVectorDatabase.script
```

### Breaking Down the Pipeline

**1. Input Source**
```
INPUT FROM "../Tutorial_1-Document_Indexing/stories.json"
```
We're reusing the synthetic stories from Tutorial 1. This demonstrates a key principle: you can enhance existing data with new capabilities without starting over.

**2. The Embedding Process**
```
| llmEmbed[field="content", source="ollama", model="mxbai-embed-large", set_as="vector"]
```
This segment:
- Takes the `content` field from each document
- Uses the `mxbai-embed-large` model to generate embeddings
- Appends the resulting vector to each document

The `mxbai-embed-large` model is specifically designed for semantic search - it's trained to place similar concepts near each other in vector space.

**3. Building the Index**
```
| addToLanceDB[path="./vector_index", table_name="stories", vector_field="vector", metadata_field_list="title,content", overwrite=True]
```
This creates a specialized index that:
- Stores vectors for similarity search in a LanceDB table named "stories"
- Preserves original metadata (title and content) for retrieval
- Enables fast nearest-neighbor queries using LanceDB's efficient vector search capabilities

---

## Step 2: Search by Example
*Finding documents through semantic similarity*

### The User Experience Challenge

Your users don't always know the right keywords. Sometimes they have an example and want to find similar content:
- A support agent pastes an error message and wants similar resolved tickets
- A researcher has one relevant paper and needs related work
- A content creator has a paragraph and wants similar articles for inspiration

### The Solution: Semantic Search Interface

The pipeline is defined in `Step_2_SearchByExample.script`:

```
| copy
| llmEmbed[field="example", source="ollama", model="mxbai-embed-large", set_as="vector"]
| searchLanceDB[field="vector", path="./vector_index", table_name="stories", limit=10]
| formatItem[field_list="document.title:Title, document.content:Content, score:Score"]
```

To run this script:

```bash
chatterlang_serve --form-config story_by_example_ui.yml --display-property example --script Step_2_SearchByExample.script
```

### Understanding the Search Pipeline

**1. Defensive Copying**
```
| copy
```
This creates a copy of the input data - important when building web endpoints to prevent unintended data modifications that could affect the browser interface.

**2. Query Embedding**
```
| llmEmbed[field="example", source="ollama", model="mxbai-embed-large", set_as="vector"]
```
The user's example text is converted to a vector using the same model that indexed the documents. This ensures the query and documents exist in the same vector space.

**3. Vector Search**
```
| searchLanceDB[field="vector", path="./vector_index", table_name="stories", limit=10]
```
This finds the documents whose vectors are closest to the query vector - literally the nearest neighbors in high-dimensional space. LanceDB provides efficient approximate nearest neighbor search for fast retrieval.

**4. Result Formatting**
```
| formatItem[field_list="document.title:Title, document.content:Content, score:Score"]
```
Results are formatted for display, showing similarity scores that indicate how closely each document matches the example.

### The User Interface

The `story_by_example_ui.yml` configuration creates a simple but effective interface:

```yaml
title: "Story Search by Example"
position: "bottom"
height: "150px"
theme: "dark"

fields:
  - name: example
    type: "textarea"
    label: "Example"
    placeholder: "Enter example here"
    required: true
```

Users can paste any text example and instantly find semantically similar documents - no keyword crafting required.

---

## Step 3: Specialized RAG (Retrieval-Augmented Generation)
*Combining search results with AI to generate contextual answers*

### Beyond Search: Intelligent Synthesis

Finding relevant documents is helpful, but what users often really want is an answer that synthesizes information from multiple sources. RAG (Retrieval-Augmented Generation) combines:
- **Retrieval**: Finding relevant documents (what we built in Step 2)
- **Augmentation**: Using those documents as context
- **Generation**: Creating new, synthesized responses

### The RAG Implementation

The pipeline is defined in `Step_3_SpecializedRag.script`:

```
| copy
| llmEmbed[field="example", source="ollama", model="mxbai-embed-large", set_as="vector"]
| searchLanceDB[field="vector", path="./vector_index", table_name="stories", all_results_at_once=True, set_as="results"]
| ragPrompt
| llmPrompt[source="ollama", model="llama3.2"]
```

To run this script:

```bash
chatterlang_serve --form-config story_by_example_ui.yml --load-module step_3_extras.py --display-property example --script Step_3_SpecializedRag.script
```

### What's Different in the RAG Pipeline

**1. Batch Results Collection**
```
| searchLanceDB[..., all_results_at_once=True, set_as="results"]
```
Instead of processing results one by one, we collect all search results together. This allows the next step to see the full context.

**2. Custom RAG Prompt Generation**
```
| ragPrompt
```
This custom segment (defined in `step_3_extras.py`) creates a specialized prompt that:
- Includes all retrieved documents as context
- Structures the user's question
- Provides clear instructions to the AI

Let's look at the custom segment (from `step_3_extras.py`):

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

    ans = f"""
    You are a helpful assistant. Your task is to answer the question based on the provided context.
    Answer the question as accurately as possible. At the end of your answer, provide a list of 
    sources used to answer the question and list the names of technologies listed in the sources.

    Context: 
    {context_text}
    
    Question: 
    {query}
    """
    return ans
```

**3. AI-Powered Answer Generation**
```
| llmPrompt
```
The formatted prompt is sent to an LLM, which generates a comprehensive answer based on the retrieved documents.

### Key Takeaways

**Vector embeddings are effective but focused**: They excel at finding semantic similarity but require the right model choice and use case.

**Example-based search changes user behavior**: When people can search by pasting examples, they find content they couldn't discover with keywords alone.

**Pipelines are composable**: You can mix traditional search (from Tutorial 1) with vector search, or use both in the same application.

**Start simple, enhance gradually**: Begin with basic vector search, then add RAG capabilities as your understanding of user needs develops.

---
Last Reviewed: 20251128