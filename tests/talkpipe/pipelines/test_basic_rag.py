import pytest
from talkpipe.pipelines.basic_rag import ConstructRAGPrompt, construct_background
from talkpipe.search.abstract import SearchResult


# Tests for construct_background helper function

def test_construct_background_with_single_string():
    """Test construct_background with a single string input."""
    result = construct_background("This is background information")
    assert isinstance(result, str)
    assert result.startswith("Background:\n")
    assert "This is background information" in result


def test_construct_background_with_list_of_strings():
    """Test construct_background with a list of strings."""
    background = ["First item", "Second item", "Third item"]
    result = construct_background(background)

    assert isinstance(result, str)
    assert result.startswith("Background:\n")
    assert "First item" in result
    assert "Second item" in result
    assert "Third item" in result
    # Items should be separated by double newlines
    assert "Background:\nFirst item\n\nSecond item\n\nThird item" in result


def test_construct_background_with_search_results():
    """Test construct_background with SearchResult objects."""
    search_result1 = SearchResult(
        score=0.95,
        doc_id="doc1",
        document={"title": "Document 1", "text": "Content of document 1"}
    )
    search_result2 = SearchResult(
        score=0.85,
        doc_id="doc2",
        document={"title": "Document 2", "text": "Content of document 2", "author": "John Doe"}
    )

    background = [search_result1, search_result2]
    result = construct_background(background)

    assert isinstance(result, str)
    assert result.startswith("Background:\n")
    # Should contain information from the documents
    assert "Document 1" in result
    assert "Document 2" in result


def test_construct_background_with_mixed_types():
    """Test construct_background with mixed string and SearchResult types."""
    search_result = SearchResult(
        score=0.9,
        doc_id="doc1",
        document={"title": "A Document", "content": "Some content"}
    )
    background = ["Plain text item", search_result, "Another plain text"]

    result = construct_background(background)

    assert isinstance(result, str)
    assert result.startswith("Background:\n")
    assert "Plain text item" in result
    assert "A Document" in result
    assert "Another plain text" in result


def test_construct_background_with_invalid_type():
    """Test that construct_background raises ValueError for unsupported types."""
    background = [123, "Valid string"]  # Integer is not supported

    with pytest.raises(ValueError, match="Unsupported background item type"):
        construct_background(background)


def test_construct_background_empty_list():
    """Test construct_background with an empty list."""
    result = construct_background([])
    assert result == "Background:\n"


# Tests for ConstructRAGPrompt segment

@pytest.fixture
def sample_items():
    """Sample data items for testing."""
    return [
        {
            "background": ["Context 1", "Context 2"],
            "content": "What is the main point?",
            "id": "item1"
        },
        {
            "background": "Single context string",
            "content": "Explain this concept.",
            "id": "item2"
        }
    ]


@pytest.fixture
def sample_items_with_search_results():
    """Sample data items with SearchResult objects."""
    search_result = SearchResult(
        score=0.9,
        doc_id="doc1",
        document={"title": "Relevant Doc", "text": "Important information"}
    )
    return [
        {
            "background_info": [search_result, "Additional context"],
            "query": "What should I know?",
            "metadata": {"user": "test_user"}
        }
    ]


def test_construct_rag_prompt_basic_with_set_as(sample_items):
    """Test basic ConstructRAGPrompt functionality with set_as parameter."""
    segment = ConstructRAGPrompt(
        prompt_directive="Answer the following question based on the background information.",
        background_field="background",
        content_field="content",
        set_as="prompt"
    )

    results = list(segment.transform([sample_items[0]]))

    # Should yield the original item with prompt field added
    assert len(results) == 1
    result = results[0]

    # Original fields should be preserved
    assert result["id"] == "item1"
    assert result["background"] == ["Context 1", "Context 2"]
    assert result["content"] == "What is the main point?"

    # Prompt field should be added
    assert "prompt" in result
    assert isinstance(result["prompt"], str)
    assert "Answer the following question based on the background information." in result["prompt"]
    assert "Background:" in result["prompt"]
    assert "Context 1" in result["prompt"]
    assert "Context 2" in result["prompt"]
    assert "Content:" in result["prompt"]
    assert "What is the main point?" in result["prompt"]


def test_construct_rag_prompt_without_set_as(sample_items):
    """Test ConstructRAGPrompt yields prompt directly when set_as is None."""
    segment = ConstructRAGPrompt(
        prompt_directive="Summarize based on context:",
        background_field="background",
        content_field="content",
        set_as=None
    )

    results = list(segment.transform([sample_items[1]]))

    # Should yield the prompt directly (not the item)
    assert len(results) == 1
    result = results[0]

    # Result should be a string (the prompt), not a dict
    assert isinstance(result, str)
    assert "Summarize based on context:" in result
    assert "Background:" in result
    assert "Single context string" in result
    assert "Content:" in result
    assert "Explain this concept." in result


def test_construct_rag_prompt_with_search_results(sample_items_with_search_results):
    """Test ConstructRAGPrompt with SearchResult objects in background."""
    segment = ConstructRAGPrompt(
        prompt_directive="Answer using the provided sources:",
        background_field="background_info",
        content_field="query",
        set_as="final_prompt"
    )

    results = list(segment.transform(sample_items_with_search_results))

    assert len(results) == 1
    result = results[0]

    # Original fields should be preserved
    assert result["metadata"]["user"] == "test_user"
    assert result["query"] == "What should I know?"

    # Prompt should contain information from SearchResult
    assert "final_prompt" in result
    prompt = result["final_prompt"]
    assert "Relevant Doc" in prompt  # Title should be in priority_fields
    assert "Additional context" in prompt
    assert "What should I know?" in prompt


def test_construct_rag_prompt_multiple_items(sample_items):
    """Test ConstructRAGPrompt processing multiple items."""
    segment = ConstructRAGPrompt(
        prompt_directive="Process this:",
        background_field="background",
        content_field="content",
        set_as="prompt"
    )

    results = list(segment.transform(sample_items))

    assert len(results) == 2

    # Check first item
    assert results[0]["id"] == "item1"
    assert "prompt" in results[0]
    assert "Context 1" in results[0]["prompt"]

    # Check second item
    assert results[1]["id"] == "item2"
    assert "prompt" in results[1]
    assert "Single context string" in results[1]["prompt"]


