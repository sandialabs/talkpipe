import logging
import re
import inspect
from types import MappingProxyType
from typing import Any, Set
from talkpipe.util.config import parse_key_value_str

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

            except Exception:
                # Skip attributes that can't be accessed
                continue

    return attributes


def extract_property(data: Any, prop_list: str, fail_on_missing=False) -> Any:
    """Extract a property from a nested data structure using dot notation.

    Args:
        data (Any): The data structure to extract the property from
        prop_list (str): The property to extract, using dot notation for nested properties
        fail_on_missing (bool): If True, raise an exception if the property is not found
            If False, return None if the property is not found
    """
    if prop_list == "_":
        return data
    of_interest = data
    for prop_name in prop_list.split("."):
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
                return None
    return of_interest


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


def compileLambda(expression: str, fail_on_error: bool = True):
    """Compile a Python expression into a callable that evaluates safely with a single item parameter.

    Args:
        expression: Python expression to compile
        fail_on_error: If True, raises exceptions when evaluation fails. If False, returns None on errors

    Returns:
        A callable function that takes a single 'item' parameter and returns the evaluated expression result
    """
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
            locals_dict.update(item)

        # Evaluate the expression in a restricted environment
        try:
            result = eval(compiled_code, dict(SAFE_BUILTINS), locals_dict)
            return result
        except Exception as e:
            error_msg = f"Error evaluating expression '{expression}' on item {item}: {e}"
            logger.error(error_msg)
            if fail_on_error:
                raise
            return None

    return lambda_function