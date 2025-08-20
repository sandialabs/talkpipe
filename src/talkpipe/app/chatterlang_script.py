"""Run a talkpipe script provided on the command line."""
from typing import Optional
import logging
import argparse
from talkpipe.chatterlang import compiler
from talkpipe.pipe.core import RuntimeComponent
from talkpipe.util import config
from talkpipe.util.config import load_module_file, load_script

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
    
    # Parse unknown arguments as constants (--CONST_NAME value pairs)
    constants = {}
    i = 0
    while i < len(unknown_args):
        if unknown_args[i].startswith('--') and i + 1 < len(unknown_args):
            const_name = unknown_args[i][2:]  # Remove '--' prefix
            const_value = unknown_args[i + 1]
            
            # Try to parse value as different types (similar to ChatterLang parameter parsing)
            if const_value.lower() in ('true', 'false'):
                constants[const_name] = const_value.lower() == 'true'
            elif const_value.isdigit() or (const_value.startswith('-') and const_value[1:].isdigit()):
                constants[const_name] = int(const_value)
            elif '.' in const_value:
                try:
                    constants[const_name] = float(const_value)
                except ValueError:
                    constants[const_name] = const_value
            else:
                constants[const_name] = const_value
            i += 2
        else:
            i += 1

    config.configure_logger(args.logger_levels, logger_files=args.logger_files) 
    if args.load_module:
        for module_file in args.load_module:
            load_module_file(fname=module_file, fail_on_missing=False)

    script_input = args.script
    
    script = load_script(script_input)

    # Create a runtime component with command-line constants
    runtime = RuntimeComponent()
    runtime.add_constants(constants, override=True)
    
    compiled = compiler.compile(script, runtime).asFunction()
    compiled()


if __name__ == '__main__':
    main()
