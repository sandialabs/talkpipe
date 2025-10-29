"""Core definitions for the Pipe Framework

This module contains the core definitions for the Pipe Framework.  
This includes the abstract base classes for creating input generators 
and operations, as well as the Pipeline class for chaining operations together.
"""
import logging
from abc import ABC, abstractmethod
from typing import (
    Any, TypeVar, Generic, Iterable, List, 
    Iterator, Union, Callable, Type, Concatenate, ParamSpec, Annotated
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
    
    def add_constants(self, 
                      constants: Annotated[dict, "Dictionary of constants to add"], 
                      override: Annotated[bool, "If True, new constants override existing ones. If False, existing constants are preserved."] = True):
        """Add constants to the const_store."""
        if override:
            self._const_store.update(constants)
        else:
            for key, value in constants.items():
                if key not in self._const_store:
                    self._const_store[key] = value
    

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
    """Abstract base class for all segments in the TalkPipe framework.
    
    A segment is an operation that can be applied to an iterable input,
    producing an iterable output. Segments are the building blocks of
    data processing pipelines in TalkPipe.
    
    Key characteristics:
    - Input and output types can be different (T -> U)
    - Number of input items may differ from output items
    - Can be chained together using the | operator
    - Supports lazy evaluation through iterators
    
    Segments can be chained together to create pipelines:
        pipeline = segment1 | segment2 | segment3
    
    Attributes:
        upstream (List[AbstractSegment]): List of upstream segments
        downstream (List[AbstractSegment]): List of downstream segments
    """

    def __init__(self):
        self.upstream = []
        self.downstream = []
    
    @abstractmethod
    def transform(self, input_iter: Annotated[Iterable[T], "An iterable of input items to process"]) -> Iterator[U]:
        """Transform input items into output items.
        
        This is the core method that must be implemented by all segment subclasses.
        It defines how the segment processes data flowing through the pipeline.
        
        Returns:
            Iterator[U]: An iterator yielding transformed output items
            
        Notes:
            - The number of output items need not equal the number of input items
            - The segment may consume only part of the input iterator
            - Implementation should use yield to produce output lazily
            - Input iterator may be consumed multiple times if needed
        
        Examples:
            # Simple 1:1 transformation
            def transform(self, input_iter):
                for item in input_iter:
                    yield item.upper()
                    
            # Filtering (reducing items)
            def transform(self, input_iter):
                for item in input_iter:
                    if item > 0:
                        yield item
                        
            # Expanding (increasing items)
            def transform(self, input_iter):
                for item in input_iter:
                    yield item
                    yield item * 2
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

    def as_function(self, 
                    single_in: Annotated[bool, "If True, the function will expect a single input argument."] = False, 
                    single_out: Annotated[bool, "If True, the function will return a single output."] = False) -> Callable:
        """Convert the segment to a callable function.
        
        By default, the function will expect and return an iterable.
        single_in and single_out can be set to True to expect a single input and return a single output.
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
    """Abstract base class for data sources that can start a pipeline.

    Sources are the entry points for data pipelines - they generate data without
    requiring input from upstream segments. Sources can read from files, databases,
    APIs, or generate synthetic data.
    
    Key characteristics:
    - No input required (unlike segments)
    - Can be chained with segments using the | operator
    - Must implement the generate() method
    - Supports lazy evaluation through iterators
    
    Examples of sources:
    - File readers (CSV, JSON, text files)
    - Database queries
    - API endpoints
    - Random data generators
    - User input prompts
    
    Attributes:
        upstream (List): Always empty (sources have no upstream)
        downstream (List[AbstractSegment]): List of downstream segments
    """
    
    def __init__(self):
        self.upstream = []
        self.downstream = []
    
    @abstractmethod
    def generate(self) -> Iterator[U]:
        """Generate data items for the pipeline.
        
        This is the core method that must be implemented by all source subclasses.
        It defines how the source produces data to feed into the pipeline.
        
        Returns:
            Iterator[U]: An iterator yielding data items
            
        Notes:
            - May generate finite or infinite sequences
            - Should use yield to produce items lazily
            - Implementation depends on the data source type
            - May involve I/O operations (files, network, databases)
        
        Examples:
            # File-based source
            def generate(self):
                with open(self.filename) as f:
                    for line in f:
                        yield line.strip()
                        
            # Infinite sequence source
            def generate(self):
                counter = 0
                while True:
                    yield counter
                    counter += 1
                    
            # API-based source
            def generate(self):
                response = requests.get(self.url)
                for item in response.json():
                    yield item
        """
    
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

def source(*decorator_args: Annotated[Any, "Positional arguments for the input generator"], 
           **decorator_kwargs: Annotated[Any, "Keyword arguments for the input generator"]):
    """Decorator to convert a function into an source class with optional parameters.
    
    Can be used with or without arguments:
    @input 
    def func(): ...
    
    @input(param1=value1, param2=value2)
    def func(): ...
    
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
                # Store reference to original function for documentation access
                self._original_func = func

            def generate(self) -> Iterator[U]:
                # If the function returns an iterator, use it
                yield from func()
        
        # Set the name of the class to match the original function
        FunctionSource.__name__ = f"{func.__name__}Input"
        # Preserve original function's docstring and metadata
        FunctionSource.__doc__ = func.__doc__
        FunctionSource._original_func = func
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
                # Store reference to original function for documentation access
                self._original_func = func
            
            def generate(self) -> Iterator[U]:
                # If the function returns an iterator, use it
                return self._func()
        
        # Set the name of the class to match the original function
        ParameterizedSource.__name__ = f"{func.__name__}Input"
        # Preserve original function's docstring and metadata
        ParameterizedSource.__doc__ = func.__doc__
        ParameterizedSource._original_func = func
        return ParameterizedSource
    
    return decorator

def segment(*decorator_args: Annotated[Any, "Positional arguments for the operation"], 
            **decorator_kwargs: Annotated[Any, "Keyword arguments for the operation"]):
    """Decorator to convert a function into an segment class with optional parameters.
    
    Can be used with or without arguments:
    @segment 
    def func(x): ...
    
    @segment(param1=value1, param2=value2)
    def func(x): ...
    
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
                # Store reference to original function for documentation access
                self._original_func = func
            
            def transform(self, input_iter: Iterable[T]) -> Iterator[U]:
                return func(input_iter)
        
        # Set the name of the class to match the original function
        FunctionSegment.__name__ = f"{func.__name__}Operation"
        # Preserve original function's docstring and metadata
        FunctionSegment.__doc__ = func.__doc__
        FunctionSegment._original_func = func
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
                # Store reference to original function for documentation access
                self._original_func = func
            
            def transform(self, input_iter: Iterable[T]) -> Iterator[U]:
                return self._func(input_iter)
        
        # Set the name of the class to match the original function
        ParameterizedSegment.__name__ = f"{func.__name__}Operation"
        # Preserve original function's docstring and metadata
        ParameterizedSegment.__doc__ = func.__doc__
        ParameterizedSegment._original_func = func
        return ParameterizedSegment
    
    return decorator

def field_segment(*decorator_args, **decorator_kwargs):
    """
    Decorator that creates a segment which processes a single field and optionally appends results.
    
    Args can include:
        field: The field to extract from each item
        set_as: The field name to append the result as
    """
    def decorator(func):
        class FieldSegment(AbstractFieldSegment):
            def __init__(self, *init_args, **init_kwargs):
                merged_kwargs = {**decorator_kwargs, **init_kwargs}
                field = merged_kwargs.pop('field', None)
                set_as = merged_kwargs.pop('set_as', None)
                multi_emit = merged_kwargs.pop('multi_emit', False)
                super().__init__(field=field, set_as=set_as, multi_emit=multi_emit)
                self._func = lambda x: func(x, *init_args, **merged_kwargs)
                # Store reference to original function for documentation access
                self._original_func = func
            
            def process_value(self, value):
                return self._func(value)
        
        FieldSegment.__name__ = f"{func.__name__}FieldSegment"
        # Preserve original function's docstring and metadata
        FieldSegment.__doc__ = func.__doc__
        FieldSegment._original_func = func
        return FieldSegment
    
    if len(decorator_args) == 1 and callable(decorator_args[0]):
        return decorator(decorator_args[0])
    return decorator

class AbstractFieldSegment(AbstractSegment[T, U]):
    """Abstract base class for segments that process a single field and optionally set results.
    
    This class handles the 'field' and 'set_as' parameters that are commonly used
    in field-processing segments, making it easy for descendant classes to have
    their own constructors while still supporting field extraction and result setting.
    
    Args:
        field: The field to extract from each item (optional)
        set_as: The field name to set/append the result as (optional)
    """

    def __init__(self, 
                 field: Annotated[str, "The field to extract.  If none, use full item."] = None, 
                 set_as: Annotated[str, "The field to set/append the result as."] = None, 
                 multi_emit: Annotated[bool, "Whether this class potentially emits multiple results per item."
                                       "Should be set by the subclass constructor call or the field_segment decorator, not by the user."] = False):
        super().__init__()
        self.field = field
        self.set_as = set_as
        self.multi_emit = multi_emit

    @abstractmethod
    def process_value(self, value: Any) -> Any:
        """Process the extracted field value or the entire item.
        
        This method must be implemented by subclasses to define how to process
        the extracted field value (or entire item if no field is specified).
        
        Args:
            value: The field value extracted from the item, or the entire item
                  if no field was specified
        
        Returns:
            Any: The processed result
        """
        pass
    
    def transform(self, input_iter: Iterable[T]) -> Iterator[U]:
        """Transform input items by processing field values.
        
        For each item:
        1. Extract the specified field value (or use entire item if no field)
        2. Process the value using process_value()
        3. Either yield the result directly or set it on the item and yield the item
        """
        for item in input_iter:
            value = data_manipulation.extract_property(item, self.field) if self.field else item
            processed = self.process_value(value)
            if not self.multi_emit: # If not multi-emitting, wrap the result in a list
                processed = [processed]
            for result in processed:
                if self.set_as:
                    ans = item.copy() if self.multi_emit else item
                    ans[self.set_as] = result
                    yield ans
                else:
                    yield result

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

    def transform(self, initial_input: Annotated[Iterable[Any], "The initial input data"] = None) -> Iterator[Any]:
        """Run the script
        
        If the first item in a segment is an AbstractSource, it will be called
        to generate the initial input. Otherwise, the initial input will be passed.
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

    


