###################################################################################
# Step 2: Search by Example and RAG
# This script allows users to search for indexed documents using an example query.
# It uses the Ollama embedding model to convert the example into a vector,
# which is then used to search a vector index.
# The results are formatted and printed to the console.
#
# The pipeline is:
# 1. Read the example query from the user.
# 2. Use the `llmEmbed` segment to convert the example into a vector.
# 3. Use the `searchVector` segment to search the vector index for similar documents.
# 4. Format the results using `formatItem` and print them.
###################################################################################

talkpipe_endpoint --form-config story_by_example_ui.yaml --script "
    | llmEmbed[field=\"example\", source=\"ollama\", model=\"mxbai-embed-large\", append_as=\"vector\"]
    | searchVector[path=\"./vector_index\", vector_field=\"vector\"]
    | formatItem[field_list=\"document.title:Title,document.content:Content,score:Score\"]
    | print
"