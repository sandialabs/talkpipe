"""Utility functions for processing HTML content"""

import contextlib
import gzip
import logging
import re
import time
import urllib
import urllib.error
from functools import cache
from html import unescape
from typing import Annotated
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import requests
from readability import Document

from talkpipe.chatterlang.registry import register_segment
from talkpipe.pipe import core
from talkpipe.util.config import get_config

logger = logging.getLogger(__name__)

USER_AGENT_KEY = "user_agent"

# Many sites answer the python-requests default agent (or a placeholder like
# "*") with 403s or bot-interstitial pages, so downloads fail before any
# content arrives.  Present a mainstream browser signature by default; override
# with the "user_agent" config key.
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# Servers also reject requests that carry a browser User-Agent but none of the
# headers a browser always sends.
BROWSER_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

RETRYABLE_STATUS_CODES = frozenset({408, 429, 500, 502, 503, 504})
RETRYABLE_EXCEPTIONS = (
    requests.exceptions.ConnectionError,
    requests.exceptions.Timeout,
    requests.exceptions.ChunkedEncodingError,
)
MAX_RETRY_DELAY = 30.0


def resolve_user_agent(user_agent=None):
    """Return the User-Agent to send: explicit argument, then the
    "user_agent" config key, then the browser-like default."""
    if user_agent is not None:
        return user_agent
    return get_config().get(USER_AGENT_KEY, DEFAULT_USER_AGENT)


def htmlToText(html, cleanText=True):
    """
    Extracts readable text from HTML content while preserving basic structure.

    Args:
        html (str): HTML content to process

    Returns:
        str: Extracted text with basic formatting preserved
    """

    if html is None:
        logger.info("No HTML content provided. Returning empty string.")
        return ""

    if html.strip() == "":
        logger.info("Empty HTML content provided. Returning empty string.")
        return ""

    if cleanText:
        try:
            d = Document(html)
            html = d.summary()
        except Exception as e:
            logger.warning(f"Failed to parse HTML: {e}: {html}")
            html = ""

    # Remove scripts and style elements
    html = re.sub(
        r"<script.*?</script\b[^>]*>", "", html, flags=re.DOTALL | re.IGNORECASE
    )
    html = re.sub(
        r"<style.*?</style\b[^>]*>", "", html, flags=re.DOTALL | re.IGNORECASE
    )

    # Replace block elements with newlines
    block_tags = ["p", "div", "br", "li", "h[1-6]", "header", "footer"]
    for tag in block_tags:
        html = re.sub(f"</?{tag}.*?>", "\n", html)

    # Remove remaining HTML tags
    html = re.sub(r"<[^>]+>", "", html)

    # Decode HTML entities
    text = unescape(html)

    # Clean up whitespace
    text = re.sub(
        r"\s*\n\s*", "\n", text
    )  # Convert line endings with surrounding whitespace to single \n
    text = re.sub(
        r"[^\S\n]+", " ", text
    )  # Replace multiple spaces with single space, preserve \n

    return text.strip()


@register_segment("htmlToText")
@core.field_segment()
def htmlToTextSegment(
    raw: Annotated[str, "The raw HTML content to be converted"],
    cleanText: Annotated[bool, "Whether to clean and normalize the output text"] = True,
):
    """
    Converts HTML content to text segment.

    This function takes HTML content and converts it to plain text format.
    If cleanText is enabled, the resulting text will also be cleaned so it
    tries to retain only the main body content.

    Returns:
        str: The extracted text content from the HTML

    See Also:
        htmlToText: The underlying function used for HTML to text conversion
    """
    return htmlToText(raw, cleanText=cleanText)


