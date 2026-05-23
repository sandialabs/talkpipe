import base64
from unittest.mock import MagicMock

import pytest

from talkpipe.llm.content import DEFAULT_VISION_PROMPT
from talkpipe.llm.vision import LLMVisionPrompt

OLLAMA_VISION_MODEL = "gemma4:31b-cloud"
OLLAMA_SOURCE = "ollama"

MINIMAL_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


@pytest.fixture
def png_file(tmp_path):
    path = tmp_path / "pixel.png"
    path.write_bytes(MINIMAL_PNG)
    return path


def test_llm_vision_prompt_default_prompt(png_file):
    segment = LLMVisionPrompt(
        image_field="path",
        model=OLLAMA_VISION_MODEL,
        source=OLLAMA_SOURCE,
    )
    mock_chat = MagicMock()
    mock_chat.execute_turn.return_value = "image description"
    segment.chat = mock_chat

    results = list(segment.transform([{"path": str(png_file)}]))
    assert results == ["image description"]
    user_turn = mock_chat.execute_turn.call_args[0][0]
    assert user_turn.parts[0].text == DEFAULT_VISION_PROMPT


def test_llm_vision_prompt_custom_prompt_field(png_file):
    segment = LLMVisionPrompt(
        image_field="path",
        prompt_field="question",
        model=OLLAMA_VISION_MODEL,
        source=OLLAMA_SOURCE,
    )
    mock_chat = MagicMock()
    mock_chat.execute_turn.return_value = "answer"
    segment.chat = mock_chat

    list(segment.transform([{"path": str(png_file), "question": "What is this?"}]))
    user_turn = mock_chat.execute_turn.call_args[0][0]
    assert user_turn.parts[0].text == "What is this?"


def test_llm_vision_prompt_context_field_empty_by_default(png_file):
    segment = LLMVisionPrompt(
        image_field="path",
        model=OLLAMA_VISION_MODEL,
        source=OLLAMA_SOURCE,
    )
    mock_chat = MagicMock()
    mock_chat.execute_turn.return_value = "done"
    segment.chat = mock_chat

    list(segment.transform([{"path": str(png_file), "notes": "ignored"}]))
    user_turn = mock_chat.execute_turn.call_args[0][0]
    assert len(user_turn.parts) == 2
    assert user_turn.parts[0].text == DEFAULT_VISION_PROMPT


def test_llm_vision_prompt_with_context_and_set_as(png_file):
    segment = LLMVisionPrompt(
        image_field="path",
        context_field="notes",
        set_as="description",
        model=OLLAMA_VISION_MODEL,
        source=OLLAMA_SOURCE,
    )
    mock_chat = MagicMock()
    mock_chat.execute_turn.return_value = "A tiny pixel."
    segment.chat = mock_chat

    item = {"path": str(png_file), "notes": "UI screenshot"}
    results = list(segment.transform([item]))
    assert results[0]["description"] == "A tiny pixel."
    user_turn = mock_chat.execute_turn.call_args[0][0]
    assert user_turn.parts[0].text == "UI screenshot"


def test_llm_vision_prompt_missing_image_field():
    segment = LLMVisionPrompt(
        image_field="path",
        model=OLLAMA_VISION_MODEL,
        source=OLLAMA_SOURCE,
    )
    segment.chat = MagicMock()

    with pytest.raises(ValueError, match="Image field 'path'"):
        list(segment.transform([{"other": "value"}]))
