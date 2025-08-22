###################################################################################
# Step 1: Executive Summary Generation
# This script creates executive summaries from retrieved documents using RAG.
# It uses the same vector index from Tutorial 2 but focuses on generating
# structured, professional summaries rather than answering specific questions.
#
# The pipeline is:
# 1. Read the topic from the user through a web interface.
# 2. Make a defensive copy of the input data for browser compatibility.
# 3. Use the `llmEmbed` segment to convert the topic into a vector.
# 4. Use the `searchVector` segment to retrieve relevant documents.
# 5. Use the custom `executiveSummaryPrompt` segment to structure the content.
# 6. Generate a professional executive summary using the LLM.
###################################################################################

export TALKPIPE_CHATTERLANG_SCRIPT='
    | copy  
    | llmEmbed[field="topic", source="ollama", model="mxbai-embed-large", append_as="vector"]
    | searchVector[vector_field="vector", path="../Tutorial_2-Search_by_Example_and_RAG/vector_index", all_results_at_once=True, append_as="results"]
    | executiveSummaryPrompt
    | llmPrompt[source="ollama", model="llama3.2"]
'

chatterlang_serve --form-config report_topic_ui.yml --load-module step_1_extras.py --display-property topic --script CHATTERLANG_SCRIPT