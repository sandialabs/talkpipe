"""This module contains segments for extracting text from files."""

from typing import Union, Iterable, Annotated, Callable, Optional, Iterator
from functools import partial
import gc
import logging
import csv
import json
from pydantic import BaseModel, ConfigDict
import glob
import os
from pathlib import PosixPath, Path
from docx import Document
from talkpipe.pipe.core import segment, AbstractFieldSegment, field_segment
from talkpipe.chatterlang.registry import register_segment
from .html import htmlToText


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

def extract_html(file_path: Union[str, Path]) -> Iterator[ExtractionResult]:
    """
    Extract readable text from an HTML file.
    """
    result = next(extract_text(file_path))
    raw_html = result.content
    readable_text = htmlToText(raw_html)
    result.content = readable_text
    result.raw_html = raw_html
    yield result


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


def extract_csv(file_path: Union[str, Path], delimiter: str = ',') -> Iterator[ExtractionResult]:
    """
    Extract rows from a delimited text file, yielding each row as an ExtractionResult.

    For each row, if a column name matches an ExtractionResult field
    (content, source, id, title), that value is used. Otherwise:
    - content: string representation of all fields
    - source: the file path
    - id: file path plus row number
    - title: filename plus row number

    Any additional columns are passed through as extra fields.

    Args:
        file_path: Path to the CSV/TSV file.
        delimiter: Column delimiter character (default ',').

    Yields:
        ExtractionResult for each row.

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

    logger.debug(f"Reading CSV file: {p}")
    source_str = str(p.resolve())
    extraction_fields = {'content', 'source', 'id', 'title'}

    with p.open("r", newline='', encoding='utf-8') as file:
        reader = csv.DictReader(file, delimiter=delimiter)
        for row_num, row in enumerate(reader, start=1):
            # Build ExtractionResult fields, using CSV values if present
            result_fields = {}

            if 'content' in row:
                result_fields['content'] = row['content']
            else:
                result_fields['content'] = ', '.join(f"{k}: {v}" for k, v in row.items())

            if 'source' in row:
                result_fields['source'] = row['source']
            else:
                result_fields['source'] = source_str

            if 'id' in row:
                result_fields['id'] = row['id']
            else:
                result_fields['id'] = f"{source_str}:{row_num}"

            if 'title' in row:
                result_fields['title'] = row['title']
            else:
                result_fields['title'] = f"{p.name}:{row_num}"

            # Add all CSV fields as extra fields (excluding ones already in result_fields)
            extra_fields = {k: v for k, v in row.items() if k not in extraction_fields}
            yield ExtractionResult(**result_fields, **extra_fields)


def extract_jsonl(file_path: Union[str, Path]) -> Iterator[ExtractionResult]:
    """
    Extract lines from a JSONL file, yielding each line as an ExtractionResult.

    For each line, if the JSON value is a dictionary and has keys matching
    ExtractionResult fields (content, source, id, title), those values are used.
    Otherwise:
    - content: string value (if string) or JSON representation of the value
    - source: the file path
    - id: file path plus line number
    - title: filename plus line number

    For dictionaries, all keys are passed through as extra fields.
    For non-dict values, the original value is stored in a 'value' extra field.

    Args:
        file_path: Path to the JSONL file.

    Yields:
        ExtractionResult for each non-empty line in the JSONL file.

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

    logger.debug(f"Reading JSONL file: {p}")
    source_str = str(p.resolve())
    extraction_fields = {'content', 'source', 'id', 'title'}

    with p.open("r", encoding='utf-8') as file:
        for line_num, line in enumerate(file, start=1):
            line = line.strip()
            if not line:
                continue  # Skip empty lines

            data = json.loads(line)

            result_fields = {}
            extra_fields = {}

            if isinstance(data, dict):
                # Dictionary: check for matching ExtractionResult fields
                if 'content' in data:
                    result_fields['content'] = str(data['content'])
                else:
                    result_fields['content'] = ', '.join(f"{k}: {v}" for k, v in data.items())

                if 'source' in data:
                    result_fields['source'] = str(data['source'])
                else:
                    result_fields['source'] = source_str

                if 'id' in data:
                    result_fields['id'] = str(data['id'])
                else:
                    result_fields['id'] = f"{source_str}:{line_num}"

                if 'title' in data:
                    result_fields['title'] = str(data['title'])
                else:
                    result_fields['title'] = f"{p.name}:{line_num}"

                # Add all dict fields as extra fields (excluding standard fields)
                extra_fields = {k: v for k, v in data.items() if k not in extraction_fields}
            else:
                # Non-dict: use value directly for content if string, else JSON representation
                if isinstance(data, str):
                    result_fields['content'] = data
                else:
                    result_fields['content'] = json.dumps(data)

                result_fields['source'] = source_str
                result_fields['id'] = f"{source_str}:{line_num}"
                result_fields['title'] = f"{p.name}:{line_num}"

                # Store original value as extra field
                extra_fields['value'] = data

            yield ExtractionResult(**result_fields, **extra_fields)


