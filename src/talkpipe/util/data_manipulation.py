from typing import Union
import logging
import re
import inspect
import json
import textwrap
from types import MappingProxyType
from typing import Any, Dict, List, Set

import numpy as np
from talkpipe.util.config import parse_key_value_str

# Type aliases
VectorLike = Union[List[float], np.ndarray]
Document = Dict[str, str]
DocID = str

logger = logging.getLogger(__name__)

def get_all_attributes(obj: Any, skip_packages: tuple = ('pydantic',), visited: Set = None,
                      depth: int = 0, max_depth: int = 10) -> list:
    """
    Recursively get all non-hidden attributes of an object, including dictionary keys
    and list lengths.

    Args:
        obj: The object to inspect
        skip_packages: Tuple of package names whose attributes should be skipped
        visited: Set of already visited objects to prevent infinite recursion
        depth: Current recursion depth
        max_depth: Maximum recursion depth to prevent stack overflow

    Returns:
        List of attribute names and their nested attributes
    """
    # Handle dictionary type specially to show keys and inspect values
    if isinstance(obj, dict):
        result = []
        for key, value in obj.items():
            if isinstance(value, dict):
                nested = get_all_attributes(value, skip_packages, visited, depth + 1, max_depth)
                result.append({key: nested})
            elif isinstance(value, list):
                result.append({key: f"list of {len(value)}"})
            elif isinstance(value, (str, int, float, bool, type(None), set, tuple, bytes, bytearray)):
                result.append(key)
            else:
                nested = get_all_attributes(value, skip_packages, visited, depth + 1, max_depth)
                if nested:
                    result.append({key: nested})
                else:
                    result.append(key)
        return result

    # Handle list type specially to show length
    if isinstance(obj, list):
        return f"list of {len(obj)}"

    # Skip introspection for other basic types
    if isinstance(obj, (str, int, float, bool, type(None), set, tuple, bytes, bytearray)):
        return []

    if visited is None:
        visited = set()

    # Skip if we've seen this object before or reached max depth
    if depth > max_depth or id(obj) in visited:
        return []

    # Add current object to visited set
    visited.add(id(obj))

    # Get all attributes that don't start with '_'
    attributes = []

    for attr_name in dir(obj):
        if not attr_name.startswith('_'):
            try:
                attr_value = getattr(obj, attr_name)

                # Check if attribute comes from a skipped package
                should_skip = False

                # Get the module of the attribute if it's a method or property
                if inspect.ismethod(attr_value) or isinstance(attr_value, property):
                    if hasattr(attr_value, '__qualname__'):
                        module = inspect.getmodule(attr_value)
                        if module:
                            module_name = module.__name__.split('.')[0]
                            should_skip = module_name in skip_packages

                # For class attributes, check the class's module
                elif hasattr(obj, '__class__'):
                    class_attr = getattr(obj.__class__, attr_name, None)
                    if class_attr is not None:
                        module = inspect.getmodule(class_attr)
                        if module:
                            module_name = module.__name__.split('.')[0]
                            should_skip = module_name in skip_packages

                if not should_skip:
                    # If it's a dictionary, include its keys and inspect values
                    if isinstance(attr_value, dict):
                        nested = get_all_attributes(attr_value, skip_packages, visited, depth + 1, max_depth)
                        attributes.append({attr_name: nested})
                    # If it's a list, include its length
                    elif isinstance(attr_value, list):
                        attributes.append({attr_name: f"list of {len(attr_value)}"})
                    # For other basic types, just add the attribute name
                    elif isinstance(attr_value, (str, int, float, bool, type(None), set, tuple, bytes, bytearray)):
                        attributes.append(attr_name)
                    # For complex types, recurse
                    else:
                        nested_attrs = get_all_attributes(attr_value, skip_packages, visited,
                                                        depth + 1, max_depth)
                        if nested_attrs:
                            attributes.append({attr_name: nested_attrs})
                        else:
                            attributes.append(attr_name)

            except Exception as e:
                # Log error when skipping attributes that can't be accessed
                logger.warning(f"Failed to access attribute '{attr_name}' on object {type(obj).__name__}: {e}")
                continue

    return attributes


def extract_property(data: Any, prop_list: str, fail_on_missing=False, default=None) -> Any:
    """Extract a property from a nested data structure using dot notation.

    Args:
        data (Any): The data structure to extract the property from
        prop_list (str): The property to extract, using dot notation for nested properties.
            The special character '_' can be used as a passthrough in dotted paths.
            For example, "X._" is equivalent to "X", and "X._.1" is equivalent to "X.1".
        fail_on_missing (bool): If True, raise an exception if the property is not found
            If False, return None if the property is not found
    """
    if prop_list == "_":
        return data
    of_interest = data
    for prop_name in prop_list.split("."):
        # Treat '_' as a passthrough/no-op in dotted paths
        if prop_name == "_":
            continue
        if hasattr(of_interest, prop_name):
            prop_actual = getattr(of_interest, prop_name)
            if callable(prop_actual):
                of_interest = prop_actual()
            else:
                of_interest = prop_actual
        elif isinstance(of_interest, dict) and prop_name in of_interest:
            of_interest = of_interest[prop_name]
        elif isinstance(of_interest, (list, tuple)) and prop_name.isdigit() and 0 <= int(prop_name) < len(of_interest):
            of_interest = of_interest[int(prop_name)]
        else:
            if fail_on_missing:
                raise AttributeError(f"Property '{prop_name}' not found in the input data of type '{type(data)}'")
            else:
                return default
    return of_interest


