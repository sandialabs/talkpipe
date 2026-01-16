from typing import Annotated, Optional, Union, Callable, List, Dict, Any, get_origin, get_args
from abc import ABC, abstractmethod
import logging
import json
import inspect
from pydantic import BaseModel
from talkpipe.util.data_manipulation import parse_key_value_str
from talkpipe.util.config import get_config
from talkpipe.util.constants import OLLAMA_SERVER_URL

logger = logging.getLogger(__name__)


def _extract_tools_from_fastmcp(mcp: Any) -> Union[List[Callable], Dict[str, Callable]]:
    """Extract tools from a FastMCP instance (server or client).
    
    Supports both:
    - FastMCP server instances (local, with _tool_manager)
    - FastMCP Client instances (external, with async call_tool method)
    
    Args:
        mcp: FastMCP server instance or Client instance
        
    Returns:
        Dictionary mapping tool names to callable functions, or list if names unavailable
    """
    # Check if it's a FastMCP Client (external server)
    # Clients have call_tool method but NOT _tool_manager (which is for servers)
    # We need to check the type or check that it has call_tool but NOT _tool_manager
    if hasattr(mcp, 'call_tool') and hasattr(mcp, 'list_tools') and not hasattr(mcp, '_tool_manager'):
        # This is a FastMCP Client - tools are accessed via async methods
        # For now, we'll need to create async wrappers
        # Return the client itself so it can be handled specially
        logger.debug("Detected FastMCP Client instance - tools accessed via async methods")
        # Note: This requires special handling in the adapter
        return mcp
    
    # FastMCP server stores tools internally in _tool_manager._tools
    # Access it directly to avoid calling async get_tools() method
    if hasattr(mcp, '_tool_manager') and hasattr(mcp._tool_manager, '_tools'):
        tools_dict = mcp._tool_manager._tools
    elif hasattr(mcp, '_tools'):
        tools_dict = mcp._tools
    elif hasattr(mcp, 'tools'):
        tools_dict = mcp.tools
    elif hasattr(mcp, '_tool_registry'):
        tools_dict = mcp._tool_registry
    else:
        logger.warning("Could not extract tools from FastMCP instance")
        return {}
    
    # Extract callable functions from the tools dictionary
    # FastMCP stores Tool objects, not raw functions, so we need to extract the function
    if isinstance(tools_dict, dict):
        # Return as dict to preserve names
        result = {}
        for name, tool_obj in tools_dict.items():
            # Tool objects may have a function attribute or be callable themselves
            if hasattr(tool_obj, 'fn') and callable(tool_obj.fn):
                result[name] = tool_obj.fn
            elif hasattr(tool_obj, 'function') and callable(tool_obj.function):
                result[name] = tool_obj.function
            elif callable(tool_obj):
                result[name] = tool_obj
        return result
    elif isinstance(tools_dict, list):
        # For lists, we can't preserve names, so return as list
        result = []
        for tool_obj in tools_dict:
            if hasattr(tool_obj, 'fn') and callable(tool_obj.fn):
                result.append(tool_obj.fn)
            elif hasattr(tool_obj, 'function') and callable(tool_obj.function):
                result.append(tool_obj.function)
            elif callable(tool_obj):
                result.append(tool_obj)
        return result
    
    return {}


def _python_type_to_json_schema_type(python_type: type) -> str:
    """Convert Python type to JSON schema type string.
    
    Args:
        python_type: Python type
        
    Returns:
        JSON schema type string
    """
    type_mapping = {
        int: "integer",
        float: "number",
        str: "string",
        bool: "boolean",
        list: "array",
        dict: "object",
    }
    
    # Handle generic types
    if get_origin(python_type) is not None:
        origin = get_origin(python_type)
        if origin is list:
            return "array"
        elif origin is dict:
            return "object"
        elif origin is Union:
            # For Union types, try to find a common type or use first
            args = get_args(python_type)
            if args:
                return _python_type_to_json_schema_type(args[0])
    
    # Check direct mapping
    if python_type in type_mapping:
        return type_mapping[python_type]
    
    # Default to string for unknown types
    return "string"