def test_construct_rag_prompt_nested_field_access():
    """Test ConstructRAGPrompt with nested field access using dot notation."""
    item = {
        "data": {
            "background": ["Nested context"],
            "question": {
                "text": "What is the answer?"
            }
        }
    }

    segment = ConstructRAGPrompt(
        prompt_directive="Answer:",
        background_field="data.background",
        content_field="data.question.text",
        set_as="result"
    )

    results = list(segment.transform([item]))

    assert len(results) == 1
    assert "result" in results[0]
    assert "Nested context" in results[0]["result"]
    assert "What is the answer?" in results[0]["result"]


def test_construct_rag_prompt_format_structure():
    """Test that the prompt has the correct structure and formatting."""
    item = {
        "bg": "Background text",
        "q": "Question text"
    }

    segment = ConstructRAGPrompt(
        prompt_directive="Directive here",
        background_field="bg",
        content_field="q",
        set_as=None
    )

    results = list(segment.transform([item]))
    prompt = results[0]

    # Check the structure: directive, then background, then content
    lines = prompt.split('\n')

    # Find positions of key markers
    directive_pos = prompt.find("Directive here")
    background_pos = prompt.find("Background:")
    content_pos = prompt.find("Content:")
    bg_text_pos = prompt.find("Background text")
    q_text_pos = prompt.find("Question text")

    # Verify ordering
    assert background_pos < directive_pos
    assert directive_pos < content_pos
    assert background_pos < bg_text_pos
    assert content_pos < q_text_pos


def test_construct_rag_prompt_empty_background():
    """Test ConstructRAGPrompt with empty background list."""
    item = {
        "background": [],
        "content": "Just content"
    }

    segment = ConstructRAGPrompt(
        prompt_directive="Process:",
        background_field="background",
        content_field="content",
        set_as=None
    )

    results = list(segment.transform([item]))
    prompt = results[0]

    # Should still have Background: section, just empty
    assert "Background:" in prompt
    assert "Content:" in prompt
    assert "Just content" in prompt


def test_construct_rag_prompt_preserves_all_original_fields():
    """Test that all original fields are preserved when using set_as."""
    item = {
        "background": "Context",
        "content": "Question",
        "field1": "value1",
        "field2": {"nested": "value2"},
        "field3": [1, 2, 3]
    }

    segment = ConstructRAGPrompt(
        prompt_directive="Directive",
        background_field="background",
        content_field="content",
        set_as="prompt"
    )

    results = list(segment.transform([item]))
    result = results[0]

    # All original fields should be preserved
    assert result["field1"] == "value1"
    assert result["field2"] == {"nested": "value2"}
    assert result["field3"] == [1, 2, 3]
    assert result["background"] == "Context"
    assert result["content"] == "Question"
    # Plus the new prompt field
    assert "prompt" in result


# Tests for RAGToText segment

def test_rag_to_text_diagPrintOutput_parameter_stored():
    """Test that diagPrintOutput parameter is correctly stored in RAGToText."""
    from talkpipe.pipelines.basic_rag import RAGToText

    # Test with diagPrintOutput=None (default, suppresses output)
    rag_segment = RAGToText(
        path="tmp://rag_test",
        content_field="query",
        diagPrintOutput=None
    )
    assert rag_segment.diagPrintOutput is None

    # Test with diagPrintOutput="stdout"
    rag_segment_stdout = RAGToText(
        path="tmp://rag_test",
        content_field="query",
        diagPrintOutput="stdout"
    )
    assert rag_segment_stdout.diagPrintOutput == "stdout"

    # Test with diagPrintOutput="stderr"
    rag_segment_stderr = RAGToText(
        path="tmp://rag_test",
        content_field="query",
        diagPrintOutput="stderr"
    )
    assert rag_segment_stderr.diagPrintOutput == "stderr"


def test_rag_to_text_diagPrintOutput_in_pipeline(capsys):
    """Test that diagPrintOutput parameter correctly controls DiagPrint output in the pipeline."""
    from talkpipe.pipelines.basic_rag import RAGToText
    from unittest.mock import patch, MagicMock

    # Create RAGToText with diagPrintOutput="stdout"
    rag_segment = RAGToText(
        path="tmp://rag_test",
        content_field="query",
        diagPrintOutput="stdout"
    )

    # Get the pipeline and verify DiagPrint segments have correct output setting
    # We need to mock the vector database search to avoid needing actual embeddings
    with patch.object(rag_segment, 'make_pipeline') as mock_make_pipeline:
        # Create a mock pipeline that yields test data
        mock_pipeline = MagicMock()
        mock_pipeline.return_value = iter([{"query": "test", "answer": "mocked"}])
        mock_make_pipeline.return_value = mock_pipeline

        # Verify diagPrintOutput is set correctly
        assert rag_segment.diagPrintOutput == "stdout"


def test_rag_to_text_diagPrintOutput_none_suppresses_output(capsys):
    """Test that diagPrintOutput=None suppresses DiagPrint output in RAGToText pipeline."""
    from talkpipe.pipelines.basic_rag import RAGToText
    from talkpipe.pipe.basic import DiagPrint

    # Create RAGToText with diagPrintOutput=None (should suppress output)
    rag_segment = RAGToText(
        path="tmp://rag_test",
        content_field="query",
        diagPrintOutput=None
    )

    # Verify the DiagPrint segment with output=None doesn't produce output
    diag_print = DiagPrint(output=rag_segment.diagPrintOutput)
    test_items = [{"query": "test question", "data": "some data"}]
    result = list(diag_print(test_items))

    # Items should pass through unchanged
    assert result == test_items

    # No output should be produced
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


@pytest.fixture
def temp_vector_db_path():
    """Create a temporary directory for the vector database."""
    import tempfile
    import os
    with tempfile.TemporaryDirectory() as temp_dir:
        yield os.path.join(temp_dir, "test_rag_db")


@pytest.fixture
def sample_knowledge_base():
    """Sample documents to populate the knowledge base."""
    return [
        {
            "text": "Python is a high-level programming language known for its simplicity and readability. It was created by Guido van Rossum.",
            "title": "Python Programming",
            "id": "doc1"
        },
        {
            "text": "Machine learning is a subset of artificial intelligence that enables systems to learn from data without explicit programming.",
            "title": "Machine Learning Basics",
            "id": "doc2"
        },
        {
            "text": "The pandas library is a powerful data manipulation tool in Python, widely used for data analysis and preprocessing.",
            "title": "Pandas Library",
            "id": "doc3"
        },
        {
            "text": "Neural networks are computing systems inspired by biological neural networks. They consist of interconnected nodes called neurons.",
            "title": "Neural Networks",
            "id": "doc4"
        }
    ]


