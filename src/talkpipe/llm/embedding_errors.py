"""Classify embedding provider errors related to input length / token limits."""

from __future__ import annotations

import re

# Substrings commonly seen when an embedding input exceeds model limits.
_TOKEN_OVERFLOW_PATTERNS = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"maximum context length",
        r"context length",
        r"token limit",
        r"too many tokens",
        r"input.*too long",
        r"reduce (the )?(length|size|your input)",
        r"exceeds the maximum",
        r"max.*tokens",
    )
)


def is_token_overflow_error(exc: BaseException) -> bool:
    """Return True if the exception likely indicates input text was too long to embed."""
    message = str(exc)
    if not message:
        message = repr(exc)
    return any(pattern.search(message) for pattern in _TOKEN_OVERFLOW_PATTERNS)
