

chatterlang_script --script "
    INPUT FROM \"Here is a story about electrons.\" | toDict[field_list=\"_:example\"]
    | llmEmbed[field=\"example\", source=\"ollama\", model=\"mxbai-embed-large\", append_as=\"vector\"]
    | searchVector[path=\"./vector_index\", vector_field=\"vector\"]
    | formatItem[field_list=\"document.title:Title,document.content:Content,score:Score\"]
"