###################################################################################
# Step 3: Multi-Format Report Generation
# This script creates reports in different formats and styles for various audiences.
# It demonstrates how the same underlying research can be presented as executive
# briefs, technical reports, client summaries, or presentation outlines.
#
# The pipeline is:
# 1. Read both the topic and desired format from the user.
# 2. Make a defensive copy of the input data for browser compatibility.
# 3. Use the `llmEmbed` segment to convert the topic into a vector.
# 4. Use the `searchVector` segment to retrieve relevant documents.
# 5. Use the custom `generateMultiFormatReport` segment to create format-specific content.
###################################################################################

export TALKPIPE_CHATTERLANG_SCRIPT='
    | copy
    | llmEmbed[field="topic", source="ollama", model="mxbai-embed-large", append_as="vector"]
    | searchVector[vector_field="vector", path="../Tutorial_2-Search_by_Example_and_RAG/vector_index", top_k=10, all_results_at_once=True, append_as="results"]
    | generateMultiFormatReport[source="ollama", model="llama3.2"]
'

chatterlang_serve --form-config multi_format_ui.yml --load-module step3_extras.py --display-property topic --script CHATTERLANG_SCRIPT