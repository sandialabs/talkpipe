

#talkpipe_endpoint --form-config story_by_example_ui.yml --script "
python -m talkpipe.app.apiendpoint --form-config story_by_example_ui.yml --load_module step_3_extras.py --display-property example --script "
    | copy
    | llmEmbed[field=\"example\", source=\"ollama\", model=\"mxbai-embed-large\", append_as=\"vector\"]
    | searchVector[vector_field=\"vector\", path=\"./vector_index\", all_results_at_once=True, append_as=\"results\"]
    | ragPrompt
    | llmPrompt[source="ollama", name="llama3.2"]
    "
