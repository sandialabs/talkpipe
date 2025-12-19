"""Standard operations for data processing pipelines."""

from typing import Iterable, Iterator, Union, Optional, Any, Annotated
import logging
import time
import sys
import json
import hashlib
import copy
import threading
from queue import Queue
import pandas as pd
from talkpipe.util.config import configure_logger, parse_key_value_str, get_config
from talkpipe.util.data_manipulation import extract_property, extract_template_field_names, get_all_attributes, toDict, assign_property
from talkpipe.util.data_manipulation import compileLambda
from talkpipe.util.os import run_command
from talkpipe.util.data_manipulation import get_type_safely
from talkpipe.pipe.core import AbstractSegment, AbstractFieldSegment, source, segment, field_segment
import talkpipe.chatterlang.registry as registry
from talkpipe.util.data_manipulation import fill_template, dict_to_text, toDict

logger = logging.getLogger(__name__)

@registry.register_segment("diagPrint")
@segment()
def DiagPrint(
    items: Iterator[Any],
    field_list: Annotated[str,
        "Comma-separated fields to extract in form 'field[:new_name],...' where _ means the whole item"
    ] = "_",
    label: Annotated[
        Optional[str],
        "Optional label to print below the separator each time."
    ] = None,
    expression: Annotated[
        Optional[str],
        "A Python expression using 'item' as the variable (e.g., 'item * 2')"
    ] = None,
    output: Annotated[
        str,
        "If 'stderr', output to stderr.  If 'stdout', output to stdout.  Otherwise write to a logger with this name.  If None or the string 'None', do not write output."
    ] = "stdout",
    level: Annotated[str, "Logging level if output is to a logger."] = "DEBUG"
) -> Iterator[Any]:
    """
    Print pass-through diagnostics for each item in a stream.

    Behavior:
    - Emits a separator, optional label, elapsed time since the last item, type, and value.
    - Optionally prints selected fields (`field_list`) and an evaluated expression (`expression`).
    - Always yields the original items unchanged.

    Output routing:
    - `stdout` (default) prints to standard output.
    - `stderr` prints to standard error.
    - Any other string is treated as a logger name; messages are emitted at `level`.
    - `None` or `"None"` disables all output.
    - `config:<key>` looks up the target (stdout, stderr, or logger name) from `get_config()[<key>]`.

    Common uses:
    - Quick inspection while composing pipelines.
    - Lightweight timing between items (elapsed time column).
    - Field-focused debugging by passing `field_list="a,b,c"` to avoid dumping entire items.
    - Expression checks, e.g. `expression="item['score'] > 0.8"`.

    Examples:
    - Pipe API: `DiagPrint(label="chunk", field_list="id,text", output="stderr")`
    - ChatterLang: `| diagPrint[label="chunk", field_list="id,text", expression="len(item['text'])"]`
    - Config-driven: set `diag_output="stderr"` in your config, then use `output="config:diag_output"`.
    """
    # Track elapsed time between calls for this DiagPrint instance
    last_time: Optional[float] = None
    if output is None or output.lower() == "none":
        output_fn = None
    else:
        if output.lower().startswith("config:"):
            output = get_config().get(output[len("config:"):].strip(), None)
        if output and output.lower() == "stderr":
            output_fn = lambda msg: print(msg, file=sys.stderr, flush=True)
        elif output and output.lower() == "stdout":
            output_fn = lambda msg: print(msg, file=sys.stdout, flush=True)
        else:
            output_fn = lambda msg: logging.getLogger(output).log(msg=msg, level=logging.getLevelName(level.upper()))

    if expression:
        f = compileLambda(expression)

    for item in items:
        if output_fn:
            now = time.perf_counter()
            if last_time is None:
                elapsed_str = "0.000s"
            else:
                elapsed_str = f"{now - last_time:.3f}s"
            last_time = now
            output_fn("================================")
            if label:
                output_fn(label)
            output_fn(f"Elapsed: {elapsed_str} since last call")
            output_fn(f"Type: {type(item)}")
            if field_list != "_":
                output_fn("-------\nFields:")
                item_dict = toDict(item, field_list=field_list, fail_on_missing=False)
                for key, value in item_dict.items():
                    output_fn(f"{key}: {value}")
            else:
                output_fn("-------\nValue:")
                output_fn(f"{item}")
            if expression:
                output_fn("-------\nExpression:")
                output_fn(f"{expression} = {f(item)}")
        yield item

