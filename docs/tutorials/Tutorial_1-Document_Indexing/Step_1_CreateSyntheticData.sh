###################################################################################
# Step 1: Create Synthetic Data
#
# This script generates synthetic data for document indexing.
# "chatterlang_script" is a command installed with talkpipe that allows you
# to run Chatterlang scripts from the command line.
#
# This particular script generates a set of fictitious stories that we'll use
# to test the document indexing and search.
# The pipeline is:
# 1. Loop 50 times
# 2. "INPUT FROM..." issues a prompt to the LLM to generate a five-sentence story 
#    about technology development in an imaginary country.
# 3. The output is processed to create a dictionary with the story content.
# 4. A second LLM prompt generates a title for the story.
# 5. The results are formatted as JSONL and printed to the console.
# 6. The output is redirected to a file named "stories.json".
###################################################################################

export TALKPIPE_CHATTERLANG_SCRIPT='
    LOOP 50 TIMES {
        INPUT FROM "Write a fictitious five sentence story about technology development in an imaginary country." 
        | llmPrompt[source="ollama", model="llama3.2", multi_turn=False] 
        | toDict[field_list="_:content"] 
        | llmPrompt[source="ollama", model="llama3.2", system_prompt="Write exactly one title for this story in plain text with no markdown", field="content", append_as="title", multi_turn=False] 
        | dumpsJsonl | print;
    }
'
#chatterlang_script --script "
python -m talkpipe.app.chatterlang_script --script CHATTERLANG_SCRIPT > stories.json