@cache
def get_robot_parser(domain, timeout=5):
    """Retrieve or create a RobotFileParser for a given domain with a timeout."""
    robots_url = f"{domain}/robots.txt"

    # Validate URL scheme for security
    parsed_url = urllib.parse.urlparse(robots_url)
    if parsed_url.scheme not in ("http", "https"):
        logger.warning(
            f"Unsafe URL scheme '{parsed_url.scheme}' in robots_url: {robots_url}. Only http/https allowed."
        )
        return None

    rp = RobotFileParser()
    rp.set_url(robots_url)

    try:
        # Send the same identification headers as page fetches; some hosts
        # refuse header-less clients even for robots.txt.
        headers = {"User-Agent": resolve_user_agent(), **BROWSER_HEADERS}
        response = requests.get(robots_url, timeout=timeout, headers=headers)
        response.raise_for_status()  # Raise an exception for bad status codes
        content_bytes = response.content
        if content_bytes.startswith(b"\x1f\x8b"):
            # If the content is gzipped, decompress it
            content = gzip.decompress(content_bytes).decode("utf-8", errors="replace")
        else:
            # If not gzipped, decode it directly
            content = content_bytes.decode("utf-8", errors="replace")

        try:
            rp.parse(content.splitlines())
        except Exception as e:
            # If parsing fails, log the error but return the robot parser anyway
            logger.warning(f"Error parsing robots.txt from {robots_url}: {e}")

    except requests.HTTPError as e:
        if e.response is not None and e.response.status_code == 404:
            # No robots.txt means no restrictions, per the robots.txt spec -- this
            # is the common case, not an error, so it shouldn't look like one.
            logger.info(
                f"No robots.txt at {robots_url} (404); treating all URLs on {domain} as allowed."
            )
        else:
            logger.warning(
                f"Failed to fetch robots.txt from {robots_url}. Assuming allowed. Error: {e}"
            )
        return None  # Use None to indicate failure to fetch
    except (requests.RequestException, ConnectionError, TimeoutError) as e:
        logger.warning(
            f"Failed to fetch robots.txt from {robots_url}. Assuming allowed. Error: {e}"
        )
        return None  # Use None to indicate failure to fetch

    return rp


def can_fetch(url, user_agent=None):
    """Check if the URL is allowed to be fetched according to robots.txt."""
    parsed_url = urlparse(url)
    domain = f"{parsed_url.scheme}://{parsed_url.netloc}"

    user_agent = resolve_user_agent(user_agent)

    try:
        rp = get_robot_parser(domain)
    except TimeoutError:
        # TODO: Update this so that the timeout is remembered for some specified amount of time.  Probably
        # involves moving the "can fetch" logic into its own class
        logger.warning(
            f"Timeout fetching robots.txt for {url}. Assuming URLs fetched will also timeout.  Indicating allowed."
        )
        return True

    if rp is None:
        # get_robot_parser already logged the specific reason (missing robots.txt is
        # the common case and logs at INFO there; real failures log at WARNING).
        logger.debug(f"Cannot check can_fetch for {url}. Assuming allowed.")
        return True  # Assume allowed if robots.txt cannot be fetched

    try:
        return rp.can_fetch(user_agent, url)
    except Exception as e:
        logger.warning(
            f"Error checking can_fetch for {url}. Assuming allowed. Error: {e}"
        )
        return True  # Assume allowed if there's an error during check


def _retry_delay(prior_attempts, response, backoff_factor):
    """Seconds to sleep before the next retry: exponential backoff, raised to
    the server's Retry-After when one was sent, capped at MAX_RETRY_DELAY."""
    delay = backoff_factor * (2**prior_attempts)
    retry_after = response.headers.get("Retry-After") if response is not None else None
    if retry_after:
        # Retry-After can be an HTTP-date; backoff alone is fine then
        with contextlib.suppress(TypeError, ValueError):
            delay = max(delay, float(retry_after))
    return min(delay, MAX_RETRY_DELAY)


def _fix_encoding(response):
    """Repair the charset guess before reading response.text.

    When a page declares no charset, requests falls back to ISO-8859-1 (the
    old HTTP default), which garbles the UTF-8 that most of the web actually
    serves.  Defer to the content-based detection requests already ships.
    """
    if response.encoding is None:
        response.encoding = response.apparent_encoding or response.encoding
    else:
        content_type = (response.headers.get("Content-Type") or "").lower()
        if "charset" not in content_type and response.encoding.lower() == "iso-8859-1":
            response.encoding = response.apparent_encoding or response.encoding


