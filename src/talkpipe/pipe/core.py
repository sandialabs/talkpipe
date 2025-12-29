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
from pydantic import BaseModel, ConfigDict
from talkpipe.util import data_manipulation
from talkpipe.util.iterators import bypass

logger = logging.getLogger(__name__)

T = TypeVar('T')
U = TypeVar('U')
P = ParamSpec('P')


class Metadata(BaseModel):
    """Metadata objects flowing through pipelines.
    
    Metadata objects are used to send control signals or metadata through
    pipelines alongside regular data items. By default, metadata is passed
    through segments without processing, but segments can opt-in to process
    metadata by setting `process_metadata=True`.
    
    This is useful for implementing features like flushing buffers, sending
    end-of-stream signals, or passing configuration updates through pipelines.
    
    Metadata inherits from Pydantic BaseModel, allowing arbitrary fields to be
    added dynamically. This makes it easy to create metadata with specific
    attributes while maintaining type safety and validation.
    
    Examples:
        # Create metadata with specific fields
        flush_signal = Metadata(action="flush", buffer_id="main")
        
        # Create from dictionary (allows arbitrary fields)
        flush_signal = Metadata(**{"action": "flush", "timestamp": "2025-01-15"})
        
        # Check if an item is metadata
        if is_metadata(item):
            if item.action == "flush":
                # Handle flush
                pass
        
        # Segments can easily differentiate metadata from regular items
        @segment()
        def my_transform(items):
            for item in items:
                if is_metadata(item):
                    yield item  # Pass through or handle
                else:
                    yield process(item)
    """
    
    model_config = ConfigDict(extra="allow")  # Allow arbitrary fields


def is_metadata(obj: Any) -> bool:
    """Check if an object is a Metadata instance.
    
    Args:
        obj: Object to check
        
    Returns:
        True if obj is a Metadata instance, False otherwise
        
    Examples:
        if is_metadata(item):
            # Handle metadata - access fields directly
            if item.action == "flush":
                # Handle flush
                pass
    """
    return isinstance(obj, Metadata)


def create_metadata(**kwargs) -> Metadata:
    """Create a Metadata object with the provided fields.
    
    This is a convenience function for creating metadata objects.
    You can also use Metadata(**kwargs) directly.
    
    Args:
        **kwargs: Fields to set on the metadata object
        
    Returns:
        A Metadata instance with the provided fields
        
    Examples:
        # In a source or segment
        yield create_metadata(action="flush", buffer_id="main")
        # Equivalent to:
        yield Metadata(action="flush", buffer_id="main")
        
        # From dictionary
        data = {"action": "flush", "timestamp": "2025-01-15"}
        yield create_metadata(**data)
    """
    return Metadata(**kwargs)

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