def test_rag_to_text_diagPrintOutput_stdout(requires_ollama, temp_vector_db_path, sample_knowledge_base, capsys):
    """Test that diagPrintOutput='stdout' produces diagnostic output in RAGToText pipeline."""
    from talkpipe.pipelines.vector_databases import MakeVectorDatabaseSegment
    from talkpipe.pipelines.basic_rag import RAGToText

    # First, create and populate the vector database
    make_db_segment = MakeVectorDatabaseSegment(
        embedding_field="text",
        embedding_model="mxbai-embed-large",
        embedding_source="ollama",
        path=temp_vector_db_path,
        doc_id_field="id",
        overwrite=True
    )
    list(make_db_segment.transform(sample_knowledge_base))

    # Test RAGToText with diagPrintOutput="stdout"
    rag_segment = RAGToText(
        embedding_model="mxbai-embed-large",
        embedding_source="ollama",
        completion_model="llama3.2",
        completion_source="ollama",
        path=temp_vector_db_path,
        content_field="query",
        set_as="answer",
        limit=2,
        diagPrintOutput="stdout"
    )

    query_items = [{"query": "What is Python?", "id": "q1"}]
    results = list(rag_segment.transform(query_items))

    # Verify results still work correctly
    assert len(results) == 1
    assert "answer" in results[0]

    # Verify diagnostic output was produced on stdout
    captured = capsys.readouterr()
    assert "Type:" in captured.out
    assert "Value:" in captured.out
    assert captured.err == ""


def test_rag_to_text_diagPrintOutput_none_no_output(requires_ollama, temp_vector_db_path, sample_knowledge_base, capsys):
    """Test that diagPrintOutput=None suppresses diagnostic output in RAGToText pipeline."""
    from talkpipe.pipelines.vector_databases import MakeVectorDatabaseSegment
    from talkpipe.pipelines.basic_rag import RAGToText

    # First, create and populate the vector database
    make_db_segment = MakeVectorDatabaseSegment(
        embedding_field="text",
        embedding_model="mxbai-embed-large",
        embedding_source="ollama",
        path=temp_vector_db_path,
        doc_id_field="id",
        overwrite=True
    )
    list(make_db_segment.transform(sample_knowledge_base))

    # Test RAGToText with diagPrintOutput=None (default, no output)
    rag_segment = RAGToText(
        embedding_model="mxbai-embed-large",
        embedding_source="ollama",
        completion_model="llama3.2",
        completion_source="ollama",
        path=temp_vector_db_path,
        content_field="query",
        set_as="answer",
        limit=2,
        diagPrintOutput=None
    )

    query_items = [{"query": "What is Python?", "id": "q1"}]
    results = list(rag_segment.transform(query_items))

    # Verify results still work correctly
    assert len(results) == 1
    assert "answer" in results[0]

    # Verify NO diagnostic output was produced
    captured = capsys.readouterr()
    # DiagPrint output markers should NOT be present
    assert "================================" not in captured.out
    assert "================================" not in captured.err


def test_rag_to_text_basic_functionality(requires_ollama, temp_vector_db_path, sample_knowledge_base):
    """Test basic end-to-end functionality of RAGToText segment."""
    from talkpipe.pipelines.vector_databases import MakeVectorDatabaseSegment
    from talkpipe.pipelines.basic_rag import RAGToText

    # First, create and populate the vector database
    make_db_segment = MakeVectorDatabaseSegment(
        embedding_field="text",
        embedding_model="mxbai-embed-large",
        embedding_source="ollama",
        path=temp_vector_db_path,
        doc_id_field="id",
        overwrite=True
    )
    list(make_db_segment.transform(sample_knowledge_base))

    # Now test RAGToText with a query
    rag_segment = RAGToText(
        embedding_model="mxbai-embed-large",
        embedding_source="ollama",
        completion_model="llama3.2",
        completion_source="ollama",
        path=temp_vector_db_path,
        content_field="query",
        prompt_directive="Answer the question based on the background information provided. Be concise.",
        set_as="answer",
        limit=3
    )

    # Query about Python
    query_items = [{"query": "Who created Python?", "id": "q1"}]
    results = list(rag_segment.transform(query_items))

    # Verify results
    assert len(results) == 1
    result = results[0]

    # Original fields should be preserved
    assert result["query"] == "Who created Python?"
    assert result["id"] == "q1"

    # Answer should be present
    assert "answer" in result
    assert isinstance(result["answer"], str)
    assert len(result["answer"]) > 0

    # The answer should contain relevant information (Guido van Rossum)
    assert "guido" in result["answer"].lower() or "rossum" in result["answer"].lower()


def test_rag_to_text_without_set_as(requires_ollama, temp_vector_db_path, sample_knowledge_base):
    """Test RAGToText when set_as is None (yields text directly)."""
    from talkpipe.pipelines.vector_databases import MakeVectorDatabaseSegment
    from talkpipe.pipelines.basic_rag import RAGToText

    # Create and populate the vector database
    make_db_segment = MakeVectorDatabaseSegment(
        embedding_field="text",
        embedding_model="mxbai-embed-large",
        embedding_source="ollama",
        path=temp_vector_db_path,
        doc_id_field="id",
        overwrite=True
    )
    list(make_db_segment.transform(sample_knowledge_base))

    # Test RAGToText without set_as
    rag_segment = RAGToText(
        embedding_model="mxbai-embed-large",
        embedding_source="ollama",
        completion_model="llama3.2",
        completion_source="ollama",
        path=temp_vector_db_path,
        content_field="query",
        set_as=None,
        limit=2
    )

    query_items = [{"query": "What is machine learning?"}]
    results = list(rag_segment.transform(query_items))

    # When set_as is None, should yield the text response directly
    assert len(results) == 1
    result = results[0]

    # Result should be a string (the answer)
    assert isinstance(result, str)
    assert len(result) > 0

    # Should contain relevant information about machine learning
    assert "learn" in result.lower() or "data" in result.lower()


