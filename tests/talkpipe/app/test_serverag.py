"""Tests for the ``serverag`` console script (RAG pipeline behind ChatterlangServer)."""

from __future__ import annotations

from typing import Any, ClassVar
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from talkpipe.app import serverag
from talkpipe.app.chatterlang_serve import ChatterlangServer
from talkpipe.util.config import reset_config


class FakePipeline:
    """A built pipeline: echoes queries as answers, remembers how often it ran."""

    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, items: Any) -> Any:
        self.calls += 1
        for item in items:
            yield {"answer": f"answer to {item['prompt']}", "sources": []}


class FakeRAG:
    """Stands in for RAGToText: records kwargs, echoes queries as answers."""

    instances: ClassVar[list[FakeRAG]] = []

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.made = False
        self.pipelines: list[FakePipeline] = []
        FakeRAG.instances.append(self)

    def make_pipeline(self) -> FakePipeline:
        self.made = True
        pipeline = FakePipeline()
        self.pipelines.append(pipeline)
        return pipeline

    def transform(self, items: Any) -> Any:
        yield from FakePipeline()(items)

    def __call__(self, items: Any) -> Any:  # used as the tail of ``a | b | rag``
        return self.transform(items)

    def __ror__(self, other: Any) -> Any:  # ``Prompt() | ToDict(...) | rag``
        rag = self

        def run() -> Any:
            return rag.transform(other())

        return run


class FakeServer:
    last: FakeServer | None = None

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.started: bool | None = None
        FakeServer.last = self

    def start(self, background: bool = False) -> None:
        self.started = background


