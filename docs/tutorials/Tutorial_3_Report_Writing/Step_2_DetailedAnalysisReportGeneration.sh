###################################################################################
# Step 2: Detailed Analysis Report Generation
# This script creates comprehensive, multi-section reports from retrieved documents.
# It extends the executive summary approach to generate in-depth analysis documents
# with multiple sections, detailed exploration, and professional formatting.
#
# The pipeline is:
# 1. Read the topic from the user through the web interface.
# 2. Make a defensive copy of the input data for browser compatibility.
# 3. Use the `llmEmbed` segment to convert the topic into a vector.
# 4. Use the `searchVector` segment to retrieve relevant documents.
# 5. Use the custom `generateReportSections` segment to create multiple sections.
# 6. Use the `formatDetailedReport` segment to combine sections into a cohesive document.
###################################################################################

export TALKPIPE_CHATTERLANG_SCRIPT='
    | copy
    | llmEmbed[field="topic", source="ollama", model="mxbai-embed-large", append_as="vector"]
    | searchVector[vector_field="vector", path="../Tutorial_2-Search_by_Example_and_RAG/vector_index", top_k=10, all_results_at_once=True, append_as="results"]
    | generateReportSectionPrompts
    | generateDetailedReport[source="ollama", model="llama3.2"]
'

python -m talkpipe.app.chatterlang_serve --form-config report_topic_ui.yml --load-module step_2_extras.py --display-property topic --script CHATTERLANG_SCRIPT