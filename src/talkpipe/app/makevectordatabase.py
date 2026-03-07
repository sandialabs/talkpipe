import argparse
import sys
import logging
from talkpipe.util.config import get_config, parse_unknown_args, add_config_values, configure_logger
from talkpipe.pipelines.vector_databases import MakeVectorDatabaseSegment, ProcessDocumentsSegment

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
        
    if not args.embedding_model:
        logger.warning("Error: --embedding_model not specified.  Will use default specified in config.")
        
    if not args.embedding_source:
        logger.warning("Error: --embedding_source not specified.  Will use default specified in config.")

    # Build Pipeline
    pipeline = (
        ProcessDocumentsSegment(
            chunk_size=args.chunk_size,
            shingle_size=args.shingle_size,
            overlap=args.overlap
        )
        | MakeVectorDatabaseSegment(
            embedding_field=args.embedding_field,
            embedding_model=args.embedding_model,
            embedding_source=args.embedding_source,
            path=args.path,
            table_name=args.table_name,
            doc_id_field=args.doc_id_field,
            overwrite=args.overwrite,
            batch_size=args.batch_size
        )
    )

    # Execute pipeline
    logger.info("Initializing vector database pipeline...")
    for item in pipeline.transform([args.data_source]):
        # We process the iterator to pull items through the pipeline
        pass
    
    logger.info("Database creation complete.")

if __name__ == "__main__":
    main()
