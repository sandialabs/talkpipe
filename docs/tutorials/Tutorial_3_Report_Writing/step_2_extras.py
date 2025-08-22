from talkpipe.llm.chat import LLMPrompt
from talkpipe.util.data_manipulation import extract_property
from talkpipe.chatterlang import register_segment
from talkpipe.pipe import field_segment


@register_segment("generateReportSectionPrompts")
@field_segment()
def generate_report_sections_segment(item):
    """
    Segment for generating multiple sections of a detailed analysis report.
    
    This segment creates individual sections that will be combined into a comprehensive
    report document. Each section focuses on a different aspect of the topic.
    """
    topic = extract_property(item, "topic", fail_on_missing=True)
    results = extract_property(item, "results", fail_on_missing=True)
    
    # Create context from retrieved documents
    context_text = "\n\n".join([
        f"Title: {result.document['title']}\nContent: {result.document['content']}" 
        for result in results
    ])
    
    # List of source titles for reference
    source_titles = [result.document['title'] for result in results]
    
    # Generate each section individually
    sections = {}
    
    # Introduction section
    intro_prompt = f"""
    Create an Introduction and Background section for a detailed analysis report about: {topic}
    
    This section should:
    - Provide context and background for the topic
    - Explain why this topic is important or relevant
    - Outline what the report will cover
    - Be 200-300 words
    - Use professional academic/business language
    
    Base your introduction on these source documents:
    {context_text}
    """
    
    # Technical analysis section  
    analysis_prompt = f"""
    Create a Detailed Analysis section for a report about: {topic}
    
    This section should:
    - Provide in-depth exploration of key themes and findings
    - Analyze trends, patterns, and significant developments
    - Include specific examples and details from the source material
    - Be 400-600 words
    - Maintain analytical objectivity
    
    Base your analysis on these source documents:
    {context_text}
    """
    
    # Technology deep dive section
    tech_prompt = f"""
    Create a Technology Deep Dive section for a report about: {topic}
    
    This section should:
    - Identify and explain specific technologies mentioned
    - Describe technical innovations and their significance
    - Explain how these technologies work and their applications
    - Be 300-400 words
    - Balance technical accuracy with accessibility
    
    Base your analysis on these source documents:
    {context_text}
    """
    
    # Future implications section
    future_prompt = f"""
    Create a Future Implications and Trends section for a report about: {topic}
    
    This section should:
    - Identify emerging trends and future directions
    - Discuss potential impacts and consequences
    - Consider both opportunities and challenges
    - Be 250-350 words
    - Be forward-looking while grounded in current evidence
    
    Base your analysis on these source documents:
    {context_text}
    """
    
    # Recommendations section
    recommendations_prompt = f"""
    Create a Recommendations and Next Steps section for a report about: {topic}
    
    This section should:
    - Provide actionable recommendations based on the analysis
    - Suggest areas for further investigation or development
    - Consider practical implementation considerations
    - Be 200-300 words
    - Be concrete and actionable
    
    Base your recommendations on these source documents:
    {context_text}
    """
    
    # Store all prompts for the next segment to process
    item['section_prompts'] = [
        ('Introduction', intro_prompt),
        ('Analysis', analysis_prompt),
        ('Technology', tech_prompt),
        ('Future', future_prompt),
        ('Recommendations', recommendations_prompt)
    ]
    item['source_titles'] = source_titles
    
    return item

@register_segment("generateDetailedReport")
@field_segment()
def format_detailed_report_segment(item, model=None, source=None, multi_turn=True):
    """
    Segment for formatting individual sections into a cohesive detailed report.
    
    This segment takes the section prompts and generates the final report by
    processing each section and combining them with proper formatting.
    """
    topic = extract_property(item, "topic", fail_on_missing=True)
    section_prompts = extract_property(item, "section_prompts", fail_on_missing=True)
    source_titles = extract_property(item, "source_titles", fail_on_missing=True)
    
    # Generate each section using the LLM
    llm = LLMPrompt(model=model, source=source, multi_turn=multi_turn, system_prompt="You are a professional report writer.")
    llm = llm.asFunction(single_in=True, single_out=True)
    sections_content = {}

    report = f"""Detailed Analysis Report: {topic}\n\n"""

    for section_name, prompt in section_prompts:
        # Generate content for this section
        section_result = llm(prompt)
        report += f"## {section_name}\n\n{section_result}\n\n"
        sections_content[section_name] = section_result

    report += f"""
## Sources Referenced
This report is based on analysis of the following source documents:
{chr(10).join([f"- {title}" for title in source_titles])}

---
*Report generated using TalkPipe RAG pipeline with vector similarity search and multi-section analysis.*
"""
    
    return report