from typing import Optional, Union

from pydantic import BaseModel

from .prompt_adapter_base import AbstractLLMPromptAdapter, logger


class OpenAIPromptAdapter(AbstractLLMPromptAdapter):
    """Prompt adapter for OpenAI."""

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
        openai = self._require_dependency("openai", "OpenAI", "openai")
        super().__init__(
            model,
            "openai",
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
        self.client = openai.OpenAI()

    def execute(self, prompt: str) -> str:
        """Execute the chat model.

        Handles its own multi-turn conversation state.
        """
        openai = self._require_dependency("openai", "OpenAI", "openai")

        logger.debug(f"Adding user message to chat history: {prompt}")
        self._messages.append({"role": "user", "content": prompt})
        self._compact_context_if_needed()

        logger.debug(f"Sending chat request to OpenAI model {self._model_name}")

        # Build request parameters, only including temperature if explicitly set.
        request_params = {
            "model": self._model_name,
            "input": self._request_messages(),
            "text_format": openai.NOT_GIVEN if self._output_format is None else self._output_format,
        }

        self._apply_temperature_if_explicit(request_params)

        self._log_message_payload("input", request_params["input"])
        response = self._responses_request(parse=True, **request_params)

        self._record_assistant_response(response.output_text)

        result = response.output_parsed if self._output_format else response.output_text
        logger.debug(f"Returning response: {result}")
        return result

    def _responses_request(self, parse: bool, **request_params):
        # `parse=True` preserves guided-generation behavior when an output schema is provided.
        if parse:
            return self.client.responses.parse(**request_params)
        return self.client.responses.create(**request_params)

    def _summarize_with_llm(self, previous_summary: str, archived_messages: list) -> str:
        self._resolve_summary_source("openai", "OpenAI")
        summary_model = self._summary_model or self._model_name
        summary_prompt = self._build_summary_prompt(previous_summary, archived_messages)
        response = self._responses_request(
            parse=False,
            model=summary_model,
            input=[{"role": "user", "content": summary_prompt}],
            temperature=0.0,
            max_output_tokens=self._summary_max_tokens,
        )
        return str(getattr(response, "output_text", "")).strip()

    def is_available(self) -> bool:
        """Check if the chat model is available.

        This method should be implemented in each subclass to check if
        the chat model is available.
        Returns:
            bool: True if the model is available, False otherwise.
        """
        try:
            test_messages = [self._system_message] if self._system_message else [{"role": "user", "content": "test"}]
            request_params = {"model": self._model_name, "messages": test_messages}

            self._apply_temperature_if_explicit(request_params)

            self.client.chat.completions.create(**request_params)
            return True
        except Exception as e:
            logger.error(f"Model {self._model_name} is not available: {e}")
            return False
