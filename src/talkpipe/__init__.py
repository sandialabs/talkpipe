from talkpipe.pipe.basic import *
from talkpipe.pipe.math import *
from talkpipe.pipe.io import *
from talkpipe.pipe.fork import *
from talkpipe.data.email import *
from talkpipe.data.rss import *
from talkpipe.llm.chat import *
from talkpipe.llm.embedding import *
from talkpipe.data.extraction import *
from talkpipe.data.html import *
from talkpipe.data.mongo import *
from talkpipe.operations.filtering import *
from talkpipe.operations.transforms import *
from talkpipe.operations.matrices import *
from talkpipe.operations.signatures import *
from talkpipe.app.chatterlang_serve import *
from talkpipe.search.whoosh import *
from talkpipe.search.simplevectordb import *

# Load plugins automatically on import
from talkpipe.util.plugin_loader import load_plugins
import logging

# Configure logging for plugin loading
logger = logging.getLogger(__name__)

try:
    load_plugins()
    logger.debug("Plugin loading completed")
except Exception as e:
    logger.warning(f"Plugin loading failed: {e}")