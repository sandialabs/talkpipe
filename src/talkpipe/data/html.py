"""Utility functions for processing HTML content"""

import logging
import re
import gzip
import urllib.error
import requests
import urllib
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser
from functools import lru_cache
from html import unescape
from readability import Document 
from talkpipe.util.config import get_config
from talkpipe.chatterlang.registry import register_segment
from talkpipe.pipe import core
from talkpipe import util

logger = logging.getLogger(__name__)

USER_AGENT_KEY = "user_agent"

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
    html = re.sub(r'<script.*?</script>', '', html, flags=re.DOTALL)
    html = re.sub(r'<style.*?</style>', '', html, flags=re.DOTALL)
    
    # Replace block elements with newlines
    block_tags = ['p', 'div', 'br', 'li', 'h[1-6]', 'header', 'footer']
    for tag in block_tags:
        html = re.sub(f'</?{tag}.*?>', '\n', html)
    
    # Remove remaining HTML tags
    html = re.sub(r'<[^>]+>', '', html)
    
    # Decode HTML entities
    text = unescape(html)
    
    # Clean up whitespace
    text = re.sub(r'\s*\n\s*', '\n', text)  # Convert line endings with surrounding whitespace to single \n
    text = re.sub(r'[^\S\n]+', ' ', text)    # Replace multiple spaces with single space, preserve \n
    
    return text.strip()


@register_segment("htmlToText")
@core.field_segment()
def htmlToTextSegment(raw, cleanText=True):
    """
    Converts HTML content to text segment.

    This function takes HTML content and converts it to plain text format.
    If cleanText is enabled, the resulting text will also be cleaned so it 
    tries to retain only the main body content.

    Args:
        raw (str): The raw HTML content to be converted
        cleanText (bool, optional): Whether to clean and normalize the output text. Defaults to True.
        field (str): The field name to be used for the segment. If None, assuming the incoming item is html.
        append_as (str): The name of the field to append the text to.  If None, just pass on the cleaned text.

    Returns:
        str: The extracted text content from the HTML

    See Also:
        htmlToText: The underlying function used for HTML to text conversion
    """
    extracted = htmlToText(raw, cleanText=cleanText)
    return extracted 

@lru_cache(maxsize=None)
def get_robot_parser(domain, timeout=5):
    """Retrieve or create a RobotFileParser for a given domain with a timeout."""
    robots_url = f"{domain}/robots.txt"
    rp = RobotFileParser()
    rp.set_url(robots_url)

    try:
        with urllib.request.urlopen(robots_url, timeout=timeout) as response:
            content = response.read()
            if content.startswith(b'\x1f\x8b'):
                # If the content is gzipped, decompress it
                content = gzip.decompress(content).decode('utf-8')
            else:
                # If not gzipped, decode it directly
                content = content.decode('utf-8')
        
        try:
            rp.parse(content.splitlines())
        except Exception as e:
            # If parsing fails, log the error but return the robot parser anyway
            logger.warning(f"Error parsing robots.txt from {robots_url}: {e}")
            
    except (urllib.error.URLError, ConnectionError, TimeoutError) as e:
        logger.warning(f"Failed to fetch robots.txt from {robots_url}. Assuming allowed. Error: {e}")
        return None  # Use None to indicate failure to fetch

    return rp

def can_fetch(url, user_agent=None):
    """Check if the URL is allowed to be fetched according to robots.txt."""
    parsed_url = urlparse(url)
    domain = f"{parsed_url.scheme}://{parsed_url.netloc}"

    if user_agent is None:
        user_agent = get_config().get(USER_AGENT_KEY, "*")

    try:
        rp = get_robot_parser(domain)
    except TimeoutError as e:
        #TODO: Update this so that the timeout is remembered for some specified amount of time.  Probably
        # involves moving the "can fetch" logic into its own class
        logger.warning(f"Timeout fetching robots.txt for {url}. Assuming URLs fetched will also timeout.  Indicating allowed.")
        return True

    if rp is None:
        logger.warning(f"Cannot check can_fetch for {url}. Assuming allowed.")
        return True  # Assume allowed if robots.txt cannot be fetched
    
    try:
        return rp.can_fetch(user_agent, url)
    except Exception as e:
        logger.warning(f"Error checking can_fetch for {url}. Assuming allowed. Error: {e}")
        return True  # Assume allowed if there's an error during check

def downloadURL(url, fail_on_error=True, user_agent=None, timeout=10):
    """Downloads content from a specified URL with respect to robots.txt rules.

    This function attempts to download content from a given URL while checking robots.txt
    permissions and handling various error conditions. It supports custom user agents and
    timeout settings.

    Args:
        url (str): The URL to download content from.
        fail_on_error (bool, optional): If True, raises exceptions on errors. If False,
            returns None on errors. Defaults to True.
        user_agent (str, optional): User agent string to use for requests.
            Defaults to "*".
        timeout (int, optional): Request timeout in seconds. Defaults to 10.

    Returns:
        str or None: The downloaded content as text if successful, None if unsuccessful
            and fail_on_error is False.

    Raises:
        PermissionError: If the URL is disallowed by robots.txt and fail_on_error is True.
        ValueError: If the HTTP response status code is not 200 and fail_on_error is True.
        Exception: If the download request fails for any other reason and fail_on_error is True.

    Example:
        >>> content = downloadURL("https://example.com")
        >>> print(content)
        '<html>...</html>'
    """
    logger.debug(f"Checking robots.txt permissions for URL: {url}")
    if user_agent is None:
        user_agent = get_config().get(USER_AGENT_KEY, "*")
    if not can_fetch(url, user_agent):
        error_message = f"Fetching URL: {url} is disallowed by robots.txt"
        logger.warning(error_message)
        if fail_on_error:
            raise PermissionError(error_message)
        else:
            return None

    headers = {"User-Agent": user_agent}
    logger.debug(f"Initiating download request for URL: {url}")
    try:
        logger.debug(f"Sending GET request to {url} with timeout {timeout}s")
        response = requests.get(url, headers=headers, timeout=timeout)
    except Exception as e:
        if fail_on_error:
            logger.error(f"Failed to download URL: {url}\nError: {e}")
            raise Exception(f"Failed to download URL: {url}\nError: {e}")
        else:
            logger.warning(f"Failed to download URL: {url}\nError: {e}")
            return None

    logger.debug(f"Received response with status code: {response.status_code}")
    if response.status_code != 200:
        error_message = f"Failed to download URL: {url} with status code {response.status_code}"
        if fail_on_error:
            logger.error(error_message)
            raise ValueError(error_message)
        else:
            logger.warning(error_message)
            return None
    else:
        logger.debug(f"Successfully downloaded content from {url}")
        return response.text


@register_segment("downloadURL")
@core.field_segment()
def downloadURLSegment(item, fail_on_error=True, timeout=10, user_agent=None):
    """Download a URL segment and return its content.

    This function is a wrapper around downloadURL that specifically handles URL segments.
    It attempts to download content from the specified URL with configurable error handling
    and timeout settings.

    Args:
        fail_on_error (bool, optional): If True, raises exceptions on download errors.
            If False, returns None on errors. Defaults to True.
        timeout (int, optional): The timeout in seconds for the download request. 
            Defaults to 10 seconds.

    Returns:
        bytes|None: The downloaded content as bytes if successful, None if fail_on_error
            is False and an error occurs.

    Raises:
        Various exceptions from downloadURL function when fail_on_error is True and
        an error occurs during download.
    """
    logger.debug(f"Downloading URL: {item}")
    return downloadURL(item, fail_on_error=fail_on_error, timeout=timeout, user_agent=user_agent)