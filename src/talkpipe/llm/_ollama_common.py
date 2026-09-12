"""Shared Ollama plumbing for the prompt and embedding adapters.

Both adapters resolve the server URL the same way and, on a refused
connection, must produce the same actionable message naming the URL that was
tried and the environment variable that changes it. Keeping one copy here
stops the two from drifting apart.
"""

from talkpipe.util.config import get_config
from talkpipe.util.constants import OLLAMA_SERVER_URL

# What the ollama SDK talks to when no host is configured.
DEFAULT_OLLAMA_SERVER_URL = "http://localhost:11434"


def resolve_ollama_server_url(explicit: str | None) -> str | None:
    """Return the configured Ollama server URL, or None for the SDK default.

    Precedence: the value passed to the adapter, then ``OLLAMA_SERVER_URL``
    from :func:`get_config` (``TALKPIPE_OLLAMA_SERVER_URL`` or
    ``~/.talkpipe.toml``).
    """
    if explicit:
        return explicit
    server_url: str | None = get_config().get(OLLAMA_SERVER_URL, None)
    return server_url


def ollama_connection_error(server_url: str | None, exc: Exception) -> ConnectionError:
    """Build the shared "cannot reach Ollama" error naming the URL and env var."""
    return ConnectionError(
        f"Failed to connect to Ollama at '{server_url or DEFAULT_OLLAMA_SERVER_URL}'. "
        "If your Ollama server is remote, set the TALKPIPE_OLLAMA_SERVER_URL environment "
        "variable (e.g. `export TALKPIPE_OLLAMA_SERVER_URL=http://your-ollama-host:11434`) "
        "or OLLAMA_SERVER_URL in ~/.talkpipe.toml. "
        f"Original error: {exc}"
    )
