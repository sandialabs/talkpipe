from typing import Any

from pydantic import BaseModel

from talkpipe.util.config import resolve_timeout
from talkpipe.util.constants import DEFAULT_LLM_TIMEOUT, LLM_TIMEOUT

from ._ollama_common import ollama_connection_error, resolve_ollama_server_url
from .content import UserTurn
from .multimodal import to_ollama_user_message
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
        system_prompt: str | None = "You are a helpful assistant.",
        multi_turn: bool = True,
        temperature: float | None = None,
        output_format: type[BaseModel] | None = None,
        server_url: str | None = None,
        role_map: str | None = None,
        memory_mode: str = "full",
        unsummarized_message_count: int = 6,
        context_token_trigger: int | float | None = None,
        memory_size: int = 512,
        debug_messages: bool = False,
        timeout: float | None = None,
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
        self._timeout = resolve_timeout(timeout, LLM_TIMEOUT, DEFAULT_LLM_TIMEOUT)

    def execute(self, prompt: str) -> str | BaseModel:
        """Execute the chat model.

        Handles its own multi-turn conversation state.
        """
        self._require_dependency("ollama", "Ollama", "ollama")
        self._append_user_prompt(prompt)
        return self._complete_from_history()

    def execute_turn(self, user_turn: UserTurn) -> str | BaseModel:
        """Execute the chat model with a multimodal user turn."""
        self._require_dependency("ollama", "Ollama", "ollama")
        self._append_user_message(to_ollama_user_message(user_turn))
        return self._complete_from_history()

    def _complete_from_history(self) -> str | BaseModel:
        # Shared dispatch for execute() and execute_turn(): both send the same
        # assembled history and parse the reply the same way.
        logger.debug(f"Sending chat request to Ollama model {self._model_name}")
        self._log_message_payload("messages", self._request_messages())
        response = self._chat_completion(
            model=self._model_name,
            messages=self._request_messages(),
            format_schema=self._output_format.model_json_schema()
            if self._output_format
            else None,
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

    def _chat_completion(
        self,
        model: str,
        messages: list[dict[str, Any]],
        format_schema: Any = None,
        options: Any = None,
    ) -> Any:
        ollama = self._require_dependency("ollama", "Ollama", "ollama")

        server_url = resolve_ollama_server_url(self._server_url)
        # Always go through a Client (never the module-level default) so the
        # request timeout applies; host=None means the SDK's own default.
        client = ollama.Client(host=server_url or None, timeout=self._timeout)
        try:
            return client.chat(
                model, messages=messages, format=format_schema, options=options
            )
        except ConnectionError as exc:
            raise ollama_connection_error(server_url, exc) from exc
        except ollama.ResponseError as exc:
            if exc.status_code == 404:
                raise ollama.ResponseError(
                    f"Model '{model}' is not available on the Ollama server"
                    f"{f' at {server_url}' if server_url else ''}. "
                    f"Run `ollama pull {model}` to download it. Original error: {exc.error}",
                    status_code=exc.status_code,
                ) from exc
            raise

    def complete_text_without_context(
        self,
        prompt: str,
        *,
        model: str | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
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
        self._require_dependency("ollama", "Ollama", "ollama")

        try:
            # Route through _chat_completion so this honors self._server_url /
            # the configured OLLAMA_SERVER_URL, instead of always checking the
            # default local Ollama regardless of where the adapter is configured
            # to talk to.
            test_messages = (
                [self._system_message]
                if self._system_message
                else [{"role": "user", "content": "test"}]
            )
            # num_predict=1 keeps this a reachability probe: without a cap the
            # test request runs a full generation, which on a thinking model
            # can take minutes and stalls callers such as the workbench
            # settings endpoint.
            self._chat_completion(
                self._model_name,
                messages=test_messages,
                options={"temperature": self._temperature, "num_predict": 1},
            )
            return True
        except Exception as e:
            logger.error(f"Model {self._model_name} is not available: {e}")
            return False
