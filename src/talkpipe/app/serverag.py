import argparse
import sys
import logging
from typing import Dict, Any

from talkpipe.util.config import get_config, parse_unknown_args, add_config_values, configure_logger
from talkpipe.pipelines.basic_rag import RAGToText
from talkpipe.app.chatterlang_serve import ChatterlangServer, FormConfig, FormField
from talkpipe.pipe.io import Prompt
from talkpipe.pipe.basic import ToDict

logger = logging.getLogger(__name__)

def main():
    """Start a Chatterlang server running a RAGToText pipeline."""
    parser = argparse.ArgumentParser(description='Serve a Talkpipe RAG pipeline.')
    
    # Required database arguments (from makevectordatabase)
    parser.add_argument('--path', type=str, required=True, help='Path to the LanceDB database')
    
    # Model configuration (optional, falls back to config)
    parser.add_argument('--embedding_model', type=str, help='Model to use for embedding (defaults to config)')
    parser.add_argument('--embedding_source', type=str, help='Source of the embedding model (defaults to config)')
    parser.add_argument('--completion_model', type=str, help='LLM model to use for completion (defaults to config)')
    parser.add_argument('--completion_source', type=str, help='Source of prompt for completion (defaults to config)')
    
    # RAG settings
    parser.add_argument('--limit', type=int, default=5, help='Number of search results to retrieve (default: 5)')
    parser.add_argument('--table_name', type=str, default='docs', help='Name of the table to query (default: "docs")')
    parser.add_argument('--prompt_directive', type=str, 
                        default="Respond to the provided content based on the background information. When citing information, include the source (title or path) from the background. If the background does not contain relevant information, respond with 'No relevant information found.'",
                        help='Directive to guide the evaluation')
    parser.add_argument('--system_prompt', type=str, help='System prompt for the completion LLM')
    
    # Server settings
    parser.add_argument('-p', '--port', type=int, default=2026, help='Port to listen on (default: 2026)')
    parser.add_argument('-o', '--host', default='localhost', help='Host to bind to (default: localhost)')
    parser.add_argument('--title', default='Talkpipe RAG Server', help='Title for the web UI')
    parser.add_argument('--api_key', help='Set API key for authentication')
    parser.add_argument('--require_auth', action='store_true', help='Require API key authentication')
    
    # System settings
    parser.add_argument('--logger_levels', type=str, help="Logger levels in format 'logger:level,logger:level,...'")
    
    # CLI Mode
    parser.add_argument('-i', '--interactive', action='store_true', help='Run in interactive CLI REPL mode instead of starting a web server')

    args, unknown_args = parser.parse_known_args()
    
    # Process logger settings
    if args.logger_levels:
        configure_logger(args.logger_levels)

    # Process settings with env/config/cli override priority
    config = get_config()
    constants = parse_unknown_args(unknown_args)
    if constants:
        add_config_values(constants, override=True)
        
    api_key = args.api_key or config.get('API_KEY')

    # Setup the RAG Pipeline Segment
    # We will instantiate it once. Alternatively, it could be instantiated per request if state isolation is needed, 
    # but Talkpipe segments are generally designed to process sequences.
    try:
        rag_pipeline = RAGToText(
            path=args.path,
            content_field='prompt',  # We'll map the UI 'prompt' field to this
            embedding_model=args.embedding_model or config.get('DEFAULT_EMBEDDING_MODEL'),
            embedding_source=args.embedding_source or config.get('DEFAULT_EMBEDDING_SOURCE'),
            completion_model=args.completion_model or config.get('DEFAULT_LLM_MODEL'),
            completion_source=args.completion_source or config.get('DEFAULT_LLM_SOURCE'),
            limit=args.limit,
            table_name=args.table_name,
            prompt_directive=args.prompt_directive,
            system_prompt=args.system_prompt if args.system_prompt else None # RAGToText has its own default if None
        )
    except Exception as e:
        logger.error(f"Failed to initialize RAG pipeline: {e}")
        sys.exit(1)

    if args.interactive:
        logger.info(f"Starting RAG CLI REPL querying {args.path}")
        print(f"Interactive RAG Mode. Querying: {args.path}")
        print("Type your questions below. Press Ctrl+D to exit.")
        print("-" * 50)
        
        # Build the pipeline: Prompt -> Dict Converter -> RAG Pipeline
        cli_pipeline = Prompt() | ToDict(field_list="_:prompt") | rag_pipeline
        
        # Consume the pipeline results
        for item in cli_pipeline():
            # RAGToText yields the final string 
            print("\n" + str(item) + "\n")
            print("-" * 50)
            
    else:
        # Define the processor function that ChatterlangServer will call for each web request
        def process_request(data: Dict[str, Any], session: Any) -> Any:
            # data will contain {"prompt": "user's question"} from the form
            logger.info(f"Received query: {data.get('prompt', '')}")
            
            # We pass a copy of the dictionary through the pipeline
            # so internal state (like _background arrays) doesn't pollute the return payload
            input_data = [data.copy()]
            
            # Yield the results directly, which ChatterlangServer supports returning
            yield from rag_pipeline.transform(input_data)
    
        # Configure the UI Form
        form_config_dict = {
            "title": args.title,
            "fields": [
                {
                    "name": "prompt",
                    "type": "text",
                    "label": "Question",
                    "placeholder": "Ask a question about your documents...",
                    "required": True,
                }
            ],
            "position": "bottom",
            "height": "100px",
            "theme": "dark"
        }
        
        # Initialize and start the server
        logger.info(f"Starting RAG Server on {args.host}:{args.port} querying {args.path}")
        server = ChatterlangServer(
            host=args.host,
            port=args.port,
            api_key=api_key,
            require_auth=args.require_auth,
            title=args.title,
            processor_func=process_request,
            form_config=form_config_dict, 
            display_property="prompt"
        )
        
        server.start(background=False)

if __name__ == "__main__":
    main()
