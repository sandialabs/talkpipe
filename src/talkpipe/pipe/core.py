"""Core definitions for the Pipe Framework

This module contains the core definitions for the Pipe Framework.  
This includes the abstract base classes for creating input generators 
and operations, as well as the Pipeline class for chaining operations together.
"""
import logging
from abc import ABC, abstractmethod
from typing import (
    Any, TypeVar, Generic, Iterable, List, 
    Iterator, Union, Callable, Type, Concatenate, ParamSpec
)
from talkpipe.util import data_manipulation

logger = logging.getLogger(__name__)

T = TypeVar('T')
U = TypeVar('U')
P = ParamSpec('P')

class RuntimeComponent:
    """A class to store runtime variables and constants.  This is available to all
    segments and sources for pipelines compiled from a chatterlang script.
    """
    _variable_store: dict
    _const_store: dict

    def __init__(self):
        self._variable_store = {}
        self._const_store = {}

    @property
    def variable_store(self):
        return self._variable_store
    
    @variable_store.setter
    def variable_store(self, value: dict):
        self._variable_store = value

    @property
    def const_store(self):
        return self._const_store
    
    @const_store.setter
    def const_store(self, value: dict):
        self._const_store = value
    

class HasRuntimeComponent:
    """A mixin class to add a runtime component to a segment or source."""
    _runtime: RuntimeComponent = None

    @property
    def runtime(self):
        return self._runtime
    
    @runtime.setter
    def runtime(self, value: RuntimeComponent):
        self._runtime = value


class AbstractSegment(ABC, HasRuntimeComponent, Generic[T, U]):
    """Common parent of all segments
    
    A segment is an operation that can be applied to an iterable input,
    producing an iterable output.  There is no requirement that the input
    and output types be the same or that the number of inputs and outputs
    be the same.  This is python, after all :)
    
    Segments can be chained together to create a pipeline.
    """

    def __init__(self):
        self.upstream = []
        self.downstream = []
    
    @abstractmethod
    def transform(self, input_iter: Iterable[T]) -> Iterator[U]:
        """This method, implemented by subclasses, are what perform the main operation of the segment.
        
        Each implementation should read as many items as necessary from the input_iter and yield 
        items as appropriate.  It is not required that the number of items emitted be the same as
        the number of items in the input iterator or that the segment fully drain the input iterator.
        """

    def registerUpstream(self, upstream: 'AbstractSegment'):
        """Register an upstream segment.  This is used in the Pipe API to track dependencies."""
        self.upstream.append(upstream)

    def registerDownstream(self, downstream: 'AbstractSegment'):
        """Register a downstream segment.  This is used in the Pipe API to track dependencies."""
        self.downstream.append(downstream)

    def __or__(self, other: 'AbstractSegment[U, Any]') -> 'Pipeline':
        """Allows chaining operations using the | (or) operator."""
        self.registerDownstream(other)
        other.registerUpstream(self)
        return Pipeline(self, other)

    def __call__(self, input_iter: Iterable[T] = None) -> Iterator[U]:
        logger.debug(f"Running segment {self.__class__.__name__}")
        ans = self.transform(input_iter)
        logger.debug(f"Finished segment {self.__class__.__name__}")
        return ans

    def asFunction(self, single_in: bool = False, single_out: bool = False) -> Callable:
        """Convert the segment to a callable function.  By default, the function will expect and return an iterable.
        single_in and single_out can be set to True to expect a single input and return a single output.
        
        <pre>
        Args:
            single_in (bool): If True, the function will expect a single input argument.
            single_out (bool): If True, the function will return a single output.
        </pre>
        """
        def func(item = None):
            results = list(self([item] if single_in else item))
            if single_out:
                if len(results) != 1:
                    raise ValueError(f"Expected 1 result, got {len(results)}")
                else:
                    return results[0]
            else:
                return results
        return func