def _convert_function_to_ollama_tool(func: Callable) -> Dict[str, Any]:
    """Convert a Python function to Ollama tool format.
    
    Args:
        func: Callable function
        
    Returns:
        Dictionary in Ollama tool format
    """
    sig = inspect.signature(func)
    func_name = func.__name__
    func_doc = inspect.getdoc(func) or ""
    
    # Extract parameters
    properties = {}
    required = []
    
    for param_name, param in sig.parameters.items():
        if param_name == 'self':
            continue
        
        param_type = "string"  # default
        param_desc = ""
        
        # Extract type from annotation
        if param.annotation != inspect.Parameter.empty:
            # Handle Annotated types
            if get_origin(param.annotation) is not None:
                origin = get_origin(param.annotation)
                args = get_args(param.annotation)
                
                # Check if it's Annotated[Type, ...]
                try:
                    from typing import Annotated
                    if origin is Annotated and args:
                        param_type = _python_type_to_json_schema_type(args[0])
                        # Look for description in metadata
                        for metadata in args[1:]:
                            if isinstance(metadata, str):
                                param_desc = metadata
                                break
                except ImportError:
                    pass
                
                # Handle other generic types
                if param_type == "string":
                    param_type = _python_type_to_json_schema_type(origin)
            else:
                param_type = _python_type_to_json_schema_type(param.annotation)
        
        properties[param_name] = {
            "type": param_type,
            "description": param_desc
        }
        
        # Add to required if no default
        if param.default == inspect.Parameter.empty:
            required.append(param_name)
    
    return {
        "type": "function",
        "function": {
            "name": func_name,
            "description": func_doc,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required
            }
        }
    }


def _convert_tools_to_ollama_format(tools: Union[Any, List[Callable], Dict[str, Callable]]) -> tuple[List[Dict[str, Any]], Dict[str, Callable]]:
    """Convert tools (FastMCP instance, list, or dict of callables) to Ollama format.
    
    Args:
        tools: FastMCP instance, list of callable functions, or dict mapping names to functions
        
    Returns:
        Tuple of (ollama_tools_list, tool_functions_dict)
    """
    tool_functions = {}
    ollama_tools = []
    
    # Extract tools from FastMCP or use provided list/dict
    if tools is None:
        return [], {}
    
    if not isinstance(tools, (list, dict)):
        # Assume it's a FastMCP instance (server or client)
        extracted = _extract_tools_from_fastmcp(tools)
        
        # Check if it's a FastMCP Client (returned as-is)
        if hasattr(extracted, 'call_tool'):
            # This is a FastMCP Client - we need to handle it differently
            # For now, log a warning that async clients need special handling
            logger.warning("FastMCP Client instances require async handling - not yet fully supported")
            # Return empty for now - this would need async wrapper implementation
            return [], {}
        
        if isinstance(extracted, dict):
            # Use the dict directly
            tool_dict = extracted
        elif isinstance(extracted, list):
            # Convert list to dict using function names
            tool_dict = {func.__name__: func for func in extracted}
        else:
            logger.warning(f"Unexpected tool extraction result: {type(extracted)}")
            tool_dict = {}
    elif isinstance(tools, dict):
        # Already a dict
        tool_dict = tools
    else:
        # List - convert to dict using function names
        tool_dict = {func.__name__: func for func in tools}
    
    # Convert each tool
    for tool_name, tool_func in tool_dict.items():
        if not callable(tool_func):
            logger.warning(f"Skipping non-callable tool: {tool_func}")
            continue
        
        ollama_tool = _convert_function_to_ollama_tool(tool_func)
        # Override name in ollama_tool to use the dict key (important for lambdas)
        ollama_tool["function"]["name"] = tool_name
        ollama_tools.append(ollama_tool)
        tool_functions[tool_name] = tool_func
    
    return ollama_tools, tool_functions