def filter_out_metadata(input_iter: Iterable[Any]) -> Iterable[Any]:
    yield from (item for item in input_iter if not is_metadata(item))

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
    - By default, metadata objects are passed through without processing
    
    Segments can be chained together to create pipelines:
        pipeline = segment1 | segment2 | segment3
    
    Attributes:
        upstream (List[AbstractSegment]): List of upstream segments
        downstream (List[AbstractSegment]): List of downstream segments
        process_metadata (bool): If True, metadata objects are passed to transform().
                                 If False (default), metadata is filtered out to preserve
                                 streaming without buffering. Segments that need metadata
                                 (e.g., for flush signals) must set process_metadata=True.
    """

    def __init__(self, process_metadata: Annotated[bool, "If True, metadata objects will be passed to transform(). If False, metadata is automatically passed through."] = False):
        self.upstream = []
        self.downstream = []
        self.process_metadata = process_metadata
    
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
        """Register an upstream segment.
        
        Used internally by the Pipe API to track dependencies when chaining segments.
        This allows the segment to know what segment is feeding it data.
        
        Args:
            upstream: The upstream segment that feeds data into this segment
        """
        self.upstream.append(upstream)

    def registerDownstream(self, downstream: 'AbstractSegment'):
        """Register a downstream segment.
        
        Used internally by the Pipe API to track dependencies when chaining segments.
        This allows the segment to know what segments consume its output.
        
        Args:
            downstream: The downstream segment that consumes this segment's output
        """
        self.downstream.append(downstream)

    def __or__(self, other: 'AbstractSegment[U, Any]') -> 'Pipeline':
        """Allows chaining operations using the | (or) operator."""
        self.registerDownstream(other)
        other.registerUpstream(self)
        return Pipeline(self, other)

    def __call__(self, input_iter: Iterable[T] = None) -> Iterator[U]:
        logger.debug(f"Running segment {self.__class__.__name__}")
        
        if input_iter is None:
            input_iter = iter([])
        
        # Handle metadata when process_metadata=False
        if not self.process_metadata:
            if len(self.downstream) > 0:
                ans = bypass(input_iter, lambda x: is_metadata(x), self.transform)
            else:
                ans = self.transform(filter_out_metadata(input_iter))
            return ans
        else:
            # process_metadata=True: pass everything to transform including metadata
            # Segments can handle metadata positioning themselves if needed
            ans = self.transform(input_iter)
            logger.debug(f"Finished segment {self.__class__.__name__}")
            return ans
        
        logger.debug(f"Finished segment {self.__class__.__name__}")

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
    - Can emit metadata objects alongside regular data items
    
    Examples of sources:
    - File readers (CSV, JSON, text files)
    - Database queries
    - API endpoints
    - Random data generators
    - User input prompts
    
    Attributes:
        upstream (List): Always empty (sources have no upstream)
        downstream (List[AbstractSegment]): List of downstream segments
        process_metadata (bool): Not used for sources (they generate, not transform),
                                 but included for API consistency
    """
    
    def __init__(self, process_metadata: Annotated[bool, "Not used for sources, but included for API consistency"] = False):
        self.upstream = []
        self.downstream = []
        self.process_metadata = process_metadata
    
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
        """Register a downstream segment.
        
        Used internally by the Pipe API to track dependencies when chaining sources with segments.
        This allows the source to know what segments consume its output.
        
        Args:
            downstream: The downstream segment that consumes this source's output
        """
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
    """Decorator to convert a function into a source class with optional parameters.
    
    Sources are entry points for pipelines. They generate data without requiring input.
    This decorator converts a generator function into a reusable Source class.
    
    Can be used with or without arguments:
    
        # Without arguments - function takes no parameters
        @source
        def myNumbers():
            for i in range(10):
                yield i
        
        # With arguments - function parameters become instance parameters
        @source()
        def myLines(filename: str):
            with open(filename) as f:
                for line in f:
                    yield line.strip()
    
    The decorated function should yield items to be consumed by segments downstream.
    
    Returns:
        A Source class that can be instantiated and chained into pipelines.
        The class preserves the original function's docstring for documentation.
    
    Examples:
        # Create and use sources
        numbers = myNumbers()
        lines = myLines("data.txt")
        
        # Chain with segments
        pipeline = myNumbers() | some_segment | output_segment
    """
    # Determine if used with or without arguments
    if len(decorator_args) == 1 and callable(decorator_args[0]):
        # Called without arguments, first arg is the function
        func = decorator_args[0]
        
        class FunctionSource(AbstractSource[U]):

            def __init__(self, process_metadata: bool = False):
                super().__init__(process_metadata=process_metadata)
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
                process_metadata = init_kwargs.pop('process_metadata', decorator_kwargs.get('process_metadata', False))
                super().__init__(process_metadata=process_metadata)
                # Create merged kwargs without process_metadata (it's already handled above)
                merged_kwargs = {k: v for k, v in {**decorator_kwargs, **init_kwargs}.items() if k != 'process_metadata'}
                
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
    """Decorator to convert a function into a segment class with optional parameters.
    
    Segments are operations that transform data flowing through pipelines.
    This decorator converts a transformation function into a reusable Segment class.
    
    Can be used with or without arguments:
    
        # Without arguments - processes all items in one pass
        @segment
        def uppercase(items):
            for item in items:
                yield item.upper()
        
        # With arguments - function receives items and additional parameters
        @segment()
        def filterByValue(items, field: str, target: str):
            for item in items:
                if item.get(field) == target:
                    yield item
    
    The decorated function receives an iterable of input items and should yield
    output items. This enables lazy evaluation - items flow through the pipeline
    on-demand rather than being fully buffered.
    
    Returns:
        A Segment class that can be instantiated and chained into pipelines.
        The class preserves the original function's docstring for documentation.
    
    Examples:
        # Create and use segments
        upper = uppercase()
        filtered = filterByValue(field="status", target="active")
        
        # Chain segments together
        pipeline = source | uppercase() | filterByValue(field="type", target="user")
    """
    # Determine if used with or without arguments
    if len(decorator_args) == 1 and callable(decorator_args[0]):
        # Called without arguments, first arg is the function
        func = decorator_args[0]
        
        class FunctionSegment(AbstractSegment[T, U]):

            def __init__(self, process_metadata: bool = False):
                super().__init__(process_metadata=process_metadata)
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
                process_metadata = init_kwargs.pop('process_metadata', decorator_kwargs.get('process_metadata', False))
                super().__init__(process_metadata=process_metadata)
                # Create merged kwargs without process_metadata (it's already handled above)
                merged_kwargs = {k: v for k, v in {**decorator_kwargs, **init_kwargs}.items() if k != 'process_metadata'}
                
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
    """Decorator that creates a segment for processing a single field per item.
    
    Field segments are specialized segments designed to extract a field from items,
    process it, and optionally set the result back on the item. This is a common
    pattern for transforming item properties in pipelines.
    
    When field_segment processes an item:
    1. Extracts the specified field from the item (or uses the entire item if no field)
    2. Passes the extracted value to the decorated function
    3. Either yields the result directly or sets it on the item and yields the item
    
    Keyword arguments can include:
        field: The name of the field to extract from each item
        set_as: The name of the field to set with the result on the item
        multi_emit: Whether the function returns multiple results per input (advanced)
    
    When used without parameters:
        @field_segment
        def extractDomain(email: str):
            return email.split('@')[1]
    
    When used with parameters:
        @field_segment()
        def extractDomain(email: str):
            return email.split('@')[1]
    
    Returns:
        A FieldSegment class that can be instantiated and chained into pipelines.
        The class preserves the original function's docstring.
    
    Examples:
        # Extract and return just the value
        pipeline = data_source | extractDomain(field="email") | output
        # Items: [{'email': 'user@example.com'}]
        # Output: ['example.com']
        
        # Extract, process, and set back on item
        pipeline = data_source | extractDomain(field="email", set_as="domain") | output
        # Items: [{'email': 'user@example.com'}]
        # Output: [{'email': 'user@example.com', 'domain': 'example.com'}]
    """
    def decorator(func):
        class FieldSegment(AbstractFieldSegment):
            def __init__(self, *init_args, **init_kwargs):
                merged_kwargs = {**decorator_kwargs, **init_kwargs}
                field = merged_kwargs.pop('field', None)
                set_as = merged_kwargs.pop('set_as', None)
                multi_emit = merged_kwargs.pop('multi_emit', False)
                process_metadata = merged_kwargs.pop('process_metadata', False)
                super().__init__(field=field, set_as=set_as, multi_emit=multi_emit, process_metadata=process_metadata)
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
    
    This class handles the common pattern of extracting a field from items, processing
    the field value, and optionally setting the result back on the item. This makes it
    easy for descendant classes to focus on the processing logic while field extraction
    and result assignment are handled automatically.
    
    The class can work in two modes:
    1. Extract and return: Process a field value and yield just the result
    2. Extract, process, and set: Process a field value and set it as a field on the item
    
    Attributes:
        field: The field name to extract (if None, uses entire item)
        set_as: The field name to set with the result (if None, yields result directly)
        multi_emit: Whether process_value returns multiple results (advanced usage)
    
    Example:
        class ExtractDomain(AbstractFieldSegment):
            def process_value(self, email_value: str) -> str:
                return email_value.split('@')[1]
        
        # Usage: Extract just the domain
        extractor = ExtractDomain(field="email")
        domains = extractor({'email': 'user@example.com'})
        
        # Usage: Extract and set as new field
        extractor = ExtractDomain(field="email", set_as="domain")
        result = extractor({'email': 'user@example.com'})
        # Yields: {'email': 'user@example.com', 'domain': 'example.com'}
    """

    def __init__(self, 
                 field: Annotated[str, "The field to extract.  If none, use full item."] = None, 
                 set_as: Annotated[str, "The field to set/append the result as."] = None, 
                 multi_emit: Annotated[bool, "Whether this class potentially emits multiple results per item."
                                       "Should be set by the subclass constructor call or the field_segment decorator, not by the user."] = False,
                 process_metadata: Annotated[bool, "If True, metadata objects will be passed to transform(). If False, metadata is automatically passed through."] = False):
        super().__init__(process_metadata=process_metadata)
        self.field = field
        self.set_as = set_as
        self.multi_emit = multi_emit

    @abstractmethod
    def process_value(self, value: Any) -> Any:
        """Process the extracted field value or the entire item.
        
        This method must be implemented by subclasses to define how to process
        the extracted field value. Subclasses should return either a single value
        or (for advanced usage with multi_emit=True) an iterable of values.
        
        Args:
            value: The field value extracted from the item, or the entire item
                  if no field was specified
        
        Returns:
            The processed result. For standard usage, return a single value.
            For advanced usage with multi_emit=True, return an iterable.
        
        Examples:
            # Standard: return single value
            def process_value(self, email: str):
                return email.split('@')[1]
            
            # Advanced: return multiple values
            def process_value(self, text: str):
                return text.split()  # Returns list of words
        """
        pass
    
    def transform(self, input_iter: Iterable[T]) -> Iterator[U]:
        """Transform input items by processing field values.
        
        For each input item:
        1. If the item is metadata and process_metadata=False, passes it through
        2. Extracts the specified field value (or uses entire item if field is None)
        3. Passes the extracted value to process_value()
        4. Handles results based on multi_emit setting:
           - If multi_emit=False: wraps single result in list
           - If multi_emit=True: assumes result is already iterable
        5. For each result:
           - If set_as is specified: sets result on item and yields modified item
           - If set_as is None: yields result directly
        
        Args:
            input_iter: An iterable of input items to process
        
        Yields:
            Processed items or values based on the multi_emit and set_as settings
            Metadata objects are passed through if process_metadata=False
        """
        for item in input_iter:
            # Handle metadata: if process_metadata=False, it was already handled by __call__
            # but if process_metadata=True, we need to handle it here
            if is_metadata(item):
                if self.process_metadata:
                    # Let the segment handle metadata explicitly
                    # Default behavior: pass through
                    yield item
                else:
                    # This shouldn't happen since __call__ handles it, but be safe
                    yield item
                continue
            
            value = data_manipulation.extract_property(item, self.field) if self.field else item
            processed = self.process_value(value)
            if not self.multi_emit: # If not multi-emitting, wrap the result in a list
                processed = [processed]
            for result in processed:
                if self.set_as:
                    ans = item.copy() if self.multi_emit else item
                    data_manipulation.assign_property(ans, self.set_as, result)
                    yield ans
                else:
                    yield result

class Pipeline(AbstractSegment):
    """A pipeline is a sequence of operations chained together for data processing.
    
    Each operation in the pipeline draws from the output of the previous operation.
    Pipelines support both sources (entry points) and segments (transformation operations).
    
    Key characteristics:
    - Operations execute in sequence: source → segment1 → segment2 → ... → segmentN
    - Data flows lazily through the pipeline on-demand
    - Sources generate initial data; segments transform it
    - Can be created using the | (pipe) operator or the Pipeline constructor
    - Metadata flows through operations, with each operation handling it according to its process_metadata flag
    
    Attributes:
        operations: List of AbstractSource and AbstractSegment objects in execution order
    
    Examples:
        # Using the pipe operator (preferred)
        pipeline = source | segment1 | segment2 | segment3
        
        # Using the constructor
        pipeline = Pipeline(source, segment1, segment2)
        
        # Execute the pipeline
        results = list(pipeline())  # Note: pass None or no arguments
    """
    
    def __init__(self, *operations: Union[AbstractSource, AbstractSegment], process_metadata: bool = True):
        # Pipeline defaults to process_metadata=True so metadata flows through to operations
        # Each operation will handle metadata according to its own process_metadata flag
        super().__init__(process_metadata=process_metadata)
        self.operations = list(operations)
        
    def transform(self, input_iter: Iterable[Any] = None) -> Iterator[Any]:
        """Execute pipeline for iterable processing.
        
        Works with both sources (which generate initial data) and segments
        (which transform data from upstream operations).
        
        Args:
            input_iter: Not used for pipelines containing sources. Can be ignored.
        
        Yields:
            Final output items from the last operation in the pipeline
        """
        current_iter = input_iter
        for op in self.operations:
            if isinstance(op, AbstractSource):
                current_iter = op()
            else:
                current_iter = op(current_iter)
        yield from current_iter
    
    def __or__(self, other: Union[AbstractSource, AbstractSegment]) -> 'Pipeline':
        """Chain another operation onto this pipeline using the | operator.
        
        Args:
            other: Another AbstractSource or AbstractSegment to append
        
        Returns:
            A new Pipeline with the additional operation appended
        """
        return Pipeline(*self.operations, other)
    

class Script(AbstractSegment):
    """A script is a sequence of segments that execute fully before the next segment begins.
    
    The difference between a Script and a Pipeline is timing:
    - Pipeline: Lazy evaluation - items flow through operations on-demand
    - Script: Each segment fully completes before the next one starts
    
    This is useful when operations have side effects or when you need to ensure
    one stage is completely finished before moving to the next. Scripts are
    particularly common in ChatterLang scripts.
    
    Attributes:
        segments: List of AbstractSegment and AbstractSource objects to execute in order
    
    Examples:
        # Create and execute a script
        script = Script([
            source,
            segment1,
            segment2,
            segment3
        ])
        results = list(script())
    """

    def __init__(self, segments: List[AbstractSegment]):
        super().__init__()
        self.segments = segments

    def transform(self, initial_input: Annotated[Iterable[Any], "The initial input data"] = None) -> Iterator[Any]:
        """Run the script with each segment fully executing before the next.
        
        If the first segment is an AbstractSource, it will be called to generate
        the initial input. Otherwise, the initial_input will be used. All
        intermediate segments are fully consumed (buffered) to ensure they
        complete before the next segment begins.
        
        Args:
            initial_input: Initial data to pass to the first segment (ignored if
                          first segment is a Source)
        
        Yields:
            Final output items from the last segment
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
    """A loop segment that executes a script multiple times over input data.
    
    This segment is useful for iterative processing where the same series of
    operations needs to be applied multiple times. It's particularly useful
    in ChatterLang for implementing algorithmic loops. In Python, typically
    writing a loop directly is preferred, but this class provides pipeline-based
    loop semantics.
    
    The Loop passes the output of one iteration as the input to the next iteration,
    allowing data to accumulate or be refined across iterations.
    
    Attributes:
        times: Number of iterations to execute
        script: The Script to execute repeatedly
    
    Examples:
        # Apply the same transformations 3 times
        loop = Loop(times=3, script=Script([segment1, segment2]))
        result = list(loop(initial_data))
    """
    
    def __init__(self, times: int, script: Script):
        super().__init__()
        self.times = times
        self.script = script

    def transform(self, initial_input: Iterable[Any] = None) -> Iterator[Any]:
        """Execute the script multiple times, passing output to the next iteration.
        
        Args:
            initial_input: Initial data for the first iteration
        
        Yields:
            Final output items from the last iteration
        """
        current_iter = initial_input
        for i in range(self.times):
            current_iter = self.script.transform(current_iter)
            if i < self.times - 1:
                list(current_iter)
        yield from current_iter

    


