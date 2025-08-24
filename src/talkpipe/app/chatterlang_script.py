"""Run a talkpipe script provided on the command line."""
from typing import Optional
import logging
import argparse
from talkpipe.chatterlang import compiler
from talkpipe.pipe.core import RuntimeComponent
from talkpipe.util import config
from talkpipe.util.config import load_module_file, load_script, parse_unknown_args, add_config_values

logger = logging.getLogger(__name__)

def main():
    """Run a talkpipe script from command line arguments.

    This function parses command line arguments to execute a talkpipe script. The --script parameter
    checks for: 1) existing file path, 2) configuration value, 3) inline script content.
    Additional features include loading custom modules and configuring loggers.

    Args:
        None (uses command line arguments)

    Command Line Arguments:
        --script: The talkpipe script to run (file path, config key, or inline script)
        --load-module: Path(s) to custom module file(s) to import before running the script (can be specified multiple times)  
        --logger_levels: Logger levels in format 'logger:level,logger:level,...'
        --logger_files: Logger files in format 'logger:file,logger:file,...'

    Raises:
        ValueError: If the script cannot be found or loaded
        ArgumentError: If --script is not provided
        
    Returns:
        None - Executes the compiled script function
    """
    parser = argparse.ArgumentParser(description='Run a talkpipe script provided on the command line.')
    parser.add_argument('--script', type=str, required=True, help='The talkpipe script to run: file path, configuration key, or inline script content.')
    parser.add_argument("--load-module", action='append', default=[], type=str, help="Path to a custom module file to import before running the script.")
    parser.add_argument("--logger_levels", type=str, help="Logger levels in format 'logger:level,logger:level,...'")
    parser.add_argument("--logger_files", type=str, help="Logger files in format 'logger:file,logger:file,...'")
    
    # Parse known arguments and capture unknown ones as potential constants
    args, unknown_args = parser.parse_known_args()
    
    # Parse unknown arguments as configuration values using abstracted function
    constants = parse_unknown_args(unknown_args)
    
    # Add command-line constants to the configuration so they're accessible via $key syntax
    if constants:
        add_config_values(constants, override=True)
        logger.info(f"Added command-line values to configuration: {list(constants.keys())}")

    config.configure_logger(args.logger_levels, logger_files=args.logger_files) 
    if args.load_module:
        for module_file in args.load_module:
            load_module_file(fname=module_file, fail_on_missing=False)

    script_input = args.script
    
    script = load_script(script_input)

    # Compile script - configuration values are now accessible via $key syntax
    compiled = compiler.compile(script).as_function()
    compiled()


if __name__ == '__main__':
    main()
