"""Utility functions for loading and normalizing image data."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Annotated, Union
from urllib.parse import urlparse

import requests
from pydantic import BaseModel, ConfigDict

from talkpipe.chatterlang.registry import register_segment
from talkpipe.pipe import core

from .html import can_fetch

logger = logging.getLogger(__name__)


class ImageResult(BaseModel):
    """Model representing a loaded image."""

    model_config = ConfigDict(extra="allow")

    data: Annotated[bytes, "Raw image bytes"]
    mime_type: Annotated[str, "MIME type of the image (e.g. image/png)"]
    source: Annotated[str, "Original path, URL, or 'bytes'"]
    id: Annotated[str, "Unique identifier for this image"]
    title: Annotated[str, "Human-readable description of the image source"]


def sniff_mime_type(data: bytes) -> str:
    """Guess MIME type from magic bytes."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return "application/octet-stream"


def _require_pillow():
    try:
        from PIL import Image  # noqa: F401
    except ImportError as exc:
        raise ImportError(
            "Pillow is not installed. Please install it with: pip install talkpipe[pillow]"
        ) from exc


def load_image_from_bytes(data: bytes, *, mime_type: str | None = None) -> ImageResult:
    if not data:
        raise ValueError("Image bytes are empty")
    resolved_mime = mime_type or sniff_mime_type(data)
    return ImageResult(
        data=data,
        mime_type=resolved_mime,
        source="bytes",
        id="bytes",
        title="Image from bytes",
    )


def load_image_from_path(file_path: Union[str, Path]) -> ImageResult:
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Image file not found: {file_path}")
    if not path.is_file():
        raise FileNotFoundError(f"Image path is not a file: {file_path}")
    data = path.read_bytes()
    source_str = str(path.resolve())
    return ImageResult(
        data=data,
        mime_type=sniff_mime_type(data),
        source=source_str,
        id=source_str,
        title=path.name,
    )


def load_image_from_url(
    url: str,
    *,
    fail_on_error: bool = True,
    user_agent: str | None = None,
    timeout: int = 10,
) -> ImageResult:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Unsupported URL scheme for image download: {parsed.scheme}")

    if not can_fetch(url, user_agent=user_agent):
        message = f"Fetching {url} is disallowed by robots.txt"
        if fail_on_error:
            raise PermissionError(message)
        logger.warning(message)
        return None  # type: ignore[return-value]

    headers = {"User-Agent": user_agent} if user_agent else None
    try:
        response = requests.get(url, timeout=timeout, headers=headers)
        response.raise_for_status()
    except requests.RequestException as exc:
        if fail_on_error:
            raise
        logger.warning("Failed to download image from %s: %s", url, exc)
        return None  # type: ignore[return-value]

    data = response.content
    header_mime = response.headers.get("Content-Type", "").split(";")[0].strip()
    mime_type = header_mime if header_mime.startswith("image/") else sniff_mime_type(data)
    return ImageResult(
        data=data,
        mime_type=mime_type,
        source=url,
        id=url,
        title=url,
    )


def load_image(
    source: Union[str, Path, bytes, ImageResult],
    *,
    mime_type: str | None = None,
) -> ImageResult:
    """Load an image from a path, URL, bytes, or existing ImageResult."""
    if isinstance(source, ImageResult):
        return source
    if isinstance(source, bytes):
        return load_image_from_bytes(source, mime_type=mime_type)
    if isinstance(source, str):
        stripped = source.strip()
        if stripped.startswith("http://") or stripped.startswith("https://"):
            return load_image_from_url(stripped)
        return load_image_from_path(stripped)
    return load_image_from_path(source)


def normalize_image(
    result: ImageResult,
    *,
    max_dimension: int | None = None,
    format: str | None = None,
) -> ImageResult:
    """Resize and/or re-encode an image. Requires Pillow."""
    _require_pillow()
    from io import BytesIO

    from PIL import Image

    image = Image.open(BytesIO(result.data))
    if max_dimension is not None:
        image.thumbnail((max_dimension, max_dimension))

    output_format = format or image.format or "PNG"
    mime_map = {
        "PNG": "image/png",
        "JPEG": "image/jpeg",
        "GIF": "image/gif",
        "WEBP": "image/webp",
    }
    buffer = BytesIO()
    save_kwargs = {}
    if output_format.upper() == "JPEG":
        save_kwargs["quality"] = 85
        if image.mode in ("RGBA", "P"):
            image = image.convert("RGB")
    image.save(buffer, format=output_format, **save_kwargs)
    normalized = buffer.getvalue()
    return ImageResult(
        data=normalized,
        mime_type=mime_map.get(output_format.upper(), result.mime_type),
        source=result.source,
        id=result.id,
        title=result.title,
        width=image.width,
        height=image.height,
    )


@register_segment("loadImage")
@core.field_segment()
def loadImageSegment(
    item: Annotated[Union[str, Path, bytes, ImageResult], "Image path, URL, bytes, or ImageResult"],
) -> ImageResult:
    """Load an image from a path, URL, or bytes."""
    return load_image(item)


@register_segment("downloadImageURL")
@core.field_segment()
def downloadImageURLSegment(
    url: Annotated[str, "URL of the image to download"],
    fail_on_error: Annotated[bool, "Raise on download errors"] = True,
    timeout: Annotated[int, "Request timeout in seconds"] = 10,
) -> ImageResult:
    """Download an image from a URL respecting robots.txt."""
    return load_image_from_url(url, fail_on_error=fail_on_error, timeout=timeout)