class AbstractLLMPromptAdapter(ABC):
    """Abstract class for prompting an LLM.

    A descendent of this class should be written for every different type 
    of LLM system (e.g. ollama) that TalkPipe can interact with.
    """
    _model_name: str
    _source: str
    _system_message: Optional[dict]
    _messages: list
    _multi_turn: bool

    def __init__(self, 
                 model: Annotated[str, "The name of the model"],
                 source: Annotated[str, "The source of the model"],
                 system_prompt: Annotated[Optional[str], "The system prompt for the model"] = "You are a helpful assistant.",
                 multi_turn: Annotated[bool, "Whether the model supports multi-turn conversations"] = True,
                 temperature: Annotated[float, "The temperature for the model"] = None,
                 output_format: Annotated[BaseModel, "The output format for the model"] = None,
                 role_map: Annotated[str, "The role map for the model in the form 'role:message,role:message'. If the system role is included here, it overrides the system_prompt message"] = None,
                 tools: Annotated[Optional[Union[Any, List[Callable]]], "FastMCP instance or list of callable tool functions"] = None):

        """Initialize the chat model"""
        self._model_name = model
        self._source = source
        self._multi_turn = multi_turn
        self._temperature = temperature
        self._temperature_explicit = temperature is not None
        self._output_format = output_format
        self._messages = []
        self._tools = tools
        self._tool_functions = {}  # Map tool names to callable functions

        # Initialize system message and prefix messages
        # Only create system message if system_prompt is not None
        self._system_message = None
        self._prefix_messages = []

        if role_map:
            role_messages = parse_key_value_str(role_map)
            found_system = False
            for role, message in role_messages.items():
                self._prefix_messages.append({"role": role, "content": message})
                if role.lower() == "system":
                    found_system = True
                    self._system_message = {"role": "system", "content": message}
            if not found_system and system_prompt is not None:
                self._system_message = {"role": "system", "content": system_prompt}
                self._prefix_messages.insert(0, self._system_message)
        elif system_prompt is not None:
            self._system_message = {"role": "system", "content": system_prompt}
            self._prefix_messages = [self._system_message]

    @property
    def model_name(self) -> str:
        """The name of the model"""
        return self._model_name

    @property
    def source(self) -> str:
        return self._source

    def description(self):
        return f"Chat with {self.model_name} ({self._source})"

    def __str__(self):
        return f"Chat with {self.model_name} ({self._source})"

    def __repr__(self):
        return self.__str__()

    @abstractmethod
    def execute(self, prompt: str) -> str:
        """Execute the chat model.

        This method is used to execute the chat model with a given input.
        """

    @abstractmethod
    def is_available(self) -> bool:
        """Check if the chat model is available.

        This method should be implemented in each subclass to check if 
        the chat model is available.
        Returns:
            bool: True if the model is available, False otherwise.
        """


