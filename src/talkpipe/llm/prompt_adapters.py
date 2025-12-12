from typing import Annotated
from abc import ABC, abstractmethod
import logging
import json
from pydantic import BaseModel
from talkpipe.util.data_manipulation import parse_key_value_str
from talkpipe.util.config import get_config
from talkpipe.util.constants import OLLAMA_SERVER_URL

logger = logging.getLogger(__name__)

class AbstractLLMPromptAdapter(ABC):
    """Abstract class for prompting an LLM.

    A descendent of this class should be written for every different type 
    of LLM system (e.g. ollama) that TalkPipe can interact with.
    """
    _model_name: str
    _source: str
    _system_message: str
    _messages: list
    _multi_turn: bool

    def __init__(self, 
                 model: Annotated[str, "The name of the model"],
                 source: Annotated[str, "The source of the model"],
                 system_prompt: Annotated[str, "The system prompt for the model"] = "You are a helpful assistant.",
                 multi_turn: Annotated[bool, "Whether the model supports multi-turn conversations"] = True,
                 temperature: Annotated[float, "The temperature for the model"] = None,
                 output_format: Annotated[BaseModel, "The output format for the model"] = None,
                 role_map: Annotated[str, "The role map for the model in the form 'role:message,role:message'. If the system role is included here, it overrides the system_prompt message"] = None):

        """Initialize the chat model"""
        self._model_name = model
        self._source = source
        self._multi_turn = multi_turn
        self._temperature = temperature
        self._temperature_explicit = temperature is not None
        self._output_format = output_format
        self._messages = []

        # Initialize system message and prefix messages
        self._system_message = {"role": "system", "content": system_prompt}
        self._prefix_messages = [self._system_message]

        if role_map:
            role_messages = parse_key_value_str(role_map)
            self._prefix_messages = []
            found_system = False
            for role, message in role_messages.items():
                self._prefix_messages.append({"role": role, "content": message})
                if role.lower() == "system":
                    found_system = True
                    self._system_message = {"role": "system", "content": message}
            if found_system:
                logger.debug("System role found in role_map, overriding system_prompt")
            else:
                self._prefix_messages.insert(0, self._system_message)

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
                 system_prompt: str = "You are a helpful assistant.",
                 multi_turn: bool = True,
                 temperature: float = None,
                 output_format: BaseModel = None,
                 server_url: str = None,
                 role_map: str = None):
        super().__init__(model, "ollama", system_prompt, multi_turn, temperature, output_format, role_map)
        # Ollama uses 0.5 as default when temperature is not specified
        if self._temperature is None:
            self._temperature = 0.5
        self._server_url = server_url

    def execute(self, prompt: str) -> str:
        """Execute the chat model.

        Handles its own multi-turn conversation state.
        """
        try:
            import ollama
        except ImportError:
            raise ImportError(
                "Ollama is not installed. Please install it with: pip install talkpipe[ollama]"
            )

        logger.debug(f"Adding user message to chat history: {prompt}")
        self._messages.append({"role": "user", "content": prompt})

        logger.debug(f"Sending chat request to Ollama model {self._model_name}")
        server_url = self._server_url
        if not server_url:
            server_url = get_config().get(OLLAMA_SERVER_URL, None)
        client = ollama.Client(server_url) if server_url else ollama
        response = client.chat(
            self._model_name,
            messages=self._prefix_messages + self._messages,
            format=self._output_format.model_json_schema() if self._output_format else None,
            options={"temperature": self._temperature}
            )

        if self._multi_turn:
            logger.debug("Multi-turn enabled, appending assistant response to chat history")
            self._messages.append({"role": "assistant", "content": str(response.message.content)})
        else:
            logger.debug("Single-turn mode, clearing message history")
            self._messages = []

        result = self._output_format.model_validate_json(response.message.content) if self._output_format else response.message.content
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
            import ollama
        except ImportError:
            raise ImportError(
                "Ollama is not installed. Please install it with: pip install talkpipe[ollama]"
            )

        try:
            # Check if the model is available
            response = ollama.chat(self._model_name, messages=[self._system_message], options={"temperature": self._temperature})
            return True
        except Exception as e:
            logger.error(f"Model {self._model_name} is not available: {e}")
            return False


class AnthropicPromptAdapter(AbstractLLMPromptAdapter):
    """Prompt adapter for Anthropic Claude

    """

    def __init__(self, model: str, system_prompt: str = "You are a helpful assistant.", multi_turn: bool = True, temperature: float = None, output_format: BaseModel = None, role_map: str = None):
        try:
            import anthropic
        except ImportError:
            raise ImportError(
                "Anthropic is not installed. Please install it with: pip install talkpipe[anthropic]"
            )

        if output_format:
            self.pydantic_json_schema = json.dumps(output_format.model_json_schema())
            system_prompt += f"\nThe output should be in the following JSON format:\n{self.pydantic_json_schema}"
        else:
            self.pydantic_json_schema = None

        super().__init__(model, "anthropic", system_prompt, multi_turn, temperature, output_format, role_map)
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
            "system": self._system_message["content"],
            "max_tokens": self._max_tokens
        }

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
                "system": self._system_message["content"],
                "max_tokens": 1
            }

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

    def __init__(self, model: str, system_prompt: str = "You are a helpful assistant.", multi_turn: bool = True, temperature: float = None, output_format: BaseModel = None, role_map: str = None):
        try:
            import openai
        except ImportError:
            raise ImportError(
                "OpenAI is not installed. Please install it with: pip install talkpipe[openai]"
            )

        super().__init__(model, "openai", system_prompt, multi_turn, temperature, output_format, role_map)
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
            request_params = {
                "model": self._model_name,
                "messages": [self._system_message]
            }
            
            if self._temperature_explicit:
                request_params["temperature"] = self._temperature
                
            response = self.client.chat.completions.create(**request_params)
            return True
        except Exception as e:
            logger.error(f"Model {self._model_name} is not available: {e}")
            return False