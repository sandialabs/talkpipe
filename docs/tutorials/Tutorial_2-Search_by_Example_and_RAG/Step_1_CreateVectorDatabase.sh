###################################################################################
# This script creates a vector database using the provided configuration file.
# It uses the `chatterlang_script` command to run a Chatterlang script that
# uses the synthetic data generated in the previous tutorial.
#
# The pipeline is:
# 1. Read the JSONL file "stories.json" created in the previous tutorial.
# 2. Use the `llmEmbed` segment to generate embeddings for the content field
#    using the specified model.
# 3. The embeddings are stored in a vector index at the specified path.
###################################################################################

export TALKPIPE_CHATTERLANG_SCRIPT='
    INPUT FROM "../Tutorial_1-Document_Indexing/stories.json"
    | readJsonl 
    | progressTicks[tick_count=1, print_count=True] 
    | llmEmbed[field="content", source="ollama", model="mxbai-embed-large", append_as="vector"]
    | addVector[path="./vector_index", vector_field="vector", metadata_field_list="title,content", overwrite=True]
'

#chatterlang_script --script "
python -m talkpipe.app.chatterlang_script --script CHATTERLANG_SCRIPT 
"