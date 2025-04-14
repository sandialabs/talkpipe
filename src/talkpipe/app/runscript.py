"""Run a talkpipe script provided on the command line or environment variable."""
from typing import Optional
import logging
import argparse
import os
import sys
from talkpipe.chatterlang import compiler
from talkpipe.util import config
from talkpipe.util.config import load_module_file

logger = logging.getLogger(__name__)

def main():
    """Run a talkpipe script from command line arguments or environment variable.

    This function parses command line arguments to execute a talkpipe script. It supports loading the script
    directly via --script argument or from an environment variable via --env. Additional features include
    loading custom modules and configuring loggers.

    Args:
        None (uses command line arguments)

    Command Line Arguments:
        --script: The talkpipe script to run (optional if --env is provided)
        --env: Environment variable containing the script (optional if --script is provided)
        --load_module: Path(s) to custom module file(s) to import before running the script (can be specified multiple times)  
        --logger_levels: Logger levels in format 'logger:level,logger:level,...'
        --logger_files: Logger files in format 'logger:file,logger:file,...'

    Raises:
        ValueError: If the specified environment variable is not found
        ArgumentError: If neither --script nor --env is provided
        
    Returns:
        None - Executes the compiled script function
    """
    parser = argparse.ArgumentParser(description='Run a talkpipe script provided on the command line or environment variable.')
    parser.add_argument('--script', type=str, nargs='?', help='The talkpipe script to run.')
    parser.add_argument('--env', type=str, help='Environment variable containing the script.')
    parser.add_argument("--load_module", action='append', default=[], type=str, help="Path to a custom module file to import before running the script.")
    parser.add_argument("--logger_levels", type=str, help="Logger levels in format 'logger:level,logger:level,...'")
    parser.add_argument("--logger_files", type=str, help="Logger files in format 'logger:file,logger:file,...'")
    args = parser.parse_args()

    config.configure_logger(args.logger_levels, logger_files=args.logger_files) 
    if args.load_module:
        for module_file in args.load_module:
            load_module_file(fname=module_file, fail_on_missing=False)

    if args.script:
        script = args.script
    elif args.env:
        script = os.environ.get(args.env)
        if script is None:
            error_message = f"Environment variable {args.env} not found"
            print(error_message, file=sys.stderr)
            raise ValueError(error_message)
    else:
        parser.error("Either --script argument or --env must be provided")

    compiled = compiler.compile(script).asFunction()
    compiled()


if __name__ == '__main__':
    main()
