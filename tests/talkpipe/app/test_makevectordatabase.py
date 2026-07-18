import sys

import pytest

from talkpipe.app import makevectordatabase
from talkpipe.pipelines import vector_databases as vdb
from talkpipe.pipelines.vector_databases import RagIngestResult


def _run_cli(monkeypatch, argv):
    monkeypatch.setattr(sys, "argv", ["makevectordatabase"] + argv)
    makevectordatabase.main()


def test_cli_reports_result_counts(tmp_path, monkeypatch, capsys):
    (tmp_path / "a.txt").write_text("alpha " * 40)
    captured_kwargs = {}

    def fake_build(source_pattern, **kwargs):
        captured_kwargs.update(kwargs, source_pattern=source_pattern)
        return RagIngestResult(
            chunks_indexed=4,
            chunks_skipped=1,
            files_indexed=1,
            embedding_source="fake-source",
            embedding_model="fake-model",
            dimension=3,
        )

    monkeypatch.setattr(makevectordatabase, "build_rag_database", fake_build)

    _run_cli(
        monkeypatch,
        [
            str(tmp_path / "*.txt"),
            "--path",
            str(tmp_path / "db"),
            "--embedding_model",
            "fake-model",
            "--embedding_source",
            "fake-source",
        ],
    )

    out = capsys.readouterr()
    assert "Indexed 4 chunk(s) from 1 file(s)" in out.out
    assert "skipped 1 chunk(s)" in out.err
    assert captured_kwargs["on_token_overflow"] == "truncate"
    assert captured_kwargs["fail_on_error"] is False


def test_cli_exits_nonzero_on_ingest_error(tmp_path, monkeypatch, capsys):
    (tmp_path / "a.txt").write_text("alpha " * 40)

    def fake_build(source_pattern, **kwargs):
        raise vdb.EmbedderPreflightError("a test embedding failed; provider down")

    monkeypatch.setattr(makevectordatabase, "build_rag_database", fake_build)

    with pytest.raises(SystemExit) as excinfo:
        _run_cli(
            monkeypatch,
            [
                str(tmp_path / "*.txt"),
                "--path",
                str(tmp_path / "db"),
                "--embedding_model",
                "fake-model",
                "--embedding_source",
                "fake-source",
            ],
        )

    assert excinfo.value.code == 1
    assert "provider down" in capsys.readouterr().err


def test_cli_exits_nonzero_when_pattern_matches_nothing(tmp_path, monkeypatch, capsys):
    with pytest.raises(SystemExit) as excinfo:
        _run_cli(
            monkeypatch,
            [
                str(tmp_path / "nothing" / "*.txt"),
                "--path",
                str(tmp_path / "db"),
                "--embedding_model",
                "fake-model",
                "--embedding_source",
                "fake-source",
            ],
        )

    assert excinfo.value.code == 1
    assert "matched no files" in capsys.readouterr().err