class OllamaPromptAdapter(AbstractLLMPromptAdapter):
    """Prompt adapter for Ollama

    Note: By default, ollama assumes localhost for the ollama server.  
    If your server is running elsewhere, you can set the OLLAMA_SERVER_URL 
    environment variable or in the configuration, or pass the server_url 
    parameter.

    """

    def __init__(self,
                 model: str,
                 system_prompt: Optional[str] = "You are a helpful assistant.",
                 multi_turn: bool = True,
                 temperature: float = None,
                 output_format: BaseModel = None,
                 server_url: str = None,
                 role_map: str = None,
                 tools: Optional[Union[Any, List[Callable]]] = None):
        super().__init__(model, "ollama", system_prompt, multi_turn, temperature, output_format, role_map, tools)
        # Ollama uses 0.5 as default when temperature is not specified
        if self._temperature is None:
            self._temperature = 0.5
        self._server_url = server_url
        
        # Convert tools to Ollama format and store tool functions
        if self._tools is not None:
            self._ollama_tools, self._tool_functions = _convert_tools_to_ollama_format(self._tools)
        else:
            self._ollama_tools = []
            self._tool_functions = {}

    def execute(self, prompt: str) -> str:
        """Execute the chat model.

        Handles its own multi-turn conversation state and tool calling.
        """
        try:
            import ollama
        except ImportError:
            raise ImportError(
                "Ollama is not installed. Please install it with: pip install talkpipe[ollama]"
            )

        logger.debug(f"Adding user message to chat history: {prompt}")
        self._messages.append({"role": "user", "content": prompt})

        server_url = self._server_url
        if not server_url:
            server_url = get_config().get(OLLAMA_SERVER_URL, None)
        client = ollama.Client(server_url) if server_url else ollama
        
        # Loop until we get a final text response (handle tool calls)
        max_iterations = 10  # Prevent infinite loops
        iteration = 0
        
        while iteration < max_iterations:
            iteration += 1
            logger.debug(f"Sending chat request to Ollama model {self._model_name} (iteration {iteration})")
            
            # Build request parameters
            request_params = {
                "model": self._model_name,
                "messages": self._prefix_messages + self._messages,
                "options": {"temperature": self._temperature}
            }
            
            # Add tools if available
            if self._ollama_tools:
                request_params["tools"] = self._ollama_tools
            
            # Add format if output_format is specified
            if self._output_format:
                request_params["format"] = self._output_format.model_json_schema()
            
            response = client.chat(**request_params)
            
            # Check for tool calls
            tool_calls = getattr(response.message, 'tool_calls', None) or []
            if not tool_calls and hasattr(response, 'tool_calls'):
                tool_calls = response.tool_calls
            
            if tool_calls:
                logger.debug(f"Model requested {len(tool_calls)} tool call(s)")
                
                # Add assistant message with tool calls to history
                assistant_message = {
                    "role": "assistant",
                    "content": getattr(response.message, 'content', None) or "",
                    "tool_calls": []
                }
                
                # Execute each tool call
                tool_results = []
                for tool_call in tool_calls:
                    tool_call_id = getattr(tool_call, 'id', None) or f"call_{iteration}_{len(tool_results)}"
                    
                    # Extract tool name and arguments
                    # Ollama returns tool_call.function as an object with .name and .arguments (dict)
                    if hasattr(tool_call, 'function'):
                        if hasattr(tool_call.function, 'name'):
                            tool_name = tool_call.function.name
                        else:
                            tool_name = getattr(tool_call.function, 'name', '')
                        
                        if hasattr(tool_call.function, 'arguments'):
                            tool_args = tool_call.function.arguments
                            # Arguments might be a dict (Ollama) or a string (some APIs)
                            if isinstance(tool_args, str):
                                try:
                                    tool_args = json.loads(tool_args)
                                except json.JSONDecodeError:
                                    logger.warning(f"Failed to parse tool arguments: {tool_args}")
                                    tool_args = {}
                        else:
                            tool_args = {}
                    else:
                        # Fallback for other formats
                        tool_name = getattr(tool_call, 'function', {}).get('name', '') if isinstance(getattr(tool_call, 'function', None), dict) else ''
                        tool_args = getattr(tool_call, 'function', {}).get('arguments', {}) if isinstance(getattr(tool_call, 'function', None), dict) else {}
                        if isinstance(tool_args, str):
                            try:
                                tool_args = json.loads(tool_args)
                            except json.JSONDecodeError:
                                tool_args = {}
                    
                    logger.debug(f"Executing tool: {tool_name} with args: {tool_args}")
                    
                    # Execute tool
                    if tool_name in self._tool_functions:
                        try:
                            tool_func = self._tool_functions[tool_name]
                            tool_result = tool_func(**tool_args)
                            # Convert result to string if needed
                            if not isinstance(tool_result, str):
                                tool_result = json.dumps(tool_result) if isinstance(tool_result, (dict, list)) else str(tool_result)
                        except Exception as e:
                            logger.error(f"Error executing tool {tool_name}: {e}")
                            tool_result = f"Error: {str(e)}"
                    else:
                        logger.warning(f"Tool {tool_name} not found in registered tools")
                        tool_result = f"Error: Tool {tool_name} not found"
                    
                    # Add to assistant message
                    # Ollama expects arguments as a dict in the message history
                    assistant_message["tool_calls"].append({
                        "id": tool_call_id,
                        "type": "function",
                        "function": {
                            "name": tool_name,
                            "arguments": tool_args  # Keep as dict for Ollama
                        }
                    })
                    
                    # Add tool result message
                    tool_results.append({
                        "role": "tool",
                        "content": tool_result,
                        "name": tool_name
                    })
                
                # Add assistant message and tool results to history
                self._messages.append(assistant_message)
                self._messages.extend(tool_results)
                
                # Continue loop to get model's response to tool results
                continue
            
            # No tool calls - this is the final response
            final_content = str(response.message.content)
            
            if self._multi_turn:
                logger.debug("Multi-turn enabled, appending assistant response to chat history")
                self._messages.append({"role": "assistant", "content": final_content})
            else:
                logger.debug("Single-turn mode, clearing message history")
                self._messages = []
            
            # Handle output format
            if self._output_format:
                result = self._output_format.model_validate_json(final_content)
            else:
                result = final_content
            
            logger.debug(f"Returning response: {result}")
            return result
        
        # If we've exceeded max iterations, return the last response
        logger.warning(f"Exceeded maximum tool call iterations ({max_iterations})")
        final_content = str(response.message.content) if hasattr(response, 'message') else ""
        return self._output_format.model_validate_json(final_content) if self._output_format else final_content
    
    def is_available(self) -> bool:
        """Check if the chat model is available.

        This method should be implemented in each subclass to check if
        the chat model is available.
        Returns:
            bool: True if the model is available, False otherwise.
        """
        try:
            import ollama
        except ImportError:
            raise ImportError(
                "Ollama is not installed. Please install it with: pip install talkpipe[ollama]"
            )

        try:
            # Check if the model is available
            test_messages = [self._system_message] if self._system_message else [{"role": "user", "content": "test"}]
            response = ollama.chat(self._model_name, messages=test_messages, options={"temperature": self._temperature})
            return True
        except Exception as e:
            logger.error(f"Model {self._model_name} is not available: {e}")
            return False