@pytest.fixture(autouse=True)
def _isolate(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> Any:
    FakeRAG.instances.clear()
    FakeServer.last = None
    monkeypatch.setenv("HOME", str(tmp_path))  # no ~/.talkpipe.toml leakage
    monkeypatch.delenv("TALKPIPE_API_KEY", raising=False)
    reset_config()
    yield
    reset_config()


def _run(argv: list[str]) -> None:
    with (
        patch.object(serverag, "RAGToText", FakeRAG),
        patch.object(serverag, "ChatterlangServer", FakeServer),
        patch("sys.argv", ["serverag", *argv]),
    ):
        serverag.main()


def test_builds_rag_from_cli_args_and_starts_server() -> None:
    _run(
        [
            "--path",
            "/tmp/db",
            "--embedding_model",
            "e-model",
            "--embedding_source",
            "e-src",
            "--completion_model",
            "c-model",
            "--completion_source",
            "c-src",
            "--limit",
            "3",
            "--table_name",
            "things",
            "--system_prompt",
            "be brief",
            "--port",
            "9999",
            "--host",
            "127.0.0.1",
            "--title",
            "My RAG",
        ]
    )
    (rag,) = FakeRAG.instances
    assert rag.made, "make_pipeline() should be called at startup to fail fast"
    assert rag.kwargs["path"] == "/tmp/db"
    assert rag.kwargs["content_field"] == "prompt"
    assert rag.kwargs["embedding_model"] == "e-model"
    assert rag.kwargs["embedding_source"] == "e-src"
    assert rag.kwargs["completion_model"] == "c-model"
    assert rag.kwargs["completion_source"] == "c-src"
    assert rag.kwargs["limit"] == 3
    assert rag.kwargs["table_name"] == "things"
    assert rag.kwargs["system_prompt"] == "be brief"

    server = FakeServer.last
    assert server is not None
    assert server.started is False  # foreground
    assert server.kwargs["port"] == 9999
    assert server.kwargs["host"] == "127.0.0.1"
    assert server.kwargs["title"] == "My RAG"
    assert server.kwargs["display_property"] == "prompt"
    assert server.kwargs["form_config"]["fields"][0]["name"] == "prompt"
    assert server.kwargs["api_key"] is None
    assert server.kwargs["require_auth"] is False


def test_models_fall_back_to_config_and_api_key_from_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TALKPIPE_default_embedding_model_name", "cfg-embed")
    monkeypatch.setenv("TALKPIPE_default_embedding_model_source", "cfg-esrc")
    monkeypatch.setenv("TALKPIPE_default_model_name", "cfg-model")
    monkeypatch.setenv("TALKPIPE_default_model_source", "cfg-src")
    monkeypatch.setenv("TALKPIPE_API_KEY", "cfg-key")
    reset_config()

    _run(["--path", "/tmp/db", "--require_auth"])

    (rag,) = FakeRAG.instances
    assert rag.kwargs["embedding_model"] == "cfg-embed"
    assert rag.kwargs["embedding_source"] == "cfg-esrc"
    assert rag.kwargs["completion_model"] == "cfg-model"
    assert rag.kwargs["completion_source"] == "cfg-src"
    assert "system_prompt" not in rag.kwargs
    assert FakeServer.last is not None
    assert FakeServer.last.kwargs["api_key"] == "cfg-key"
    assert FakeServer.last.kwargs["require_auth"] is True


def test_cli_api_key_wins_over_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TALKPIPE_API_KEY", "cfg-key")
    reset_config()
    _run(["--path", "/tmp/db", "--api_key", "cli-key"])
    assert FakeServer.last is not None
    assert FakeServer.last.kwargs["api_key"] == "cli-key"


def test_bad_provider_config_exits_nonzero(capsys: pytest.CaptureFixture[str]) -> None:
    """A bad provider config must say so on stderr, not just in a log record.

    talkpipe attaches a NullHandler to its own logger, so logging.lastResort
    never fires: reporting this failure only through ``logger.error`` left the
    command exiting 1 with no output at all.
    """

    class BrokenRAG(FakeRAG):
        def make_pipeline(self) -> None:
            raise ValueError("no such embedding source")

    with (
        patch.object(serverag, "RAGToText", BrokenRAG),
        patch.object(serverag, "ChatterlangServer", FakeServer),
        patch("sys.argv", ["serverag", "--path", "/tmp/db"]),
        pytest.raises(SystemExit) as excinfo,
    ):
        serverag.main()
    assert excinfo.value.code == 1
    stderr = capsys.readouterr().err
    assert "Failed to initialize RAG pipeline" in stderr
    assert "no such embedding source" in stderr
    assert "--embedding_source" in stderr
    assert FakeServer.last is None


def test_bad_provider_config_reports_in_interactive_mode(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The same failure is reported when --interactive is used."""

    class BrokenRAG(FakeRAG):
        def make_pipeline(self) -> None:
            raise ValueError("no such embedding source")

    with (
        patch.object(serverag, "RAGToText", BrokenRAG),
        patch.object(serverag, "ChatterlangServer", FakeServer),
        patch("sys.argv", ["serverag", "--path", "/tmp/db", "--interactive"]),
        pytest.raises(SystemExit) as excinfo,
    ):
        serverag.main()
    assert excinfo.value.code == 1
    assert "Failed to initialize RAG pipeline" in capsys.readouterr().err


def test_processor_answers_through_a_real_chatterlang_server() -> None:
    """The processor handed to ChatterlangServer runs the RAG pipeline per request."""
    real_server_kwargs: dict[str, Any] = {}

    class CapturingServer(FakeServer):
        def __init__(self, **kwargs: Any) -> None:
            super().__init__(**kwargs)
            real_server_kwargs.update(kwargs)

    with (
        patch.object(serverag, "RAGToText", FakeRAG),
        patch.object(serverag, "ChatterlangServer", CapturingServer),
        patch("sys.argv", ["serverag", "--path", "/tmp/db"]),
    ):
        serverag.main()

    server = ChatterlangServer(**real_server_kwargs)
    client = TestClient(server.app)
    response = client.post("/process", json={"prompt": "what is talkpipe?"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["data"]["input"] == {"prompt": "what is talkpipe?"}
    assert body["data"]["output"][0]["answer"] == "answer to what is talkpipe?"


def test_each_session_keeps_its_own_pipeline_across_requests() -> None:
    """One built RAG pipeline per browser session, reused for every request.

    Rebuilding per request reset the LLM's conversation memory on every turn;
    sharing one pipeline across sessions would leak one user's conversation
    into another's.
    """
    real_server_kwargs: dict[str, Any] = {}

    class CapturingServer(FakeServer):
        def __init__(self, **kwargs: Any) -> None:
            super().__init__(**kwargs)
            real_server_kwargs.update(kwargs)

    with (
        patch.object(serverag, "RAGToText", FakeRAG),
        patch.object(serverag, "ChatterlangServer", CapturingServer),
        patch("sys.argv", ["serverag", "--path", "/tmp/db"]),
    ):
        serverag.main()
    (rag,) = FakeRAG.instances
    startup_builds = len(rag.pipelines)  # the fail-fast build at startup

    server = ChatterlangServer(**real_server_kwargs)
    alice = TestClient(server.app)  # cookies persist per client => one session
    bob = TestClient(server.app)

    assert alice.post("/process", json={"prompt": "hi"}).status_code == 200
    assert alice.post("/process", json={"prompt": "again"}).status_code == 200
    assert bob.post("/process", json={"prompt": "hello"}).status_code == 200

    session_pipelines = rag.pipelines[startup_builds:]
    assert len(session_pipelines) == 2, "one pipeline per session, not per request"
    assert sorted(p.calls for p in session_pipelines) == [1, 2]


def test_interactive_mode_reads_prompts_and_prints_answers(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with (
        patch.object(serverag, "RAGToText", FakeRAG),
        patch.object(serverag, "ChatterlangServer", FakeServer),
        patch.object(serverag, "Prompt", _echo_source),
        patch("sys.argv", ["serverag", "--path", "/tmp/db", "-i"]),
    ):
        serverag.main()
    out = capsys.readouterr().out
    assert "Interactive RAG Mode" in out
    assert "answer to hello" in out
    assert FakeServer.last is None  # no web server in CLI mode


def _echo_source() -> Any:
    from talkpipe.pipe.io import echo

    return echo(data="hello")
