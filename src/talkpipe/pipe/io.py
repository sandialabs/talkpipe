"""Utility segments and sources for io operations.
"""
from typing import Optional, Iterable, Iterator
import logging
import os
import pickle
import json
from pprint import pformat
from prompt_toolkit import PromptSession

from talkpipe.chatterlang.registry import register_source, register_segment
import talkpipe.chatterlang.registry as registry
from talkpipe.pipe.core import AbstractSource, source, AbstractSegment, segment
from talkpipe.util import data_manipulation


@registry.register_segment(name="print")
class Print(AbstractSegment):
    """
    An operation prints and passes on each item from the input stream.
    """

    def __init__(self, pprint: Optional[bool] = False, field_list: Optional[str] = None):
        super().__init__()
        self.pprint = pprint
        self.field_list = field_list

    def transform(self, input_iter: Iterable[int]) -> Iterator[int]:
        """
        Execute the operation on an iterable input.

        Args:
            input_iter (Iterable[int]): Iterable input data

        Yields:
            int: Each element of the input iterable
        """
        for x in input_iter:
            to_print = x
            if self.field_list is not None:
                to_print = data_manipulation.toDict(x, self.field_list)
            print(pformat(to_print) if self.pprint else to_print)
            yield x

@registry.register_segment(name="log")
class Log(AbstractSegment):
    """
    An operation that logs each item from the input stream.
    """

    def __init__(self, level: Optional[str] = 'INFO', field_list: Optional[str] = None, log_name: Optional[str] = None):
        super().__init__()
        self.level = level
        self.field_list = field_list
        self.log_name = log_name
        self.logger = logging.getLogger(log_name)

    def transform(self, input_iter: Iterable[int]) -> Iterator[int]:
        """
        Execute the operation on an iterable input.

        Args:
            input_iter (Iterable[int]): Iterable input data

        Yields:
            int: Each element of the input iterable
        """
        for x in input_iter:
            to_log = x
            if self.field_list is not None:
                to_log = data_manipulation.toDict(x, self.field_list)
            self.logger.log(logging.getLevelNamesMapping()[self.level], pformat(to_log))
            yield x


@register_source('prompt')
class Prompt(AbstractSource):
    """A source that generates input from a prompt.
    
    This source will generate input from a prompt until the user enters an EOF.
    It is for creating interactive pipelines.  It uses prompt_toolkit under the
    hood to provide a nice prompt experience.
    """

    def __init__(self):
        super().__init__()
        self.session = PromptSession()

    def generate(self) -> Iterable[str]:
        while True:
            try:
                yield self.session.prompt('> ')
            except EOFError:
                break

@register_source('echo')
@source(delimiter=',')
def echo(data, delimiter):
    """A source that generates input from a string.

    This source will generate input from a string, splitting it on a delimiter.
    """
    if delimiter is None:
        yield data
    else:
        for item in data.split(delimiter):
            yield item

@register_segment('readJsonl')
@segment()
def readJsonl(fnames: Iterable[str]):
    """Reads each item from the input stream as a path to a jsonl file. Loads each line of
    each file as a json object and yields each individually.

    """
    for fname in fnames:
        with open(fname, 'r') as f:
            for line in f:
                yield json.loads(line)

@register_segment("loadsJsonl")
@segment()
def loadsJsonl(data: Iterable[str]):
    """Reads each item from the input stream, interpreting it as a jsonl string. 
    
    """
    for line in data:
        yield json.loads(line)

@register_segment('dumpsJsonl')
@segment()
def dumpsJsonl(data: Iterable):
    """Drains the input stream and dumps each item as a jsonl string.
    """
    for item in data:
        yield json.dumps(item) 

@register_segment('writePickle')
@segment()
def writePickle(data, fname: str, first_only: bool = False):
    """Drains the input stream into a list and then writes the list as a pickle file.

    Args:
        fname (str): The name of the file to write.
        first_only (bool): If True, the segment will write only the first item in the input stream,
            throwing an exception if there is more than one.
            If False, the segment will write the entire input stream.
    """
    everything = list(data)
    if first_only:
        assert len(everything) == 1, "first_only is True, but there is more than one item to write"
        everything = everything[0]
    with open(os.path.expanduser(fname), 'wb') as f:
        pickle.dump(everything, f)
    yield everything