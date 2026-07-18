import argparse
import glob
import sys
import logging
from talkpipe.util.config import get_config, parse_unknown_args, add_config_values, configure_logger
from talkpipe.util.constants import TALKPIPE_EMBEDDING_MODEL_NAME, TALKPIPE_EMBEDDING_MODEL_SOURCE
from talkpipe.llm.config import getEmbeddingSources
from talkpipe.pipelines.vector_databases import RagIngestError, build_rag_database

logger = logging.getLogger(__name__)

def main():
    """Create a vector database using the Talkpipe document pipeline."""
    parser = argparse.ArgumentParser(description='Create a LanceDB vector database from a set of documents.')
    
    # Required arguments
    parser.add_argument('data_source', type=str, help='File path or glob pattern of documents to process (e.g. "docs/*.md")')
    parser.add_argument('--path', type=str, required=True, help='Path where the LanceDB database will be created')
    
    # Pipeline arguments
    parser.add_argument('--shingle_size', type=int, default=3, help='Size threshold for text chunking shingles (default: 3 chunks)')
    parser.add_argument('--overlap', type=int, default=1, help='Overlap threshold for text chunking shingles (default: 1)')
    parser.add_argument('--chunk_size', type=int, default=300, help='Size threshold for text chunking (default: 300 characters)')
    
    # Optional arguments that fall back to config settings
    parser.add_argument('--embedding_model', type=str, help='Model to use for embedding (defaults to config)')
    parser.add_argument('--embedding_source', type=str, help='Source of the embedding model (defaults to config)')
    parser.add_argument('--embedding_field', type=str, default='shingle_text', help='Field to use for embeddings (default: shingle_text)')
    parser.add_argument('--embedding_fail_on_error', action='store_true', help='If set, fail on error when embedding', default=False)
    parser.add_argument('--on_token_overflow', type=str, choices=['error', 'truncate', 'chunk_pool'], default='truncate',
                        help='What to do when a chunk is too long for the embedding model: error (abort the run), truncate (shrink and retry; default), or chunk_pool (split, embed, and mean-pool)')

    # Other LanceDB options
    parser.add_argument('--table_name', type=str, default='docs', help='Name of the table to create (default: "docs")')
    parser.add_argument('--doc_id_field', type=str, default=None,
                        help='Field containing document ID. Default None generates unique IDs per chunk (recommended for document pipelines with multiple chunks per file)')
    parser.add_argument('--overwrite', action='store_true', help='If set, overwrite existing database table')
    parser.add_argument('--batch_size', type=int, default=100, help='Batch size for committing to database (default: 100)')
    
    # System settings
    parser.add_argument('--logger_levels', type=str, help="Logger levels in format 'logger:level,logger:level,...'")

    args, unknown_args = parser.parse_known_args()
    
    # Process logger settings
    configure_logger(args.logger_levels)

    # Process settings with env/config/cli override priority
    config = get_config()
    constants = parse_unknown_args(unknown_args)
    if constants:
        add_config_values(constants, override=True)
        
    # Resolve embedding source/model from CLI flags, falling back to config, and
    # fail fast with an actionable message rather than crashing deep in the
    # pipeline with "Source 'None' is not supported".
    embedding_source = args.embedding_source or config.get(TALKPIPE_EMBEDDING_MODEL_SOURCE)
    embedding_model = args.embedding_model or config.get(TALKPIPE_EMBEDDING_MODEL_NAME)
    missing = []
    if not embedding_source:
        missing.append("--embedding_source (" + "|".join(getEmbeddingSources()) + ")")
    if not embedding_model:
        missing.append("--embedding_model <name>")
    if missing:
        parser.error(
            "No embedding configuration found. Provide " + " and ".join(missing)
            + f", or set {TALKPIPE_EMBEDDING_MODEL_SOURCE} / {TALKPIPE_EMBEDDING_MODEL_NAME}"
            + " in ~/.talkpipe.toml (or as TALKPIPE_* environment variables)."
        )

    # A pattern matching zero files is almost always a typo or wrong working
    # directory; fail loudly instead of "successfully" indexing nothing.
    if not glob.glob(args.data_source, recursive=True):
        print(
            f"error: '{args.data_source}' matched no files. Check the path or "
            f"glob pattern (quote it so your shell does not expand it).",
            file=sys.stderr,
        )
        sys.exit(1)

    # Run the shared RAG ingestion driver (preflight, skip counting, and
    # overflow handling live there, so the CLI and downstream apps behave alike).
    logger.info("Initializing vector database pipeline...")
    try:
        result = build_rag_database(
            args.data_source,
            path=args.path,
            embedding_model=embedding_model,
            embedding_source=embedding_source,
            table_name=args.table_name,
            embedding_field=args.embedding_field,
            chunk_size=args.chunk_size,
            shingle_size=args.shingle_size,
            overlap=args.overlap,
            doc_id_field=args.doc_id_field,
            overwrite=args.overwrite,
            batch_size=args.batch_size,
            fail_on_error=args.embedding_fail_on_error,
            on_token_overflow=args.on_token_overflow,
        )
    except RagIngestError as exc:
        print(f"\nerror: {exc}", file=sys.stderr)
        sys.exit(1)

    logger.info("Database creation complete.")
    print(
        f"\nIndexed {result.chunks_indexed} chunk(s) from {result.files_indexed} "
        f"file(s) into '{args.path}' (table '{args.table_name}') "
        f"using {embedding_source}/{embedding_model}."
    )
    if result.chunks_skipped:
        print(
            f"warning: skipped {result.chunks_skipped} chunk(s) that failed to "
            f"embed — check the log for the embedding errors.",
            file=sys.stderr,
        )
    if result.chunks_indexed == 0:
        print(
            f"warning: no chunks were indexed from '{args.data_source}' — "
            f"the matched paths contained no readable document content.",
            file=sys.stderr,
        )
        sys.exit(1)

if __name__ == "__main__":
    main()