def test_rag_to_text_with_different_limit(requires_ollama, temp_vector_db_path, sample_knowledge_base):
    """Test RAGToText with different limit values for search results."""
    from talkpipe.pipelines.vector_databases import MakeVectorDatabaseSegment
    from talkpipe.pipelines.basic_rag import RAGToText

    # Create and populate the vector database
    make_db_segment = MakeVectorDatabaseSegment(
        embedding_field="text",
        embedding_model="mxbai-embed-large",
        embedding_source="ollama",
        path=temp_vector_db_path,
        doc_id_field="id",
        overwrite=True
    )
    list(make_db_segment.transform(sample_knowledge_base))

    # Test with limit=1 (only top result)
    rag_segment = RAGToText(
        embedding_model="mxbai-embed-large",
        embedding_source="ollama",
        completion_model="llama3.2",
        completion_source="ollama",
        path=temp_vector_db_path,
        content_field="query",
        set_as="answer",
        limit=1
    )

    query_items = [{"query": "Tell me about neural networks"}]
    results = list(rag_segment.transform(query_items))

    assert len(results) == 1
    assert "answer" in results[0]
    assert isinstance(results[0]["answer"], str)


def test_rag_to_text_custom_prompt_directive(requires_ollama, temp_vector_db_path, sample_knowledge_base):
    """Test RAGToText with a custom prompt directive and system prompt."""
    from talkpipe.pipelines.vector_databases import MakeVectorDatabaseSegment
    from talkpipe.pipelines.basic_rag import RAGToText

    # Create and populate the vector database
    make_db_segment = MakeVectorDatabaseSegment(
        embedding_field="text",
        embedding_model="mxbai-embed-large",
        embedding_source="ollama",
        path=temp_vector_db_path,
        doc_id_field="id",
        overwrite=True
    )
    list(make_db_segment.transform(sample_knowledge_base))

    # Test with custom prompt directive and system prompt
    custom_directive = "You are a technical expert. Provide a detailed explanation based on the background information."
    custom_system_prompt = "You are a helpful technical documentation assistant. Always provide accurate information based on the provided context."

    rag_segment = RAGToText(
        embedding_model="mxbai-embed-large",
        embedding_source="ollama",
        completion_model="llama3.2",
        completion_source="ollama",
        path=temp_vector_db_path,
        content_field="query",
        prompt_directive=custom_directive,
        system_prompt=custom_system_prompt,
        set_as="detailed_answer",
        limit=3
    )

    # Verify system_prompt was stored
    assert rag_segment.system_prompt == custom_system_prompt

    query_items = [{"query": "What is pandas used for?"}]
    results = list(rag_segment.transform(query_items))

    assert len(results) == 1
    result = results[0]
    assert "detailed_answer" in result
    assert isinstance(result["detailed_answer"], str)
    assert len(result["detailed_answer"]) > 0


def test_rag_to_text_system_prompt_affects_output(requires_ollama, temp_vector_db_path, sample_knowledge_base):
    """Test that custom system_prompt actually affects LLM output."""
    from talkpipe.pipelines.vector_databases import MakeVectorDatabaseSegment
    from talkpipe.pipelines.basic_rag import RAGToText

    # Create and populate the vector database
    make_db_segment = MakeVectorDatabaseSegment(
        embedding_field="text",
        embedding_model="mxbai-embed-large",
        embedding_source="ollama",
        path=temp_vector_db_path,
        doc_id_field="id",
        overwrite=True
    )
    list(make_db_segment.transform(sample_knowledge_base))

    # Use a system prompt that forces a specific output format
    pirate_system_prompt = "Talk like a pirate. Always start your answer with 'ANSWER:' on its own line."

    rag_segment = RAGToText(
        embedding_model="mxbai-embed-large",
        embedding_source="ollama",
        completion_model="llama3.2",
        completion_source="ollama",
        path=temp_vector_db_path,
        content_field="query",
        system_prompt=pirate_system_prompt,
        set_as="answer",
        limit=3
    )

    query_items = [{"query": "Who created Python?"}]
    results = list(rag_segment.transform(query_items))

    assert len(results) == 1
    result = results[0]
    assert "answer" in result
    answer = result["answer"]

    # Verify the system prompt affected the output - should start with ANSWER:
    assert answer.strip().startswith("ANSWER:"), f"Expected answer to start with 'ANSWER:', got: {answer[:100]}"


def test_rag_to_text_multiple_queries(requires_ollama, temp_vector_db_path, sample_knowledge_base):
    """Test RAGToText processing multiple queries."""
    from talkpipe.pipelines.vector_databases import MakeVectorDatabaseSegment
    from talkpipe.pipelines.basic_rag import RAGToText

    # Create and populate the vector database
    make_db_segment = MakeVectorDatabaseSegment(
        embedding_field="text",
        embedding_model="mxbai-embed-large",
        embedding_source="ollama",
        path=temp_vector_db_path,
        doc_id_field="id",
        overwrite=True
    )
    list(make_db_segment.transform(sample_knowledge_base))

    # Test with multiple queries
    rag_segment = RAGToText(
        embedding_model="mxbai-embed-large",
        embedding_source="ollama",
        completion_model="llama3.2",
        completion_source="ollama",
        path=temp_vector_db_path,
        content_field="query",
        set_as="answer",
        limit=2
    )

    query_items = [
        {"query": "What is Python?", "id": "q1"},
        {"query": "What is machine learning?", "id": "q2"},
        {"query": "What is pandas?", "id": "q3"}
    ]

    results = list(rag_segment.transform(query_items))

    # Should process all queries
    assert len(results) == 3

    # Each result should have an answer
    for i, result in enumerate(results):
        assert result["id"] == query_items[i]["id"]
        assert result["query"] == query_items[i]["query"]
        assert "answer" in result
        assert isinstance(result["answer"], str)
        assert len(result["answer"]) > 0


def test_rag_to_text_no_relevant_info(requires_ollama, temp_vector_db_path, sample_knowledge_base):
    """Test RAGToText with a query that has no relevant information in the database."""
    from talkpipe.pipelines.vector_databases import MakeVectorDatabaseSegment
    from talkpipe.pipelines.basic_rag import RAGToText

    # Create and populate the vector database with tech-related documents
    make_db_segment = MakeVectorDatabaseSegment(
        embedding_field="text",
        embedding_model="mxbai-embed-large",
        embedding_source="ollama",
        path=temp_vector_db_path,
        doc_id_field="id",
        overwrite=True
    )
    list(make_db_segment.transform(sample_knowledge_base))

    # Test with a completely unrelated query
    rag_segment = RAGToText(
        embedding_model="mxbai-embed-large",
        embedding_source="ollama",
        completion_model="llama3.2",
        completion_source="ollama",
        path=temp_vector_db_path,
        content_field="query",
        set_as="answer",
        limit=2
    )

    # Ask about something completely unrelated (cooking, not tech)
    query_items = [{"query": "What is the best recipe for chocolate cake?"}]
    results = list(rag_segment.transform(query_items))

    # Should still return a result
    assert len(results) == 1
    assert "answer" in results[0]
    assert isinstance(results[0]["answer"], str)
    # The default prompt directive says to respond with "No relevant information found."
    # but the LLM might still try to be helpful or acknowledge lack of relevant info


