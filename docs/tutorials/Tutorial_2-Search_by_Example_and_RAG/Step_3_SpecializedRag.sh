###################################################################################
# This script demonstrates how to use Talkpipe to search by example and generate results using RAG (Retrieval-Augmented Generation).
# It allows users to input an example query, which is then converted into a vector
# using an LLM embedding model. The vector is used to search a vector index for similar
# documents, and the results are formatted and returned.
# 
# The pipeline is:
# 1. Read the example query from the user.
# 2. Make a defensive copy of the input data for browser compatibility.
# 3. Use the `llmEmbed` segment to convert the example into a vector.
# 4. Use the `searchVector` segment to search the vector index for similar documents
# 5. use ragPrompt to create a prompt from the query and the retrieve documents.
# 6. Use the `llmPrompt` segment to generate a final response using the LLM.
###################################################################################

export TALKPIPE_CHATTERLANG_SCRIPT='
    | copy
    | llmEmbed[field="example", source="ollama", model="mxbai-embed-large", append_as="vector"]
    | searchVector[vector_field="vector", path="./vector_index", all_results_at_once=True, append_as="results"]
    | ragPrompt
    | llmPrompt[source="ollama", model="llama3.2"]
'

chatterlang_serve --form-config story_by_example_ui.yml --load-module step_3_extras.py --display-property example --script CHATTERLANG_SCRIPT