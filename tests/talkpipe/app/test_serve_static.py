"""chatterlang_serve's browser assets are packaged and served by the server itself."""

from fastapi.testclient import TestClient

from talkpipe.app import chatterlang_serve
from talkpipe.app.server_common import STATIC_DIR


def test_serve_static_assets_served():
    client = TestClient(chatterlang_serve.ChatterlangServer().app)
    for path, content_type in [
        ("/static/serve/common.js", "javascript"),
        ("/static/serve/stream.js", "javascript"),
        ("/static/serve/index.js", "javascript"),
        ("/static/serve/stream.css", "text/css"),
        ("/static/serve/index.css", "text/css"),
        ("/static/serve/vendor/marked.min.js", "javascript"),
        ("/static/serve/vendor/purify.min.js", "javascript"),
    ]:
        response = client.get(path)
        assert response.status_code == 200, path
        assert content_type in response.headers["content-type"], path


def test_vendored_markdown_libraries_are_real_and_licensed():
    """Guard against placeholder files: the real bundles are tens of KB and
    announce themselves, and their licenses ship alongside."""
    vendor = STATIC_DIR / "serve" / "vendor"
    marked = (vendor / "marked.min.js").read_text(encoding="utf-8")
    purify = (vendor / "purify.min.js").read_text(encoding="utf-8")
    assert len(marked) > 20_000
    assert "marked" in marked[:200]
    assert len(purify) > 20_000
    assert "DOMPurify" in purify[:200]
    licenses = (vendor / "LICENSES.txt").read_text(encoding="utf-8")
    assert "MIT" in licenses
    assert "Apache" in licenses


def test_templates_are_packaged():
    for name in ("stream.html", "index.html"):
        template = chatterlang_serve.TEMPLATE_DIR / name
        assert template.is_file(), name
        assert "cdn.jsdelivr.net" not in template.read_text(encoding="utf-8")
