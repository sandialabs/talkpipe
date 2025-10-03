""" A registry for input, transform and output modules. 

Used by the CLI to load the correct modules based on the pipeline provided.
The register_input_module, register_transform_module and register_output_module
decorators are used to register the modules in the registry.
"""
from typing import Dict, Type, TypeVar, Generic

T = TypeVar('T')

class Registry(Generic[T]):
    """ A registry for input, transform and output modules. """

    def __init__(self):
        """ Initialize the registry. """
        self._registry: Dict[str, Type[T]] = {}
    
    def register(self, cls: Type[T], name: str) -> None:
        """ Register a module in the registry. """
        self._registry[name] = cls
    
    def get(self, name: str) -> Type[T]:
        """ Get a module from the registry. """
        return self._registry[name]
    
    @property
    def all(self) -> Dict[str, Type[T]]:
        """ Get all modules from the registry. """
        return self._registry.copy()
    
input_registry = Registry()
segment_registry = Registry()

def register_source(*names: str, name: str = None):
    """Decorator to register a source module with one or more names in the registry. """
    # Handle backward compatibility with name= keyword argument
    if name is not None:
        if names:
            raise ValueError("Cannot specify both positional names and 'name' keyword argument")
        names = (name,)

    if not names:
        raise ValueError("At least one name must be provided")

    def wrap(cls):
        for source_name in names:
            input_registry.register(cls, name=source_name)
        return cls
    return wrap

def register_segment(*names: str, name: str = None):
    """Decorator to register a segment module with one or more names in the registry. """
    # Handle backward compatibility with name= keyword argument
    if name is not None:
        if names:
            raise ValueError("Cannot specify both positional names and 'name' keyword argument")
        names = (name,)

    if not names:
        raise ValueError("At least one name must be provided")

    def wrap(cls):
        for segment_name in names:
            segment_registry.register(cls, name=segment_name)
        return cls
    return wrap

