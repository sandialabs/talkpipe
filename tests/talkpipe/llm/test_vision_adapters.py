import base64

import pytest

from talkpipe.llm.prompt_adapters import OllamaPromptAdapter
from talkpipe.llm.content import DEFAULT_VISION_PROMPT, user_turn_from_fields

OLLAMA_VISION_MODEL = "gemma4:31b-cloud"
OLLAMA_SOURCE = "ollama"

MINIMAL_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def _patch_ollama_dependency(monkeypatch):
    class DummyOllamaModule:
        @staticmethod
        def chat(*_args, **_kwargs):
            return None

    monkeypatch.setattr(
        OllamaPromptAdapter,
        "_require_dependency",
        lambda *_args, **_kwargs: DummyOllamaModule(),
    )


def test_ollama_execute_turn_sends_multimodal_message(monkeypatch):
    _patch_ollama_dependency(monkeypatch)
    adapter = OllamaPromptAdapter(OLLAMA_VISION_MODEL, multi_turn=False)
    captured = {}

    class DummyMessage:
        content = "A single red pixel."

    class DummyResponse:
        message = DummyMessage()

    def fake_chat_completion(model, messages, format_schema=None, options=None):
        captured["model"] = model
        captured["messages"] = messages
        return DummyResponse()

    monkeypatch.setattr(adapter, "_chat_completion", fake_chat_completion)

    user_turn = user_turn_from_fields(prompt=DEFAULT_VISION_PROMPT, images=MINIMAL_PNG)
    result = adapter.execute_turn(user_turn)

    assert result == "A single red pixel."
    assert captured["model"] == OLLAMA_VISION_MODEL
    user_messages = [message for message in captured["messages"] if message.get("role") == "user"]
    assert user_messages[-1]["content"] == DEFAULT_VISION_PROMPT
    assert user_messages[-1]["images"] == [base64.b64encode(MINIMAL_PNG).decode("ascii")]


def test_ollama_execute_turn_clears_history_when_single_turn(monkeypatch):
    _patch_ollama_dependency(monkeypatch)
    adapter = OllamaPromptAdapter(OLLAMA_VISION_MODEL, multi_turn=False)

    class DummyMessage:
        content = "done"

    class DummyResponse:
        message = DummyMessage()

    monkeypatch.setattr(adapter, "_chat_completion", lambda *_args, **_kwargs: DummyResponse())

    user_turn = user_turn_from_fields(images=MINIMAL_PNG)
    adapter.execute_turn(user_turn)
    assert adapter._messages == []
