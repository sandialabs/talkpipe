"""This module contains segments for extracting text from files."""

from typing import Union, Iterable, Annotated, Callable, Optional, Iterator
import logging
from pydantic import BaseModel, ConfigDict
import glob
import os
from pathlib import PosixPath, Path
from docx import Document
from talkpipe.pipe.core import segment, AbstractFieldSegment, field_segment
from talkpipe.chatterlang.registry import register_segment


logger = logging.getLogger(__name__)

class ExtractionResult(BaseModel):
    """Model representing the result of a file extraction."""
    model_config = ConfigDict(extra="allow")
    content: Annotated[str, "Extracted text content from the file"]
    source: Annotated[str, "Source file path"]
    id: Annotated[str, "Unique identifier for the extraction result.  Typically will be source unless multiple results are emitted per source."]
    title: Annotated[str, "Title or description of the extracted content. Generally includes filename and part of file if appropriate."]

# Type alias for extractor functions: take a path, yield ExtractionResult objects (or nothing for skip)
ExtractorFunc = Callable[[Union[str, Path]], Iterator[ExtractionResult]]

class ExtractorRegistry:
    """
    A registry for file text extractors that maps file patterns to extraction functions.

    Extractors are registered with file extension patterns and are called with a file path
    to extract text content from the file. Extractors are generators that yield strings,
    allowing them to emit multiple items (e.g., CSV rows, JSONL lines) or a single item.

    Attributes:
        _extractors: Dict mapping file extensions to extractor callables.
        _default_extractor: Optional callable used when no pattern matches.
    """

    def __init__(self):
        self._extractors: dict[str, ExtractorFunc] = {}
        self._default_extractor: Optional[ExtractorFunc] = None

    def register(self, extension: str, extractor: ExtractorFunc) -> None:
        """
        Register an extractor for a file extension.

        Args:
            extension: File extension without the dot (e.g., 'txt', 'docx').
            extractor: Callable that takes a file path and yields extracted text strings.
        """
        logger.debug(f"Registering extractor for extension: {extension}")
        self._extractors[extension.lower()] = extractor

    def register_default(self, extractor: ExtractorFunc) -> None:
        """
        Register a default extractor to use when no extension matches.

        Args:
            extractor: Callable that takes a file path and yields extracted text strings.
                      Yield nothing to skip the file.
        """
        logger.debug("Registering default extractor")
        self._default_extractor = extractor

    def get_extractor(self, file_path: Union[str, Path]) -> Optional[ExtractorFunc]:
        """
        Get the appropriate extractor for a file path.

        Args:
            file_path: Path to the file.

        Returns:
            The extractor callable, or the default extractor if no match,
            or None if no default is registered.
        """
        path = Path(file_path) if isinstance(file_path, str) else file_path
        extension = path.suffix[1:].lower() if path.suffix else ""

        if extension in self._extractors:
            return self._extractors[extension]
        return self._default_extractor

    def extract(self, file_path: Union[str, Path]) -> Iterator[ExtractionResult]:
        """
        Extract text from a file using the appropriate extractor.

        Args:
            file_path: Path to the file.

        Yields:
            ExtractionResult objects from the file.

        Raises:
            ValueError: If no extractor is registered for the file type and no default exists.
        """
        extractor = self.get_extractor(file_path)
        if extractor is None:
            path = Path(file_path) if isinstance(file_path, str) else file_path
            extension = path.suffix[1:] if path.suffix else "(no extension)"
            raise ValueError(f"No extractor registered for extension: {extension}")

        logger.debug(f"Extracting content from file: {file_path}")
        yield from extractor(file_path)

    @property
    def registered_extensions(self) -> list[str]:
        """Return list of registered file extensions."""
        return list(self._extractors.keys())

    def has_default(self) -> bool:
        """Return True if a default extractor is registered."""
        return self._default_extractor is not None


# Standalone extractor functions for use with the registry

