# Tutorial 2: Search by Example and RAG - Going Beyond Keyword Search

Imagine you're building a knowledge management system for your team. You've already created a traditional keyword search (as shown in Tutorial 1), but your users keep saying things like:

- "I want to find documents similar to this one"
- "Show me all content that talks about the same concepts as this paragraph"
- "Can you find articles with a similar vibe to what I'm writing?"

Traditional keyword search falls short here. What you need is **semantic search** - the ability to find documents based on meaning and context, not just matching words. Even better, you want to use those search results to generate intelligent summaries and answers. That's where this tutorial comes in.

## The Journey: From Keywords to Understanding

In Tutorial 1, we built a document system using traditional full-text search. Now we'll enhance it with AI-powered capabilities:

1. **Step 1: Create a Vector Database** - Transform documents into mathematical representations that capture meaning
2. **Step 2: Search by Example** - Find similar documents using semantic similarity instead of keywords
3. **Step 3: Specialized RAG** - Combine search results with AI to generate contextual answers

This progression mirrors how many real-world systems evolve: starting with basic search, then adding intelligence as user needs become more sophisticated.

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

```bash
export TALKPIPE_CHATTERLANG_SCRIPT='
    INPUT FROM "../Tutorial_1-Document_Indexing/stories.json"
    | readJsonl 
    | progressTicks[tick_count=1, print_count=True] 
    | llmEmbed[field="content", source="ollama", model="mxbai-embed-large", append_as="vector"]
    | addVector[path="./vector_index", vector_field="vector", metadata_field_list="title,content", overwrite=True]
'

python -m talkpipe.app.chatterlang_script --script CHATTERLANG_SCRIPT
```

### Breaking Down the Pipeline

**1. Input Source**
```
INPUT FROM "../Tutorial_1-Document_Indexing/stories.json"
```
We're reusing the synthetic stories from Tutorial 1. This demonstrates a key principle: you can enhance existing data with new capabilities without starting over.

**2. The Embedding Process**
```
| llmEmbed[field="content", source="ollama", model="mxbai-embed-large", append_as="vector"]
```
This segment:
- Takes the `content` field from each document
- Uses the `mxbai-embed-large` model to generate embeddings
- Appends the resulting vector to each document

The `mxbai-embed-large` model is specifically designed for semantic search - it's trained to place similar concepts near each other in vector space.

**3. Building the Index**
```
| addVector[path="./vector_index", vector_field="vector", metadata_field_list="title,content", overwrite=True]
```
This creates a specialized index that:
- Stores vectors for similarity search
- Preserves original metadata (title and content) for retrieval
- Enables fast nearest-neighbor queries

### Real-World Applications

This vector indexing approach powers many modern applications:
- **Customer Support**: Find previous tickets similar to new issues
- **Content Recommendation**: Suggest articles based on reading history
- **Research Tools**: Discover related papers across disciplines
- **Code Search**: Find functions that solve similar problems

---

## Step 2: Search by Example
*Finding documents through semantic similarity*

### The User Experience Challenge

Your users don't always know the right keywords. Sometimes they have an example and want to find similar content:
- A support agent pastes an error message and wants similar resolved tickets
- A researcher has one relevant paper and needs related work
- A content creator has a paragraph and wants similar articles for inspiration

### The Solution: Semantic Search Interface

```bash
export TALKPIPE_CHATTERLANG_SCRIPT='    
    | copy
    | llmEmbed[field="example", source="ollama", model="mxbai-embed-large", append_as="vector"]
    | searchVector[vector_field="vector", path="./vector_index"]
    | formatItem[field_list="document.title:Title, document.content:Content, score:Score"]
'

python -m talkpipe.app.chatterlang_serve --form-config story_by_example_ui.yml --display-property example --script CHATTERLANG_SCRIPT
```

### Understanding the Search Pipeline

**1. Defensive Copying**
```
| copy
```
This creates a copy of the input data - crucial when building web endpoints to prevent unintended data modifications that could affect the browser interface.

**2. Query Embedding**
```
| llmEmbed[field="example", source="ollama", model="mxbai-embed-large", append_as="vector"]
```
The user's example text is converted to a vector using the same model that indexed the documents. This ensures the query and documents exist in the same vector space.

**3. Vector Search**
```
| searchVector[vector_field="vector", path="./vector_index"]
```
This finds the documents whose vectors are closest to the query vector - literally the nearest neighbors in high-dimensional space.

**4. Result Formatting**
```
| formatItem[field_list="document.title:Title, document.content:Content, score:Score"]
```
Results are formatted for display, showing similarity scores that indicate how closely each document matches the example.

### The User Interface

The `story_by_example_ui.yaml` configuration creates a simple but effective interface:

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

```bash
export TALKPIPE_CHATTERLANG_SCRIPT='
    | copy
    | llmEmbed[field="example", source="ollama", model="mxbai-embed-large", append_as="vector"]
    | searchVector[vector_field="vector", path="./vector_index", all_results_at_once=True, append_as="results"]
    | ragPrompt
    | llmPrompt[source="ollama", model="llama3.2"]
'

python -m talkpipe.app.chatterlang_serve --form-config story_by_example_ui.yml --load-module step_3_extras.py --display-property example --script CHATTERLANG_SCRIPT
```

### What's Different in the RAG Pipeline

**1. Batch Results Collection**
```
| searchVector[..., all_results_at_once=True, append_as="results"]
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

Let's look at the custom segment:

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

### Real-World RAG Applications

This pattern powers many modern AI applications:
- **Customer Support Bots**: Answer questions using your knowledge base
- **Research Assistants**: Synthesize findings from multiple papers
- **Documentation Systems**: Generate answers from technical docs
- **Legal Research**: Summarize relevant case law
- **Medical Information**: Compile information from multiple sources (with appropriate disclaimers)

### Why RAG Matters

RAG solves several critical problems in AI applications:

1. **Accuracy**: Answers are grounded in your actual documents, reducing hallucination
2. **Currency**: The AI uses your latest information, not just its training data
3. **Transparency**: You can show which documents informed each answer
4. **Control**: You decide what information the AI can access

---

## Putting It All Together: The Evolution of Search

This tutorial demonstrates a natural progression in search capabilities:

1. **Vector Indexing**: Move beyond keywords to understand meaning
2. **Semantic Search**: Let users search by example, not just terms
3. **RAG Integration**: Transform search results into intelligent answers

Each step builds on the previous one, and you can stop at any level that meets your needs:
- Just need similarity search? Stop after Step 2
- Want full question-answering? Complete all three steps
- Need something custom? Modify any pipeline to fit your requirements

### Key Takeaways

**Vector embeddings are powerful but focused**: They excel at finding semantic similarity but require the right model choice and use case.

**Example-based search changes user behavior**: When people can search by pasting examples, they find content they couldn't discover with keywords alone.

**RAG is more than just search + AI**: The quality depends on your retrieval strategy, prompt engineering, and the documents in your index.

**Pipelines are composable**: You can mix traditional search (from Tutorial 1) with vector search, or use both in the same application.

**Start simple, enhance gradually**: Begin with basic vector search, then add RAG capabilities as your understanding of user needs develops.

### Next Steps

With these foundations, you can experiment with:
- Different embedding models for various domains (legal, medical, technical)
- Hybrid search combining keywords and vectors
- Multi-stage RAG with filtering and re-ranking
- Custom prompt strategies for different use cases
- Performance optimization for large-scale deployments

Remember: TalkPipe's pipeline approach means you can modify and test each component independently, making it easy to find the perfect configuration for your specific needs.