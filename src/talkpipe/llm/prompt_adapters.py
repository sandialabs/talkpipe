from .prompt_adapter_base import AbstractLLMPromptAdapter, logger
from .prompt_adapters_anthropic import AnthropicPromptAdapter
from .prompt_adapters_eliza import ElizaPromptAdapter
from .prompt_adapters_ollama import OllamaPromptAdapter
from .prompt_adapters_openai import OpenAIPromptAdapter

# Compatibility facade: keep legacy import path stable while internals live in split modules.
__all__ = [
    "AbstractLLMPromptAdapter",
    "OllamaPromptAdapter",
    "AnthropicPromptAdapter",
    "OpenAIPromptAdapter",
    "ElizaPromptAdapter",
    "logger",
]