def assign_property(data: Any, prop_name: str, value: Any) -> None:
    """Assign a value to a property on a data structure.

    This function provides a unified interface for assigning values to different types
    of objects, similar to how extract_property provides a unified interface for reading.

    Supports:
    - Dictionaries: Uses bracket notation (data[prop_name] = value)
    - Objects (including pydantic models): Uses setattr (setattr(data, prop_name, value))

    Args:
        data (Any): The data structure to assign the property to
        prop_name (str): The property name to assign
        value (Any): The value to assign

    Examples:
        >>> # With a dictionary
        >>> d = {"a": 1}
        >>> assign_property(d, "b", 2)
        >>> d
        {"a": 1, "b": 2}

        >>> # With a pydantic model
        >>> class MyModel(BaseModel):
        ...     a: int
        >>> model = MyModel(a=1)
        >>> assign_property(model, "b", 2)
        >>> model.b
        2
    """
    if isinstance(data, dict):
        # Use bracket notation for dictionaries
        data[prop_name] = value
    else:
        # Use setattr for pydantic models and other objects
        setattr(data, prop_name, value)


def get_type_safely(type_name, module=None):
    """Get a type by name, handling module imports."""
    if "." in type_name:
        module, type_name = type_name.rsplit(".", 1)
    try:
        if module:
            imported_module = __import__(module)
            return getattr(imported_module, type_name)
        else:
            return getattr(__import__('builtins'), type_name)
    except (ImportError, AttributeError):
        return None


def toDict(data, field_list: str = "_", fail_on_missing: bool = True):
    """Convert each item in the input string into a dictionary based on the provided parameter list.

    Args:
        field_list (str): A list of properties to extract from the input data.  The properties are separated by commas.
            Each property can be a path to a nested property.  If the property is "_", the entire data object is used.
        fail_on_missing (bool): If True, the segment will raise an exception if a property is missing from the input data.
            If False, the segment will skip missing properties.
    """
    ans = {}
    parsed_field_list = parse_key_value_str(field_list)
    for assignment in parsed_field_list.items():
        ans[assignment[1]] = data if assignment[0]=="_" else extract_property(data, assignment[0], fail_on_missing)
    return ans

def dict_to_text(data: dict, wrap_width: int = 80, field_name_separator: str = ": ",
                 field_separator: str = "\n", item_suffix = "") -> str:
    """
    Convert a dictionary to a formatted string. Each field is separated by the specified field_separator, and
    each property and value is separated by the specified separator.
    Args:
        data (dict): The input dictionary to format
        wrap_width (int): Width for text wrapping.  No wrapping if wrap_width is less than 1 (default: 80).
        separator (str): Separator between property and value (default: ": ")
        field_separator (str): Separator between different fields (default: "\n")
    Returns:
        str: Formatted string containing all fields
    """
    if not isinstance(data, dict):
        raise TypeError("Input data must be a dictionary")
    output_lines = []
    for key, value in data.items():
        cleaned_value = str(value).strip()
        if wrap_width > 0:
            cleaned_value = textwrap.fill(cleaned_value, width=wrap_width)
        output_lines.append(f"{key}{field_name_separator}{cleaned_value}")
    return field_separator.join(output_lines) + item_suffix


def extract_template_field_names(template: str) -> list:
    """
    Extract field names from a template string.

    The function looks for patterns like "{name}" in the template and returns
    a list of all unique field names found. Handles literal curly braces 
    (escaped as "{{" and "}}").

    Args:
        template: A string containing fields in the format "{field_name}"

    Returns:
        A list of field names (without the curly braces)

    Example:
        >>> extract_field_names("Hello, {name}! Today is {day}.")
        ['name', 'day']
        >>> extract_field_names("{{ This has literal braces and {field} }}")
        ['field']
    """
    # Replace escaped braces temporarily
    temp_open = "___OPEN_BRACE___"
    temp_close = "___CLOSE_BRACE___"

    # Replace escaped braces with temporary markers
    temp_template = template.replace("{{", temp_open).replace("}}", temp_close)

    # Use regular expression to find all matches of {field_name}
    pattern = r'\{([^{}]+)\}'
    matches = re.findall(pattern, temp_template)

    # Return unique field names
    return list(set(matches))