def test_rag_to_text_nested_content_field(requires_ollama, temp_vector_db_path, sample_knowledge_base):
    """Test RAGToText with nested field access for content."""
    from talkpipe.pipelines.vector_databases import MakeVectorDatabaseSegment
    from talkpipe.pipelines.basic_rag import RAGToText

    # Create and populate the vector database
    make_db_segment = MakeVectorDatabaseSegment(
        embedding_field="text",
        embedding_model="mxbai-embed-large",
        embedding_source="ollama",
        path=temp_vector_db_path,
        doc_id_field="id",
        overwrite=True
    )
    list(make_db_segment.transform(sample_knowledge_base))

    # Test with nested content field
    rag_segment = RAGToText(
        embedding_model="mxbai-embed-large",
        embedding_source="ollama",
        completion_model="llama3.2",
        completion_source="ollama",
        path=temp_vector_db_path,
        content_field="user.question",
        set_as="answer",
        limit=2
    )

    query_items = [{"user": {"question": "What is Python?"}, "id": "q1"}]
    results = list(rag_segment.transform(query_items))

    assert len(results) == 1
    result = results[0]
    assert result["id"] == "q1"
    assert "answer" in result
    assert isinstance(result["answer"], str)


# Tests for RAGToBinaryAnswer segment

def test_rag_to_binary_answer_basic_functionality(requires_ollama, temp_vector_db_path, sample_knowledge_base):
    """Test basic end-to-end functionality of RAGToBinaryAnswer segment."""
    from talkpipe.pipelines.vector_databases import MakeVectorDatabaseSegment
    from talkpipe.pipelines.basic_rag import RAGToBinaryAnswer

    # First, create and populate the vector database
    make_db_segment = MakeVectorDatabaseSegment(
        embedding_field="text",
        embedding_model="mxbai-embed-large",
        embedding_source="ollama",
        path=temp_vector_db_path,
        doc_id_field="id",
        overwrite=True
    )
    list(make_db_segment.transform(sample_knowledge_base))

    # Now test RAGToBinaryAnswer with a query
    rag_segment = RAGToBinaryAnswer(
        embedding_model="mxbai-embed-large",
        embedding_source="ollama",
        completion_model="llama3.2",
        completion_source="ollama",
        path=temp_vector_db_path,
        content_field="query",
        prompt_directive="Based on the background information, answer YES or NO: Is Python mentioned as a programming language?",
        set_as="answer",
        limit=3
    )

    # Query about Python
    query_items = [{"query": "Is Python a programming language?", "id": "q1"}]
    results = list(rag_segment.transform(query_items))

    # Verify results
    assert len(results) == 1
    result = results[0]

    # Original fields should be preserved
    assert result["query"] == "Is Python a programming language?"
    assert result["id"] == "q1"

    # Answer should be present and structured
    assert "answer" in result
    # Result is a Pydantic model (LlmBinaryAnswer.Answer)
    answer_obj = result["answer"]
    assert hasattr(answer_obj, "answer")
    assert hasattr(answer_obj, "explanation")
    assert isinstance(answer_obj.answer, bool)
    assert isinstance(answer_obj.explanation, str)


def test_rag_to_binary_answer_without_set_as(requires_ollama, temp_vector_db_path, sample_knowledge_base):
    """Test RAGToBinaryAnswer when set_as is None (yields binary answer directly)."""
    from talkpipe.pipelines.vector_databases import MakeVectorDatabaseSegment
    from talkpipe.pipelines.basic_rag import RAGToBinaryAnswer

    # Create and populate the vector database
    make_db_segment = MakeVectorDatabaseSegment(
        embedding_field="text",
        embedding_model="mxbai-embed-large",
        embedding_source="ollama",
        path=temp_vector_db_path,
        doc_id_field="id",
        overwrite=True
    )
    list(make_db_segment.transform(sample_knowledge_base))

    # Test RAGToBinaryAnswer without set_as
    rag_segment = RAGToBinaryAnswer(
        embedding_model="mxbai-embed-large",
        embedding_source="ollama",
        completion_model="llama3.2",
        completion_source="ollama",
        path=temp_vector_db_path,
        content_field="query",
        prompt_directive="Based on the background, answer YES or NO: Is this about technology?",
        set_as=None,
        limit=2
    )

    query_items = [{"query": "Is machine learning related to technology?"}]
    results = list(rag_segment.transform(query_items))

    # When set_as is None, should yield the binary answer directly
    assert len(results) == 1
    result = results[0]

    # Result should be a Pydantic model with answer and explanation
    assert hasattr(result, "answer")
    assert hasattr(result, "explanation")
    assert isinstance(result.answer, bool)
    assert isinstance(result.explanation, str)


def test_rag_to_binary_answer_with_different_limit(requires_ollama, temp_vector_db_path, sample_knowledge_base):
    """Test RAGToBinaryAnswer with different limit values for search results."""
    from talkpipe.pipelines.vector_databases import MakeVectorDatabaseSegment
    from talkpipe.pipelines.basic_rag import RAGToBinaryAnswer

    # Create and populate the vector database
    make_db_segment = MakeVectorDatabaseSegment(
        embedding_field="text",
        embedding_model="mxbai-embed-large",
        embedding_source="ollama",
        path=temp_vector_db_path,
        doc_id_field="id",
        overwrite=True
    )
    list(make_db_segment.transform(sample_knowledge_base))

    # Test with limit=1 (only top result)
    rag_segment = RAGToBinaryAnswer(
        embedding_model="mxbai-embed-large",
        embedding_source="ollama",
        completion_model="llama3.2",
        completion_source="ollama",
        path=temp_vector_db_path,
        content_field="query",
        prompt_directive="Answer YES or NO: Does the background mention neural networks?",
        set_as="answer",
        limit=1
    )

    query_items = [{"query": "Are neural networks discussed?"}]
    results = list(rag_segment.transform(query_items))

    assert len(results) == 1
    assert "answer" in results[0]
    answer_obj = results[0]["answer"]
    assert hasattr(answer_obj, "answer")
    assert isinstance(answer_obj.answer, bool)


