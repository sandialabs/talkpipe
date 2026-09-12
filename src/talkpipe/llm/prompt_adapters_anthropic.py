import json
from typing import Any

from pydantic import BaseModel

from talkpipe.util.config import resolve_timeout
from talkpipe.util.constants import DEFAULT_LLM_TIMEOUT, LLM_TIMEOUT

from .content import UserTurn
from .multimodal import to_anthropic_user_message
from .prompt_adapter_base import AbstractLLMPromptAdapter, logger


class AnthropicPromptAdapter(AbstractLLMPromptAdapter):
    """Prompt adapter for Anthropic Claude."""

    def __init__(
        self,
        model: str,
        system_prompt: str | None = "You are a helpful assistant.",
        multi_turn: bool = True,
        temperature: float | None = None,
        output_format: type[BaseModel] | None = None,
        role_map: str | None = None,
        memory_mode: str = "full",
        unsummarized_message_count: int = 6,
        context_token_trigger: int | float | None = None,
        memory_size: int = 512,
        debug_messages: bool = False,
        timeout: float | None = None,
    ):
        anthropic = self._require_dependency("anthropic", "Anthropic", "anthropic")

        self.pydantic_json_schema: str | None
        if output_format and system_prompt:
            self.pydantic_json_schema = json.dumps(output_format.model_json_schema())
            system_prompt = (
                system_prompt
                + f"\nThe output should be in the following JSON format:\n{self.pydantic_json_schema}"
            )
        else:
            self.pydantic_json_schema = None

        super().__init__(
            model,
            "anthropic",
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
        self._timeout = resolve_timeout(timeout, LLM_TIMEOUT, DEFAULT_LLM_TIMEOUT)
        self.client = self._build_client(
            lambda: anthropic.Anthropic(timeout=self._timeout),
            "Anthropic",
            "ANTHROPIC_API_KEY",
        )
        self._max_tokens = 4096  # Default max tokens for response

    def execute(self, prompt: str) -> str | BaseModel:
        """Execute the chat model.

        Handles its own multi-turn conversation state.
        """
        self._require_dependency("anthropic", "Anthropic", "anthropic")
        self._append_user_prompt(prompt)
        return self._complete_from_history()

    def execute_turn(self, user_turn: UserTurn) -> str | BaseModel:
        """Execute the chat model with a multimodal user turn."""
        self._require_dependency("anthropic", "Anthropic", "anthropic")
        self._append_user_message(to_anthropic_user_message(user_turn))
        return self._complete_from_history()

    def _complete_from_history(self) -> str | BaseModel:
        # Shared dispatch for execute() and execute_turn(): both send the same
        # assembled history and parse the reply the same way.
        logger.debug(f"Sending chat request to Anthropic model {self._model_name}")

        request_params = self._build_messages_request_params()

        self._log_message_payload("messages", request_params["messages"])
        if self._debug_messages and "system" in request_params:
            logger.debug(
                "LLM outbound payload (system) for %s (%s): %s",
                self._model_name,
                self._source,
                self._clip_debug_text(str(request_params["system"])),
            )
        response = self._messages_create(**request_params)

        response_text = self._extract_anthropic_text(response)
        self._record_assistant_response(response_text)

        result: str | BaseModel
        if self._output_format:
            result = self._output_format.model_validate_json(response_text)
        else:
            result = response_text

        logger.debug(f"Returning response: {result}")
        return result

    def _build_messages_request_params(self) -> dict[str, Any]:
        non_system_prefix = [
            msg for msg in self._prefix_messages if msg["role"].lower() != "system"
        ]
        non_system_summary = []
        if self._summary_message:
            non_system_summary = [
                {
                    "role": "assistant",
                    "content": f"Conversation memory:\n{self._summary_message['content']}",
                }
            ]
        request_params = {
            "model": self._model_name,
            "messages": non_system_prefix + non_system_summary + self._messages,
            "max_tokens": self._max_tokens,
        }
        if self._system_message:
            summary_text = (
                f"\n\nConversation memory:\n{self._summary_message['content']}"
                if self._summary_message
                else ""
            )
            request_params["system"] = self._system_message["content"] + summary_text
        self._apply_temperature_if_explicit(request_params)
        return request_params

    def _messages_create(self, **request_params: Any) -> Any:
        try:
            return self.client.messages.create(**request_params)
        except Exception as exc:
            msg = str(exc).lower()
            if any(
                kw in msg
                for kw in (
                    "authentication",
                    "api_key",
                    "api key",
                    "auth_token",
                    "credentials",
                    "could not resolve",
                )
            ):
                raise RuntimeError(
                    "Could not authenticate with Anthropic. Set the ANTHROPIC_API_KEY environment variable "
                    "to your API key (see https://console.anthropic.com/). "
                    "See https://github.com/sandialabs/talkpipe/blob/main/docs/guides/model-and-source-configuration.md."
                ) from exc
            raise

    def _apply_temperature_if_explicit(self, request_params: dict[str, Any]) -> None:
        # The Anthropic API removed sampling parameters (temperature, top_p,
        # top_k) on current models, and anthropic SDK 1.x rejects them with a
        # TypeError at the client. Never send temperature to Anthropic; log a
        # warning instead so a configured temperature is not silently ignored.
        if self._temperature_explicit:
            self._warn_temperature_unsupported(self._temperature)

    @staticmethod
    def _warn_temperature_unsupported(temperature: float | None) -> None:
        logger.warning(
            "The Anthropic API no longer supports the temperature parameter; "
            "ignoring temperature=%s for this request.",
            temperature,
        )

    def _extract_anthropic_text(self, response: Any) -> str:
        response_text = ""
        for block in response.content:
            if hasattr(block, "text"):
                response_text += block.text
        return response_text

    def complete_text_without_context(
        self,
        prompt: str,
        *,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        if temperature is not None:
            self._warn_temperature_unsupported(temperature)
        response = self._messages_create(
            model=model or self._model_name,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens or self._summary_max_tokens,
        )
        return self._extract_anthropic_text(response).strip()

    def is_available(self) -> bool:
        """Check if the chat model is available.

        This method should be implemented in each subclass to check if
        the chat model is available.
        Returns:
            bool: True if the model is available, False otherwise.
        """
        self._require_dependency("anthropic", "Anthropic", "anthropic")

        try:
            # Check if the model is available by making a minimal request.
            request_params = {
                "model": self._model_name,
                "messages": [{"role": "user", "content": "test"}],
                "max_tokens": 1,
            }

            # Only include system parameter if system_message exists.
            if self._system_message:
                request_params["system"] = self._system_message["content"]

            self._apply_temperature_if_explicit(request_params)

            self.client.messages.create(**request_params)
            return True
        except Exception as e:
            logger.error(f"Model {self._model_name} is not available: {e}")
            return False
