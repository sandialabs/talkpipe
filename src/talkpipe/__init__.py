import warnings

warnings.filterwarnings(
    "ignore", message=".*ColPaliEmbeddings.*has conflict with protected namespace.*"
)
warnings.filterwarnings(
    "ignore", message=".*SigLipEmbeddings.*has conflict with protected namespace.*"
)

# The warning filters above must be installed before talkpipe's own modules
# are imported, hence the late imports.
import logging  # noqa: E402
from importlib.metadata import PackageNotFoundError, version  # noqa: E402

from talkpipe.chatterlang import compile  # noqa: E402
from talkpipe.chatterlang.registry import (  # noqa: E402
    register_segment,
    register_source,
)
from talkpipe.pipe.core import (  # noqa: E402
    AbstractFieldSegment,
    AbstractSegment,
    AbstractSource,
    field_segment,
    segment,
    source,
)
from talkpipe.util.plugin_loader import load_plugins  # noqa: E402

try:
    __version__ = version("talkpipe")
except PackageNotFoundError:  # pragma: no cover - only when run from an unbuilt tree
    __version__ = "0.0.0+unknown"

__all__ = [
    "AbstractFieldSegment",
    "AbstractSegment",
    "AbstractSource",
    "__version__",
    "compile",
    "field_segment",
    "register_segment",
    "register_source",
    "segment",
    "source",
]

# Library logging: attach a NullHandler so that, in an application that has not
# configured logging, warnings from talkpipe go nowhere instead of through
# Python's last-resort stderr handler. Applications configure logging themselves.
logging.getLogger(__name__).addHandler(logging.NullHandler())

# Configure logging for plugin loading
logger = logging.getLogger(__name__)

try:
    load_plugins()
    logger.debug("Plugin loading completed")
except Exception as e:
    logger.warning(f"Plugin loading failed: {e}")