def fill_template(template: str, values: dict) -> str:
    """
    Fill a template string with values from a dictionary.

    Replaces each instance of "{field_name}" with the corresponding value
    from the values dictionary. Handles literal curly braces (escaped as
    "{{" and "}}").

    Args:
        template: A string containing fields in the format "{field_name}"
        values: A dictionary mapping field names to their replacement values

    Returns:
        The template string with all fields replaced by their values

    Example:
        >>> fill_template("Hello, {name}! Today is {day}.", {"name": "Alice", "day": "Monday"})
        'Hello, Alice! Today is Monday.'
        >>> fill_template("{{ This has literal braces and {field} }}", {"field": "value"})
        '{ This has literal braces and value }'
    """
    # First, handle escaped braces by replacing them temporarily
    temp_open = "___OPEN_BRACE___"
    temp_close = "___CLOSE_BRACE___"

    # Replace escaped braces with temporary markers
    result = template.replace("{{", temp_open).replace("}}", temp_close)

    # Replace each field with its value from the dictionary
    for field, value in values.items():
        placeholder = "{" + field + "}"
        result = result.replace(placeholder, str(value))

    # Restore literal braces
    result = result.replace(temp_open, "{").replace(temp_close, "}")

    return result

def compileLambda(expression: str):
    """Compile a Python expression into a callable that evaluates safely with a single item parameter.

    Args:
        expression: Python expression to compile
        fail_on_error: If True, raises exceptions when evaluation fails. If False, returns None on errors

    Returns:
        A callable function that takes a single 'item' parameter and returns the evaluated expression result
    """
    # Security check: block dangerous patterns in expressions
    dangerous_patterns = [
        '__import__', 'import', 'exec', 'eval', 'compile', 'open', 'file',
        'input', 'raw_input', 'reload', 'vars', 'locals', 'globals',
        'dir', 'hasattr', 'getattr', 'setattr', 'delattr', 'classmethod',
        'staticmethod', 'super', 'property', '__', '.mro', '.subclasses'
    ]
    
    expression_lower = expression.lower()
    for pattern in dangerous_patterns:
        if pattern in expression_lower:
            raise ValueError(f"Security violation: Expression contains prohibited pattern '{pattern}'")
    
    # Additional security: check for attribute access to dangerous methods
    if '.__' in expression or 'getitem' in expression_lower or 'setitem' in expression_lower:
        raise ValueError("Security violation: Expression contains prohibited attribute access patterns")

    # Set of safe built-ins that can be used in expressions
    _SAFE_BUILTINS = {
        'abs': abs, 'all': all, 'any': any, 'bool': bool, 'dict': dict,
        'enumerate': enumerate, 'filter': filter, 'float': float,
        'frozenset': frozenset, 'int': int, 'isinstance': isinstance,
        'issubclass': issubclass, 'len': len, 'list': list, 'map': map,
        'max': max, 'min': min, 'ord': ord, 'pow': pow, 'range': range,
        'repr': repr, 'reversed': reversed, 'round': round,
        'set': set, 'slice': slice, 'sorted': sorted, 'str': str,
        'sum': sum, 'tuple': tuple, 'zip': zip
    }

    # Create an immutable view of the safe built-ins
    SAFE_BUILTINS = MappingProxyType(_SAFE_BUILTINS)

    # Pre-compile the expression for efficiency
    try:
        compiled_code = compile(expression, '<string>', 'eval')
        logger.debug(f"Successfully pre-compiled expression: {expression}")
    except SyntaxError as e:
        error_msg = f"Invalid expression syntax: {e}"
        logger.error(error_msg)
        raise ValueError(error_msg)

    def lambda_function(item: Any) -> Any:
        """Evaluate the pre-compiled expression on a single item."""
        # Always make the item available
        locals_dict = {'item': item}

        # If item is a dictionary, add its keys as variables for convenience
        if isinstance(item, dict):
            # Filter dictionary keys to prevent injection of dangerous names
            safe_keys = {k: v for k, v in item.items() 
                        if isinstance(k, str) and not k.startswith('_') and k not in dangerous_patterns}
            locals_dict.update(safe_keys)

        # Create a completely restricted environment with no access to dangerous globals
        restricted_globals = {'__builtins__': {}}
        restricted_globals.update(SAFE_BUILTINS)

        # Evaluate the expression in a heavily restricted environment
        # Note: eval() is used intentionally here with extensive security controls:
        # - Restricted globals (no dangerous builtins)
        # - Input validation (blocks dangerous patterns)
        # - Compiled code with syntax checking
        # - Exception handling for safety
        # ast.literal_eval() cannot be used as this evaluates dynamic expressions, not just literals
        try:
            result = eval(compiled_code, restricted_globals, locals_dict)  # nosec B307
            return result
        except Exception as e:
            error_msg = f"Error evaluating expression '{expression}' on item {item}: {e}"
            raise RuntimeError(error_msg, e)

    return lambda_function


