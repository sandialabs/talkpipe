"""Tests for the ``talkpipe_precache_model2vec`` CLI."""

from __future__ import annotations

from typing import Any

import pytest

from talkpipe.app import precache_model2vec
from talkpipe.llm.model2vec_embeddings import DEFAULT_MODEL


def test_precache_subcommand_passes_args_and_prints_result(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls: list[dict[str, Any]] = []

    def fake_precache(model_name: str, *, revision: Any, cache_dir: Any) -> dict:
        calls.append(
            {"model": model_name, "revision": revision, "cache_dir": cache_dir}
        )
        return {"model": model_name, "dimension": 256}

    monkeypatch.setattr(precache_model2vec, "precache_model", fake_precache)
    rc = precache_model2vec.main(
        ["precache", "org/model", "--revision", "abc123", "--cache-dir", "/c"]
    )
    assert rc == 0
    assert calls == [{"model": "org/model", "revision": "abc123", "cache_dir": "/c"}]
    out = capsys.readouterr().out
    assert "model: org/model" in out
    assert "dimension: 256" in out


def test_precache_defaults_to_the_default_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[str] = []
    monkeypatch.setattr(
        precache_model2vec,
        "precache_model",
        lambda name, *, revision, cache_dir: seen.append(name) or {},
    )
    assert precache_model2vec.main(["precache"]) == 0
    assert seen == [DEFAULT_MODEL]


def test_demo_subcommand_uses_embedder(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    class FakeEmbedder:
        model_name = "fake/model"
        dimension = 4
        normalize = True

        def embed_one(self, text: str) -> list[float]:
            return [0.0] * 4

    monkeypatch.setattr(precache_model2vec, "Model2VecEmbedder", FakeEmbedder)
    assert precache_model2vec.main(["demo"]) == 0
    out = capsys.readouterr().out
    assert "fake/model" in out
    assert "Dimension: 4" in out
    assert "Length:    4" in out


def test_no_subcommand_prints_help(capsys: pytest.CaptureFixture[str]) -> None:
    assert precache_model2vec.main([]) == 0
    assert "precache" in capsys.readouterr().out
