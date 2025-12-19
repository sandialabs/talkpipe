"""
Shared utilities for extracting documentation from registered TalkPipe components.

This module provides common functionality for the chatterlang reference generator
and browser to extract docstrings, parameters, and metadata from registered
sources and segments.
"""

import inspect
import logging
from typing import Dict, List, Any, Optional, get_origin, get_args
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class ParamSpec:
    """Holds detailed parameter info: name, annotation, default, and description."""
    name: str
    annotation: str = ""
    default: str = ""
    description: str = ""


@dataclass
class ComponentInfo:
    """Represents extracted information about a TalkPipe component."""
    name: str
    chatterlang_name: str
    component_type: str  # "Source", "Segment", "Field Segment"
    module: str
    base_classes: List[str]
    docstring: str
    parameters: List[ParamSpec]
    original_function: Optional[callable] = None


def extract_function_info(func: callable) -> Dict[str, Any]:
    """
    Extract parameter information from a function using inspect.
    Handles Annotated types to extract descriptions from metadata.
    """
    try:
        sig = inspect.signature(func)
        params = []
        for param_name, param in sig.parameters.items():
            if param_name in ['self', 'items', 'item']:
                continue  # Skip common parameter names
            
            annotation_str = ""
            description = ""
            
            if param.annotation != param.empty:
                # Check if it's an Annotated type
                if get_origin(param.annotation) is not None:
                    # This could be Annotated[Type, metadata]
                    origin = get_origin(param.annotation)
                    args = get_args(param.annotation)
                    
                    # Handle Annotated types from typing_extensions or typing
                    if hasattr(origin, '__name__') and 'Annotated' in str(origin):
                        if args:
                            # First argument is the actual type
                            type_arg = args[0]
                            # Format the type nicely
                            if hasattr(type_arg, '__name__'):
                                annotation_str = type_arg.__name__
                            else:
                                annotation_str = str(type_arg)
                            
                            # Additional arguments are metadata (descriptions)
                            if len(args) > 1:
                                # Look for string descriptions in the metadata
                                for metadata in args[1:]:
                                    if isinstance(metadata, str):
                                        description = metadata
                                        break
                    else:
                        annotation_str = str(param.annotation)
                else:
                    annotation_str = str(param.annotation)
            
            param_info = ParamSpec(
                name=param_name,
                annotation=annotation_str,
                default=str(param.default) if param.default != param.empty else "",
                description=description
            )
            params.append(param_info)
        
        return {
            'docstring': inspect.getdoc(func) or "",
            'parameters': params
        }
    except Exception as e:
        logger.warning(f"Failed to extract function info: {e}")
        return {
            'docstring': "",
            'parameters': []
        }


def clean_class_name(class_name: str, component_type: str) -> str:
    """
    Clean up internal class names for user-friendly display.
    
    Removes implementation suffixes like 'Input', 'Operation', 'FieldSegment'
    that are added by decorators but shouldn't be shown to users.
    """
    if component_type == "Source" and class_name.endswith('Input'):
        return class_name[:-5]  # Remove 'Input'
    elif component_type in ["Segment", "Field Segment"]:
        if class_name.endswith('Operation'):
            return class_name[:-9]  # Remove 'Operation'
        elif class_name.endswith('FieldSegment'):
            return class_name[:-12]  # Remove 'FieldSegment'
    return class_name


def extract_component_info(chatterlang_name: str, cls: type, component_type: str) -> Optional[ComponentInfo]:
    """
    Extract comprehensive information about a registered component.
    
    Args:
        chatterlang_name: The name used to register the component in ChatterLang
        cls: The registered class
        component_type: "Source", "Segment", or "Field Segment"
        
    Returns:
        ComponentInfo object with extracted information, or None if extraction fails
    """
    try:
        # Get basic class info
        raw_name = cls.__name__
        name = clean_class_name(raw_name, component_type)
        docstring = inspect.getdoc(cls) or ""
        base_classes = [base.__name__ for base in cls.__bases__ if base.__name__ != 'object']
        
        # Determine if it's a decorated function or regular class
        is_decorated_function = False
        original_function = None
        
        # Check for field segment with preserved original function
        if hasattr(cls, '_original_func'):
            is_decorated_function = True
            original_function = cls._original_func
        # Check for other wrapped functions (segment decorators)
        elif hasattr(cls, '_func') or hasattr(cls, '__wrapped__'):
            is_decorated_function = True
            original_function = getattr(cls, '_func', None) or getattr(cls, '__wrapped__', None)
        
        # Get module - prefer original function's module for decorated functions
        if is_decorated_function and original_function and hasattr(original_function, '__module__'):
            module = original_function.__module__
        else:
            module = cls.__module__ if hasattr(cls, '__module__') else "unknown"
        
        # Extract parameters
        parameters = []
        if is_decorated_function and original_function:
            # For decorated functions, use the original function signature
            func_info = extract_function_info(original_function)
            parameters = func_info['parameters']
            # Use function docstring if class docstring is generic
            if not docstring or "Abstract base class" in docstring:
                func_docstring = func_info['docstring']
                if func_docstring:
                    docstring = func_docstring
        else:
            # For regular classes, use __init__ method
            if hasattr(cls, '__init__'):
                init_info = extract_function_info(cls.__init__)
                parameters = init_info['parameters']
        
        # For field segments, try additional docstring extraction
        if component_type == "Field Segment":
            if hasattr(cls, '_original_func'):
                original_docstring = inspect.getdoc(cls._original_func)
                if original_docstring:
                    docstring = original_docstring
            elif hasattr(cls, '__doc__') and cls.__doc__ and "Abstract base class" not in cls.__doc__:
                docstring = cls.__doc__
            elif "Abstract base class" in docstring:
                docstring = f"Field segment '{chatterlang_name}' - processes individual fields from input items.\n\nNote: Original function documentation is not available."

            # Ensure synthetic parameters 'field' and 'set_as' are documented
            existing_param_names = {p.name for p in parameters}
            if 'field' not in existing_param_names:
                parameters.insert(0, ParamSpec(
                    name='field',
                    annotation='str',
                    default='',
                    description='The field to extract. If none, use full item.'
                ))
            if 'set_as' not in existing_param_names:
                parameters.append(ParamSpec(
                    name='set_as',
                    annotation='str',
                    default='',
                    description='The field to set/append the result as.'
                ))
        
        return ComponentInfo(
            name=name,
            chatterlang_name=chatterlang_name,
            component_type=component_type,
            module=module,
            base_classes=base_classes,
            docstring=docstring,
            parameters=parameters,
            original_function=original_function
        )
        
    except Exception as e:
        print(f"Warning: Failed to extract info for component {chatterlang_name}: {e}")
        return None