extract_tsv = partial(extract_csv, delimiter='\t')
extract_tsv.__doc__ = "Extract rows from a TSV (tab-separated) file. See extract_csv."


def extract_json(file_path: Union[str, Path]) -> Iterator[ExtractionResult]:
    """
    Extract content from a JSON file, yielding a single ExtractionResult.

    If the JSON value is a dictionary and has keys matching ExtractionResult
    fields (content, source, id, title), those values are used.  All dict keys
    are passed through as extra fields.  Non-dict values use the same logic as
    extract_jsonl (string used directly, others JSON-serialised).

    Args:
        file_path: Path to the JSON file.

    Yields:
        A single ExtractionResult for the file.

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

    logger.debug(f"Reading JSON file: {p}")
    source_str = str(p.resolve())
    extraction_fields = {'content', 'source', 'id', 'title'}

    with p.open("r", encoding="utf-8") as f:
        data = json.load(f)

    result_fields: dict = {}
    extra_fields: dict = {}

    if isinstance(data, dict):
        result_fields['content'] = str(data['content']) if 'content' in data else ', '.join(f"{k}: {v}" for k, v in data.items())
        result_fields['source'] = str(data['source']) if 'source' in data else source_str
        result_fields['id'] = str(data['id']) if 'id' in data else source_str
        result_fields['title'] = str(data['title']) if 'title' in data else p.name
        extra_fields = {k: v for k, v in data.items() if k not in extraction_fields}
    else:
        result_fields['content'] = data if isinstance(data, str) else json.dumps(data)
        result_fields['source'] = source_str
        result_fields['id'] = source_str
        result_fields['title'] = p.name
        extra_fields['value'] = data

    yield ExtractionResult(**result_fields, **extra_fields)


def extract_pdf(file_path: Union[str, Path]) -> Iterator[ExtractionResult]:
    """
    Extract text from a PDF file.

    Requires the pypdf package. Install with: pip install talkpipe[pypdf]

    Args:
        file_path: Path to the PDF file.

    Yields:
        ExtractionResult with the text content of the document.

    Raises:
        FileNotFoundError: If the file does not exist.
        ImportError: If pypdf is not installed.
    """
    try:
        from pypdf import PdfReader
    except ImportError:
        raise ImportError(
            "PDF extraction requires pypdf. Install it with: pip install talkpipe[pypdf]"
        ) from None

    p = Path(file_path)
    if not p.exists():
        logger.error(f"Path does not exist: {file_path}")
        raise FileNotFoundError(f"Path does not exist: {file_path}")
    if not p.is_file():
        logger.error(f"Unsupported path type: {file_path}")
        raise FileNotFoundError(f"Unsupported path type: {file_path}")

    def read_all_pages(path):
        reader = PdfReader(path)
        text_parts = []
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)
        return "\n\n".join(text_parts) if text_parts else ""

    logger.info(f"Reading PDF file: {p}")
    source_str = str(p.resolve())
    content = read_all_pages(p)
    # pypdf's reader graph is full of reference cycles, and parsing a large
    # file promotes it to GC generation 2, where dead readers pile up between
    # rare full collections and fragment the heap so RSS never comes back
    # down over a long ingest. Collect now that the reader is out of scope.
    gc.collect()
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
        ExtractorRegistry with txt, md, docx, and csv extractors registered,
        and a default skip handler.
    """
    registry = ExtractorRegistry()
    registry.register("txt", extract_text)
    registry.register("md", extract_text)
    registry.register("rst", extract_text)
    registry.register("html", extract_html)
    registry.register("htm", extract_html)
    registry.register("docx", extract_docx)
    registry.register("pdf", extract_pdf)
    registry.register("csv", extract_csv)
    registry.register("tsv", extract_tsv)
    registry.register("json", extract_json)
    registry.register("jsonl", extract_jsonl)
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


@register_segment("readhtml")
@field_segment(multi_emit=True)
def readhtml(file_path: Annotated[str, "Path to the HTML file to read"]):
    """Read and extract readable text from HTML files.

    Yields:
        ExtractionResult: Result containing readable text as content,
                         raw HTML preserved in the raw_html field,
                         and source path, id, and title.

    Raises:
        FileNotFoundError: If a path does not exist.
    """
    yield from extract_html(file_path)


@register_segment("readjson")
@field_segment(multi_emit=True)
def readjson(file_path: Annotated[str, "Path to the JSON file to read"]):
    """Read and extract content from a JSON file.

    Yields:
        ExtractionResult: A single result for the file. If the JSON is a
                         dictionary, keys matching ExtractionResult fields
                         are used; all keys are passed through as extra fields.

    Raises:
        FileNotFoundError: If a path does not exist.
    """
    yield from extract_json(file_path)


