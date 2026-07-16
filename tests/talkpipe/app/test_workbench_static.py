"""Tests for the workbench's static-file UI (Phase 1 of the workbench IDE)."""

from fastapi.testclient import TestClient

from talkpipe.app import chatterlang_workbench


def get_client():
    return TestClient(chatterlang_workbench.app)


def test_root_serves_workbench_html():
    client = get_client()
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "/static/workbench/app.js" in response.text
    assert "TalkPipe" in response.text


def test_workbench_static_assets_served():
    client = get_client()
    for path, content_type in [
        ("/static/workbench/app.js", "javascript"),
        ("/static/workbench/editor.js", "javascript"),
        ("/static/workbench/workspace.js", "javascript"),
        ("/static/workbench/suggest.js", "javascript"),
        ("/static/workbench/styles.css", "text/css"),
        ("/static/workbench/vendor/codemirror.js", "javascript"),
    ]:
        response = client.get(path)
        assert response.status_code == 200, path
        assert content_type in response.headers["content-type"], path


def test_vendored_codemirror_bundle_is_nontrivial():
    """Guard against a broken/placeholder vendored bundle."""
    bundle = chatterlang_workbench.WORKBENCH_STATIC_DIR / "vendor" / "codemirror.js"
    assert bundle.stat().st_size > 100_000
    licenses = chatterlang_workbench.WORKBENCH_STATIC_DIR / "vendor" / "LICENSES.txt"
    assert "MIT" in licenses.read_text()
