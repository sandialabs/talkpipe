"""Standard operations for data processing pipelines."""

from typing import Iterable, Iterator, Union, Optional, Any
import logging
import pickle
import hashlib
import pandas as pd
from talkpipe.util.config import configure_logger, parse_key_value_str
from talkpipe.util.data_manipulation import extract_property, extract_template_field_names, get_all_attributes, toDict
from talkpipe.util.data_manipulation import compileLambda
from talkpipe.util.os import run_command
from talkpipe.util.data_manipulation import get_type_safely
from talkpipe.pipe.core import AbstractSegment, source, segment, field_segment
import talkpipe.chatterlang.registry as registry
from talkpipe.util.data_manipulation import fill_template

logger = logging.getLogger(__name__)

@registry.register_segment("sleep")
@segment()
def sleep(items, seconds: int):
    """Sleep for a specified number of seconds.

    Args:
        items (Iterable): An iterable of items to process.
        seconds (int): The number of seconds to sleep.

    Yields:
        None: This segment does not yield any items; it simply sleeps.
    """
    import time
    # Yielding None to indicate that this segment does not produce output
    for item in items:
        yield item  # Yield the item to maintain the flow of the pipeline
        time.sleep(seconds)

@registry.register_segment(name="progressTicks")
@segment()
def progressTicks(items, tick: str = ".", tick_count: int = 10, eol_count: Optional[int] = 10, print_count: bool = False):
    """Prints a tick marks to help visualize progress.

    Prints a tick mark for each tick_count items processed. If eol_count is specified, it will print a new line after every eol_count tick marks.
    If print_count is True, it will print the total count of items processed at the end of each line and at the end.

    Args:
        items (Iterable): An iterable of items to process.
        tick (str): The character to print as a tick mark. Defaults to '.'.
        tick_count (int): The number of items to process before printing a tick mark. Defaults to 10.
        eol_count (Optional[int]): The number of tick marks to print before starting a new line. If None, no new line is printed. Defaults to 10.
        print_count (bool): If True, prints the count of items processed at the end of each line and at the end.
    Yields:
        The original items from the input iterable.
    """
    count = 0
    for idx, item in enumerate(items, 1):
        if idx % tick_count == 0 and idx != 0:
            print(tick, end="", flush=True)
            if eol_count and (idx // tick_count) % eol_count == 0:
                if print_count:
                    print(f"{idx}", end="", flush=True)
                print()
        count = idx
        yield item
    if print_count:
        print(f"\nTotal items processed: {count}")

@registry.register_segment(name="firstN")
@segment()
def firstN(items, n: int = 1):
    """Yields the first n items from the input stream.
    Args:
        n (int): The number of items to yield.
    Yields:
        The first n items from the input stream."""
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
    def __init__(self, cast_type: Union[type, str], fail_silently: bool = True):
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

    def __init__(self, field_list: str = "_", fail_on_missing: bool = True):
        """Convert each item in the input string into a dictionary based on the provided parameter list.

        Args:
            field_list (str): A list of properties to extract from the input data.  The properties are separated by commas.
                Each property can be a path to a nested property.  If the property is "_", the entire data object is used.
            fail_on_missing (bool): If True, the segment will raise an exception if a property is missing from the input data.
                If False, the segment will skip missing properties.
        """
        super().__init__()
        self.field_list = field_list
        self.fail_on_missing = fail_on_missing

    def transform(self, input_iter: Iterable) -> Iterator:
        for data in input_iter:
            ans = toDict(data, self.field_list, self.fail_on_missing)
            yield ans

@registry.register_segment("appendAs")
@field_segment
def appendAs(item, field_list:str):
    """Appends the specified fields to the input item.
    
    Equivalent to toDict except that that item is modified with the new key/value pairs 
    rather than a new dictionary returned.

    Assumes that the input item can has items assigned using bracket notation ([]).
    
    """
    new_vals = toDict(item, field_list)
    for k, v in new_vals.items():
        item[k] = v
    return item

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
def exec(command: str) -> Iterator:
    """Execute a command and yields each line passed to stdout as an item."""
    yield from run_command(command)


@registry.register_segment("concat")
@segment(fields=None, delimiter="\n\n", append_as=None)
def concat(items, fields, delimiter="\n\n", append_as=None):
    """Concatenates specified fields from each item with a delimiter.

    Args:
        items: Iterable of input items to process
        fields: String specifying fields to extract and concatenate
        delimiter (str, optional): String to insert between concatenated fields. Defaults to "\n\n"
        append_as (str, optional): If specified, adds concatenated result as new field with this name. 
                                Defaults to None.

    Yields:
        If append_as is specified, yields the original item with concatenated result added as new field.
        Otherwise, yields just the concatenated string.
    """
    props = parse_key_value_str(fields)
    for item in items:
        ans = ""
        for i, prop in enumerate(props.items()):
            if i>0:
                ans +=delimiter
            ans += str(extract_property(item, prop[0]))            
        if append_as:
            item[append_as] = ans
            yield item
        else:
            yield ans

@registry.register_segment("slice")
@field_segment()
def slice(item, range=None):
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
def longestStr(items, field_list, append_as=None):
    """Finds the longest string among specified fields in the input item.  If 
    a field is not present or is not a string, it is ignored.  If two or more
    fields have the same length, the first one encountered is returned.  If
    none of the specified fields are present, and emptry string is yielded.
    Args:
        items: The input items
        field_list (str): Comma-separated list of fields to check for longest string
    Yields:
        The longest string found in the specified fields of the input items.
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
        if append_as:
            item[append_as] = longest
            yield item
        else:   
            yield longest

@registry.register_segment("isIn")
@segment()
def isIn(items, field, value):
    """Filters items based on whether a field contains a specified value.

    Args:
        items: Iterable of items to filter
        field: Field name to check for value
        value: Value to check for in the field

    Yields:
        Items where the specified field contains the specified value.
    """
    for item in items:
        data = extract_property(item, field)
        if value in data:
            yield item

@registry.register_segment("isNotIn")
@segment()
def isNotIn(items, field, value):
    """Filters items based on whether a field does not contain a specified value.

    Args:
        field: Field name to check for value
        value: Value to check for in the field

    Yields:
        Items where the specified field does not contain the specified value.
    """
    for item in items:
        data = extract_property(item, field)
        if value not in data:
            yield item

@registry.register_segment("everyN")
@segment()
def everyN(items, n):
    """Yields every nth item from the input stream.

    Args:
        items: Iterable of items to process
        n: Number of items to skip between each yield

    Yields:
        Every nth item from the input stream.
    """
    for i, item in enumerate(items):
        if (i+1) % n == 0:
            yield item

@registry.register_segment("flatten")
@segment()
def flatten(items):
    """Flattens a nested list of items.

    Args:
        items: Iterable of items to flatten

    Yields:
        Flattened list of items
    """
    for item in items:
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
    def __init__(self, logger_levels: Optional[str]=None, logger_files: Optional[str] = None):
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

def hash_data(data, algorithm="MD5", field_list="_", use_repr=False, fail_on_missing=True):
    """Hash a single data item using the specified parameters.
    
    Args:
        data: The data item to hash
        algorithm (str): Hash algorithm to use. Options include SHA1, SHA224, SHA256, SHA384, SHA512, SHA-3, and MD5.
        fields (list): List of fields to include in the hash
        use_repr (bool): Whether to use repr() or pickle
        fail_on_missing (bool): Whether to fail on missing fields
        
    Returns:
        str: The resulting hash digest
    """
    hasher = hashlib.new(algorithm)
    for field in field_list:
        item = extract_property(data, field, fail_on_missing)
        if item is None:
            if fail_on_missing:
                raise ValueError(f"Field {field} value was None")
            else:
                logging.warning(f"Field {field} value was None.  Ignoring")
                continue
        if use_repr:
            hasher.update(repr(item).encode())
        else:
            hasher.update(pickle.dumps(item))
    return hasher.hexdigest()

@registry.register_segment("hash")
class Hash(AbstractSegment):
    """Hashes the input data using the specified algorithm.

    This segment hashes the input data using the specified algorithm.
    Strings will be encoded and hashed.  All other datatypes wil be hashed using either pickle or repr().

    Args:
        algorithm (str): Hash algorithm to use.  Options include SHA1, SHA224, SHA256, SHA384, SHA512, SHA-3, and MD5.
        use_repr (bool): If True, the repr() version of the input data is hashed.  If False, the input data is hashed via 
            pickling.  Using repr() will handle all object, even those that can't be pickled and won't be subject to
            changes in pickling formats.  But the pickled version will include more state and generally be more reliable.
    """
    def __init__(self, algorithm: str="MD5", use_repr=False, field_list: str = "_", append_as=None, fail_on_missing: bool = True):
        super().__init__()
        self.algorithm = algorithm
        self.use_repr = use_repr
        self.field_list = list(parse_key_value_str(field_list).keys())
        self.fail_on_missing = fail_on_missing
        self.append_as = append_as


    def transform(self, input_iter: Iterable) -> Iterator:
        """Hash the input data using the specified algorithm.

        Args:
            input_iter (Iterable): The input data
        """
        for data in input_iter:
            digest = hash_data(data, self.algorithm, self.field_list, 
                                    self.use_repr, self.fail_on_missing)
            if self.append_as:
                data[self.append_as] = digest
                yield data
            else:
                yield digest

@registry.register_segment("fillTemplate")
@field_segment
def fillTemplate(item, template:str, fail_on_missing:bool=True):
    """Fill a template string with values from the input item.

    Args:
        item: The input item containing values to fill the template
        template (str): The template string with placeholders for values

    Returns:
        str: The filled template string
    """
    assert template is not None
    field_names = extract_template_field_names(template)
    values = {field_name:extract_property(item, field_name, fail_on_missing=fail_on_missing) for field_name in field_names}
    return fill_template(template, values)

@registry.register_segment("lambda")
class EvalExpression(AbstractSegment):
    """Evaluate a Python expression on each item in the input stream.
    
    This segment pre-compiles the expression during initialization for efficiency 
    and then applies it to each item during transformation. Expressions are evaluated
    in a restricted environment for security.
    
    The item is available in expressions as 'item'. If the item is a dictionary,
    its fields can be accessed directly as variables in the expression.
    
    Args:
        expression: The Python expression to evaluate
        field: If provided, extract this field from each item before evaluating
        append_as: If provided, append the result to each item under this field name
        fail_on_error: If True, raises exceptions when evaluation fails. If False, logs errors and returns None
    """
    
    def __init__(self, 
                 expression: str,
                 field: Optional[str] = "_",
                 append_as: Optional[str] = None,
                 fail_on_error: bool = True):
        super().__init__()
        self.expression = expression
        self.field = field
        self.append_as = append_as
        self.fail_on_error = fail_on_error
        
        # Compile the expression into a lambda function
        self.lambda_function = compileLambda(expression, fail_on_error)
    
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
            
            # Handle the result according to append_as
            if self.append_as is not None and hasattr(item, '__setitem__'):
                logger.debug(f"Appending result to field {self.append_as}")
                item[self.append_as] = result
                yield item
            else:
                logger.debug("Yielding result directly")
                yield result

@registry.register_segment("lambdaFilter")
class FilterExpression(AbstractSegment):
    """Filter items from the input stream based on a Python expression.
    
    This segment pre-compiles the expression during initialization for efficiency 
    and then applies it to each item during transformation. Expressions are evaluated
    in a restricted environment for security.
    
    The item is available in expressions as 'item'. If the item is a dictionary,
    its fields can be accessed directly as variables in the expression.
    
    Args:
        expression: The Python expression to evaluate
        field: If provided, extract this field from each item before evaluating
        fail_on_error: If True, raises exceptions when evaluation fails. If False, logs errors and returns None
    """
    
    def __init__(self, 
                 expression: str,
                 field: Optional[str] = "_",
                 fail_on_error: bool = True):
        super().__init__()
        self.expression = expression
        self.field = field
        self.fail_on_error = fail_on_error
        
        # Compile the expression into a lambda function
        self.lambda_function = compileLambda(expression, fail_on_error)
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