@register_segment("readtsv")
@field_segment(multi_emit=True)
def readtsv(file_path: Annotated[str, "Path to the TSV file to read"]):
    """Read and extract rows from a TSV (tab-separated) file.

    Each row is emitted as an ExtractionResult, following the same logic
    as readcsv but with tab delimiters.

    Yields:
        ExtractionResult: Result for each row.

    Raises:
        FileNotFoundError: If a path does not exist.
    """
    yield from extract_tsv(file_path)


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


@register_segment("readpdf")
@field_segment(multi_emit=True)
def readpdf(file_path: Annotated[str, "Path to the PDF file to read"]):
    """Read and extract text from PDF files.

    Requires the pypdf package. Install with: pip install talkpipe[pypdf]

    Yields:
        ExtractionResult: Result containing content, source path, id, and title.

    Raises:
        FileNotFoundError: If a path does not exist.
        ImportError: If pypdf is not installed.
    """
    yield from extract_pdf(file_path)


@register_segment("readcsv")
@field_segment(multi_emit=True)
def readcsv(file_path: Annotated[str, "Path to the CSV file to read"]):
    """Read and extract rows from a CSV file.

    Each row is emitted as an ExtractionResult. If a CSV column name matches
    an ExtractionResult field (content, source, id, title), that value is used.
    Otherwise, content is a string of all fields, source is the file path,
    id is path plus row number, and title is filename plus row number.
    Additional CSV columns are passed through as extra fields.

    Yields:
        ExtractionResult: Result for each row containing content, source, id, title,
                         and any additional CSV columns as extra fields.

    Raises:
        FileNotFoundError: If a path does not exist.
        IOError: If there is an error reading the file.

    """
    yield from extract_csv(file_path)


@register_segment("readjsonl")
@field_segment(multi_emit=True)
def readjsonl(file_path: Annotated[str, "Path to the JSONL file to read"]):
    """Read and extract lines from a JSONL file.

    Each non-empty line is emitted as an ExtractionResult. If the JSON value is
    a dictionary with keys matching ExtractionResult fields (content, source, id,
    title), those values are used. Otherwise, content is the string value (for
    strings) or JSON representation (for other types), source is the file path,
    id is path plus line number, and title is filename plus line number.

    For dictionaries, all keys are passed through as extra fields.
    For non-dict values, the original value is stored in a 'value' extra field.

    Yields:
        ExtractionResult: Result for each line containing content, source, id, title,
                         and any additional fields from the JSON data.

    Raises:
        FileNotFoundError: If a path does not exist.
        IOError: If there is an error reading the file.

    """
    yield from extract_jsonl(file_path)


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

@register_segment("readFile", "fileToText")
class ReadFile(AbstractFieldSegment):
    """
    A segment for extracting text content from different file types.

    This class implements the AbstractSegment interface and provides functionality to extract
    text content from various file formats using an ExtractorRegistry. It supports multiple
    file formats and can be extended with additional extractors.

    This is a multi-emit segment, meaning extractors can yield multiple items per file
    or a single item.

    By default, uses the global_extractor_registry which has txt, md, and docx extractors
    registered by defualt, and skips unsupported files. Plugins or applications can register
    additional extractors.

    To raise an error on unsupported
    files instead of skipping, pass skip_unsupported=False.

    A file with a supported extension can still fail to be read (for example a
    truncated or corrupt PDF). By default such a file is logged and skipped so a
    single bad file does not abort a large batch. To raise the extraction error
    instead of skipping, pass skip_errors=False.

    """
    _registry: ExtractorRegistry
    _skip_unsupported: bool
    _skip_errors: bool

    def __init__(self, field: str = None, set_as: str = None, skip_unsupported: bool = True,
                 skip_errors: bool = True, registry: ExtractorRegistry = None):
        """
        Initialize ReadFile with an optional custom registry.

        Args:
            field: Field name to extract from input items.
            set_as: Field name to set the result as.
            skip_unsupported: If True, skip files with unsupported extensions.
                             If False, raise an error for unsupported files.
            skip_errors: If True, log and skip files whose extractor raises an
                         error (e.g. a corrupt PDF) and continue with the next
                         file. If False, re-raise the error.
            registry: Optional custom ExtractorRegistry. If None, uses global_extractor_registry.
        """
        super().__init__(field=field, set_as=set_as, multi_emit=True)
        logger.debug("Initializing ReadFile")
        self._skip_unsupported = skip_unsupported
        self._skip_errors = skip_errors

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
            Exception: If the extractor fails to read the file and skip_errors is False.
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
        try:
            yield from extractor(file_path)
        except Exception as exc:
            if not self._skip_errors:
                raise
            logger.warning(
                f"Skipping file that could not be read: {file_path} "
                f"({type(exc).__name__}: {exc})"
            )

