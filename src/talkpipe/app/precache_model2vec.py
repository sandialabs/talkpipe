"""CLI for precaching model2vec embedding models."""

from __future__ import annotations

import argparse
import sys

from talkpipe.llm.model2vec_embeddings import DEFAULT_MODEL, Model2VecEmbedder, precache_model


def _demo() -> None:
    """Quick end-to-end check with the default model."""
    embedder = Model2VecEmbedder()
    print(f"Model:     {embedder.model_name}")
    print(f"Dimension: {embedder.dimension}")
    print(f"Normalize: {embedder.normalize}")

    paragraph = (
        "Static embeddings tokenize input text and combine fixed token vectors. "
        "They are much smaller and faster than full transformer models, with "
        "competitive quality for many retrieval tasks."
    )
    vec = embedder.embed_one(paragraph)
    print(f"Length:    {len(vec)}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="talkpipe_precache_model2vec",
        description="Precache model2vec embedding models for offline use.",
    )
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser(
        "precache",
        help="Download and cache a model2vec model for offline use.",
    )
    p.add_argument(
        "model_name",
        nargs="?",
        default=DEFAULT_MODEL,
        help=f"Hugging Face model id (default: {DEFAULT_MODEL})",
    )
    p.add_argument(
        "--revision",
        default=None,
        help="Pin to a specific commit SHA (recommended for reproducible builds).",
    )
    p.add_argument(
        "--cache-dir",
        default=None,
        help="Override the HF cache directory.",
    )

    sub.add_parser("demo", help="Run a quick embedding demo with the default model.")

    args = parser.parse_args(argv)

    if args.command == "precache":
        result = precache_model(
            args.model_name,
            revision=args.revision,
            cache_dir=args.cache_dir,
        )
        for key, value in result.items():
            print(f"{key}: {value}")
        return 0

    if args.command == "demo":
        _demo()
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
