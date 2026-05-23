import base64

from talkpipe.llm.content import ImagePart, TextPart, UserTurn, user_turn_from_fields
from talkpipe.llm.multimodal import (
    to_anthropic_user_message,
    to_ollama_user_message,
    to_openai_user_message,
)

MINIMAL_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)
PNG_B64 = base64.b64encode(MINIMAL_PNG).decode("ascii")


def _sample_turn() -> UserTurn:
    return user_turn_from_fields(
        context="Context text",
        prompt="Prompt text",
        images=MINIMAL_PNG,
    )


def test_to_ollama_user_message():
    message = to_ollama_user_message(_sample_turn())
    assert message["role"] == "user"
    assert "Context text" in message["content"]
    assert "Prompt text" in message["content"]
    assert message["images"] == [PNG_B64]


def test_to_openai_user_message():
    message = to_openai_user_message(_sample_turn())
    assert message["role"] == "user"
    assert message["content"][0]["type"] == "input_text"
    assert message["content"][1]["type"] == "input_text"
    assert message["content"][2]["type"] == "input_image"
    assert message["content"][2]["image_url"].startswith("data:image/")


def test_to_anthropic_user_message():
    message = to_anthropic_user_message(_sample_turn())
    assert message["role"] == "user"
    assert message["content"][0]["type"] == "text"
    assert message["content"][-1]["type"] == "image"
    assert message["content"][-1]["source"]["data"] == PNG_B64


def test_to_ollama_user_message_text_only():
    turn = UserTurn(parts=[TextPart(text="hello")])
    message = to_ollama_user_message(turn)
    assert message == {"role": "user", "content": "hello"}
    assert "images" not in message