def downloadURL(
    url, fail_on_error=True, user_agent=None, timeout=10, retries=2, backoff_factor=0.5
):
    """Downloads content from a specified URL with respect to robots.txt rules.

    This function attempts to download content from a given URL while checking robots.txt
    permissions and handling various error conditions. Requests are sent with
    browser-like headers, and transient failures (connection errors, timeouts,
    HTTP 408/429/5xx) are retried with exponential backoff, honoring the
    server's Retry-After header when present.

    Args:
        url (str): The URL to download content from.
        fail_on_error (bool, optional): If True, raises exceptions on errors. If False,
            returns None on errors. Defaults to True.
        user_agent (str, optional): User agent string to use for requests.
            Defaults to the "user_agent" config key, then DEFAULT_USER_AGENT.
        timeout (int, optional): Request timeout in seconds. Defaults to 10.
        retries (int, optional): How many additional attempts to make after a
            transient failure. Defaults to 2.
        backoff_factor (float, optional): Base delay in seconds between
            retries; attempt n waits backoff_factor * 2**n. Defaults to 0.5.

    Returns:
        str or None: The downloaded content as text if successful, None if unsuccessful
            and fail_on_error is False.

    Raises:
        PermissionError: If the URL is disallowed by robots.txt and fail_on_error is True.
        ValueError: If the final HTTP response status is not 2xx and fail_on_error is True.
        Exception: If the download request fails for any other reason and fail_on_error is True.
    """
    logger.debug(f"Checking robots.txt permissions for URL: {url}")
    user_agent = resolve_user_agent(user_agent)
    if not can_fetch(url, user_agent):
        error_message = f"Fetching URL: {url} is disallowed by robots.txt"
        logger.warning(error_message)
        if fail_on_error:
            raise PermissionError(error_message)
        return None

    headers = {"User-Agent": user_agent, **BROWSER_HEADERS}
    attempts = max(0, retries) + 1
    response: requests.Response | None = None
    last_exception: Exception | None = None
    logger.debug(f"Initiating download request for URL: {url}")
    for attempt in range(attempts):
        if attempt:
            delay = _retry_delay(attempt - 1, response, backoff_factor)
            logger.debug(
                f"Retrying {url} in {delay:.1f}s (attempt {attempt + 1} of {attempts})"
            )
            time.sleep(delay)
        try:
            logger.debug(f"Sending GET request to {url} with timeout {timeout}s")
            response = requests.get(url, headers=headers, timeout=timeout)
            last_exception = None
        except RETRYABLE_EXCEPTIONS as e:
            logger.warning(
                f"Transient error downloading {url} (attempt {attempt + 1} of {attempts}): {e}"
            )
            response = None
            last_exception = e
            continue
        except Exception as e:
            # Not transient (bad URL, SSL failure, ...): retrying won't help.
            response = None
            last_exception = e
            break
        if response.status_code in RETRYABLE_STATUS_CODES:
            logger.warning(
                f"Got status {response.status_code} from {url} (attempt {attempt + 1} of {attempts})"
            )
            continue
        break

    if last_exception is not None:
        error_message = f"Failed to download URL: {url}\nError: {last_exception}"
        if fail_on_error:
            logger.error(error_message)
            raise Exception(error_message)
        logger.warning(error_message)
        return None

    # Every attempt either set response or recorded an exception (handled above).
    if response is None:
        raise RuntimeError(f"No response received from {url}")
    logger.debug(f"Received response with status code: {response.status_code}")
    if not 200 <= response.status_code < 300:
        error_message = (
            f"Failed to download URL: {url} with status code {response.status_code}"
        )
        if fail_on_error:
            logger.error(error_message)
            raise ValueError(error_message)
        logger.warning(error_message)
        return None
    logger.debug(f"Successfully downloaded content from {url}")
    _fix_encoding(response)
    return response.text


@register_segment("downloadURL")
@core.field_segment()
def downloadURLSegment(
    item: Annotated[str, "The URL to download"],
    fail_on_error: Annotated[
        bool,
        "If True, raises exceptions on download errors. If False, returns None on errors",
    ] = True,
    timeout: Annotated[int, "The timeout in seconds for the download request"] = 10,
    user_agent: Annotated[
        str | None, "User agent string to use for the request"
    ] = None,
    retries: Annotated[
        int,
        "How many additional attempts to make after a transient failure (connection error, timeout, HTTP 408/429/5xx)",
    ] = 2,
):
    """Download a URL segment and return its content.

    This function is a wrapper around downloadURL that specifically handles URL segments.
    It attempts to download content from the specified URL with configurable error handling,
    timeout, and retry settings.

    Returns:
        str|None: The downloaded content as text if successful, None if fail_on_error
            is False and an error occurs.

    Raises:
        Various exceptions from downloadURL function when fail_on_error is True and
        an error occurs during download.
    """
    logger.debug(f"Downloading URL: {item}")
    return downloadURL(
        item,
        fail_on_error=fail_on_error,
        timeout=timeout,
        user_agent=user_agent,
        retries=retries,
    )
