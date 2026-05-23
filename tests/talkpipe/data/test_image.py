import base64
from pathlib import Path

import pytest

from talkpipe.data.image import (
    ImageResult,
    load_image,
    load_image_from_bytes,
    load_image_from_path,
    loadImageSegment,
    sniff_mime_type,
)

# Minimal 1x1 PNG
MINIMAL_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)
MINIMAL_PNG = base64.b64decode(MINIMAL_PNG_B64)


@pytest.fixture
def png_file(tmp_path):
    path = tmp_path / "pixel.png"
    path.write_bytes(MINIMAL_PNG)
    return path


def test_sniff_mime_type_png():
    assert sniff_mime_type(MINIMAL_PNG) == "image/png"


def test_load_image_from_bytes():
    result = load_image_from_bytes(MINIMAL_PNG)
    assert isinstance(result, ImageResult)
    assert result.data == MINIMAL_PNG
    assert result.mime_type == "image/png"
    assert result.source == "bytes"


def test_load_image_from_path(png_file):
    result = load_image_from_path(png_file)
    assert result.data == MINIMAL_PNG
    assert result.mime_type == "image/png"
    assert result.source == str(png_file.resolve())
    assert result.id == result.source
    assert "pixel.png" in result.title


def test_load_image_from_path_missing():
    with pytest.raises(FileNotFoundError):
        load_image_from_path("/nonexistent/image.png")


def test_load_image_dispatches_bytes_and_path(png_file):
    from_bytes = load_image(MINIMAL_PNG)
    from_path = load_image(png_file)
    assert from_bytes.data == from_path.data


def test_load_image_returns_image_result_unchanged():
    original = load_image_from_bytes(MINIMAL_PNG)
    again = load_image(original)
    assert again is original


def test_load_image_from_url(monkeypatch):
    captured = {}

    class DummyResponse:
        content = MINIMAL_PNG
        headers = {"Content-Type": "image/png"}

        @staticmethod
        def raise_for_status():
            return None

    def fake_get(url, timeout=10, headers=None):
        captured["url"] = url
        return DummyResponse()

    monkeypatch.setattr("talkpipe.data.image.can_fetch", lambda url, user_agent=None: True)
    monkeypatch.setattr("talkpipe.data.image.requests.get", fake_get)

    result = load_image("https://example.com/photo.png")
    assert captured["url"] == "https://example.com/photo.png"
    assert result.data == MINIMAL_PNG
    assert result.mime_type == "image/png"
    assert result.source == "https://example.com/photo.png"


def test_load_image_segment(png_file):
    segment = loadImageSegment(field="path", set_as="image")
    items = list(segment.transform([{"path": str(png_file)}]))
    assert len(items) == 1
    assert isinstance(items[0]["image"], ImageResult)
    assert items[0]["image"].data == MINIMAL_PNG
