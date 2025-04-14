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

    def __init__(self, model_name: str,
                 source: str,
                 system_prompt: str = "You are a helpful assistant.",
                 multi_turn: bool = True,
                 temperature: float = 0.5,
                 output_format: BaseModel = None):
        """Initialize the chat model"""
        self._model_name = model_name
        self._source = source
        self._system_message = {"role": "system", "content": system_prompt}
        self._multi_turn = multi_turn
        self._temperature = temperature
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


class OllamaPromptAdapter(AbstractLLMPromptAdapter):
    """Prompt adapter for Ollama

    """

    def __init__(self, model_name: str, system_prompt: str = "You are a helpful assistant.", multi_turn: bool = True, temperature: float = 0.5, output_format: BaseModel = None):
        super().__init__(model_name, "ollama", system_prompt, multi_turn, temperature, output_format)

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


class OpenAIPromptAdapter(AbstractLLMPromptAdapter):
    """Prompt adapter for OpenAI

    """

    def __init__(self, model_name: str, system_prompt: str = "You are a helpful assistant.", multi_turn: bool = True, temperature: float = 0.5, output_format: BaseModel = None):
        super().__init__(model_name, "openai", system_prompt, multi_turn, temperature, output_format)
        self.client = openai.OpenAI()

    def execute(self, prompt: str) -> str:
        """Execute the chat model.

        Handles its own multi-turn conversation state.
        """
        logger.debug(f"Adding user message to chat history: {prompt}")
        self._messages.append({"role": "user", "content": prompt})

        logger.debug(f"Sending chat request to OpenAI model {self._model_name}")
        response = self.client.beta.chat.completions.parse(
            model=self._model_name,
            messages=[self._system_message] + self._messages,
            temperature=self._temperature,
            response_format=self._output_format
            )

        if self._multi_turn:
            logger.debug("Multi-turn enabled, appending assistant response to chat history")
            self._messages.append({"role": "assistant", "content": response.choices[0].message.content})
        else:
            logger.debug("Single-turn mode, clearing message history")
            self._messages = []

        result = self._output_format.model_validate_json(response.choices[0].message.content) if self._output_format else response.choices[0].message.content
        logger.debug(f"Returning response: {result}")
        return result