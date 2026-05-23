"""Provider-agnostic multimodal message content for LLM adapters."""

from __future__ import annotations

from typing import Annotated, Union

from pydantic import BaseModel, ConfigDict

from talkpipe.data.image import ImageResult, load_image

DEFAULT_VISION_PROMPT = "Explains the contents of this image."


class TextPart(BaseModel):
    """A text fragment within a user turn."""

    text: str


class ImagePart(BaseModel):
    """An image fragment within a user turn."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    data: Annotated[bytes, "Raw image bytes"]
    mime_type: Annotated[str, "MIME type of the image"]


class UserTurn(BaseModel):
    """Provider-neutral representation of one user message."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    parts: list[Union[TextPart, ImagePart]]


def image_part_from_result(result: ImageResult) -> ImagePart:
    return ImagePart(data=result.data, mime_type=result.mime_type)


def _coerce_image(image: Union[ImageResult, bytes, str]) -> ImagePart:
    if isinstance(image, ImagePart):
        return image
    if isinstance(image, ImageResult):
        return image_part_from_result(image)
    return image_part_from_result(load_image(image))


def user_turn_from_text(text: str) -> UserTurn:
    return UserTurn(parts=[TextPart(text=text)])


def user_turn_from_fields(
    *,
    prompt: str = DEFAULT_VISION_PROMPT,
    context: str | None = None,
    images: Union[ImageResult, bytes, str, ImagePart, list, None] = None,
) -> UserTurn:
    """Build a UserTurn from vision segment field values."""
    parts: list[Union[TextPart, ImagePart]] = []
    if context:
        parts.append(TextPart(text=context))
    if prompt:
        parts.append(TextPart(text=prompt))
    if images is not None:
        if isinstance(images, list):
            for image in images:
                parts.append(_coerce_image(image))
        else:
            parts.append(_coerce_image(images))
    if not parts:
        raise ValueError("UserTurn requires at least one text or image part")
    return UserTurn(parts=parts)


def user_turn_text(user_turn: UserTurn) -> str:
    """Concatenate text parts for logging and legacy string paths."""
    return "\n".join(part.text for part in user_turn.parts if isinstance(part, TextPart))
