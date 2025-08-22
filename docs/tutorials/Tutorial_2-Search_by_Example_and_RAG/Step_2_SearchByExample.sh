###################################################################################
# Step 2: Search by Example and RAG
# This script allows users to search for indexed documents using an example query.
# It uses the Ollama embedding model to convert the example into a vector,
# which is then used to search a vector index.
# The results are formatted and printed to the console.
#
# The pipeline is:
# 1. Read the example query from the user.
# 2. Make a defensive copy of the input data.  This is especially important when
#    working with the endpoint api because the input data will be sent to the
#    browser.
# 3. Use the `llmEmbed` segment to convert the example into a vector.
# 4. Use the `searchVector` segment to search the vector index for similar documents.
# 5. Format the results using `formatItem` and print them.
###################################################################################

export TALKPIPE_CHATTERLANG_SCRIPT='    
    | copy
    | llmEmbed[field="example", source="ollama", model="mxbai-embed-large", append_as="vector"]
    | searchVector[vector_field="vector", path="./vector_index", top_k=10]
    | formatItem[field_list="document.title:Title, document.content:Content, score:Score"]
'

chatterlang_serve --form-config story_by_example_ui.yml --display-property example --script CHATTERLANG_SCRIPT