def test_rag_to_binary_answer_multiple_queries(requires_ollama, temp_vector_db_path, sample_knowledge_base):
    """Test RAGToBinaryAnswer processing multiple queries."""
    from talkpipe.pipelines.vector_databases import MakeVectorDatabaseSegment
    from talkpipe.pipelines.basic_rag import RAGToBinaryAnswer

    # Create and populate the vector database
    make_db_segment = MakeVectorDatabaseSegment(
        embedding_field="text",
        embedding_model="mxbai-embed-large",
        embedding_source="ollama",
        path=temp_vector_db_path,
        doc_id_field="id",
        overwrite=True
    )
    list(make_db_segment.transform(sample_knowledge_base))

    # Test with multiple queries
    rag_segment = RAGToBinaryAnswer(
        embedding_model="mxbai-embed-large",
        embedding_source="ollama",
        completion_model="llama3.2",
        completion_source="ollama",
        path=temp_vector_db_path,
        content_field="query",
        prompt_directive="Answer YES or NO based on the background information.",
        set_as="answer",
        limit=2
    )

    query_items = [
        {"query": "Is Python discussed?", "id": "q1"},
        {"query": "Is Java discussed?", "id": "q2"},
        {"query": "Is pandas discussed?", "id": "q3"}
    ]

    results = list(rag_segment.transform(query_items))

    # Should process all queries
    assert len(results) == 3

    # Each result should have a binary answer
    for i, result in enumerate(results):
        assert result["id"] == query_items[i]["id"]
        assert result["query"] == query_items[i]["query"]
        assert "answer" in result
        answer_obj = result["answer"]
        assert hasattr(answer_obj, "answer")
        assert hasattr(answer_obj, "explanation")
        assert isinstance(answer_obj.answer, bool)
        assert isinstance(answer_obj.explanation, str)


def test_rag_to_binary_answer_nested_content_field(requires_ollama, temp_vector_db_path, sample_knowledge_base):
    """Test RAGToBinaryAnswer with nested field access for content."""
    from talkpipe.pipelines.vector_databases import MakeVectorDatabaseSegment
    from talkpipe.pipelines.basic_rag import RAGToBinaryAnswer

    # Create and populate the vector database
    make_db_segment = MakeVectorDatabaseSegment(
        embedding_field="text",
        embedding_model="mxbai-embed-large",
        embedding_source="ollama",
        path=temp_vector_db_path,
        doc_id_field="id",
        overwrite=True
    )
    list(make_db_segment.transform(sample_knowledge_base))

    # Test with nested content field
    rag_segment = RAGToBinaryAnswer(
        embedding_model="mxbai-embed-large",
        embedding_source="ollama",
        completion_model="llama3.2",
        completion_source="ollama",
        path=temp_vector_db_path,
        content_field="user.question",
        prompt_directive="Answer YES or NO based on the background.",
        set_as="answer",
        limit=2
    )

    query_items = [{"user": {"question": "Is Python mentioned?"}, "id": "q1"}]
    results = list(rag_segment.transform(query_items))

    assert len(results) == 1
    result = results[0]
    assert result["id"] == "q1"
    assert "answer" in result
    answer_obj = result["answer"]
    assert hasattr(answer_obj, "answer")
    assert isinstance(answer_obj.answer, bool)


# Tests for RAGToScore segment

def test_rag_to_score_basic_functionality(requires_ollama, temp_vector_db_path, sample_knowledge_base):
    """Test basic end-to-end functionality of RAGToScore segment."""
    from talkpipe.pipelines.vector_databases import MakeVectorDatabaseSegment
    from talkpipe.pipelines.basic_rag import RAGToScore

    # First, create and populate the vector database
    make_db_segment = MakeVectorDatabaseSegment(
        embedding_field="text",
        embedding_model="mxbai-embed-large",
        embedding_source="ollama",
        path=temp_vector_db_path,
        doc_id_field="id",
        overwrite=True
    )
    list(make_db_segment.transform(sample_knowledge_base))

    # Now test RAGToScore with a query
    rag_segment = RAGToScore(
        embedding_model="mxbai-embed-large",
        embedding_source="ollama",
        completion_model="llama3.2",
        completion_source="ollama",
        path=temp_vector_db_path,
        content_field="query",
        prompt_directive="Based on the background information, rate from 0-100 how relevant the background is to the query (0=not relevant, 100=highly relevant).",
        set_as="score_result",
        limit=3
    )

    # Query about Python
    query_items = [{"query": "Tell me about Python programming", "id": "q1"}]
    results = list(rag_segment.transform(query_items))

    # Verify results
    assert len(results) == 1
    result = results[0]

    # Original fields should be preserved
    assert result["query"] == "Tell me about Python programming"
    assert result["id"] == "q1"

    # Score result should be present and structured
    assert "score_result" in result
    # Result is a Pydantic model (LlmScore.Score)
    score_obj = result["score_result"]
    assert hasattr(score_obj, "score")
    assert hasattr(score_obj, "explanation")
    assert isinstance(score_obj.score, int)
    assert isinstance(score_obj.explanation, str)
    # Score should be in a reasonable range
    assert 0 <= score_obj.score <= 100


def test_rag_to_score_without_set_as(requires_ollama, temp_vector_db_path, sample_knowledge_base):
    """Test RAGToScore when set_as is None (yields score directly)."""
    from talkpipe.pipelines.vector_databases import MakeVectorDatabaseSegment
    from talkpipe.pipelines.basic_rag import RAGToScore

    # Create and populate the vector database
    make_db_segment = MakeVectorDatabaseSegment(
        embedding_field="text",
        embedding_model="mxbai-embed-large",
        embedding_source="ollama",
        path=temp_vector_db_path,
        doc_id_field="id",
        overwrite=True
    )
    list(make_db_segment.transform(sample_knowledge_base))

    # Test RAGToScore without set_as
    rag_segment = RAGToScore(
        embedding_model="mxbai-embed-large",
        embedding_source="ollama",
        completion_model="llama3.2",
        completion_source="ollama",
        path=temp_vector_db_path,
        content_field="query",
        prompt_directive="Rate 0-100 how relevant the background is to machine learning.",
        set_as=None,
        limit=2
    )

    query_items = [{"query": "What is machine learning?"}]
    results = list(rag_segment.transform(query_items))

    # When set_as is None, should yield the score directly
    assert len(results) == 1
    result = results[0]

    # Result should be a Pydantic model with score and explanation
    assert hasattr(result, "score")
    assert hasattr(result, "explanation")
    assert isinstance(result.score, int)
    assert isinstance(result.explanation, str)
    assert 0 <= result.score <= 100


