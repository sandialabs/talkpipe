"""Multimodal translation helpers for LLM prompt adapters."""

from __future__ import annotations

import base64

from .content import ImagePart, TextPart, UserTurn


def to_ollama_user_message(user_turn: UserTurn) -> dict:
    text = "\n".join(part.text for part in user_turn.parts if isinstance(part, TextPart))
    images = [
        base64.b64encode(part.data).decode("ascii")
        for part in user_turn.parts
        if isinstance(part, ImagePart)
    ]
    message = {"role": "user", "content": text}
    if images:
        message["images"] = images
    return message


def to_openai_user_message(user_turn: UserTurn) -> dict:
    content = []
    for part in user_turn.parts:
        if isinstance(part, TextPart):
            content.append({"type": "input_text", "text": part.text})
        elif isinstance(part, ImagePart):
            encoded = base64.b64encode(part.data).decode("ascii")
            content.append(
                {
                    "type": "input_image",
                    "image_url": f"data:{part.mime_type};base64,{encoded}",
                }
            )
    return {"role": "user", "content": content}


def to_anthropic_user_message(user_turn: UserTurn) -> dict:
    content = []
    for part in user_turn.parts:
        if isinstance(part, TextPart):
            content.append({"type": "text", "text": part.text})
        elif isinstance(part, ImagePart):
            encoded = base64.b64encode(part.data).decode("ascii")
            content.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": part.mime_type,
                        "data": encoded,
                    },
                }
            )
    return {"role": "user", "content": content}
