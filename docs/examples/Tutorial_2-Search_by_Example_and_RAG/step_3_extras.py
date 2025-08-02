from talkpipe.util.data_manipulation import extract_property
from talkpipe.chatterlang import register_segment
from talkpipe.pipe import field_segment

@register_segment("ragPrompt")
@field_segment()
def rag_prompt_segment(item):
    """
    Segment for creating a specialized prompt for RAG (Retrieval-Augmented Generation) tasks.
    
    This segment formats the input item into a prompt that can be used for RAG operations.
    """
    query = extract_property(item, "example", fail_on_missing=True)
    results = extract_property(item, "results", fail_on_missing=True)
    context_text = "\n\n".join([f"Title: {result.document['title']}\nContent: {result.document['content']}" for result in results])

    ans = f"""
    You are a helpful assistant. Your task is to answer the question based on the provided context.
    Answer the question as accurately as possible.  At the end of your answer, provide a list of 
    sources used to answer the question and list the names of technologies listed in the sources.

    Context: 
    {context_text}
    
    Question: 
    {query}
    """

    return ans