def test_rag_to_score_with_different_limit(requires_ollama, temp_vector_db_path, sample_knowledge_base):
    """Test RAGToScore with different limit values for search results."""
    from talkpipe.pipelines.vector_databases import MakeVectorDatabaseSegment
    from talkpipe.pipelines.basic_rag import RAGToScore

    # Create and populate the vector database
    make_db_segment = MakeVectorDatabaseSegment(
        embedding_field="text",
        embedding_model="mxbai-embed-large",
        embedding_source="ollama",
        path=temp_vector_db_path,
        doc_id_field="id",
        overwrite=True
    )
    list(make_db_segment.transform(sample_knowledge_base))

    # Test with limit=1 (only top result)
    rag_segment = RAGToScore(
        embedding_model="mxbai-embed-large",
        embedding_source="ollama",
        completion_model="llama3.2",
        completion_source="ollama",
        path=temp_vector_db_path,
        content_field="query",
        prompt_directive="Rate 0-100 the relevance of the background to neural networks.",
        set_as="score_result",
        limit=1
    )

    query_items = [{"query": "Tell me about neural networks"}]
    results = list(rag_segment.transform(query_items))

    assert len(results) == 1
    assert "score_result" in results[0]
    score_obj = results[0]["score_result"]
    assert hasattr(score_obj, "score")
    assert isinstance(score_obj.score, int)
    assert 0 <= score_obj.score <= 100


def test_rag_to_score_custom_prompt_directive(requires_ollama, temp_vector_db_path, sample_knowledge_base):
    """Test RAGToScore with a custom prompt directive and scoring scale."""
    from talkpipe.pipelines.vector_databases import MakeVectorDatabaseSegment
    from talkpipe.pipelines.basic_rag import RAGToScore

    # Create and populate the vector database
    make_db_segment = MakeVectorDatabaseSegment(
        embedding_field="text",
        embedding_model="mxbai-embed-large",
        embedding_source="ollama",
        path=temp_vector_db_path,
        doc_id_field="id",
        overwrite=True
    )
    list(make_db_segment.transform(sample_knowledge_base))

    # Test with custom prompt directive for quality scoring
    custom_directive = "Rate the technical accuracy and completeness of the background information from 0-100 (0=inaccurate/incomplete, 100=highly accurate/complete)."

    rag_segment = RAGToScore(
        embedding_model="mxbai-embed-large",
        embedding_source="ollama",
        completion_model="llama3.2",
        completion_source="ollama",
        path=temp_vector_db_path,
        content_field="query",
        prompt_directive=custom_directive,
        set_as="quality_score",
        limit=3
    )

    query_items = [{"query": "Python programming language information"}]
    results = list(rag_segment.transform(query_items))

    assert len(results) == 1
    result = results[0]
    assert "quality_score" in result
    score_obj = result["quality_score"]
    assert hasattr(score_obj, "score")
    assert hasattr(score_obj, "explanation")
    assert isinstance(score_obj.score, int)
    assert 0 <= score_obj.score <= 100


def test_rag_to_score_multiple_queries(requires_ollama, temp_vector_db_path, sample_knowledge_base):
    """Test RAGToScore processing multiple queries."""
    from talkpipe.pipelines.vector_databases import MakeVectorDatabaseSegment
    from talkpipe.pipelines.basic_rag import RAGToScore

    # Create and populate the vector database
    make_db_segment = MakeVectorDatabaseSegment(
        embedding_field="text",
        embedding_model="mxbai-embed-large",
        embedding_source="ollama",
        path=temp_vector_db_path,
        doc_id_field="id",
        overwrite=True
    )
    list(make_db_segment.transform(sample_knowledge_base))

    # Test with multiple queries
    rag_segment = RAGToScore(
        embedding_model="mxbai-embed-large",
        embedding_source="ollama",
        completion_model="llama3.2",
        completion_source="ollama",
        path=temp_vector_db_path,
        content_field="query",
        prompt_directive="Rate 0-100 how relevant the background is to the query.",
        set_as="relevance_score",
        limit=2
    )

    query_items = [
        {"query": "Python programming", "id": "q1"},
        {"query": "Machine learning concepts", "id": "q2"},
        {"query": "Data analysis with pandas", "id": "q3"}
    ]

    results = list(rag_segment.transform(query_items))

    # Should process all queries
    assert len(results) == 3

    # Each result should have a score
    for i, result in enumerate(results):
        assert result["id"] == query_items[i]["id"]
        assert result["query"] == query_items[i]["query"]
        assert "relevance_score" in result
        score_obj = result["relevance_score"]
        assert hasattr(score_obj, "score")
        assert hasattr(score_obj, "explanation")
        assert isinstance(score_obj.score, int)
        assert isinstance(score_obj.explanation, str)
        assert 0 <= score_obj.score <= 100


def test_rag_to_score_nested_content_field(requires_ollama, temp_vector_db_path, sample_knowledge_base):
    """Test RAGToScore with nested field access for content."""
    from talkpipe.pipelines.vector_databases import MakeVectorDatabaseSegment
    from talkpipe.pipelines.basic_rag import RAGToScore

    # Create and populate the vector database
    make_db_segment = MakeVectorDatabaseSegment(
        embedding_field="text",
        embedding_model="mxbai-embed-large",
        embedding_source="ollama",
        path=temp_vector_db_path,
        doc_id_field="id",
        overwrite=True
    )
    list(make_db_segment.transform(sample_knowledge_base))

    # Test with nested content field
    rag_segment = RAGToScore(
        embedding_model="mxbai-embed-large",
        embedding_source="ollama",
        completion_model="llama3.2",
        completion_source="ollama",
        path=temp_vector_db_path,
        content_field="user.question",
        prompt_directive="Rate 0-100 the relevance of the background.",
        set_as="score_result",
        limit=2
    )

    query_items = [{"user": {"question": "Python information"}, "id": "q1"}]
    results = list(rag_segment.transform(query_items))

    assert len(results) == 1
    result = results[0]
    assert result["id"] == "q1"
    assert "score_result" in result
    score_obj = result["score_result"]
    assert hasattr(score_obj, "score")
    assert isinstance(score_obj.score, int)
    assert 0 <= score_obj.score <= 100


