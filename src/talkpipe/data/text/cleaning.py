"""Cleaning of encoded binary payloads out of text bound for embedding or indexing."""

import re
from functools import lru_cache
from typing import Annotated

from talkpipe.chatterlang import register_segment
from talkpipe.pipe.core import field_segment

# Default minimum length for an unbroken base64-alphabet run to be treated as an
# encoded payload rather than a word. No natural-language token approaches this
# length, while even a small pasted image produces runs of tens of thousands of
# characters.
DEFAULT_MIN_RUN = 64

# A data URI with a base64 payload, e.g. an image pasted into Markdown or HTML.
# Matched regardless of payload length so short embedded blobs are removed along
# with their "data:...;base64," prefix.
_DATA_URI_RE = re.compile(r"data:[\w.+-]+/[\w.+-]+;\s*base64,\s*[A-Za-z0-9+/=]+")


@lru_cache(maxsize=8)
def _base64_run_re(min_run: int) -> re.Pattern:
    return re.compile(r"[A-Za-z0-9+/]{%d,}={0,2}" % min_run)


def _looks_like_base64(run: str) -> bool:
    # Random base64 of this length virtually always mixes cases and digits;
    # requiring all three preserves non-encoded long runs such as repeated
    # characters, DNA sequences, or hex digests.
    return (
        any(c.islower() for c in run)
        and any(c.isupper() for c in run)
        and any(c.isdigit() for c in run)
    )


def strip_base64_blobs(text: str, min_run: int = DEFAULT_MIN_RUN) -> str:
    """Remove base64-encoded payloads from text, keeping the surrounding prose.

    Base64 blobs are poison for embedding-based search: an unbroken run collapses
    to unknown tokens, and a chunk whose tokens are all unknown embeds to the zero
    vector — which, under L2 distance against normalized embeddings, is closer to
    every query than any unrelated real document. Stripping the blobs before
    chunking keeps the encoded payload out of the index while the real text around
    it (titles, captions, body prose) is preserved.

    Removes both data URIs (``data:image/png;base64,...``) and bare runs of
    base64-alphabet characters at least ``min_run`` long that mix upper case,
    lower case, and digits (so repeated characters, DNA sequences, and hex
    digests survive), replacing each with a single space.
    """
    text = _DATA_URI_RE.sub(" ", text)
    return _base64_run_re(min_run).sub(
        lambda m: " " if _looks_like_base64(m.group(0)) else m.group(0), text
    )


@register_segment("stripBase64")
@field_segment()
def stripBase64(
    text: Annotated[str, "Text to clean"],
    min_run: Annotated[int, "Minimum unbroken base64 run length to strip"] = DEFAULT_MIN_RUN,
) -> str:
    """Removes base64-encoded payloads (data URIs and bare encoded runs) from text.

    Expects string input (or a string field on dict items) and produces the same
    text with encoded blobs replaced by spaces. Intended to run on document
    content before chunking and embedding, so encoded images and attachments
    never reach the embedding model or the search index.
    """
    return strip_base64_blobs(text, min_run=min_run)
