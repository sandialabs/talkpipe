"""Standard operations for data processing pipelines."""

from typing import Iterable, Iterator, Union, Optional
import logging
import pickle
import hashlib
import pandas as pd
from talkpipe.util.config import configure_logger, parse_key_value_str
from talkpipe.util.data_manipulation import extract_property, extract_template_field_names, get_all_attributes, toDict
from talkpipe.util.os import run_command
from talkpipe.util.data_manipulation import get_type_safely
from talkpipe.pipe.core import AbstractSegment, source, segment, field_segment
import talkpipe.chatterlang.registry as registry
from talkpipe.util.data_manipulation import fill_template

logger = logging.getLogger(__name__)

@registry.register_segment(name="firstN")
class First(AbstractSegment[int, int]):
    """
    Passes on the first N items from the input stream.
    
    <pre>
    Args:
        n (int): The number of items to pass on. Default is 1.
    <pre>
    """
    n: int

    def __init__(self, n: int = 1):
        super().__init__()
        self.n = n

    def transform(self, input_iter: Iterable[int]) -> Iterator[int]:
        """
        Execute the operation on an iterable input.
        
        Args:
            input_iter (Iterable[int]): Iterable input data
        
        Yields:
            the first n elements of the input iterable
        """
        it  = iter(input_iter)
        for _ in range(self.n):
            yield next(it)

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


@registry.register_segment(name="call_func")
@segment()
def call_func(item_iter: Iterable, func: callable) -> Iterator:
    """Call a function on each item in the input stream.
    
    Args:
        func (callable): The function to call on each item
    """
    for item in item_iter:
        yield from func(item)

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

