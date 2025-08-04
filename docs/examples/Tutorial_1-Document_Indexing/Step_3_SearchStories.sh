###################################################################################
# Step 3: Search Stories
# This script allows users to search for indexed stories using the Whoosh library.
# It opens two interface.  The first is an API endpoint that accepts search queries
# and returns matching stories. The second is a command-line interface that allows
# users to enter search terms interactively.
#
# It accomplishes this by using the talkpipe_endpoint to serve a pipeline that
# reads queries in the form of JSON objects, processes them, and returns results.
# The same application provides a search-like interface, configured by a yaml file,
# that makes it easy for a user to create the JSON sent to the endpoint without
# needing to write any code.
###################################################################################

export TALKPIPE_CHATTERLANG_SCRIPT='
  | searchWhoosh[index_path="full_text_index", field="query"] 
  | formatItem[field_list="document.title:Title,document.content:Content,score:Score"]
'
#talkpipe_endpoint --form-config story_search_ui.yml --title "Story Search" --script "
python -m talkpipe.app.apiendpoint --form-config story_search_ui.yml --title \"Story\ Search\" --display-property query --script CHATTERLANG_SCRIPT