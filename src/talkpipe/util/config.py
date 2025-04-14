from typing import Optional
import importlib 
import logging
import os
import sys
import tomllib
from logging.handlers import TimedRotatingFileHandler
from typing import Any, Dict

logger = logging.getLogger(__name__)

_config = None


def parse_key_value_str(field_list: str, require_value: bool = False) -> Dict[str, str]:
    """Parse a property assignment list into a dictionary.

    Args:
        field_list (str): A comma-separated string of key-value pairs in the format "key:value,key:value".
        require_value (bool, optional): If True, raises a ValueError when a key is missing a value.

    Returns:
        Dict[str, str]: A dictionary where keys are property names and values are assigned values.

    Raises:
        ValueError: If require_value is True and a key is missing a value.
    """
    result = {}
    for property in field_list.split(","):
        key, *value = property.split(":", 1)
        key = key.strip()
        value = value[0].strip() if len(value)>0 else None

        if value is None:
            if require_value:
                raise ValueError(f"Value required for property '{key}'")
            value = "original" if key == "_" else key.rsplit(".", 1)[-1]

        result[key] = value

    return result


def reset_config():
    """Reset the configuration to None.

    This function resets the global _config variable to None, forcing
    the next call to get_config() to reload configuration from disk
    and environment variables.
    """
    global _config
    _config = None


def get_config(reload=False, path="~/.talkpipe.toml", ignore_env=False):
    """Get the configuration from the config file and environment variables.
    This function reads configuration from a TOML file and environment variables.
    Environment variables starting with 'TALKPIPE_' override config file values.
    Args:
        reload (bool, optional): Force reload config from disk. Defaults to False.
        path (str, optional): Path to config file. Defaults to "~/talkpipe.toml".
    Returns:
        dict: Configuration dictionary combining file and environment settings.
    Notes:
        - Config file values are read from the TOML file if it exists
        - Environment variables prefixed with 'TALKPIPE_' take precedence
        - If config file doesn't exist, returns environment variables only
        - Configuration is cached after first load unless reload=True
    """
    global _config
    if _config is None or reload:
        logger.debug("Loading configuration")
        config_path = os.path.expanduser(path)
        if os.path.exists(config_path):
            logger.info(f"Reading config from {config_path}")
            with open(config_path, 'rb') as f:
                _config = tomllib.load(f)
                logger.debug(f"Loaded config: {_config}")
        else:
            logger.warning(f"Config file {config_path} not found, using empty config")
            _config = {}

        if not ignore_env:
            logger.debug("Checking environment variables")
            # Override with environment variables
            for env_var in os.environ:
                if env_var.startswith('TALKPIPE_'):
                    config_key = env_var[9:].lower()  # Remove TALKPIPE_ prefix
                    _config[config_key] = os.environ[env_var]
                    logger.debug(f"Set {config_key} from environment variable {env_var}")

    return _config


def configure_logger(logger_levels: Optional[str] = None, base_level="WARNING", logger_files: Optional[str] = None, transformers_to_debug=True):
    """Configure logging levels for specified loggers.

    This function sets up logging configuration for multiple loggers, including optional
    suppression of transformers-related logs. It configures both the log level and
    output format for each specified logger.

    Args:
        logger_levels (str): A string containing logger name and level pairs in the format
            "logger1:LEVEL1,logger2:LEVEL2". Use "root" as logger name for root logger.
            Valid levels are DEBUG, INFO, WARNING, ERROR, CRITICAL.
        base_level (str, optional): Default logging level. Defaults to "WARNING".
        logger_files (str, optional): A string mapping loggers to file paths in "logger:path" format.
        transformers_to_debug (bool, optional): If True, sets all transformers-related
            loggers to ERROR level. Defaults to True.

    Examples:
        >>> configure_logger("root:INFO,myapp:DEBUG")
        >>> configure_logger("root:WARNING", transformers_to_debug=False)

    Note:
        - Each logger gets a StreamHandler with formatted output
        - Format: '%(asctime)s - %(levelname)s:%(name)s:%(message)s'
        - Levels are converted to uppercase automatically
    """

    if not logger_levels:
        logger_levels = get_config().get("logger_levels", None)

    if not logger_files:
        logger_files = get_config().get("logger_files", None)

    logging.basicConfig(level=base_level.upper())

    if transformers_to_debug:
        for name, logger in logging.Logger.manager.loggerDict.items():
            if "transformers" in name and isinstance(logger, logging.Logger):
                logger.setLevel(logging.ERROR)

    formatter = logging.Formatter('%(asctime)s - %(levelname)s:%(name)s:%(message)s')

    if logger_levels:
        for logger_name, level in parse_key_value_str(logger_levels).items():
            level = level.upper()
            logger = logging.getLogger(logger_name if logger_name != "root" else None)
            logger.setLevel(level)

            # Remove existing handlers to prevent duplicate logs
            logger.handlers.clear()

            console_handler = logging.StreamHandler()
            console_handler.setLevel(level)
            console_handler.setFormatter(formatter)
            logger.addHandler(console_handler)

    if logger_files:
        for logger_name, file_name in parse_key_value_str(logger_files).items():
            logger = logging.getLogger(logger_name if logger_name != "root" else None)

            file_handler = TimedRotatingFileHandler(file_name, when='midnight', backupCount=7)
            file_handler.setLevel(level)
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)


def load_module_file(fname: str, fail_on_missing=False) -> Optional[Any]:
    """
    Safely load a Python custom module.
    Supports ~ notation for home directory.

    Args:
        fname: Path to the module file (absolute, relative, or with ~)

    Returns:
        Module object containing the module, or None if file cannot be loaded

    Raises:
        ImportError: If there are issues importing the module
        FileNotFoundError: If the module file doesn't exist and fail_on_missing is True
    """
    try:
        # Expand ~ to home directory if present
        config_path = os.path.expanduser(fname)
        # Convert to absolute path if relative
        config_path = os.path.abspath(config_path)

        if not os.path.exists(config_path):
            logger.warning(f"Custom module file not found: {config_path}")
            if fail_on_missing:
                raise FileNotFoundError(f"Custom module file not found: {config_path}")
            else:
                return None

        # Get the directory containing the config file
        config_dir = os.path.dirname(config_path)

        # Generate a unique module name based on the file path
        module_name = f"config_{os.path.splitext(os.path.basename(fname))[0]}"

        # Create the spec for the module
        spec = importlib.util.spec_from_file_location(module_name, config_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load custom module from {config_path}")

        # Create the module
        module = importlib.util.module_from_spec(spec)

        # Add the config file's directory to sys.path temporarily
        sys.path.insert(0, config_dir)

        try:
            # Execute the module
            spec.loader.exec_module(module)
            return module
        finally:
            # Remove the config directory from sys.path
            sys.path.remove(config_dir)

    except Exception as e:
        # Log or handle specific exceptions as needed
        raise ImportError(f"Error loading module file: {str(e)}") from e