@registry.register_segment("sleep")
@segment()
def sleep(items, 
          seconds: Annotated[int, "The number of seconds to sleep after processing n items"],
          n: Annotated[int, "The number of items to process before sleeping"] = 1):
    """Sleep for a specified number of seconds after each n items.
    
    This segment introduces a delay between processing each item in the pipeline.
    Useful for rate limiting, testing timing-sensitive code, or simulating slow operations.
            
    Yields:
        Any: Each input item unchanged after the sleep delay.
    """
    count = 0
    for item in items:
        yield item  # Pass through the item unchanged
        count += 1
        if count % n == 0:
            time.sleep(seconds)  # Sleep after yielding to maintain pipeline flow

@registry.register_segment(name="progressTicks")
@segment()
def progressTicks(items, 
                  tick: Annotated[str, "The character to print as a tick mark."] = ".", 
                  tick_count: Annotated[int, "Number of items to process before printing a tick mark."] = 10, 
                  eol_count: Annotated[Optional[int], "Number of tick marks before starting a new line. If None, no new line is printed."] = 10, 
                  print_count: Annotated[bool, "If True, prints the count of items processed at line ends."] = False):
    """Display progress indicators while processing items in the pipeline.

    Prints tick marks to stderr to visualize processing progress without interfering 
    with the main data stream. Useful for monitoring long-running pipelines.

    ChatterLang Usage:
        progressTicks[tick="*", tick_count=100, eol_count=10, print_count=true]
                
    Yields:
        Any: The original items from the input iterable, unchanged.
    """
    count = 0
    for idx, item in enumerate(items, 1):
        if idx % tick_count == 0 and idx != 0:
            print(tick, end="", flush=True, file=sys.stderr)
            if eol_count and (idx // tick_count) % eol_count == 0:
                if print_count:
                    print(f"{idx}", end="", flush=True, file=sys.stderr)
                print(file=sys.stderr)
        count = idx
        yield item
    if print_count:
        print(f"\nTotal items processed: {count}", file=sys.stderr)

@registry.register_segment(name="firstN")
@segment()
def firstN(items, n: Annotated[int, "The number of items to yield."] = 1):
    """Yields the first n items from the input stream.
    
    Useful for sampling data, testing pipelines with limited data, or implementing
    pagination-like functionality.
    
    ChatterLang Usage:
        firstN[n=5]
        
    Args:
        items (Iterable): An iterable of items to process.
        n (int): The number of items to yield. Defaults to 1.
        
    Yields:
        Any: The first n items from the input stream."""
    for i, item in enumerate(items):
        if i < n:
            yield item
        else:
            break

@registry.register_segment(name="describe")
class DescribeData(AbstractSegment):
    """Returns a dictionary of all attributes of the input data.
    
    This is useful mostly for debugging and understanding the 
    structure of the data.
    """

    def __init__(self):
        super().__init__()

    def transform(self, input_iter: Iterable) -> Iterator:
        for data in input_iter:
            yield get_all_attributes(data)

@registry.register_segment(name="cast")
class Cast(AbstractSegment):
    """Casts the input data to a specified type.
    
    The type can be specified by passing a type object or a string representation of the type.
    The cast will optionally fail silently if the data cannot be cast to the specified type.
    This lets this segment also be used as a filter to remove data that cannot be cast.
    The cast occurs by calling the type object on the data.  
    """
    def __init__(self, 
                 cast_type: Annotated[Union[type, str], "The type to cast the data to."] , 
                 fail_silently: Annotated[bool, "Whether to fail silently if the cast fails."] = True):
        super().__init__()
        self.cast_type = cast_type if isinstance(cast_type, type) else get_type_safely(cast_type)
        self.fail_silently = fail_silently

    def transform(self, input_iter: Iterable) -> Iterator:
        """Cast each item in the input stream to the specified type.
        
        Args:
            input_iter (Iterable): The input data
        """
        for data in input_iter:
            try:
                yield self.cast_type(data)
            except (ValueError, TypeError):
                if not self.fail_silently:
                    raise ValueError(f"Could not cast {data} to {self.cast_type}")

@registry.register_segment(name="toDict")
class ToDict(AbstractSegment):
    """Creates a dictionary from the input data."""

    def __init__(self, 
                 field_list: Annotated[str, "A list of properties in field_list format to extract from the input data."] = "_", 
                 fail_on_missing: Annotated[bool, "Whether to fail on missing properties."] = True):
        """Convert each item in the input string into a dictionary based on the provided parameter list.

        """
        super().__init__()
        self.field_list = field_list
        self.fail_on_missing = fail_on_missing

    def transform(self, input_iter: Iterable) -> Iterator:
        for data in input_iter:
            ans = toDict(data, self.field_list, self.fail_on_missing)
            yield ans

@registry.register_segment("formatItem")
class FormattedItem(AbstractSegment):
    """
    Generate formatted output for specified fields in "Property: Value" format.
    
    This segment takes each input item and generates one formatted string output 
    containing all specified fields. Each field is in the format "Label: Value".
    
    Yields:
        str: One formatted string per input item containing all fields
    """
    
    def __init__(self, 
                 field_list: Annotated[str, "Comma-separated list of field:label pairs."] = "_", 
                 wrap_width: Annotated[int, "Width for text wrapping"] = 80, 
                 fail_on_missing: Annotated[bool, "Whether to fail if a field is missing"] = False, 
                 field_name_separator: Annotated[str, "Separator between property and value"] = ": ", 
                 field_separator: Annotated[str, "Separator between different fields"] = "\n", 
                 item_suffix: Annotated[str, "Suffix to append to each item"] = ""):
        super().__init__()
        self.field_list = field_list
        self.wrap_width = wrap_width
        self.field_name_separator = field_name_separator
        self.fail_on_missing = fail_on_missing
        self.field_separator = field_separator
        self.item_suffix = item_suffix

        # Parse field mappings
        self.field_list = field_list

    def transform(self, input_iter: Iterable) -> Iterator:
        """Transform each input item into a single formatted string"""
        for item in input_iter:
            d = toDict(item, self.field_list, self.fail_on_missing)
            # Use the standalone function to format the item
            formatted_string = dict_to_text(
                d,
                wrap_width=self.wrap_width,
                field_name_separator=self.field_name_separator,
                field_separator=self.field_separator,
                item_suffix=self.item_suffix
            )
            
            # Yield one string per item
            yield formatted_string

@registry.register_segment("setAs")
@field_segment
def setAs(item,
          field_list:Annotated[str, "Comma-separated list of field:label pairs."]):
    """Appends the specified fields to the input item.

    Equivalent to toDict except that the item is modified with the new key/value pairs
    rather than a new dictionary returned.

    Supports both dictionary-like objects and regular objects (including pydantic models).

    """
    new_vals = toDict(item, field_list)
    for k, v in new_vals.items():
        assign_property(item, k, v)
    return item

@registry.register_segment("extractProperty")
@field_segment
def extractProperty(item, 
                    property: Annotated[str, "The property to extract from the input item."]):
    """Extracts the specified property from the input item.

    Returns:
        The value of the specified property.
    """
    return extract_property(item, property)

@registry.register_segment("set")
@segment()
def assign(items: Annotated[Iterator[Any], "The input item to modify"],
           value: Annotated[Any, "The value to assign"],
           set_as: Annotated[str, "The field to assign the value to"]):
    """Set a field to a constant value on each item in the pipeline.
    
    This segment modifies each input item by setting a specified field to the same
    value for every item. The modified items are then passed through for downstream
    processing.
    
    Useful for adding metadata, enriching items with constants, or setting default values.
    Works with dictionaries, objects, and Pydantic models.
    
    Yields:
        Modified items with the specified field set to the given value.
    """
    for item in items:
        assign_property(item, set_as, value)
        yield item

@registry.register_segment(name="toDataFrame")
class ToDataFrame(AbstractSegment):
    """Drain all items from the input stream and emit a single DataFrame.

    The input data stream should be composed of dictionaries, where each 
    dictionary represents a row in the DataFrame.
    """

    def __init__(self):
        super().__init__()

    def transform(self, input_iter: Iterable) -> Iterator:
        """Create a DataFrame from the input data.
        
        This segment empties the generator before creating the DataFrame.

        Args:
            input_iter (Iterable): The input data
        """
        data = list(input_iter)
        if len(data) > 0 and isinstance(data[0], dict):
            yield pd.DataFrame(data)

@registry.register_segment(name="toList")
class ToList(AbstractSegment):
    """Drains the input stream and emits a list of all items."""

    def __init__(self):
        super().__init__()

    def transform(self, input_iter: Iterable) -> Iterator:
        yield list(input_iter)

@registry.register_source(name="exec")
@source()
def exec(command: Annotated[str, "The shell command to execute."]) -> Iterator:
    """Execute a shell command and yield each line from stdout as a data item.
    
    This source allows you to integrate shell commands into TalkPipe pipelines,
    streaming the output line by line for further processing.
    
    ChatterLang Usage:
        input exec[command="ls -la"]
        input exec[command="find /path -name '*.txt'"]
        
    Args:
        command (str): The shell command to execute.
        
    Yields:
        str: Each line from the command's stdout output.
    """
    yield from run_command(command)


@registry.register_segment("concat")
@segment(fields=None, delimiter="\n\n", set_as=None)
def concat(items, 
           fields: Annotated[str, "Comma-separated list of fields to concatenate."],
           delimiter: Annotated[str, "String to insert between concatenated fields."] = "\n\n", 
           set_as: Annotated[str, "If specified, adds concatenated result as new field with this name."] = None):
    """Concatenate specified fields from each item into a single string.
    
    This segment extracts multiple fields from each item, converts them to strings,
    and joins them with the specified delimiter. Can either replace the item with
    the concatenated string or add the result as a new field on the original item.
    
    Useful for combining text from multiple fields, creating composite keys, or
    generating summaries from item components.
    
    Yields:
        If set_as is specified: Original item with concatenated result added as new field.
        Otherwise: Just the concatenated string.
    """
    props = parse_key_value_str(fields)
    for item in items:
        ans = ""
        for i, prop in enumerate(props.items()):
            if i>0:
                ans +=delimiter
            ans += str(extract_property(item, prop[0]))            
        if set_as:
            assign_property(item, set_as, ans)
            yield item
        else:
            yield ans

@registry.register_segment("slice")
@field_segment()
def slice(item, range: Annotated[str, "String in format 'start:end' where both start and end are optional."] = None):
    """Slices a sequence using start and end indices.

    This function takes a sequence and a range string in the format "start:end" to slice the sequence.
    Both start and end indices are optional.

    Args:
        item: Any sequence that supports slicing (e.g., list, string, tuple)
        range (str, optional): String in format "start:end" where both start and end are optional.
            For example: "2:5", ":3", "4:", ":" are all valid. Defaults to None.

    Returns:
        The sliced sequence containing elements from start to end index.
        If range is None, returns a full copy of the sequence.

    Examples:
        >>> slice([1,2,3,4,5], "1:3")
        [2, 3]
        >>> slice("hello", ":3")
        "hel"
        >>> slice([1,2,3,4,5], "2:")
        [3, 4, 5]
    """
    if range is None:
        start=None
        end=None
    else:
        sstring, send = range.split(":")
        start = int(sstring) if len(sstring)>0 else None
        end = int(send) if len(send)>0 else None

    modified_data = item[start:end]
    return modified_data

@registry.register_segment("longestStr")
@segment()
def longestStr(items, 
               field_list: Annotated[str, "Comma-separated list of fields to check for longest string."],
               set_as: Annotated[str, "If specified, adds longest string as new field with this name."] = None):
    """Find the longest string value among specified fields in each item.
    
    Compares the string representations of multiple fields and returns the one
    with the greatest length. Non-string fields are converted to strings before
    comparison. Missing fields are ignored. If multiple fields have equal length,
    the first one is returned.
    
    Useful for selecting the most detailed description from multiple fields,
    or finding the fullest version of redundant data.
    
    Yields:
        The longest string found. If set_as is specified: original item with
        the longest string added as a new field. Otherwise: just the string.
    """
    fields = parse_key_value_str(field_list)
    for item in items:
        longest = ""
        for field in fields:
            data = extract_property(item, field, fail_on_missing=False)
            if data is None:
                continue
            if len(str(data)) > len(longest):
                longest = str(data)
        if set_as:
            assign_property(item, set_as, longest)
            yield item
        else:
            yield longest

@registry.register_segment("isIn")
@segment()
def isIn(items, 
         field: Annotated[str, "Field name to check for value"],
         value: Annotated[Any, "Value to check for in the field"],
         as_filter: Annotated[bool, "Whether to use this function as a filter. If false, only return True or False. If true, yield the item if the condition is true."] = True,
         set_as: Annotated[str, "If specified, the result will be added to this field in the item."] = None):
    """Check if a field contains a value, optionally filtering items.
    
    Tests whether a specified value is contained in a field using Python's 'in' operator.
    Can operate in two modes:
    - Filter mode (as_filter=True): yields items where the condition is true
    - Boolean mode (as_filter=False): yields boolean results for all items
    
    Useful for searching strings for substrings, checking list membership, or
    checking dictionary key existence.
    
    Yields:
        In filter mode: items where value is in the field.
        In boolean mode: True/False for each item.
        If set_as is specified: item with boolean result added as new field.
    """
    for item in items:
        data = extract_property(item, field)
        ans = value in data

        if set_as:
            assign_property(item, set_as, ans)
            to_return = item
        else:
            to_return = item if as_filter else ans

        if not as_filter or ans:
            yield to_return

@registry.register_segment("isNotIn")
@segment()
def isNotIn(items,
            field: Annotated[str, "Field name to check for value"],
            value: Annotated[Any, "Value to check for in the field"],
            as_filter: Annotated[bool, "Whether to use this function as a filter. If false, only return True or False. If true, yield the item if the condition is true."] = True,
            set_as: Annotated[str, "If specified, the result will be added to this field in the item."] = None):
    """Check if a field does not contain a value, optionally filtering items.
    
    Tests whether a specified value is NOT contained in a field using Python's 'not in' operator.
    Can operate in two modes:
    - Filter mode (as_filter=True): yields items where the condition is true
    - Boolean mode (as_filter=False): yields boolean results for all items
    
    Useful for excluding items with specific patterns, filtering out unwanted strings,
    or checking that values are absent.
    
    Yields:
        In filter mode: items where value is NOT in the field.
        In boolean mode: True/False for each item.
        If set_as is specified: item with boolean result added as new field.
    """
    for item in items:
        data = extract_property(item, field)
        ans = value not in data

        if set_as:
            assign_property(item, set_as, ans)
            to_return = item
        else:
            to_return = item if as_filter else ans

        if not as_filter or ans:
            yield to_return

@registry.register_segment("isTrue")
@segment()
def isTrue(items,
           as_filter: Annotated[bool, "Whether to use this function as a filter. If false, only return True or False. If true, yield the item if the condition is true."] = True,
           field: Annotated[str, "The field to check for truthiness. Defaults to '_', which means the entire item."] = "_",
           set_as: Annotated[str, "If specified, the result will be added to this field in the item."] = None):
    """Check if a field is truthy, optionally filtering items.
    
    Tests whether the specified field is considered true. A value is considered false
    if it is None, False, an integer 0, or an empty string. All other values are true.
    Can operate in two modes:
    - Filter mode (as_filter=True): yields items where the field is truthy
    - Boolean mode (as_filter=False): yields boolean results for all items
    
    Useful for filtering items by presence of content, non-empty fields, or truthy values.
    
    Yields:
        In filter mode: items where the field is truthy.
        In boolean mode: True/False for each item.
        If set_as is specified: item with boolean result added as new field.
    """
    for item in items:
        to_eval = extract_property(item, field)
        # Check if value is truthy (not None, False, 0, or empty string)
        ans = bool(to_eval) and (to_eval != 0) and (not isinstance(to_eval, str) or len(to_eval.strip()) > 0)

        if set_as:
            assign_property(item, set_as, ans)
            to_return = item
        else:
            to_return = item if as_filter else ans

        if not as_filter or ans:
            yield to_return

@registry.register_segment("isFalse")
@segment()
def isFalse(items,
             as_filter: Annotated[bool, "Whether to use this function as a filter. If false, only return True or False. If true, yield the item if the condition is true."] = True,
             field: Annotated[str, "The field to check for falsiness. Defaults to '_', which means the entire item."] = "_",
             set_as: Annotated[str, "If specified, the result will be added to this field in the item."] = None):
    """Check if a field is falsy, optionally filtering items.
    
    Tests whether the specified field is considered false. A value is considered false
    if it is None, False, an integer 0, or an empty string. All other values are true.
    Can operate in two modes:
    - Filter mode (as_filter=True): yields items where the field is falsy
    - Boolean mode (as_filter=False): yields boolean results for all items
    
    Useful for filtering items with missing data, empty fields, or falsy values.
    
    Yields:
        In filter mode: items where the field is falsy.
        In boolean mode: True/False for each item.
        If set_as is specified: item with boolean result added as new field.
    """
    for item in items:
        to_eval = extract_property(item, field)
        # Check if value is falsy (None, False, 0, or empty string)
        ans = not (bool(to_eval) and (to_eval != 0) and (not isinstance(to_eval, str) or len(to_eval.strip()) > 0))

        if set_as:
            assign_property(item, set_as, ans)
            to_return = item
        else:
            to_return = item if as_filter else ans

        if not as_filter or ans:
            yield to_return

@registry.register_segment("everyN")
@segment()
def everyN(items, n: Annotated[int, "Number of items to skip between each yield"]):
    """Yield every nth item from the input stream, creating a sampling effect.
    
    This segment yields only items at positions that are multiples of n, effectively
    sampling every nth item from the stream. Useful for reducing data volume, creating
    summaries, or testing with subset of large datasets.
    
    For example, with n=5: yields items 5, 10, 15, 20, etc. (items at positions 5, 10, 15...).
    With n=1: yields all items. With n=2: yields every other item.
    
    Yields:
        Every nth item from the input stream.
    """
    for i, item in enumerate(items):
        if (i+1) % n == 0:
            yield item

@registry.register_segment("flatten")
@field_segment(multi_emit=True)
def flatten(item):
    """Flatten a nested collection by emitting its individual elements.
    
    For dictionaries: yields key-value tuples (like .items())
    For iterables: yields each element in the collection
    For non-iterables: yields the item unchanged
    
    Useful for expanding nested lists, unpacking collections, or flattening
    hierarchical data structures into individual items.
    
    Multi-emit segment: each input item can produce multiple output items.
    
    Yields:
        Individual elements from dictionaries, iterables, or the item itself.
    """
    if isinstance(item, dict):
        yield from item.items()
    else:
        try:
            yield from item
        except TypeError:
            yield item

@registry.register_segment("configureLogger")
class ConfigureLogger(AbstractSegment):
    """Configures loggers based on the provided logger levels and files.

    This segment configures loggers based on the provided logger levels and files.
    The logger levels are specified as a string in the format "logger:level,logger:level,...".
    The logger files are specified as a string in the format "logger:file,logger:file,...".

    It configures when the script is compiled or the object is instantiated and never again 
    after that.  It passes the input data through unchanged.

    Args:
        logger_levels (str): Logger levels in format 'logger:level,logger:level,...'
        logger_files (str): Logger files in format 'logger:file,logger:file,...'
    """
    def __init__(self, 
                 logger_levels: Annotated[Optional[str], "Logger levels in format 'logger:level,logger:level,...'"] = None, 
                 logger_files: Annotated[Optional[str], "Logger files in format 'logger:file,logger:file,...'"] = None):
        super().__init__()
        self.logger_levels = logger_levels
        self.logger_files = logger_files
        configure_logger(self.logger_levels, logger_files=self.logger_files)


    def transform(self, input_iter: Iterable) -> Iterator:
        """Configure loggers based on the provided logger levels and files.

        Args:
            input_iter (Iterable): The input data
        """
        yield from input_iter

def hash_data(data, 
              algorithm: Annotated[str, "Hash algorithm to use. Options include SHA1, SHA224, SHA256, SHA384, SHA512, SHA-3, and MD5."] = "SHA256", 
              field_list: Annotated[str, "List of fields to include in the hash"] = "_", 
              use_repr: Annotated[bool, "Whether to use repr() or JSON serialization. Defaults to True for security."] = True, 
              fail_on_missing: Annotated[bool, "Whether to fail on missing fields"] = True, 
              default: Annotated[Any, "Default value to use for missing fields"] = None):
    """Hash a single data item using the specified parameters.
            
    Returns:
        str: The resulting hash digest
    """
    _SECURE_HASH_ALGOS = {
        "SHA224", "SHA256", "SHA384", "SHA512",
        "SHA3_224", "SHA3_256", "SHA3_384", "SHA3_512"
    }
    if algorithm.upper() in {"MD5", "SHA1"} or algorithm.upper() not in {algo.upper() for algo in _SECURE_HASH_ALGOS}:
        raise ValueError(f"Unsupported or insecure hash algorithm: {algorithm}. Allowed: {', '.join(sorted(_SECURE_HASH_ALGOS))}")
    hasher = hashlib.new(algorithm)
    for field in field_list:
        item = extract_property(data, field, fail_on_missing, default=default)
        if item is None:
            if fail_on_missing:
                raise ValueError(f"Field {field} value was None")
            else:
                logging.warning(f"Field {field} value was None. Ignoring")
                continue
        
        if use_repr:
            # Safe: repr() doesn't execute code and works with all objects
            hasher.update(repr(item).encode('utf-8'))
        else:
            # Safe: JSON serialization instead of pickle
            try:
                # Use JSON with sorted keys for deterministic hashing
                json_str = json.dumps(item, sort_keys=True, default=str, ensure_ascii=False)
                hasher.update(json_str.encode('utf-8'))
            except (TypeError, ValueError) as e:
                # Fallback to repr for non-JSON-serializable objects
                logging.debug(f"JSON serialization failed for {type(item)}, using repr: {e}")
                hasher.update(repr(item).encode('utf-8'))
    
    return hasher.hexdigest()

@registry.register_segment("hash")
class Hash(AbstractSegment):
    """Hashes the input data using the specified algorithm.

    This segment hashes the input data using the specified algorithm.
    All datatypes are hashed using either repr() or JSON serialization for security.

    """
    def __init__(self, 
                 algorithm: Annotated[str, "Hash algorithm to use. Options include SHA1, SHA224, SHA256, SHA384, SHA512, SHA-3, and MD5."] = "SHA256", 
                 use_repr: Annotated[bool, "Whether to use repr() or JSON serialization. Defaults to True for security."] = True, 
                 field_list: Annotated[str, "List of fields to include in the hash"] = "_", 
                 set_as: Optional[str] = None, 
                 fail_on_missing: Annotated[bool, "Whether to fail on missing fields"] = True):
        super().__init__()
        _SECURE_HASH_ALGOS = {
            "SHA224", "SHA256", "SHA384", "SHA512",
            "SHA3_224", "SHA3_256", "SHA3_384", "SHA3_512"
        }
        if algorithm.upper() in {"MD5", "SHA1"} or algorithm.upper() not in {algo.upper() for algo in _SECURE_HASH_ALGOS}:
            raise ValueError(f"Unsupported or insecure hash algorithm: {algorithm}. Allowed: {', '.join(sorted(_SECURE_HASH_ALGOS))}")
        self.algorithm = algorithm
        self.use_repr = use_repr
        self.field_list = list(parse_key_value_str(field_list).keys())
        self.fail_on_missing = fail_on_missing
        self.set_as = set_as


    def transform(self, input_iter: Iterable) -> Iterator:
        """Hash the input data using the specified algorithm.

        Args:
            input_iter (Iterable): The input data
        """
        for data in input_iter:
            digest = hash_data(data, self.algorithm, self.field_list,
                                    self.use_repr, self.fail_on_missing)
            if self.set_as:
                assign_property(data, self.set_as, digest)
                yield data
            else:
                yield digest

@registry.register_segment("fillTemplate")
@field_segment
def fillTemplate(item, 
                 template: Annotated[str, "The template string with placeholders for values"], 
                 fail_on_missing: Annotated[bool, "Whether to fail on missing fields"] = True, 
                 default: Annotated[Optional[Any], "Default value to use for missing fields"] = ""):
    """Fill a template string with values from the input `item`.

        Template writing guide:
        - Placeholders: Use `{path}` where `path` is a dot-notation path
            resolved on `item` via `extract_property`. Examples: `{user.name}`,
            `{address.city}`, `{tags.0}` (numeric index for lists/tuples).
        - Whole item: `{_}` inserts the entire `item`. `_.field` acts as a
            passthrough, so `{_.name}` is equivalent to `{name}`.
        - Literal braces: Use `{{` and `}}` to render literal `{` and `}`
            characters in output.
        - Missing values: Controlled by `fail_on_missing` and `default`.
            If `fail_on_missing` is True, missing fields raise an error; otherwise,
            missing fields are replaced with `default` (empty string by default).

        Examples:
        - Dict item:
            item = {"user": {"name": "Alice"}, "day": "Monday"}
            template = "Hello {user.name}, today is {day}."
            -> "Hello Alice, today is Monday."

        - Lists and indices:
            item = {"tags": ["news", "tech"]}
            template = "First tag: {tags.0}"
            -> "First tag: news"

        - Literal braces:
            item = {"user": {"name": "Alice"}}
            template = "{{Escaped}} {_.user.name}"
            -> "{Escaped} Alice"

    Returns:
        str: The filled template string
    """
    if template is None:
        raise ValueError("Template cannot be None")
    field_names = extract_template_field_names(template)
    values = {field_name:extract_property(item, field_name, fail_on_missing=fail_on_missing, default=default) for field_name in field_names}
    return fill_template(template, values)

@registry.register_segment("lambda")
class EvalExpression(AbstractFieldSegment):
    """Evaluate a Python expression on each item in the input stream.
    
    This segment pre-compiles the expression during initialization for efficiency 
    and then applies it to each item during transformation. Expressions are evaluated
    in a restricted environment for security.
    
    The item is available in expressions as 'item'.     
    """
    
    def __init__(self, 
                 expression: Annotated[str, "The Python expression to evaluate"],
                 field: Annotated[Optional[str], "If provided, extract this field from each item before evaluating"] = "_",
                 set_as: Annotated[Optional[str], "If provided, append the result to each item under this field name"] = None):
        super().__init__()
        self.expression = expression
        self.field = field
        self.set_as = set_as
        
        # Compile the expression into a lambda function
        self.lambda_function = compileLambda(expression)
    
    def process_value(self, value):
        try:
            return self.lambda_function(value)
        except Exception as e:
            logger.error(f"Error evaluating expression '{self.expression}' on value '{value}': {e}")
            raise

@registry.register_segment("lambdaFilter")
class FilterExpression(AbstractSegment):
    """Filter items from the input stream based on a Python expression.
    
    This segment pre-compiles the expression during initialization for efficiency 
    and then applies it to each item during transformation. Expressions are evaluated
    in a restricted environment for security.
    
    The item is available in expressions as 'item'. If the item is a dictionary,
    its fields can be accessed directly as variables in the expression.
    
    """
    
    def __init__(self, 
                 expression: Annotated[str, "The Python expression to evaluate"],
                 field: Annotated[Optional[str], "If provided, extract this field from each item before evaluating"] = "_"):
        super().__init__()
        self.expression = expression
        self.field = field
        
        # Compile the expression into a lambda function
        self.lambda_function = compileLambda(expression)
        logger.debug(f"Compiled filter expression: {self.expression}")
    
    def transform(self, input_iter: Iterable[Any]) -> Iterator[Any]:
        """Process each item from the input stream."""
        for item in input_iter:
            logger.debug(f"Processing input item: {item}")
            
            # Extract field value if specified
            if self.field is not None:
                value = extract_property(item, self.field)
                logger.debug(f"Extracted value from field {self.field}: {value}")
            else:
                value = item
                logger.debug(f"Using item directly: {value}")
            
            # Evaluate the expression on the value
            result = self.lambda_function(value)
            logger.debug(f"Evaluation result: {result}")
            
            # Yield the item if the expression evaluates to True
            if result:
                yield item


@registry.register_segment("copy")
@segment
def copy_segment(items):
    """Create shallow copies of each item in the pipeline.
    
    This segment creates a shallow copy of each item, suitable when you need to
    prevent downstream modifications from affecting the original items. Shallow
    copies share references to nested objects (lists, dicts within dicts), so
    modifications to nested structures will still affect originals.
    
    Use deepCopy instead if you need complete independence from the originals,
    though deepCopy is slower and more memory-intensive.
    
    Useful for:
    - Preventing accidental mutations in complex pipelines
    - Creating independent item instances before modification
    - Preserving original data while processing
    
    Yields:
        Shallow copies of each input item.
    """
    for item in items:
        yield copy.copy(item)

@registry.register_segment("deepCopy")
@segment
def deep_copy_segment(items):
    """Create complete independent deep copies of each item in the pipeline.
    
    This segment creates a deep copy of each item, recursively copying all nested
    structures (lists, dicts, and objects within them). This ensures complete
    independence from the originals - modifications to any nested structure won't
    affect the original items.
    
    Deep copy is slower and more memory-intensive than shallow copy. Use copy
    instead if nested structures don't need to be independent.
    
    Useful for:
    - Complex nested data that will be heavily modified
    - When you need complete independence from original data
    - Pipelines where multiple branches process the same item
    
    Yields:
        Deep copies of each input item.
    """
    for item in items:
        yield copy.deepcopy(item)

@registry.register_segment("debounce")
@segment()
def Debounce(items: Any,
             key_field: Annotated[str, "Field name to use as the debounce key"] = "path",
             debounce_seconds: Annotated[float, "Seconds to wait for stability before yielding"] = 1.0):
    """
    Segment that debounces events by a key field, waiting for stability before yielding.

    Expects input items as dicts with a field to use as the debounce key (default: "path").
    When multiple events arrive for the same key, only the last event is yielded after
    no new events have arrived for that key within the debounce period.

    This is useful for handling race conditions where files are created and then
    immediately modified (e.g., create with 0 bytes, then write content). The debounce
    ensures processing only happens after the file has stabilized.

    Yields the most recent event for each key after the debounce period expires.
    """
    pending = {}  # key -> (item, timestamp)
    lock = threading.Lock()
    output_queue = Queue()
    stop_event = threading.Event()
    input_done = threading.Event()

    def add_pending(item):
        key = item.get(key_field) if isinstance(item, dict) else None
        if key is None:
            output_queue.put(item)
            return
        with lock:
            pending[key] = (item, time.time())

    def input_consumer():
        try:
            for item in items:
                if stop_event.is_set():
                    break
                add_pending(item)
        finally:
            input_done.set()

    def checker():
        while not stop_event.is_set():
            time.sleep(0.1)
            now = time.time()
            with lock:
                stable_keys = [
                    k for k, (item, ts) in pending.items()
                    if now - ts >= debounce_seconds
                ]
                for k in stable_keys:
                    item, _ = pending.pop(k)
                    output_queue.put(item)

            # Signal completion when input is done and no pending items
            if input_done.is_set():
                with lock:
                    if not pending:
                        output_queue.put(None)  # Sentinel to signal done
                        break

    input_thread = threading.Thread(target=input_consumer, daemon=True)
    checker_thread = threading.Thread(target=checker, daemon=True)
    input_thread.start()
    checker_thread.start()

    try:
        while True:
            item = output_queue.get()
            if item is None:  # Sentinel
                break
            yield item
    finally:
        stop_event.set()
        input_thread.join(timeout=1.0)
        checker_thread.join(timeout=1.0)