class AnthropicPromptAdapter(AbstractLLMPromptAdapter):
    """Prompt adapter for Anthropic Claude

    """

    def __init__(self, model: str, system_prompt: Optional[str] = "You are a helpful assistant.", multi_turn: bool = True, temperature: float = None, output_format: BaseModel = None, role_map: str = None, tools: Optional[Union[Any, List[Callable]]] = None):
        try:
            import anthropic
        except ImportError:
            raise ImportError(
                "Anthropic is not installed. Please install it with: pip install talkpipe[anthropic]"
            )

        if output_format and system_prompt:
            self.pydantic_json_schema = json.dumps(output_format.model_json_schema())
            system_prompt = system_prompt + f"\nThe output should be in the following JSON format:\n{self.pydantic_json_schema}"
        else:
            self.pydantic_json_schema = None

        super().__init__(model, "anthropic", system_prompt, multi_turn, temperature, output_format, role_map, tools)
        self.client = anthropic.Anthropic()
        self._max_tokens = 4096  # Default max tokens for response

    def execute(self, prompt: str) -> str:
        """Execute the chat model.

        Handles its own multi-turn conversation state.
        """
        try:
            import anthropic
        except ImportError:
            raise ImportError(
                "Anthropic is not installed. Please install it with: pip install talkpipe[anthropic]"
            )

        logger.debug(f"Adding user message to chat history: {prompt}")
        self._messages.append({"role": "user", "content": prompt})

        logger.debug(f"Sending chat request to Anthropic model {self._model_name}")

        # Build request parameters
        # Anthropic uses a separate system parameter, so we filter out system messages from prefix_messages
        non_system_prefix = [msg for msg in self._prefix_messages if msg["role"].lower() != "system"]
        request_params = {
            "model": self._model_name,
            "messages": non_system_prefix + self._messages,
            "max_tokens": self._max_tokens
        }

        # Only include system parameter if system_message exists
        if self._system_message:
            request_params["system"] = self._system_message["content"]

        if self._temperature_explicit:
            request_params["temperature"] = self._temperature

        response = self.client.messages.create(**request_params)

        # Extract text content from response
        response_text = ""
        for block in response.content:
            if hasattr(block, 'text'):
                response_text += block.text

        if self._multi_turn:
            logger.debug("Multi-turn enabled, appending assistant response to chat history")
            self._messages.append({"role": "assistant", "content": response_text})
        else:
            logger.debug("Single-turn mode, clearing message history")
            self._messages = []

        # Handle output format if specified
        if self._output_format:
            result = self._output_format.model_validate_json(response_text)
        else:
            result = response_text

        logger.debug(f"Returning response: {result}")
        return result

    def is_available(self) -> bool:
        """Check if the chat model is available.

        This method should be implemented in each subclass to check if
        the chat model is available.
        Returns:
            bool: True if the model is available, False otherwise.
        """
        try:
            import anthropic
        except ImportError:
            raise ImportError(
                "Anthropic is not installed. Please install it with: pip install talkpipe[anthropic]"
            )

        try:
            # Check if the model is available by making a minimal request
            request_params = {
                "model": self._model_name,
                "messages": [{"role": "user", "content": "test"}],
                "max_tokens": 1
            }

            # Only include system parameter if system_message exists
            if self._system_message:
                request_params["system"] = self._system_message["content"]

            if self._temperature_explicit:
                request_params["temperature"] = self._temperature

            response = self.client.messages.create(**request_params)
            return True
        except Exception as e:
            logger.error(f"Model {self._model_name} is not available: {e}")
            return False