class AbstractSource(ABC, HasRuntimeComponent, Generic[U]):
    """
    Abstract base class for creating input generators that can start a pipeline.

    An AbstractSource is like a segment, but it does not require an input.
    """
    
    def __init__(self):
        self.upstream = []
        self.downstream = []
    
    @abstractmethod
    def generate(self) -> Iterator[U]:
        """Generate an infinite or finite iterator of outputs."""
    
    def registerUpstream(self, upstream: 'AbstractSegment'):
        raise RuntimeError("Cannot register an upstream segment for a source.")

    def registerDownstream(self, downstream: 'AbstractSegment'):
        """Register a downstream segment.  This is used in the Pipe API to track dependencies."""
        self.downstream.append(downstream)

    def __or__(self, other: 'AbstractSegment[U, Any]') -> 'Pipeline':
        """Allows chaining operations using the | (or) operator."""
        self.registerDownstream(other)
        other.registerUpstream(self)
        return Pipeline(self, other)
    
    def __call__(self) -> Iterator[U]:
        """Allows calling the instance to generate an iterator."""
        logger.debug(f"Running source {self.__class__.__name__}")
        ans = self.generate()
        logger.debug(f"Finished source {self.__class__.__name__}")
        return ans

def source(*decorator_args, **decorator_kwargs):
    """
    Decorator to convert a function into an source class with optional parameters.
    
    Can be used with or without arguments:
    @input 
    def func(): ...
    
    @input(param1=value1, param2=value2)
    def func(): ...
    
    Args:
        *decorator_args: Positional arguments for the input generator
        **decorator_kwargs: Keyword arguments for the input generator
    
    Returns:
        Callable: A decorator that creates an Input subclass
    """
    # Determine if used with or without arguments
    if len(decorator_args) == 1 and callable(decorator_args[0]):
        # Called without arguments, first arg is the function
        func = decorator_args[0]
        
        class FunctionSource(AbstractSource[U]):

            def __init__(self):
                super().__init__()

            def generate(self) -> Iterator[U]:
                # If the function returns an iterator, use it
                yield from func()
        
        # Set the name of the class to match the original function
        FunctionSource.__name__ = f"{func.__name__}Input"
        return FunctionSource
    
    # Called with arguments, return a decorator
    def decorator(func: Callable[P, U]) -> Type[AbstractSource[U]]:
        class ParameterizedSource(AbstractSource[U]):
            def __init__(self, *init_args, **init_kwargs):
                """
                Initialize the input generator with constructor arguments.
                Combines decorator-level and constructor-level arguments.
                """
                # Merge decorator and constructor arguments
                # Constructor arguments take precedence
                super().__init__()
                merged_kwargs = {**decorator_kwargs, **init_kwargs}
                
                # Bind arguments to the function
                self._func = lambda: func(*init_args, **merged_kwargs)
            
            def generate(self) -> Iterator[U]:
                # If the function returns an iterator, use it
                return self._func()
        
        # Set the name of the class to match the original function
        ParameterizedSource.__name__ = f"{func.__name__}Input"
        return ParameterizedSource
    
    return decorator

def segment(*decorator_args, **decorator_kwargs):
    """
    Decorator to convert a function into an segment class with optional parameters.
    
    Can be used with or without arguments:
    @segment 
    def func(x): ...
    
    @segment(param1=value1, param2=value2)
    def func(x): ...
    
    Args:
        *decorator_args: Positional arguments for the operation
        **decorator_kwargs: Keyword arguments for the operation
    
    Returns:
        Callable: A decorator that creates an Operation subclass
    """
    # Determine if used with or without arguments
    if len(decorator_args) == 1 and callable(decorator_args[0]):
        # Called without arguments, first arg is the function
        func = decorator_args[0]
        
        class FunctionSegment(AbstractSegment[T, U]):

            def __init__(self):
                super().__init__()
            
            def transform(self, input_iter: Iterable[T]) -> Iterator[U]:
                return func(input_iter)
        
        # Set the name of the class to match the original function
        FunctionSegment.__name__ = f"{func.__name__}Operation"
        return FunctionSegment
    
    # Called with arguments, return a decorator
    def decorator(func: Callable[Concatenate[T, P], U]) -> Type[AbstractSegment[T, U]]:
        class ParameterizedSegment(AbstractSegment[T, U]):
            def __init__(self, *init_args, **init_kwargs):
                """
                Initialize the operation with constructor arguments.
                Combines decorator-level and constructor-level arguments.
                """
                # Merge decorator and constructor arguments
                # Constructor arguments take precedence
                super().__init__()
                merged_kwargs = {**decorator_kwargs, **init_kwargs}
                
                # Bind arguments to the function
                self._func = lambda x: func(x, *init_args, **merged_kwargs)
            
            def transform(self, input_iter: Iterable[T]) -> Iterator[U]:
                return self._func(input_iter)
        
        # Set the name of the class to match the original function
        ParameterizedSegment.__name__ = f"{func.__name__}Operation"
        return ParameterizedSegment
    
    return decorator

