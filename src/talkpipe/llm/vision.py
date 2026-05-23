"""Vision LLM segment for multimodal prompts."""

from __future__ import annotations

import logging
from typing import Annotated, Iterable, Iterator, Optional

from talkpipe.chatterlang.registry import register_segment
from talkpipe.pipe.core import AbstractSegment
from talkpipe.util.config import get_config
from talkpipe.util.constants import TALKPIPE_MODEL_NAME, TALKPIPE_SOURCE
from talkpipe.util.data_manipulation import assign_property, extract_property

from .config import getPromptAdapter, getPromptSources
from .content import DEFAULT_VISION_PROMPT, user_turn_from_fields

logger = logging.getLogger(__name__)


@register_segment("llmVisionPrompt")
class LLMVisionPrompt(AbstractSegment):
    """Send a multimodal prompt (text plus image) to a vision-capable LLM.

    Reads context, prompt, and image fields from each input item and returns the
    model response. By default each item is handled independently (single-turn).
    """

    def __init__(
        self,
        image_field: Annotated[str, "Item field containing the image path, URL, bytes, or ImageResult"],
        model: Annotated[Optional[str], "The name of the model to chat with"] = None,
        source: Annotated[Optional[str], "The source of the model (ollama, openai, or anthropic)"] = None,
        system_prompt: Annotated[Optional[str], "The system prompt for the model"] = "You are a helpful assistant.",
        context_field: Annotated[Optional[str], "Optional item field for text context"] = "",
        prompt: Annotated[str, "Fixed prompt when prompt_field is not used"] = DEFAULT_VISION_PROMPT,
        prompt_field: Annotated[Optional[str], "Optional item field overriding the fixed prompt"] = None,
        set_as: Annotated[Optional[str], "Field to store the response on the input item"] = None,
        multi_turn: Annotated[bool, "Whether to retain conversation history between items"] = False,
        temperature: Annotated[Optional[float], "The temperature to use for the model"] = None,
        debug_messages: Annotated[bool, "Whether to log outbound LLM request messages"] = False,
    ):
        super().__init__()
        cfg = get_config()
        model = model or cfg.get(TALKPIPE_MODEL_NAME, None)
        source = source or cfg.get(TALKPIPE_SOURCE, None)

        if model is None or source is None:
            raise ValueError(
                "Model name and source must be provided, specified in the configuration file, "
                "or in environment variables."
            )
        if source not in getPromptSources():
            raise ValueError(f"Unknown source: {source}")

        adapter_kwargs = {
            "model": model,
            "system_prompt": system_prompt,
            "multi_turn": multi_turn,
            "temperature": temperature,
            "debug_messages": debug_messages,
        }
        self.chat = getPromptAdapter(source)(**adapter_kwargs)

        self.image_field = image_field
        self.context_field = context_field or ""
        self.prompt = prompt
        self.prompt_field = prompt_field
        self.set_as = set_as

    def _resolve_prompt(self, item) -> str:
        if self.prompt_field:
            value = extract_property(item, self.prompt_field)
            if value is not None and str(value).strip():
                return str(value)
        return self.prompt

    def _resolve_context(self, item) -> str | None:
        if not self.context_field:
            return None
        value = extract_property(item, self.context_field)
        if value is None or not str(value).strip():
            return None
        return str(value)

    def _resolve_image(self, item):
        value = extract_property(item, self.image_field)
        if value is None:
            raise ValueError(f"Image field '{self.image_field}' is missing or empty on item: {item!r}")
        return value

    def transform(self, input_iter: Iterable) -> Iterator:
        for item in input_iter:
            user_turn = user_turn_from_fields(
                prompt=self._resolve_prompt(item),
                context=self._resolve_context(item),
                images=self._resolve_image(item),
            )
            response = self.chat.execute_turn(user_turn)
            if self.set_as is not None:
                assign_property(item, self.set_as, response)
                yield item
            else:
                yield response