class OpenAIPromptAdapter(AbstractLLMPromptAdapter):
    """Prompt adapter for OpenAI

    """

    def __init__(self, model: str, system_prompt: Optional[str] = "You are a helpful assistant.", multi_turn: bool = True, temperature: float = None, output_format: BaseModel = None, role_map: str = None, tools: Optional[Union[Any, List[Callable]]] = None):
        try:
            import openai
        except ImportError:
            raise ImportError(
                "OpenAI is not installed. Please install it with: pip install talkpipe[openai]"
            )

        super().__init__(model, "openai", system_prompt, multi_turn, temperature, output_format, role_map, tools)
        self.client = openai.OpenAI()

    def execute(self, prompt: str) -> str:
        """Execute the chat model.

        Handles its own multi-turn conversation state.
        """
        try:
            import openai
        except ImportError:
            raise ImportError(
                "OpenAI is not installed. Please install it with: pip install talkpipe[openai]"
            )

        logger.debug(f"Adding user message to chat history: {prompt}")
        self._messages.append({"role": "user", "content": prompt})

        logger.debug(f"Sending chat request to OpenAI model {self._model_name}")

        # Build request parameters, only including temperature if explicitly set
        request_params = {
            "model": self._model_name,
            "input": self._prefix_messages + self._messages,
            "text_format": openai.NOT_GIVEN if self._output_format is None else self._output_format
        }
        
        if self._temperature_explicit:
            request_params["temperature"] = self._temperature
            
        response = self.client.responses.parse(**request_params)

        if self._multi_turn:
            logger.debug("Multi-turn enabled, appending assistant response to chat history")
            self._messages.append({"role": "assistant", "content": response.output_text})
        else:
            logger.debug("Single-turn mode, clearing message history")
            self._messages = []

        result = response.output_parsed if self._output_format else response.output_text
        logger.debug(f"Returning response: {result}")
        return result
    
    def is_available(self) -> bool:
        """Check if the chat model is available.

        This method should be implemented in each subclass to check if
        the chat model is available.
        Returns:
            bool: True if the model is available, False otherwise.
        """
        try:
            # Check if the model is available
            test_messages = [self._system_message] if self._system_message else [{"role": "user", "content": "test"}]
            request_params = {
                "model": self._model_name,
                "messages": test_messages
            }
            
            if self._temperature_explicit:
                request_params["temperature"] = self._temperature
                
            response = self.client.chat.completions.create(**request_params)
            return True
        except Exception as e:
            logger.error(f"Model {self._model_name} is not available: {e}")
            return False