def field_segment(*decorator_args, **decorator_kwargs):
    """
    Decorator that creates a segment which processes a single field and optionally appends results.
    
    Args can include:
        field: The field to extract from each item
        append_as: The field name to append the result as
    """
    def decorator(func):
        class FieldSegment(AbstractSegment):
            def __init__(self, *init_args, **init_kwargs):
                super().__init__()
                merged_kwargs = {**decorator_kwargs, **init_kwargs}
                self.field = merged_kwargs.get('field')
                self.append_as = merged_kwargs.get('append_as')
                merged_kwargs.pop('field', None)
                merged_kwargs.pop('append_as', None)
                self._func = lambda x: func(x, *init_args, **merged_kwargs)
            
            def transform(self, input_iter):
                for item in input_iter:
                    value = data_manipulation.extract_property(item, self.field) if self.field else item
                    result = self._func(value)
                    if self.append_as:
                        item[self.append_as] = result
                        yield item
                    else:
                        yield result
        
        FieldSegment.__name__ = f"{func.__name__}FieldSegment"
        return FieldSegment
    
    if len(decorator_args) == 1 and callable(decorator_args[0]):
        return decorator(decorator_args[0])
    return decorator

class Pipeline(AbstractSegment):
    """A pipeline is a sequence of operations.  Each operation draws from the output of the previous operation
    and yields items to the next operation.  The pipeline can be executed by calling it with an input iterator.    
    """
    
    def __init__(self, *operations: Union[AbstractSource, AbstractSegment]):
        super().__init__()
        self.operations = list(operations)
        
    def transform(self, input_iter: Iterable[Any] = None) -> Iterator[Any]:
        """
        Execute pipeline for iterable processing.
        Works with both AbstractInput and AbstractTransform.
        """
        current_iter = input_iter
        for op in self.operations:
            if isinstance(op, AbstractSource):
                current_iter = op()
            else:
                current_iter = op(current_iter)
        yield from current_iter
    
    def __or__(self, other: Union[AbstractSource, AbstractSegment]) -> 'Pipeline':
        return Pipeline(*self.operations, other)
    

class Script(AbstractSegment):
    """A list of one or more segments to execute in order.
    
    The difference between a Script and a Pipeline is that a Script
    fully resolves each segment before moving to the next one.
    """

    def __init__(self, segments: List[AbstractSegment]):
        super().__init__()
        self.segments = segments

    def transform(self, initial_input: Iterable[Any] = None) -> Iterator[Any]:
        """Run the script
        
        If the first item in a segment is an AbstractSource, it will be called
        to generate the initial input.  Otherwise, the initial input will be passed.

        Args:
            initial_input (Iterable[Any]): The initial input data

        """
        current_iter = initial_input
        for i, seg in enumerate(self.segments):
            if isinstance(seg, AbstractSource):
                current_iter = seg()
            else:
                current_iter = seg(current_iter)
            if i < len(self.segments) - 1:
                list(current_iter) #consume the iterator unless it is the last one.  Ensures the previous segment is fully executed
                current_iter = None
        yield from current_iter


class Loop(AbstractSegment):
    """
    A class that allows looping over an iterable multiple times.  Mostly useful
    in chatterlang.  In python, just using your own loop is probably easier.
    """
    
    def __init__(self, times: int, script: Script):
        super().__init__()
        self.times = times
        self.script = script

    def transform(self, initial_input: Iterable[Any] = None) -> Iterator[Any]:
        current_iter = initial_input
        for i in range(self.times):
            current_iter = self.script.transform(current_iter)
            if i < self.times - 1:
                list(current_iter)
        yield from current_iter

    


