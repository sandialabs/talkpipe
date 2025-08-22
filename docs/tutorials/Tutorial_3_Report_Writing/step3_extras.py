from talkpipe.llm.chat import LLMPrompt
from talkpipe.util.data_manipulation import extract_property
from talkpipe.chatterlang import register_segment
from talkpipe.pipe import field_segment

@register_segment("generateMultiFormatReport")
@field_segment()
def generate_multi_format_report_segment(item, source=None, model=None):
    """
    Segment for generating reports in different formats based on user selection.
    
    This segment creates format-specific reports from the same source material,
    adapting content, style, and structure for different audiences and use cases.
    """
    topic = extract_property(item, "topic", fail_on_missing=True)
    report_format = extract_property(item, "format", fail_on_missing=True)
    results = extract_property(item, "results", fail_on_missing=True)
    
    # Create context from retrieved documents
    context_text = "\n\n".join([
        f"Title: {result.document['title']}\nContent: {result.document['content']}" 
        for result in results
    ])
    
    # List of source titles for reference
    source_titles = [result.document['title'] for result in results]
    
    # Define format-specific prompts
    format_prompts = {
        "Executive Brief": f"""
        Create a 1-page Executive Brief about: {topic}
        
        Format requirements:
        - Maximum 400-500 words total
        - Executive summary (2-3 sentences)
        - Key insights (3-4 bullet points)
        - Strategic implications (2-3 bullet points)
        - Bottom-line recommendation (1-2 sentences)
        - Professional tone suitable for C-level executives
        - Focus on business impact and strategic relevance
        
        Source material:
        {context_text}
        """,
        
        "Technical Report": f"""
        Create a Technical Report about: {topic}
        
        Format requirements:
        - Detailed technical analysis (600-800 words)
        - Technical specifications and details
        - Implementation considerations
        - Performance metrics and benchmarks where applicable
        - Technical challenges and solutions
        - Future technical developments
        - Use appropriate technical terminology
        - Include specific examples from source material
        
        Source material:
        {context_text}
        """,
        
        "Client Summary": f"""
        Create a Client Summary about: {topic}
        
        Format requirements:
        - Accessible language for non-technical stakeholders
        - Clear explanation of concepts and benefits
        - Real-world applications and examples
        - Potential impact on client's business/interests
        - Easy-to-understand structure with clear headings
        - 400-600 words
        - Professional but approachable tone
        - Avoid technical jargon
        
        Source material:
        {context_text}
        """,

        "Research Memo": f"""
        Create a Research Memo about: {topic}
        
        Format requirements:
        - Academic-style analysis with proper structure
        - Literature review of source material
        - Methodology and analysis approach
        - Key findings with supporting evidence
        - Discussion of implications and significance
        - Areas for future research
        - Formal academic tone
        - Include references to source documents
        - 600-800 words
        
        Source material:
        {context_text}
        """,
        
        "Presentation Outline": f"""
        Create a Presentation Outline about: {topic}
        
        Format requirements:
        - Structured as talking points for a 15-20 minute presentation
        - Slide-by-slide outline with main points
        - Key messages and supporting details
        - Suggested visuals or examples
        - Strong opening and closing
        - Logical flow and transitions
        - Interactive elements or discussion points
        - Speaker notes where helpful
        
        Source material:
        {context_text}
        """
    }
    
    # Get the appropriate prompt for the selected format
    if report_format not in format_prompts:
        return f"Error: Unknown format '{report_format}'. Available formats: {', '.join(format_prompts.keys())}"
    
    selected_prompt = format_prompts[report_format]
    
    # Generate the report using the LLM
    llm = LLMPrompt(source=source, model=model)
    report_content = list(llm([{'content': selected_prompt}]))[0]

    formatted_report = f"""# {report_format}: {topic}

{report_content}

---

**Document Information:**
- Format: {report_format}
- Topic: {topic}
- Sources Analyzed: {len(source_titles)} documents
- Generated: Using TalkPipe multi-format reporting pipeline

**Source Documents:**
{chr(10).join([f"- {title}" for title in source_titles])}
"""
    
    return formatted_report