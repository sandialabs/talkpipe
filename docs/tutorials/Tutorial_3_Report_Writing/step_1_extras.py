from talkpipe.util.data_manipulation import extract_property
from talkpipe.chatterlang import register_segment
from talkpipe.pipe import field_segment

@register_segment("executiveSummaryPrompt")
@field_segment()
def executive_summary_prompt_segment(item):
    """
    Segment for creating a specialized prompt for executive summary generation.
    
    This segment formats the input item into a prompt that generates professional
    executive summaries with structured sections including key findings, technology
    highlights, and strategic implications.
    """
    topic = extract_property(item, "topic", fail_on_missing=True)
    results = extract_property(item, "results", fail_on_missing=True)
    
    # Create context from retrieved documents
    context_text = "\n\n".join([
        f"Title: {result.document['title']}\nContent: {result.document['content']}" 
        for result in results
    ])

    ans = f"""
    You are a professional business analyst and technical writer. Your task is to create 
    a comprehensive executive summary based on the provided documents about: {topic}

    Please create an executive summary with the following structure:

    # Executive Summary: {topic}

    ## Executive Overview
    Provide a 2-3 paragraph high-level synthesis of the key themes and most important 
    insights from the source documents. This should be suitable for C-level executives 
    who need to understand the strategic implications quickly.

    ## Key Findings
    List 4-6 bullet points highlighting the most critical discoveries, developments, 
    or insights from the analyzed documents. Focus on findings that have business 
    or strategic relevance.

    ## Technology Highlights
    Identify and briefly describe the specific technologies, innovations, or technical 
    developments mentioned in the source material. Include both current implementations 
    and emerging trends.

    ## Strategic Implications
    Explain what these findings mean for decision-makers. Include potential impacts on:
    - Market opportunities or threats
    - Competitive positioning
    - Investment considerations
    - Operational implications

    ## Sources Referenced
    List the titles of the source documents analyzed for this summary.

    Guidelines:
    - Keep the total summary between 500-750 words
    - Use professional business language appropriate for executives
    - Focus on actionable insights and strategic relevance
    - Ensure all claims are supported by the source material
    - Use clear headings and bullet points for readability

    Source Documents:
    {context_text}
    
    Topic for Analysis: {topic}
    """

    return ans