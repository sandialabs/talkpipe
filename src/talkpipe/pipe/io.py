"""Utility segments and sources for io operations.
"""
from typing import Optional, Iterable, Iterator, Annotated
import logging
import os
import pickle  # nosec B403 - Used only for write operations, not loading untrusted data
import json
import traceback
from pprint import pformat
from prompt_toolkit import PromptSession

from talkpipe.chatterlang.registry import register_source, register_segment
import talkpipe.chatterlang.registry as registry
from talkpipe.pipe.core import AbstractSource, source, AbstractSegment, segment, Pipeline
from talkpipe.util import data_manipulation


class ErrorResilientPromptPipeline(Pipeline):
    """A special pipeline that handles errors in interactive prompt workflows.

    When a downstream segment raises an exception, this pipeline catches it,
    displays the error, and continues processing the next item from the prompt.
    """

    def __init__(self, prompt_source, *operations):
        super().__init__(prompt_source, *operations)
        self.prompt_source = prompt_source

    def transform(self, input_iter=None):
        """Execute pipeline with error resilience for prompt-based workflows."""
        # Get the prompt generator
        prompt_iter = self.prompt_source()

        # Build the downstream pipeline (everything after the prompt)
        downstream_ops = [op for op in self.operations if op is not self.prompt_source]

        # Process each prompt input with error handling
        for user_input in prompt_iter:
            try:
                # Create a single-item iterator for this input
                current_iter = iter([user_input])

                # Pass through each downstream operation
                for op in downstream_ops:
                    current_iter = op(current_iter)

                # Consume and yield results
                for result in current_iter:
                    yield result

            except Exception as e:
                # Catch and display errors, but continue prompting
                print(f"Error: {e}")
                traceback.print_exc()
                # Don't yield anything for this failed input, just continue to next prompt

    def __or__(self, other):
        """Support chaining additional operations to the error-resilient pipeline."""
        # Add the new operation to our operations list
        return ErrorResilientPromptPipeline(self.prompt_source, *self.operations[1:], other)


@registry.register_segment(name="print")
class Print(AbstractSegment):
    """
    An operation prints and passes on each item from the input stream.
    """

    def __init__(self, 
                 pprint: Annotated[Optional[bool], "If True, uses pformat for pretty printing"] = False, 
                 field_list: Annotated[Optional[str], "Comma-separated list of fields to extract and print"] = None):
        super().__init__()
        self.pprint = pprint
        self.field_list = field_list

    def transform(self, input_iter: Annotated[Iterable[int], "Iterable input data"]) -> Iterator[int]:
        """Execute the operation on an iterable input.

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

    def __init__(self, 
                 level: Annotated[Optional[str], "Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)"] = 'INFO', 
                 field_list: Annotated[Optional[str], "Comma-separated list of fields to extract and log"] = None, 
                 log_name: Annotated[Optional[str], "Name of the logger to use"] = None):
        super().__init__()
        self.level = level
        self.field_list = field_list
        self.log_name = log_name
        self.logger = logging.getLogger(log_name)

    def transform(self, input_iter: Annotated[Iterable[int], "Iterable input data"]) -> Iterator[int]:
        """Execute the operation on an iterable input.

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

    To enable error recovery (continue prompting after downstream errors), this source
    needs to actively consume the downstream pipeline with error handling. This is done
    by overriding the __or__ method to wrap the downstream in error handling.
    """

    def __init__(self, error_resilient: Annotated[bool, "If True, catches downstream errors and continues prompting"] = True):
        super().__init__()
        self.session = PromptSession()
        self.error_resilient = error_resilient

    def generate(self) -> Iterable[str]:
        while True:
            try:
                user_input = self.session.prompt('> ')
                yield user_input
            except EOFError:
                break
            except KeyboardInterrupt:
                print("\nInterrupted. Press Ctrl+D to exit or continue entering input.")
                continue

    def __or__(self, other):
        """Override to add error handling when chaining with other segments."""
        if self.error_resilient:
            # Register the downstream relationship
            self.registerDownstream(other)
            other.registerUpstream(self)

            # Return an error-resilient pipeline instead of a regular one
            return ErrorResilientPromptPipeline(self, other)
        else:
            # Use default behavior
            return super().__or__(other)

@register_source('echo')
@source(delimiter=',', n=1)
def echo(data: Annotated[str, "The input string to split and generate items from"],
         delimiter: Annotated[str, "The delimiter to split the string on"],
         n: Annotated[int, "Number of times to emit the data"] = 1):
    """A source that generates input from a string.

    This source will generate input from a string, splitting it on a delimiter,
    and optionally repeating the output n times.
    """
    if delimiter is None:
        items = [data]
    else:
        items = data.split(delimiter)

    for _ in range(n):
        for item in items:
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
def writePickle(data, 
                fname: Annotated[str, "The name of the file to write"], 
                field: Annotated[Optional[str], "Field to extract from each item before writing"] = None, 
                first_only: Annotated[bool, "If True, only the first item in the input stream is written"] = False):
    """Writes each item into a pickle file. If first_only is True, only the first item is written.
    In any event, all items are yielded.
    """
    first = True
    with open(os.path.expanduser(fname), 'wb') as f:
        for item in data:
            if not first_only or first:
                if field is not None:
                    item = data_manipulation.extract_property(item, field, fail_on_missing=True)
                pickle.dump(item, f)
                first = False
            yield item

@register_segment('writeString')
@segment()
def writeString(data, 
                fname: Annotated[str, "The name of the file to write"], 
                field: Annotated[Optional[str], "Field to extract from each item before writing"] = None, 
                new_line: Annotated[bool, "If True, a new line will be written after each item"] = True, 
                first_only: Annotated[bool, "If True, the segment will write only the first item in the input stream"] = False):
    """Writes each item into a file after casting it to a string.
    
    In any event, all items will be yielded.
    """
    first = True
    with open(os.path.expanduser(fname), 'w') as f:
        for item in data:
            if not first_only or first:
                if field is not None:
                    item = data_manipulation.extract_property(item, field, fail_on_missing=True)
                f.write(str(item))
                if new_line:
                    f.write('\n')
                first = False
            yield item


