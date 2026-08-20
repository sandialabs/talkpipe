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

# Model2vec embedding settings (used by talkpipe.llm.embedding_adapters_model2vec)
MODEL2VEC_REVISION = "MODEL2VEC_REVISION"
MODEL2VEC_CACHE_DIR = "MODEL2VEC_CACHE_DIR"

# Network timeouts, in seconds. Each is a config key (settable as
# TALKPIPE_<key> or in ~/.talkpipe.toml); an explicit ``timeout=`` argument on
# the segment or adapter overrides the configured value, which overrides the
# DEFAULT_* fallback. They exist so a hung server fails a pipeline instead of
# blocking it forever.
LLM_TIMEOUT = "llm_timeout"
EMAIL_TIMEOUT = "email_timeout"
MONGO_TIMEOUT = "mongo_timeout"
DEFAULT_LLM_TIMEOUT = 120.0
DEFAULT_EMAIL_TIMEOUT = 30.0
DEFAULT_MONGO_TIMEOUT = 30.0

# ---------------------------------------------------------------------------
# Every other config key read anywhere in talkpipe. Each is looked up with
# get_config().get(KEY), so it can be set in ~/.talkpipe.toml as ``key = ...``
# or in the environment as ``TALKPIPE_<KEY>`` (matching is case-insensitive).
#
# Note that a constant's *name* does not always match its *value*: the four
# ``TALKPIPE_*`` constants above predate this list and keep their names for
# compatibility, e.g. ``TALKPIPE_EMBEDDING_MODEL_NAME`` is the config key
# ``default_embedding_model_name`` (environment variable
# ``TALKPIPE_DEFAULT_EMBEDDING_MODEL_NAME``). The value is what matters.
# ---------------------------------------------------------------------------

# Logging (talkpipe.util.config.configure_logger / the configureLogger segment)
LOGGER_LEVELS = "logger_levels"
LOGGER_FILES = "logger_files"

# HTTP servers (chatterlang_serve, serverag): API key when --require_auth is set
API_KEY = "API_KEY"
# Extra CORS origins for chatterlang_serve, comma-separated. Read from the
# environment only (``TALKPIPE_ALLOWED_ORIGINS``), not from ~/.talkpipe.toml.
ALLOWED_ORIGINS = "ALLOWED_ORIGINS"

# Component registry diagnostics (talkpipe.chatterlang.registry)
LAZY_IMPORT = "LAZY_IMPORT"

# Web fetching (talkpipe.data.html)
USER_AGENT = "user_agent"

# RSS source default feed (talkpipe.data.rss)
RSS_URL = "rss_url"

# Email (talkpipe.data.email)
SMTP_SERVER = "smtp_server"
SMTP_PORT = "smtp_port"
IMAP_SERVER = "imap_server"
EMAIL_ADDRESS = "email_address"
EMAIL_PASSWORD = "email_password"  # nosec B105 - config key name, not a secret
SENDER_EMAIL = "sender_email"
RECIPIENT_EMAIL = "recipient_email"

# MongoDB (talkpipe.data.mongo)
MONGO_CONNECTION_STRING = "mongo_connection_string"

# chatterlang_workbench (talkpipe.app.chatterlang_workbench and talkpipe.app.workbench)
WORKBENCH_WORKSPACE = "workbench_workspace"
WORKBENCH_LOAD_MODULES = "workbench_load_modules"
WORKBENCH_API_KEY = "workbench_api_key"
WORKBENCH_LLM_SUGGESTIONS = "workbench_llm_suggestions"
WORKBENCH_SUGGEST_SOURCE = "workbench_suggest_source"
WORKBENCH_SUGGEST_MODEL = "workbench_suggest_model"
