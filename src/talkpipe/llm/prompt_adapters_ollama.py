from typing import Optional, Union

from pydantic import BaseModel

from talkpipe.util.config import get_config
from talkpipe.util.constants import OLLAMA_SERVER_URL

from .prompt_adapter_base import AbstractLLMPromptAdapter, logger


class OllamaPromptAdapter(AbstractLLMPromptAdapter):
    """Prompt adapter for Ollama.

    Note: By default, ollama assumes localhost for the ollama server.
    If your server is running elsewhere, you can set the OLLAMA_SERVER_URL
    environment variable or in the configuration, or pass the server_url
    parameter.
    """

    def __init__(
        self,
        model: str,
        system_prompt: Optional[str] = "You are a helpful assistant.",
        multi_turn: bool = True,
        temperature: float = None,
        output_format: BaseModel = None,
        server_url: str = None,
        role_map: str = None,
        memory_mode: str = "full",
        unsummarized_message_count: int = 6,
        context_token_trigger: Optional[Union[int, float]] = None,
        memory_size: int = 512,
        debug_messages: bool = False,
    ):
        super().__init__(
            model,
            "ollama",
            system_prompt,
            multi_turn,
            temperature,
            output_format,
            role_map,
            memory_mode,
            unsummarized_message_count,
            context_token_trigger,
            memory_size,
            debug_messages,
        )
        # Ollama uses 0.5 as default when temperature is not specified
        if self._temperature is None:
            self._temperature = 0.5
        self._server_url = server_url

    def execute(self, prompt: str) -> str:
        """Execute the chat model.

        Handles its own multi-turn conversation state.
        """
        self._require_dependency("ollama", "Ollama", "ollama")

        logger.debug(f"Adding user message to chat history: {prompt}")
        self._messages.append({"role": "user", "content": prompt})
        # Memory compaction may update `_summary_message` and trim `_messages` before request dispatch.
        self._compact_context_if_needed()

        logger.debug(f"Sending chat request to Ollama model {self._model_name}")
        self._log_message_payload("messages", self._request_messages())
        response = self._chat_completion(
            model=self._model_name,
            messages=self._request_messages(),
            format_schema=self._output_format.model_json_schema() if self._output_format else None,
            options={"temperature": self._temperature},
        )

        self._record_assistant_response(str(response.message.content))

        result = (
            self._output_format.model_validate_json(response.message.content)
            if self._output_format
            else response.message.content
        )
        logger.debug(f"Returning response: {result}")
        return result

    def _chat_completion(self, model: str, messages: list, format_schema=None, options=None):
        ollama = self._require_dependency("ollama", "Ollama", "ollama")

        server_url = self._server_url
        if not server_url:
            server_url = get_config().get(OLLAMA_SERVER_URL, None)
        client = ollama.Client(server_url) if server_url else ollama
        return client.chat(model, messages=messages, format=format_schema, options=options)

    def complete_text_without_context(
        self,
        prompt: str,
        *,
        model: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: Optional[int] = None,
    ) -> str:
        options = {"temperature": temperature}
        if max_tokens is not None:
            options["num_predict"] = max_tokens
        response = self._chat_completion(
            model or self._model_name,
            messages=[{"role": "user", "content": prompt}],
            options=options,
        )
        return str(response.message.content).strip()

    def is_available(self) -> bool:
        """Check if the chat model is available.

        This method should be implemented in each subclass to check if
        the chat model is available.
        Returns:
            bool: True if the model is available, False otherwise.
        """
        ollama = self._require_dependency("ollama", "Ollama", "ollama")

        try:
            # Check if the model is available
            test_messages = [self._system_message] if self._system_message else [{"role": "user", "content": "test"}]
            ollama.chat(self._model_name, messages=test_messages, options={"temperature": self._temperature})
            return True
        except Exception as e:
            logger.error(f"Model {self._model_name} is not available: {e}")
            return False
