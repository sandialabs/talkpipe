from abc import ABC, abstractmethod
import json
import logging
from typing import Annotated, Optional, Union

from pydantic import BaseModel

from talkpipe.util.data_manipulation import parse_key_value_str

from .prompt_adapter_memory import PromptAdapterMemoryMixin

# Keep the historical logger name for compatibility with existing monkeypatches.
logger = logging.getLogger("talkpipe.llm.prompt_adapters")


class AbstractLLMPromptAdapter(PromptAdapterMemoryMixin, ABC):
    """Abstract class for prompting an LLM.

    A descendent of this class should be written for every different type
    of LLM system (e.g. ollama) that TalkPipe can interact with.
    """

    _model_name: str
    _source: str
    _system_message: Optional[dict]
    _summary_message: Optional[dict]
    _messages: list
    _multi_turn: bool

    def __init__(
        self,
        model: Annotated[str, "The name of the model"],
        source: Annotated[str, "The source of the model"],
        system_prompt: Annotated[Optional[str], "The system prompt for the model"] = "You are a helpful assistant.",
        multi_turn: Annotated[bool, "Whether the model supports multi-turn conversations"] = True,
        temperature: Annotated[float, "The temperature for the model"] = None,
        output_format: Annotated[BaseModel, "The output format for the model"] = None,
        role_map: Annotated[str, "The role map for the model in the form 'role:message,role:message'. If the system role is included here, it overrides the system_prompt message"] = None,
        memory_mode: Annotated[str, "Memory behavior: full, recent_only, summary_llm, summary_deterministic, or summary_truncate"] = "full",
        unsummarized_message_count: Annotated[int, "Recent message count kept out of summary compaction"] = 6,
        context_token_trigger: Annotated[Optional[Union[int, float]], "Approximate context-token trigger for rolling memory compaction (values < 1 are ignored)"] = None,
        memory_size: Annotated[int, "Target max tokens for generated summary memory"] = 512,
        debug_messages: Annotated[bool, "Whether to log outbound LLM request messages"] = False,
    ):
        """Initialize the chat model."""
        self._model_name = model
        self._source = source
        self._multi_turn = multi_turn
        self._temperature = temperature
        self._temperature_explicit = temperature is not None
        self._output_format = output_format
        self._messages = []
        self._summary_message = None
        self._memory_mode = memory_mode
        self._unsummarized_message_count = unsummarized_message_count
        self._context_token_trigger = context_token_trigger
        self._debug_messages = debug_messages
        self._summary_max_tokens = memory_size
        self._summary_max_chars = 2400
        self._summary_model = None
        self._configure_memory_mode(memory_mode)

        # Initialize system message and prefix messages.
        # Only create system message if system_prompt is not None.
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

    def _request_messages(self) -> list:
        # Providers consume the same assembled order: static prefix, rolling summary, then live turns.
        summary_messages = [self._summary_message] if self._summary_message else []
        return self._prefix_messages + summary_messages + self._messages

    def _require_dependency(self, module_name: str, display_name: str, extra_name: str):
        try:
            return __import__(module_name)
        except ImportError as exc:
            raise ImportError(
                f"{display_name} is not installed. Please install it with: pip install talkpipe[{extra_name}]"
            ) from exc

    def _build_client(self, factory, display_name: str, api_key_env_var: str):
        """Instantiate a provider SDK client with friendly credential errors.

        Cloud SDK clients raise a raw, provider-specific exception when no API
        key is configured (e.g. anthropic's "Could not resolve authentication
        method"). Wrap construction so a TalkPipe user gets an actionable
        message pointing at the environment variable the SDK actually reads.

        Args:
            factory: Zero-argument callable that constructs the SDK client.
            display_name: Human-readable provider name (e.g. "Anthropic").
            api_key_env_var: The env var the SDK reads (e.g. "ANTHROPIC_API_KEY").
        """
        try:
            return factory()
        except Exception as exc:
            raise RuntimeError(
                f"Could not initialize the {display_name} client: {exc} "
                f"This usually means the API key is missing or invalid. Set the "
                f"{api_key_env_var} environment variable to your API key "
                f"(the {display_name} SDK reads it directly, not TALKPIPE_* keys). "
                f"See docs/guides/model-and-source-configuration.md."
            ) from exc

    def _apply_temperature_if_explicit(self, request_params: dict) -> None:
        if self._temperature_explicit:
            request_params["temperature"] = self._temperature

    def _record_assistant_response(self, response_text: str) -> None:
        # Single helper keeps history mutation consistent across providers.
        if self._multi_turn:
            logger.debug("Multi-turn enabled, appending assistant response to chat history")
            self._messages.append({"role": "assistant", "content": response_text})
        else:
            logger.debug("Single-turn mode, clearing message and summary history")
            self._messages = []
            self._summary_message = None

    def _log_message_payload(self, payload_name: str, messages: list) -> None:
        if not self._debug_messages:
            return
        sanitized = [self._format_message_for_debug(message) for message in messages]
        logger.debug(
            "LLM outbound payload (%s) for %s (%s): %s",
            payload_name,
            self._model_name,
            self._source,
            json.dumps(sanitized, ensure_ascii=True),
        )

    def _format_message_for_debug(self, message: dict) -> dict:
        role = message.get("role", "unknown")
        if message.get("images"):
            content = str(message.get("content", ""))
            if len(content) > 500:
                content = content[:500] + "...[truncated]"
            return {
                "role": role,
                "content": content,
                "images": [f"<{len(image)} base64 chars>" for image in message["images"]],
            }
        content = message.get("content", "")
        if isinstance(content, list):
            sanitized_parts = []
            for part in content:
                if not isinstance(part, dict):
                    sanitized_parts.append(part)
                    continue
                part_type = part.get("type", "unknown")
                if "image" in part_type or part.get("type") == "image":
                    sanitized_parts.append({"type": part_type, "image": "<redacted>"})
                else:
                    sanitized_parts.append(part)
            return {"role": role, "content": sanitized_parts}
        content = str(content)
        if len(content) > 500:
            content = content[:500] + "...[truncated]"
        return {"role": role, "content": content}

    def _clip_debug_text(self, text: str, limit: int = 1200) -> str:
        if text is None:
            return ""
        if len(text) <= limit:
            return text
        return text[:limit] + "...[truncated]"

    def complete_text_without_context(
        self,
        prompt: str,
        *,
        model: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: Optional[int] = None,
    ) -> str:
        """Return a plain text completion without reading or mutating chat history."""
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement complete_text_without_context() "
            "to support memory_mode='summary_llm'."
        )

    @property
    def model_name(self) -> str:
        """The name of the model."""
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

    def execute_turn(self, user_turn) -> str:
        """Execute the chat model with a multimodal user turn."""
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement execute_turn() for multimodal prompts."
        )

    @abstractmethod
    def is_available(self) -> bool:
        """Check if the chat model is available.

        This method should be implemented in each subclass to check if
        the chat model is available.
        Returns:
            bool: True if the model is available, False otherwise.
        """
