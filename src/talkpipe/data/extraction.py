"""This module contains segments for extracting text from files."""

from typing import Union, Iterable
from pathlib import PosixPath
from docx import Document
from talkpipe.pipe.core import segment, AbstractSegment, field_segment
from talkpipe.chatterlang.registry import register_segment, register_source
import logging
from pathlib import Path
import glob
import os

@register_segment("readtxt")
@field_segment()
def readtxt(file_path):
    """
    Reads text files from given file paths or directories and yields their contents.

    If an item is a directory, it will scan the directory (recursively by default)
    and read all .txt files.

    Args:
        items (Iterable[str]): Iterable of file or directory paths.
        recursive (bool): Whether to scan directories recursively for .txt files.

    Yields:
        str: The contents of each text file.

    Raises:
        FileNotFoundError: If a path does not exist.
        IOError: If there is an error reading any of the files.
    """

    p = Path(file_path)

    if not p.exists():
        logging.error(f"Path does not exist: {file_path}")
        raise FileNotFoundError(f"Path does not exist: {file_path}")

    if p.is_file():
        logging.info(f"Reading text file: {p}")
        with p.open("r") as file:
            return file.read()
    else:
        logging.error(f"Unsupported path type: {file_path}")
        raise FileNotFoundError(f"Unsupported path type: {file_path}")
        
@register_segment("readdocx")
@field_segment()
def readdocx(file_path):
    """Read and extract text from Microsoft Word (.docx) files.

    If an item is a directory, it will scan the directory (recursively by default)
    and read all .docx files.

    Args:
        items (Iterable[str]): Iterable of file or directory paths.
        recursive (bool): Whether to scan directories recursively for .docx files.

    Yields:
        str: The full text content of each document with paragraphs joined by spaces

    Raises:
        FileNotFoundError: If a path does not exist.
        IOError: If there is an error reading any of the files.

    """
    p = Path(file_path)

    if not p.exists():
        logging.error(f"Path does not exist: {file_path}")
        raise FileNotFoundError(f"Path does not exist: {file_path}")

    if p.is_file():
        logging.info(f"Reading docx file: {p}")
        doc = Document(p)
        full_text = []
        for para in doc.paragraphs:
            full_text.append(para.text)
        return " ".join(full_text)
    else:
        logging.error(f"Unsupported path type: {file_path}")
        raise FileNotFoundError(f"Unsupported path type: {file_path}")

@register_segment("listFiles")
@segment()
def listFiles(patterns: Iterable[str], full_path: bool = True, files_only: bool = False):
    """
    Lists files matching given patterns (potentially with wildcards) and yields their paths.

    Args:
        patterns (Iterable[str]): Iterable of file patterns or paths (supports wildcards like *, ?, []).
        full_path (bool): Whether to yield full absolute paths or just filenames.
        files_only (bool): Whether to include only files (excluding directories).

    Yields:
        str: File paths (absolute if full_path=True, filenames if full_path=False).


    Raises:
        None: This function does not raise exceptions for non-matching patterns.
    """
    for pattern in patterns:
        expanded_pattern = os.path.expanduser(pattern)
        
        # If no wildcard is provided and the path is a directory, add implied "/*"
        path = Path(expanded_pattern)
        if path.is_dir() and not any(char in expanded_pattern for char in ['*', '?', '[']):
            expanded_pattern = os.path.join(expanded_pattern, '*')
        
        logging.info(f"Searching for files matching pattern: {expanded_pattern}")
        matches = glob.glob(expanded_pattern, recursive=True)
        
        for match in sorted(matches):
            path = Path(match)
            if path.is_file() or (not files_only and path.is_dir()):
                if full_path:
                    yield str(path.resolve())
                else:
                    yield path.name
            else:
                logging.debug(f"Skipping non-file: {match}")

@register_segment("extract")
class FileExtractor(AbstractSegment):
    """
    A class for extracting text content from different file types.

    This class implements the AbstractSegment interface and provides functionality to extract
    text content from various file formats using registered extractors. It supports multiple
    file formats and can be extended with additional extractors.

    Attributes:
        _extractors (dict): A dictionary mapping file extensions to their corresponding extractor functions.

    Methods:
        register_extractor(file_extension: str, extractor): Register a new file extractor for a specific extension.
        extract(file_path: Union[str, PosixPath]): Extract content from a single file.
        transform(input_iter): Transform an iterator of file paths into an iterator of their contents.

    Example:
        >>> extractor = FileExtractor()
        >>> content = extractor.extract("document.txt")
        >>> for text in extractor.transform(["file1.txt", "file2.docx"]):
        ...     print(text)

    Raises:
        Exception: When trying to extract content from a file with an unsupported extension.
    """
    _extractors:dict

    def __init__(self):
        super().__init__()
        logging.debug("Initializing FileExtractor")
        self._extractors = {}
        self.register_extractor("txt", readtxt())
        self.register_extractor("md", readtxt())
        self.register_extractor("docx", readdocx())

    def register_extractor(self, file_extension:str, extractor):
        logging.debug(f"Registering extractor for extension: {file_extension}")
        self._extractors[file_extension] = extractor

    def extract(self, file_path:Union[str, PosixPath]):
        file_extension = file_path.split(".")[-1] if isinstance(file_path, str) else file_path.suffix[1:]
        if file_extension not in self._extractors:
            logging.error(f"Unsupported file extension: {file_extension}")
            raise Exception(f"File extension {file_extension} not supported")
        logging.debug(f"Extracting content from file: {file_path}")
        return next(self._extractors[file_extension]([file_path]))

    def transform(self, input_iter):
        for file_path in input_iter:
            yield self.extract(file_path)
