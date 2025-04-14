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

def register_source(name: str):
    """Decorator to register a source module in the registry. """
    def wrap(cls):
        input_registry.register(cls, name=name)
        return cls
    return wrap

def register_segment(name: str):
    """Decorator to register a setment module in the registry. """
    def wrap(cls):
        segment_registry.register(cls, name=name)
        return cls
    return wrap

