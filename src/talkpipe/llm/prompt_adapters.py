from typing import Annotated, Optional
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
    _system_message: Optional[dict]
    _summary_message: Optional[dict]
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
                 max_context_tokens: Annotated[Optional[int], "Maximum context tokens before compaction"] = None,
                 reserve_response_tokens: Annotated[int, "Reserved tokens for model response"] = 1024,
                 summary_trigger_ratio: Annotated[float, "Compaction trigger ratio of available input budget"] = 0.75,
                 keep_recent_turns: Annotated[int, "Recent message count to keep unsummarized"] = 6,
                 summarization_mode: Annotated[str, "Conversation summarization mode: off or rolling"] = "off",
                 summary_strategy: Annotated[str, "Summary strategy: llm, deterministic, or truncate"] = "llm",
                 summary_model: Annotated[Optional[str], "Optional model override for summary generation"] = None,
                 summary_source: Annotated[Optional[str], "Optional source override for summary generation"] = None,
                 summary_max_tokens: Annotated[int, "Max tokens requested for LLM summary generation"] = 512,
                 summary_max_chars: Annotated[int, "Max characters stored in summary memory"] = 2400):

        """Initialize the chat model"""
        self._model_name = model
        self._source = source
        self._multi_turn = multi_turn
        self._temperature = temperature
        self._temperature_explicit = temperature is not None
        self._output_format = output_format
        self._messages = []
        self._summary_message = None
        self._max_context_tokens = max_context_tokens
        self._reserve_response_tokens = reserve_response_tokens
        self._summary_trigger_ratio = summary_trigger_ratio
        self._keep_recent_turns = keep_recent_turns
        self._summarization_mode = summarization_mode
        self._summary_strategy = summary_strategy
        self._summary_model = summary_model
        self._summary_source = summary_source
        self._summary_max_tokens = summary_max_tokens
        self._summary_max_chars = summary_max_chars

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

    def _request_messages(self) -> list:
        summary_messages = [self._summary_message] if self._summary_message else []
        return self._prefix_messages + summary_messages + self._messages

    def _estimate_tokens(self, messages: list) -> int:
        # Provider-agnostic approximation to stay lightweight and deterministic.
        content_size = sum(len(str(message.get("content", ""))) for message in messages)
        return (content_size // 4) + (6 * len(messages))

    def _needs_compaction(self) -> bool:
        if self._summarization_mode != "rolling" or not self._max_context_tokens:
            return False
        if self._max_context_tokens <= self._reserve_response_tokens:
            return False
        input_budget = self._max_context_tokens - self._reserve_response_tokens
        trigger_limit = max(1, int(input_budget * self._summary_trigger_ratio))
        return self._estimate_tokens(self._request_messages()) > trigger_limit

    def _messages_to_summary_text(self, messages: list) -> str:
        lines = []
        for message in messages:
            role = str(message.get("role", "unknown")).upper()
            content = str(message.get("content", ""))
            lines.append(f"{role}: {content}")
        return "\n".join(lines)

    def _summarize_with_llm(self, previous_summary: str, archived_messages: list) -> str:
        raise NotImplementedError("LLM summary strategy is not implemented for this adapter.")

    def _summarize_deterministic(self, previous_summary: str, archived_messages: list) -> str:
        history_text = self._messages_to_summary_text(archived_messages)
        combined = history_text if not previous_summary else f"{previous_summary}\n{history_text}"
        if not combined.strip():
            return ""
        clipped = combined.strip()[: self._summary_max_chars]
        return f"Conversation memory (deterministic fallback):\n{clipped}"

    def _summarize_truncate(self, previous_summary: str, archived_messages: list) -> str:
        history_text = self._messages_to_summary_text(archived_messages)
        combined = history_text if not previous_summary else f"{previous_summary}\n{history_text}"
        if not combined.strip():
            return ""
        return combined.strip()[-self._summary_max_chars :]

    def _summarize_history(self, previous_summary: str, archived_messages: list) -> str:
        if self._summary_strategy == "deterministic":
            return self._summarize_deterministic(previous_summary, archived_messages)
        if self._summary_strategy == "truncate":
            return self._summarize_truncate(previous_summary, archived_messages)

        # Default strategy: llm
        try:
            summary = self._summarize_with_llm(previous_summary, archived_messages)
            if summary and summary.strip():
                return summary.strip()[: self._summary_max_chars]
        except Exception as exc:
            logger.warning(f"LLM summary strategy failed, using deterministic fallback: {exc}")

        deterministic_summary = self._summarize_deterministic(previous_summary, archived_messages)
        if deterministic_summary and deterministic_summary.strip():
            return deterministic_summary.strip()[: self._summary_max_chars]
        return self._summarize_truncate(previous_summary, archived_messages)

    def _compact_context_if_needed(self) -> None:
        if not self._needs_compaction():
            return

        current_estimate = self._estimate_tokens(self._request_messages())
        logger.info(
            "Context compaction triggered for %s (%s): estimated_tokens=%s",
            self._model_name,
            self._source,
            current_estimate,
        )
        keep_count = max(0, self._keep_recent_turns)
        if len(self._messages) <= keep_count:
            logger.debug(
                "Context compaction skipped: message count (%s) <= keep_recent_turns (%s)",
                len(self._messages),
                keep_count,
            )
            return

        archived_messages = self._messages[:-keep_count]
        recent_messages = self._messages[-keep_count:] if keep_count > 0 else []
        logger.debug(
            "Compacting context: archived_messages=%s recent_messages_kept=%s strategy=%s",
            len(archived_messages),
            len(recent_messages),
            self._summary_strategy,
        )
        previous_summary = self._summary_message["content"] if self._summary_message else ""
        new_summary = self._summarize_history(previous_summary, archived_messages)

        self._summary_message = {"role": "system", "content": new_summary} if new_summary else None
        self._messages = recent_messages
        logger.info(
            "Context compaction complete: summary_created=%s summary_chars=%s remaining_messages=%s",
            bool(self._summary_message),
            len(new_summary) if new_summary else 0,
            len(self._messages),
        )

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
                 max_context_tokens: Optional[int] = None,
                 reserve_response_tokens: int = 1024,
                 summary_trigger_ratio: float = 0.75,
                 keep_recent_turns: int = 6,
                 summarization_mode: str = "off",
                 summary_strategy: str = "llm",
                 summary_model: Optional[str] = None,
                 summary_source: Optional[str] = None,
                 summary_max_tokens: int = 512,
                 summary_max_chars: int = 2400):
        super().__init__(
            model, "ollama", system_prompt, multi_turn, temperature, output_format, role_map,
            max_context_tokens, reserve_response_tokens, summary_trigger_ratio, keep_recent_turns,
            summarization_mode, summary_strategy, summary_model, summary_source, summary_max_tokens,
            summary_max_chars
        )
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
        self._compact_context_if_needed()

        logger.debug(f"Sending chat request to Ollama model {self._model_name}")
        server_url = self._server_url
        if not server_url:
            server_url = get_config().get(OLLAMA_SERVER_URL, None)
        client = ollama.Client(server_url) if server_url else ollama
        response = client.chat(
            self._model_name,
            messages=self._request_messages(),
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

    def _summarize_with_llm(self, previous_summary: str, archived_messages: list) -> str:
        try:
            import ollama
        except ImportError:
            raise ImportError(
                "Ollama is not installed. Please install it with: pip install talkpipe[ollama]"
            )

        source = self._summary_source or self._source
        if source != "ollama":
            raise ValueError(f"Unsupported summary source for Ollama adapter: {source}")

        server_url = self._server_url
        if not server_url:
            server_url = get_config().get(OLLAMA_SERVER_URL, None)
        client = ollama.Client(server_url) if server_url else ollama
        summary_model = self._summary_model or self._model_name
        history_text = self._messages_to_summary_text(archived_messages)
        summary_prompt = (
            "Summarize the archived chat history for future context. "
            "Keep key facts, user constraints/preferences, decisions, open questions, and actionable items. "
            "Be concise.\n\n"
            f"Previous summary:\n{previous_summary or '(none)'}\n\n"
            f"Archived messages:\n{history_text}"
        )
        response = client.chat(
            summary_model,
            messages=[{"role": "user", "content": summary_prompt}],
            options={"temperature": 0.0, "num_predict": self._summary_max_tokens}
        )
        return str(response.message.content).strip()
    
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

    def __init__(self, model: str, system_prompt: Optional[str] = "You are a helpful assistant.", multi_turn: bool = True, temperature: float = None, output_format: BaseModel = None, role_map: str = None, max_context_tokens: Optional[int] = None, reserve_response_tokens: int = 1024, summary_trigger_ratio: float = 0.75, keep_recent_turns: int = 6, summarization_mode: str = "off", summary_strategy: str = "llm", summary_model: Optional[str] = None, summary_source: Optional[str] = None, summary_max_tokens: int = 512, summary_max_chars: int = 2400):
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

        super().__init__(model, "anthropic", system_prompt, multi_turn, temperature, output_format, role_map, max_context_tokens, reserve_response_tokens, summary_trigger_ratio, keep_recent_turns, summarization_mode, summary_strategy, summary_model, summary_source, summary_max_tokens, summary_max_chars)
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
        self._compact_context_if_needed()

        logger.debug(f"Sending chat request to Anthropic model {self._model_name}")

        # Build request parameters
        # Anthropic uses a separate system parameter, so we filter out system messages from prefix_messages
        non_system_prefix = [msg for msg in self._prefix_messages if msg["role"].lower() != "system"]
        non_system_summary = []
        if self._summary_message:
            non_system_summary = [{"role": "assistant", "content": f"Conversation memory:\n{self._summary_message['content']}"}]
        request_params = {
            "model": self._model_name,
            "messages": non_system_prefix + non_system_summary + self._messages,
            "max_tokens": self._max_tokens
        }

        # Only include system parameter if system_message exists
        if self._system_message:
            summary_text = f"\n\nConversation memory:\n{self._summary_message['content']}" if self._summary_message else ""
            request_params["system"] = self._system_message["content"] + summary_text

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

    def _summarize_with_llm(self, previous_summary: str, archived_messages: list) -> str:
        source = self._summary_source or self._source
        if source != "anthropic":
            raise ValueError(f"Unsupported summary source for Anthropic adapter: {source}")

        summary_model = self._summary_model or self._model_name
        history_text = self._messages_to_summary_text(archived_messages)
        summary_prompt = (
            "Summarize the archived chat history for future context. "
            "Keep key facts, user constraints/preferences, decisions, open questions, and actionable items. "
            "Be concise.\n\n"
            f"Previous summary:\n{previous_summary or '(none)'}\n\n"
            f"Archived messages:\n{history_text}"
        )
        response = self.client.messages.create(
            model=summary_model,
            messages=[{"role": "user", "content": summary_prompt}],
            max_tokens=self._summary_max_tokens,
            temperature=0.0
        )
        summary_text = ""
        for block in response.content:
            if hasattr(block, "text"):
                summary_text += block.text
        return summary_text.strip()

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

    def __init__(self, model: str, system_prompt: Optional[str] = "You are a helpful assistant.", multi_turn: bool = True, temperature: float = None, output_format: BaseModel = None, role_map: str = None, max_context_tokens: Optional[int] = None, reserve_response_tokens: int = 1024, summary_trigger_ratio: float = 0.75, keep_recent_turns: int = 6, summarization_mode: str = "off", summary_strategy: str = "llm", summary_model: Optional[str] = None, summary_source: Optional[str] = None, summary_max_tokens: int = 512, summary_max_chars: int = 2400):
        try:
            import openai
        except ImportError:
            raise ImportError(
                "OpenAI is not installed. Please install it with: pip install talkpipe[openai]"
            )

        super().__init__(model, "openai", system_prompt, multi_turn, temperature, output_format, role_map, max_context_tokens, reserve_response_tokens, summary_trigger_ratio, keep_recent_turns, summarization_mode, summary_strategy, summary_model, summary_source, summary_max_tokens, summary_max_chars)
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
        self._compact_context_if_needed()

        logger.debug(f"Sending chat request to OpenAI model {self._model_name}")

        # Build request parameters, only including temperature if explicitly set
        request_params = {
            "model": self._model_name,
            "input": self._request_messages(),
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

    def _summarize_with_llm(self, previous_summary: str, archived_messages: list) -> str:
        source = self._summary_source or self._source
        if source != "openai":
            raise ValueError(f"Unsupported summary source for OpenAI adapter: {source}")

        summary_model = self._summary_model or self._model_name
        history_text = self._messages_to_summary_text(archived_messages)
        summary_prompt = (
            "Summarize the archived chat history for future context. "
            "Keep key facts, user constraints/preferences, decisions, open questions, and actionable items. "
            "Be concise.\n\n"
            f"Previous summary:\n{previous_summary or '(none)'}\n\n"
            f"Archived messages:\n{history_text}"
        )
        response = self.client.responses.create(
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