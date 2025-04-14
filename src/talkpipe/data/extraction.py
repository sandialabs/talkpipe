"""This module contains segments for extracting text from files."""

from typing import Union, Iterable
from pathlib import PosixPath
from docx import Document
from talkpipe.pipe.core import segment, AbstractSegment
from talkpipe.chatterlang.registry import register_segment
import logging

@register_segment("readtxt")
@segment
def readtxt(items: Iterable[str]):
    """
    Reads text files from given file paths and yields their contents.

    Args:
        file_paths (Iterable[str]): An iterable containing paths to text files to be read.

    Yields:
        str: The contents of each text file.

    Raises:
        FileNotFoundError: If a file path does not exist.
        IOError: If there is an error reading any of the files.

    Example:
        >>> files = ['file1.txt', 'file2.txt']
        >>> for content in readtxt(files):
        ...     print(content)
    """
    for file_path in items:
        logging.info(f"Reading text file: {file_path}")
        with open(file_path, "r") as file:
            yield file.read()
        
@register_segment("readdocx")
@segment
def readdocx(items: Iterable[str]):
    """Read and extract text from Microsoft Word (.docx) files.

    This function takes an iterable of file paths to .docx documents and yields the
    extracted text content from each document, with paragraphs joined by spaces.

    Yields:
        str: The full text content of each document with paragraphs joined by spaces

    Raises:
        Exception: If there are issues reading the .docx files

    Example:
        >>> paths = ['doc1.docx', 'doc2.docx']
        >>> for text in readdocx(paths):
        ...     print(text)
    """
    for file_path in items:
        logging.info(f"Reading docx file: {file_path}")
        doc = Document(file_path)
        full_text = []
        for para in doc.paragraphs:
            full_text.append(para.text)
        yield " ".join(full_text)

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
