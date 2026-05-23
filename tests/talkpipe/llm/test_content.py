import base64

import pytest

from talkpipe.data.image import ImageResult, load_image_from_bytes
from talkpipe.llm.content import (
    DEFAULT_VISION_PROMPT,
    ImagePart,
    TextPart,
    UserTurn,
    user_turn_from_fields,
    user_turn_from_text,
    user_turn_text,
)

MINIMAL_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def test_user_turn_from_text():
    turn = user_turn_from_text("hello")
    assert turn.parts == [TextPart(text="hello")]
    assert user_turn_text(turn) == "hello"


def test_default_vision_prompt():
    turn = user_turn_from_fields(images=MINIMAL_PNG)
    assert turn.parts[0] == TextPart(text=DEFAULT_VISION_PROMPT)
    assert isinstance(turn.parts[1], ImagePart)


def test_user_turn_from_fields_with_context_and_prompt():
    turn = user_turn_from_fields(
        context="Background info",
        prompt="What color is the pixel?",
        images=MINIMAL_PNG,
    )
    assert [type(part) for part in turn.parts] == [TextPart, TextPart, ImagePart]
    assert turn.parts[0].text == "Background info"
    assert turn.parts[1].text == "What color is the pixel?"


def test_user_turn_from_fields_skips_empty_context():
    turn = user_turn_from_fields(prompt="Describe this", context=None, images=MINIMAL_PNG)
    assert turn.parts[0].text == "Describe this"
    assert len(turn.parts) == 2


def test_user_turn_from_image_result():
    image = load_image_from_bytes(MINIMAL_PNG)
    turn = user_turn_from_fields(images=image)
    assert turn.parts[-1].data == MINIMAL_PNG


def test_user_turn_requires_content():
    with pytest.raises(ValueError):
        user_turn_from_fields(prompt="", context=None, images=None)
