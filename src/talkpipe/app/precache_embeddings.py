"""CLI for precaching local Hugging Face embedding models."""

from __future__ import annotations

import argparse
import sys

from talkpipe.llm.local_embeddings import DEFAULT_MODEL, LocalEmbedder, precache_model


def _demo() -> None:
    """Quick end-to-end check with the default model."""
    embedder = LocalEmbedder()
    print(f"Model:      {embedder.model_name}")
    print(f"Dimension:  {embedder.dimension}")
    print(f"Max tokens: {embedder.max_tokens}")

    paragraph = (
        "Sentence-transformer models that target sentence-level inputs "
        "typically cap context at 256 to 512 tokens. For full paragraphs, "
        "a model with a longer context window avoids silent truncation, "
        "which would otherwise drop the tail of the input and produce "
        "embeddings that ignore part of what was passed in."
    )
    vec = embedder.embed_one(paragraph)
    print(f"Length:     {len(vec)}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="talkpipe_precache_embeddings",
        description="Precache local Hugging Face embedding models for offline use.",
    )
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser(
        "precache",
        help="Download and cache a model (or just its tokenizer) for offline use.",
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
    p.add_argument(
        "--tokenizer-only",
        action="store_true",
        help="Download only tokenizer files (~1 MB) instead of the full model.",
    )

    sub.add_parser("demo", help="Run a quick embedding demo with the default model.")

    args = parser.parse_args(argv)

    if args.command == "precache":
        result = precache_model(
            args.model_name,
            revision=args.revision,
            cache_dir=args.cache_dir,
            tokenizer_only=args.tokenizer_only,
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