def detect_component_type(cls: type, registry_type: str) -> str:
    """
    Detect the specific component type based on class characteristics.
    
    Args:
        cls: The registered class
        registry_type: "Source" or "Segment" from the registry
        
    Returns:
        Specific component type: "Source", "Segment", or "Field Segment"
    """
    if registry_type == "Source":
        return "Source"
    elif registry_type == "Segment":
        # Check if it's a field segment
        if 'FieldSegment' in cls.__name__ or 'field_segment' in str(cls.__module__):
            return "Field Segment"
        else:
            return "Segment"
    else:
        return registry_type


def extract_parameters_dict(cls: type) -> Dict[str, str]:
    """
    Extract parameter information as a dictionary (for browser compatibility).
    
    Returns:
        Dict mapping parameter names to formatted parameter strings
    """
    parameters = {}
    
    def _process_parameter(param_name: str, param) -> str:
        """Helper function to process a single parameter."""
        param_str = param_name
        annotation_str = ""
        description = ""
        
        if param.annotation != param.empty:
            # Check if it's an Annotated type
            if get_origin(param.annotation) is not None:
                origin = get_origin(param.annotation)
                args = get_args(param.annotation)
                
                # Handle Annotated types
                if hasattr(origin, '__name__') and 'Annotated' in str(origin):
                    if args:
                        # First argument is the actual type
                        type_arg = args[0]
                        # Format the type nicely
                        if hasattr(type_arg, '__name__'):
                            annotation_str = type_arg.__name__
                        else:
                            annotation_str = str(type_arg)
                        
                        # Additional arguments are metadata (descriptions)
                        if len(args) > 1:
                            for metadata in args[1:]:
                                if isinstance(metadata, str):
                                    description = metadata
                                    break
                else:
                    annotation_str = str(param.annotation)
            else:
                annotation_str = str(param.annotation)
        
        if annotation_str:
            param_str += f": {annotation_str}"
        if param.default != param.empty:
            param_str += f" = {param.default}"
        if description:
            param_str += f"  # {description}"
        
        return param_str
    
    try:
        # Check if it's a field segment with preserved original function
        if hasattr(cls, '_original_func'):
            sig = inspect.signature(cls._original_func)
            for param_name, param in sig.parameters.items():
                if param_name in ['self', 'items', 'item']:
                    continue
                parameters[param_name] = _process_parameter(param_name, param)
        # Check if it's a decorated function with original function
        elif hasattr(cls, '_func'):
            original_func = cls._func
            sig = inspect.signature(original_func)
            for param_name, param in sig.parameters.items():
                if param_name in ['self', 'items', 'item']:
                    continue
                parameters[param_name] = _process_parameter(param_name, param)
        elif hasattr(cls, '__wrapped__'):
            original_func = cls.__wrapped__
            sig = inspect.signature(original_func)
            for param_name, param in sig.parameters.items():
                if param_name in ['self', 'items', 'item']:
                    continue
                parameters[param_name] = _process_parameter(param_name, param)
        else:
            # For regular classes, use __init__ method
            if hasattr(cls, '__init__'):
                sig = inspect.signature(cls.__init__)
                for param_name, param in sig.parameters.items():
                    if param_name == 'self':
                        continue
                    parameters[param_name] = _process_parameter(param_name, param)

        # If this appears to be a FieldSegment, add synthetic 'field' and 'set_as' parameters
        try:
            from talkpipe.pipe.core import AbstractFieldSegment
            is_field_seg = issubclass(cls, AbstractFieldSegment)
        except Exception:
            # Fallback detection by class name
            is_field_seg = 'FieldSegment' in getattr(cls, '__name__', '')

        if is_field_seg:
            if 'field' not in parameters:
                parameters['field'] = "field: <class 'str'>  # The field to extract. If none, use full item."
            if 'set_as' not in parameters:
                parameters['set_as'] = "set_as: <class 'str'>  # The field to set/append the result as."
    except Exception as e:
        logger.warning(f"Failed to extract parameters for class {cls.__name__}: {e}")
        pass  # If parameter extraction fails, just return empty dict
    
    return parameters