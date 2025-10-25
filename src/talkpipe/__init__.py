import warnings
warnings.filterwarnings("ignore", message=".*ColPaliEmbeddings.*has conflict with protected namespace.*")
warnings.filterwarnings("ignore", message=".*SigLipEmbeddings.*has conflict with protected namespace.*")

# Load plugins automatically on import
from talkpipe.util.plugin_loader import load_plugins
from talkpipe.chatterlang import compile
from talkpipe.pipe.core import segment, field_segment, AbstractFieldSegment, AbstractSegment, source, AbstractSource
from talkpipe.chatterlang.registry import register_segment, register_source

import logging

# Configure logging for plugin loading
logger = logging.getLogger(__name__)

try:
    load_plugins()
    logger.debug("Plugin loading completed")
except Exception as e:
    logger.warning(f"Plugin loading failed: {e}")