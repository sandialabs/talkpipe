###################################################################################
# Step 2: Index Stories
#
# This script indexes the stories generated in Step 1 using the Whoosh library.
# It reads the JSON file created in Step 1 and indexes the content and titles of the stories.
# The indexed data can then be used for full-text search.
#
# As a side note, the first half of this script issues a single piece of data, the
# filename.  The next segment, `readJsonl`, reads the JSONL file line by line and 
# issues one decoded JSON object at a time.  This is a good example of how the 
# constitution of the data being processed can change as it flows through the pipeline.
#
# The pipeline is:
# 1. Read the JSONL file "stories.json" created in Step 1.
# 2. Use the `indexWhoosh` segment to index the content and title fields.
# 3. The index is stored in the specified path "./full_text_index".
###################################################################################

export TALKPIPE_CHATTERLANG_SCRIPT='
    INPUT FROM "stories.json" 
    | readJsonl 
    | progressTicks[tick_count=1, print_count=True]
    | indexWhoosh[index_path="./full_text_index", field_list="content,title", overwrite=True]
'

#chatterlang_script --script "
python -m talkpipe.app.runscript --script CHATTERLANG_SCRIPT