def extract_text(file_path: Union[str, Path]) -> Iterator[ExtractionResult]:
    """
    Extract text from a plain text file.

    Args:
        file_path: Path to the text file.

    Yields:
        ExtractionResult with the text content of the file.

    Raises:
        FileNotFoundError: If the file does not exist.
    """
    p = Path(file_path)
    if not p.exists():
        logger.error(f"Path does not exist: {file_path}")
        raise FileNotFoundError(f"Path does not exist: {file_path}")
    if not p.is_file():
        logger.error(f"Unsupported path type: {file_path}")
        raise FileNotFoundError(f"Unsupported path type: {file_path}")

    logger.debug(f"Reading text file: {p}")
    source_str = str(p.resolve())
    with p.open("r") as file:
        content = file.read()
        yield ExtractionResult(
            content=content,
            source=source_str,
            id=source_str,
            title=p.name
        )


def extract_docx(file_path: Union[str, Path]) -> Iterator[ExtractionResult]:
    """
    Extract text from a Microsoft Word (.docx) file.

    Args:
        file_path: Path to the .docx file.

    Yields:
        ExtractionResult with the text content of the document.

    Raises:
        FileNotFoundError: If the file does not exist.
    """
    p = Path(file_path)
    if not p.exists():
        logger.error(f"Path does not exist: {file_path}")
        raise FileNotFoundError(f"Path does not exist: {file_path}")
    if not p.is_file():
        logger.error(f"Unsupported path type: {file_path}")
        raise FileNotFoundError(f"Unsupported path type: {file_path}")

    logger.info(f"Reading docx file: {p}")
    source_str = str(p.resolve())
    doc = Document(p)
    full_text = []
    for para in doc.paragraphs:
        full_text.append(para.text)
    content = " ".join(full_text)
    yield ExtractionResult(
        content=content,
        source=source_str,
        id=source_str,
        title=p.name
    )


def skip_file(file_path: Union[str, Path]) -> Iterator[ExtractionResult]:
    """Default extractor that skips files by yielding nothing."""
    logger.debug(f"Skipping unsupported file: {file_path}")
    if False:
        yield


def get_default_registry() -> ExtractorRegistry:
    """
    Get a new ExtractorRegistry pre-populated with default extractors.

    Returns:
        ExtractorRegistry with txt, md, and docx extractors registered,
        and a default skip handler.
    """
    registry = ExtractorRegistry()
    registry.register("txt", extract_text)
    registry.register("md", extract_text)
    registry.register("docx", extract_docx)
    registry.register_default(skip_file)
    return registry


# Global registry instance pre-populated with default extractors.
# Use this to register additional extractors that will be available application-wide.
global_extractor_registry = get_default_registry()


@register_segment("readtxt")
@field_segment(multi_emit=True)
def readtxt(file_path: Annotated[str, "Path to the text file to read"]):
    """
    Reads text files from given file paths or directories and yields their contents.

    Yields:
        ExtractionResult: Result containing content, source path, id, and title.

    Raises:
        FileNotFoundError: If a path does not exist.
        IOError: If there is an error reading any of the files.
    """
    yield from extract_text(file_path)


@register_segment("readdocx")
@field_segment(multi_emit=True)
def readdocx(file_path: Annotated[str, "Path to the .docx file to read"]):
    """Read and extract text from Microsoft Word (.docx) files.

    Yields:
        ExtractionResult: Result containing content, source path, id, and title.

    Raises:
        FileNotFoundError: If a path does not exist.
        IOError: If there is an error reading any of the files.

    """
    yield from extract_docx(file_path)

@register_segment("listFiles")
@segment()
def listFiles(patterns: Annotated[Iterable[str], "Iterable of file patterns or paths (supports wildcards like *, ?, [])"], full_path: Annotated[bool, "Whether to yield full absolute paths or just filenames"] = True, files_only: Annotated[bool, "Whether to include only files (excluding directories)"] = False):
    """List files matching given glob patterns and yield their paths.
    
    Takes file patterns (supporting standard glob wildcards) and yields matching file
    paths. Glob patterns support:
    - * : matches any number of characters in a filename
    - ? : matches exactly one character
    - [abc] : matches any character in the brackets
    - ** : matches across directories (recursive)
    
    Patterns are expanded to include home directory (~) and environment variables.
    If a pattern contains no wildcards and is a directory, all files in that directory
    are implicitly searched.
    
    Useful for:
    - Discovering files by pattern (e.g., all CSV files)
    - Finding files by name (e.g., log files)
    - Batch processing multiple files matching a pattern
    - Building file lists for pipelines
    
    Yields:
        Absolute paths if full_path=True, just filenames if full_path=False.
    
    Examples:
        listFiles(["*.txt"]) - all text files in current directory
        listFiles(["/data/**/*.csv"]) - all CSV files under /data recursively
        listFiles(["~/Documents"]) - all files in ~/Documents
    """
    for pattern in patterns:
        expanded_pattern = os.path.expanduser(pattern)
        
        # If no wildcard is provided and the path is a directory, add implied "/*"
        path = Path(expanded_pattern)
        if path.is_dir() and not any(char in expanded_pattern for char in ['*', '?', '[']):
            expanded_pattern = os.path.join(expanded_pattern, '*')

        logger.info(f"Searching for files matching pattern: {expanded_pattern}")
        matches = glob.glob(expanded_pattern, recursive=True)
        
        for match in sorted(matches):
            path = Path(match)
            if path.is_file() or (not files_only and path.is_dir()):
                if full_path:
                    yield str(path.resolve())
                else:
                    yield path.name
            else:
                logger.debug(f"Skipping non-file: {match}")