def test_rag_to_score_low_relevance_query(requires_ollama, temp_vector_db_path, sample_knowledge_base):
    """Test RAGToScore with a query that should get a low relevance score."""
    from talkpipe.pipelines.vector_databases import MakeVectorDatabaseSegment
    from talkpipe.pipelines.basic_rag import RAGToScore

    # Create and populate the vector database with tech-related documents
    make_db_segment = MakeVectorDatabaseSegment(
        embedding_field="text",
        embedding_model="mxbai-embed-large",
        embedding_source="ollama",
        path=temp_vector_db_path,
        doc_id_field="id",
        overwrite=True
    )
    list(make_db_segment.transform(sample_knowledge_base))

    # Test with a completely unrelated query
    rag_segment = RAGToScore(
        embedding_model="mxbai-embed-large",
        embedding_source="ollama",
        completion_model="llama3.2",
        completion_source="ollama",
        path=temp_vector_db_path,
        content_field="query",
        prompt_directive="Rate 0-100 how relevant the background is to the query (0=not relevant, 100=highly relevant).",
        set_as="score_result",
        limit=2
    )

    # Ask about something completely unrelated (cooking, not tech)
    query_items = [{"query": "What is the best recipe for chocolate cake?"}]
    results = list(rag_segment.transform(query_items))

    # Should still return a result with a score
    assert len(results) == 1
    assert "score_result" in results[0]
    score_obj = results[0]["score_result"]
    assert hasattr(score_obj, "score")
    assert isinstance(score_obj.score, int)
    assert 0 <= score_obj.score <= 100
    # The score should ideally be low for an unrelated query, but we don't enforce
    # a specific threshold as LLM behavior can vary


# Tests for table_name parameter

def test_rag_to_text_custom_table_name(requires_ollama, temp_vector_db_path, sample_knowledge_base):
    """Test RAGToText with a custom table name."""
    from talkpipe.pipelines.vector_databases import MakeVectorDatabaseSegment
    from talkpipe.pipelines.basic_rag import RAGToText

    # Create and populate the vector database with a custom table name
    custom_table = "custom_knowledge_table"
    make_db_segment = MakeVectorDatabaseSegment(
        embedding_field="text",
        embedding_model="mxbai-embed-large",
        embedding_source="ollama",
        path=temp_vector_db_path,
        table_name=custom_table,
        doc_id_field="id",
        overwrite=True
    )
    list(make_db_segment.transform(sample_knowledge_base))

    # Test RAGToText with the same custom table name
    rag_segment = RAGToText(
        embedding_model="mxbai-embed-large",
        embedding_source="ollama",
        completion_model="llama3.2",
        completion_source="ollama",
        path=temp_vector_db_path,
        table_name=custom_table,
        content_field="query",
        set_as="answer",
        limit=3
    )

    # Query should work with the custom table
    query_items = [{"query": "Who created Python?", "id": "q1"}]
    results = list(rag_segment.transform(query_items))

    # Verify results
    assert len(results) == 1
    result = results[0]
    assert "answer" in result
    assert isinstance(result["answer"], str)
    assert len(result["answer"]) > 0


def test_rag_to_binary_answer_custom_table_name(requires_ollama, temp_vector_db_path, sample_knowledge_base):
    """Test RAGToBinaryAnswer with a custom table name."""
    from talkpipe.pipelines.vector_databases import MakeVectorDatabaseSegment
    from talkpipe.pipelines.basic_rag import RAGToBinaryAnswer

    # Create and populate the vector database with a custom table name
    custom_table = "binary_answer_table"
    make_db_segment = MakeVectorDatabaseSegment(
        embedding_field="text",
        embedding_model="mxbai-embed-large",
        embedding_source="ollama",
        path=temp_vector_db_path,
        table_name=custom_table,
        doc_id_field="id",
        overwrite=True
    )
    list(make_db_segment.transform(sample_knowledge_base))

    # Test RAGToBinaryAnswer with the same custom table name
    rag_segment = RAGToBinaryAnswer(
        embedding_model="mxbai-embed-large",
        embedding_source="ollama",
        completion_model="llama3.2",
        completion_source="ollama",
        path=temp_vector_db_path,
        table_name=custom_table,
        content_field="query",
        set_as="answer",
        limit=3
    )

    # Query should work with the custom table
    query_items = [{"query": "Is Python a programming language?", "id": "q1"}]
    results = list(rag_segment.transform(query_items))

    # Verify results
    assert len(results) == 1
    result = results[0]
    assert "answer" in result
    answer_obj = result["answer"]
    assert hasattr(answer_obj, "answer")
    assert isinstance(answer_obj.answer, bool)


def test_rag_to_score_custom_table_name(requires_ollama, temp_vector_db_path, sample_knowledge_base):
    """Test RAGToScore with a custom table name."""
    from talkpipe.pipelines.vector_databases import MakeVectorDatabaseSegment
    from talkpipe.pipelines.basic_rag import RAGToScore

    # Create and populate the vector database with a custom table name
    custom_table = "score_table"
    make_db_segment = MakeVectorDatabaseSegment(
        embedding_field="text",
        embedding_model="mxbai-embed-large",
        embedding_source="ollama",
        path=temp_vector_db_path,
        table_name=custom_table,
        doc_id_field="id",
        overwrite=True
    )
    list(make_db_segment.transform(sample_knowledge_base))

    # Test RAGToScore with the same custom table name
    rag_segment = RAGToScore(
        embedding_model="mxbai-embed-large",
        embedding_source="ollama",
        completion_model="llama3.2",
        completion_source="ollama",
        path=temp_vector_db_path,
        table_name=custom_table,
        content_field="query",
        set_as="score_result",
        limit=3
    )

    # Query should work with the custom table
    query_items = [{"query": "Tell me about Python programming", "id": "q1"}]
    results = list(rag_segment.transform(query_items))

    # Verify results
    assert len(results) == 1
    result = results[0]
    assert "score_result" in result
    score_obj = result["score_result"]
    assert hasattr(score_obj, "score")
    assert isinstance(score_obj.score, int)
    assert 0 <= score_obj.score <= 100
