from pydantic import BaseModel
import logging
import ollama
import openai

from abc import ABC, abstractmethod

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

    def __init__(self, model: str,
                 source: str,
                 system_prompt: str = "You are a helpful assistant.",
                 multi_turn: bool = True,
                 temperature: float = None,
                 output_format: BaseModel = None):
        """Initialize the chat model"""
        self._model_name = model
        self._source = source
        self._system_message = {"role": "system", "content": system_prompt}
        self._multi_turn = multi_turn
        self._temperature = temperature
        self._temperature_explicit = temperature is not None
        self._output_format = output_format
        self._messages = []

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

    """

    def __init__(self, model: str, system_prompt: str = "You are a helpful assistant.", multi_turn: bool = True, temperature: float = None, output_format: BaseModel = None):
        super().__init__(model, "ollama", system_prompt, multi_turn, temperature, output_format)
        # Ollama uses 0.5 as default when temperature is not specified
        if self._temperature is None:
            self._temperature = 0.5

    def execute(self, prompt: str) -> str:
        """Execute the chat model.

        Handles its own multi-turn conversation state.
        """
        logger.debug(f"Adding user message to chat history: {prompt}")
        self._messages.append({"role": "user", "content": prompt})

        logger.debug(f"Sending chat request to Ollama model {self._model_name}")
        response = ollama.chat(
            self._model_name,
            messages=[self._system_message] + self._messages,
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
            # Check if the model is available
            response = ollama.chat(self._model_name, messages=[self._system_message], options={"temperature": self._temperature})
            return True
        except Exception as e:
            logger.error(f"Model {self._model_name} is not available: {e}")
            return False


class OpenAIPromptAdapter(AbstractLLMPromptAdapter):
    """Prompt adapter for OpenAI

    """

    def __init__(self, model: str, system_prompt: str = "You are a helpful assistant.", multi_turn: bool = True, temperature: float = None, output_format: BaseModel = None):
        super().__init__(model, "openai", system_prompt, multi_turn, temperature, output_format)
        self.client = openai.OpenAI()

    def execute(self, prompt: str) -> str:
        """Execute the chat model.

        Handles its own multi-turn conversation state.
        """
        logger.debug(f"Adding user message to chat history: {prompt}")
        self._messages.append({"role": "user", "content": prompt})

        logger.debug(f"Sending chat request to OpenAI model {self._model_name}")
        
        # Build request parameters, only including temperature if explicitly set
        request_params = {
            "model": self._model_name,
            "input": [self._system_message] + self._messages,
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