import json
from typing import Optional, Union

from pydantic import BaseModel

from .prompt_adapter_base import AbstractLLMPromptAdapter, logger
from .content import UserTurn
from .multimodal import to_anthropic_user_message


class AnthropicPromptAdapter(AbstractLLMPromptAdapter):
    """Prompt adapter for Anthropic Claude."""

    def __init__(
        self,
        model: str,
        system_prompt: Optional[str] = "You are a helpful assistant.",
        multi_turn: bool = True,
        temperature: float = None,
        output_format: BaseModel = None,
        role_map: str = None,
        memory_mode: str = "full",
        unsummarized_message_count: int = 6,
        context_token_trigger: Optional[Union[int, float]] = None,
        memory_size: int = 512,
        debug_messages: bool = False,
    ):
        anthropic = self._require_dependency("anthropic", "Anthropic", "anthropic")

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
        self.client = self._build_client(
            anthropic.Anthropic, "Anthropic", "ANTHROPIC_API_KEY"
        )
        self._max_tokens = 4096  # Default max tokens for response

    def execute(self, prompt: str) -> str:
        """Execute the chat model.

        Handles its own multi-turn conversation state.
        """
        self._require_dependency("anthropic", "Anthropic", "anthropic")

        logger.debug(f"Adding user message to chat history: {prompt}")
        self._messages.append({"role": "user", "content": prompt})
        self._compact_context_if_needed()

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

        if self._output_format:
            result = self._output_format.model_validate_json(response_text)
        else:
            result = response_text

        logger.debug(f"Returning response: {result}")
        return result

    def execute_turn(self, user_turn: UserTurn) -> str:
        """Execute the chat model with a multimodal user turn."""
        self._require_dependency("anthropic", "Anthropic", "anthropic")

        user_message = to_anthropic_user_message(user_turn)
        logger.debug("Adding multimodal user message to chat history")
        self._messages.append(user_message)
        self._compact_context_if_needed()

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

        if self._output_format:
            result = self._output_format.model_validate_json(response_text)
        else:
            result = response_text

        logger.debug(f"Returning response: {result}")
        return result

    def _build_messages_request_params(self) -> dict:
        non_system_prefix = [msg for msg in self._prefix_messages if msg["role"].lower() != "system"]
        non_system_summary = []
        if self._summary_message:
            non_system_summary = [
                {"role": "assistant", "content": f"Conversation memory:\n{self._summary_message['content']}"}
            ]
        request_params = {
            "model": self._model_name,
            "messages": non_system_prefix + non_system_summary + self._messages,
            "max_tokens": self._max_tokens,
        }
        if self._system_message:
            summary_text = (
                f"\n\nConversation memory:\n{self._summary_message['content']}" if self._summary_message else ""
            )
            request_params["system"] = self._system_message["content"] + summary_text
        self._apply_temperature_if_explicit(request_params)
        return request_params

    def _messages_create(self, **request_params):
        return self.client.messages.create(**request_params)

    def _extract_anthropic_text(self, response) -> str:
        response_text = ""
        for block in response.content:
            if hasattr(block, "text"):
                response_text += block.text
        return response_text

    def complete_text_without_context(
        self,
        prompt: str,
        *,
        model: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: Optional[int] = None,
    ) -> str:
        response = self._messages_create(
            model=model or self._model_name,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens or self._summary_max_tokens,
            temperature=temperature,
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
            request_params = {"model": self._model_name, "messages": [{"role": "user", "content": "test"}], "max_tokens": 1}

            # Only include system parameter if system_message exists.
            if self._system_message:
                request_params["system"] = self._system_message["content"]

            self._apply_temperature_if_explicit(request_params)

            self.client.messages.create(**request_params)
            return True
        except Exception as e:
            logger.error(f"Model {self._model_name} is not available: {e}")
            return False
