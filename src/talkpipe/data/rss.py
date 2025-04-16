import logging
import time
import sqlite3
import feedparser
from talkpipe.util.config import get_config
from talkpipe.pipe import core
from talkpipe.chatterlang import registry
from talkpipe.data import html

logger = logging.getLogger(__name__)

def rss_monitor(
    url: str,
    db_path: str = ':memory:',
    poll_interval_minutes: int = 60
):
    """Monitor an RSS feed URL and yield new items as they are published.

    This function continuously polls an RSS feed at specified intervals, tracks seen items
    using a SQLite database, and yields new items as dictionaries. It can run indefinitely
    or make a single poll based on the poll_interval_minutes parameter.

    Args:
        url (str): The URL of the RSS feed to monitor
        db_path (str, optional): Path to SQLite database file. Defaults to ':memory:' for in-memory database
        poll_interval_minutes (int, optional): Minutes between feed polls. Use -1 for single poll. Defaults to 60

    Yields:
        dict: Dictionary containing item details with keys:
            - title (str): Item title
            - link (str): Item URL/link
            - published (str): Publication date/time
            - summary (str): Item summary/description
            - author (str): Item author

    Note:
        - Uses SQLite to track seen items and prevent duplicate processing
        - Stores full content in database but doesn't include it in yielded dictionary
        - Items without links are skipped
        - All RSS fields are optional; missing fields will be empty strings
    """

    # Connect to (or create) the SQLite database.
    logger.debug(f"Connecting to database at {db_path}")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    logger.debug("Creating feed_items table if not exists")
    # Create a table to store feed item data (including full content).
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS feed_items (
            link TEXT PRIMARY KEY,
            title TEXT,
            published TEXT,
            summary TEXT,
            author TEXT,
            content TEXT
        )
    """)
    conn.commit()

    while True:
        logger.debug(f"Attempting to parse RSS feed from {url}")
        # Parse the RSS feed using feedparser.
        feed = feedparser.parse(url)

        logger.debug(f"Processing {len(feed.entries)} entries from feed")
        # Iterate over each entry in the feed.
        for entry in feed.entries:
            link = entry.get('link')
            if not link:
                logger.debug("Skipping entry with no link")
                continue

            # Check if we've already seen (and stored) this item.
            cursor.execute("SELECT link FROM feed_items WHERE link = ?", (link,))
            result = cursor.fetchone()

            # Only process if this item is new.
            if result is None:
                logger.debug(f"Processing new entry with link: {link}")
                # Extract fields from the feed entry.
                title = entry.get('title', '')
                published = entry.get('published', '')
                summary = entry.get('summary', '')
                author = entry.get('author', '')

                # Attempt to get the "full content" from the 'content' field if it exists.
                # Often this might be a list of dicts with 'value' being the HTML/text.
                content = ''
                if 'content' in entry:
                    logger.debug("Extracting full content from entry")
                    content_list = entry['content']
                    if isinstance(content_list, list) and len(content_list) > 0:
                        content = content_list[0].get('value', '')

                # Prepare a dictionary to yield.
                item_dict = {
                    'title': title,
                    'link': link,
                    'published': published,
                    'summary': summary,
                    'author': author
                }

                logger.debug(f"Yielding new item: {title}")
                # Yield the item so that the caller can process it.
                yield item_dict

                logger.debug("Storing new item in database")
                # Store the new item in the database (INSERT).
                cursor.execute("""
                    INSERT INTO feed_items (link, title, published, summary, author, content)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (link, title, published, summary, author, content))
                conn.commit()

        if poll_interval_minutes == -1:
            # If poll_interval_minutes is -1, only poll once.
            break
        else:
            # Sleep for the specified poll interval (convert minutes to seconds).
            logger.debug(f"Sleeping for {poll_interval_minutes} minutes...")
            time.sleep(poll_interval_minutes * 60)

@registry.register_source("rss")
@core.source(url=None)
def rss_source(url: str, db_path: str = ':memory:', poll_interval_minutes: int = 10):
    """
    Generator function that monitors and yields new entries from an RSS feed.

    This function continuously monitors an RSS feed at the specified URL and yields new entries
    as they become available. It uses a SQLite database to keep track of previously seen entries
    to avoid duplicates.

    Args:
        url (str): The URL of the RSS feed to monitor.  If None, the URL is read from the config using
            the key "RSS_URL"
        db_path (str, optional): Path to the SQLite database file for storing entry history.
            Defaults to ':memory:' for an in-memory database.
        poll_interval_minutes (int, optional): Number of minutes to wait between polling
            the RSS feed for updates. Defaults to 10 minutes.

    Yields:
        dict: New entries from the RSS feed, containing feed item data.

    Example:
        >>> for entry in rss_source("http://example.com/feed.xml"):
        ...     print(entry["title"])
    """

    try:
        url = url or get_config().get("rss_url")
    except Exception as e:
        logger.error(f"Failed to get rss_url from config: {e}")
        raise


    yield from rss_monitor(url, db_path, poll_interval_minutes)
