"""Config keys for LLM and embedding defaults.

These constants name keys used with get_config() to resolve default model
names, sources, and server URLs. Set via ~/.talkpipe.toml or TALKPIPE_*
environment variables.
"""
# Embedding defaults (used by talkpipe.llm.embedding)
TALKPIPE_EMBEDDING_MODEL_NAME = "default_embedding_model_name"
TALKPIPE_EMBEDDING_MODEL_SOURCE = "default_embedding_model_source"

# Chat model defaults (used by talkpipe.llm.chat)
TALKPIPE_MODEL_NAME = "default_model_name"
TALKPIPE_SOURCE = "default_model_source"

# Ollama server URL when using ollama source (e.g. http://localhost:11434)
OLLAMA_SERVER_URL = "OLLAMA_SERVER_URL"