@register_segment("readFile")
class ReadFile(AbstractFieldSegment):
    """
    A class for extracting text content from different file types.

    This class implements the AbstractSegment interface and provides functionality to extract
    text content from various file formats using an ExtractorRegistry. It supports multiple
    file formats and can be extended with additional extractors.

    This is a multi-emit segment, meaning extractors can yield multiple items per file
    (e.g., CSV rows, JSONL lines) or a single item.

    By default, uses the global_extractor_registry which has txt, md, and docx extractors
    registered, and skips unsupported files. To raise an error on unsupported files instead
    of skipping, pass skip_unsupported=False.

    Attributes:
        _registry (ExtractorRegistry): Registry mapping file extensions to extractor functions.
        _skip_unsupported (bool): Whether to skip unsupported files (True) or raise an error (False).

    Methods:
        register_extractor(file_extension: str, extractor): Register a new file extractor for a specific extension.
        process_value(file_path: Union[str, PosixPath]): Extract content from a single file.

    """
    _registry: ExtractorRegistry
    _skip_unsupported: bool

    def __init__(self, field: str = None, set_as: str = None, skip_unsupported: bool = True,
                 registry: ExtractorRegistry = None):
        """
        Initialize ReadFile with an optional custom registry.

        Args:
            field: Field name to extract from input items.
            set_as: Field name to set the result as.
            skip_unsupported: If True, skip files with unsupported extensions.
                             If False, raise an error for unsupported files.
            registry: Optional custom ExtractorRegistry. If None, uses global_extractor_registry.
        """
        super().__init__(field=field, set_as=set_as, multi_emit=True)
        logger.debug("Initializing ReadFile")
        self._skip_unsupported = skip_unsupported

        if registry is not None:
            self._registry = registry
        else:
            self._registry = global_extractor_registry

    def register_extractor(self, file_extension: str, extractor: ExtractorFunc):
        """
        Register a new file extractor for a specific extension.

        Args:
            file_extension: File extension without the dot (e.g., 'txt', 'docx').
            extractor: Callable that takes a file path and yields extracted text strings.
        """
        self._registry.register(file_extension, extractor)

    def process_value(self, file_path: Union[str, PosixPath]) -> Iterator[ExtractionResult]:
        """
        Extract content from a single file.

        Args:
            file_path: Path to the file to extract.

        Yields:
            ExtractionResult objects containing extracted content, source path, id, and title.

        Raises:
            Exception: If the file extension is not supported and skip_unsupported is False.
        """
        path = Path(file_path) if isinstance(file_path, str) else file_path
        extension = path.suffix[1:].lower() if path.suffix else ""

        # Check if there's a specific extractor for this extension
        if extension not in self._registry.registered_extensions:
            if not self._skip_unsupported:
                logger.error(f"Unsupported file extension: {extension}")
                raise Exception(f"File extension {extension} not supported")
            # Use default extractor (skip_file) if skip_unsupported is True
            extractor = self._registry.get_extractor(file_path)
            if extractor is None:
                logger.error(f"Unsupported file extension: {extension}")
                raise Exception(f"File extension {extension} not supported")
        else:
            extractor = self._registry.get_extractor(file_path)

        logger.debug(f"Extracting content from file: {file_path}")
        yield from extractor(file_path)

