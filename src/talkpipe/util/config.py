"""Configuration, logging, and script loading utilities.

Provides TOML-based config with environment overrides, logger setup,
custom module loading, CLI argument parsing, and script resolution
from files, config keys, or inline content.
"""
from typing import Optional
import importlib
import logging
import os
import sys
import tomllib
from logging.handlers import TimedRotatingFileHandler
from typing import Any, Dict
from pathlib import Path

logger = logging.getLogger(__name__)

# Cached config; None forces reload on next get_config()
_config = None


def parse_key_value_str(field_list: str, require_value: bool = False) -> Dict[str, str]:
    """Parse a comma-separated key:value string into a dictionary.

    Pairs may omit the value; if so, the key gets ``"original"`` when the key
    is ``"_"``, otherwise the last segment after a dot (e.g. ``"a.b.c"`` → ``"c"``).

    Args:
        field_list: Comma-separated pairs, e.g. ``"key1:val1,key2:val2"``.
        require_value: If True, raise ValueError when a key has no value.

    Returns:
        Dict mapping keys to their values (or defaults when value omitted).

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
    """Clear the cached config so the next get_config() reloads from disk and env."""
    global _config
    _config = None


def add_config_values(values_dict, override=True):
    """Merge additional values into the current configuration.

    Loads config if not yet loaded. Useful for injecting command-line
    arguments so they are available via ``$key`` syntax in ChatterLang scripts.

    Args:
        values_dict: Key-value pairs to add.
        override: If True, overwrite existing keys. If False, only add new keys.
    """
    global _config
    
    # Ensure config is loaded first
    if _config is None:
        get_config()
    
    # Merge the values
    for key, value in values_dict.items():
        if override or key not in _config:
            _config[key] = value
            logger.debug(f"Added config value: {key} = {value}")


def get_config(reload=False, path="~/.talkpipe.toml", ignore_env=False):
    """Load and return configuration from TOML file and environment variables.

    Reads from a TOML file at the given path. Environment variables prefixed
    with ``TALKPIPE_`` override config file values (e.g. ``TALKPIPE_DEBUG``
    sets ``config['DEBUG']``). Configuration is cached after first load.

    Args:
        reload: Force reload from disk, bypassing cache.
        path: Path to TOML config file. Defaults to ``~/.talkpipe.toml``.
        ignore_env: If True, skip loading TALKPIPE_* environment variables.

    Returns:
        Configuration dict combining file and environment settings.
        Empty dict if file does not exist and no env vars are loaded.

    Notes:
        - Config file values are read from the TOML file if it exists.
        - Environment variables take precedence over file values.
        - If config file does not exist, starts with empty dict.
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
            logger.debug(f"Config file {config_path} not found, using empty config")
            _config = {}

        if not ignore_env:
            logger.debug("Checking environment variables")
            # Override with environment variables
            for env_var in os.environ:
                if env_var.startswith('TALKPIPE_'):
                    config_key = env_var[9:]  # Remove TALKPIPE_ prefix
                    _config[config_key] = os.environ[env_var]
                    logger.debug(f"Set {config_key} from environment variable {env_var}")

    return _config


def configure_logger(logger_levels: Optional[str] = None, base_level="WARNING", logger_files: Optional[str] = None, transformers_to_debug=True):
    """Configure logging levels and optional file handlers for loggers.

    Sets levels and handlers for loggers specified in ``logger_levels`` and
    ``logger_files``. If either is omitted, falls back to config keys
    ``logger_levels`` and ``logger_files``.

    Args:
        logger_levels: Comma-separated ``logger:LEVEL`` pairs, e.g.
            ``"root:INFO,talkpipe:DEBUG"``. Use ``"root"`` for the root logger.
        base_level: Default level for the root logger.
        logger_files: Comma-separated ``logger:path`` pairs for file handlers.
            Rotates at midnight, keeps 7 backups.
        transformers_to_debug: If True, set transformers loggers to ERROR.

    Note:
        Output format: ``%(asctime)s - %(levelname)s:%(name)s:%(message)s``.
        When using ``logger_files``, also set ``logger_levels`` so handler
        levels are correct.
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


def load_module_file(fname: str, fail_on_missing: bool = False) -> Optional[Any]:
    """Load a Python module from a file path.

    Supports ``~`` for home directory. The file's directory is temporarily
    added to ``sys.path`` so local imports work. Module name is derived
    from the filename (e.g. ``my_config.py`` → ``config_my_config``).

    Args:
        fname: Path to the module file (absolute, relative, or ``~``).
        fail_on_missing: If True, raise FileNotFoundError when file does not exist.
            If False, return None.

    Returns:
        Loaded module object, or None if file not found and fail_on_missing is False.

    Raises:
        ImportError: If the module cannot be loaded.
        FileNotFoundError: If the file does not exist and fail_on_missing is True.
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


def parse_unknown_args(unknown_args):
    """Parse ``--key value`` and ``--flag`` style args into a dict.

    Values are parsed as bool (true/false), int, float, or str. Flags
    without a value are set to True.

    Args:
        unknown_args: List of leftover CLI args (e.g. from argparse).

    Returns:
        Dict mapping names (without ``--``) to parsed values.
    """
    constants = {}
    i = 0
    while i < len(unknown_args):
        if unknown_args[i].startswith('--'):
            const_name = unknown_args[i][2:]  # Remove '--' prefix

            # Check if next arg exists and is not another flag
            if i + 1 < len(unknown_args) and not unknown_args[i + 1].startswith('--'):
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
                # Binary flag (no value provided)
                constants[const_name] = True
                i += 1
        else:
            i += 1
    return constants


def load_script(script_input: str) -> str:
    """Resolve script content from a path, config key, or inline string.

    Resolution order:
    1. If ``script_input`` is an existing file path, read and return its contents.
    2. If ``script_input`` is a config key, use its value. If that value is a
       file path, read it; otherwise return the value as script content.
    3. Otherwise treat ``script_input`` as inline script content.

    Args:
        script_input: File path, config key, or inline ChatterLang script.

    Returns:
        Script content as a string.

    Raises:
        ValueError: If script_input is None or empty.
        IOError: If a file path is given but cannot be read.
    """
    if script_input is None or script_input.strip() == "":
        raise ValueError("script_input cannot be None or empty")
    
    # 1. Check if the script input is an existing file path
    script_path = Path(script_input)
    try:
        is_file = script_path.is_file()
    except OSError as e:
        logger.debug(f"Script path could not be checked as a file {script_input[0:25]}...: {e}")
        is_file = False
    if is_file:
        try:
            with open(script_path, 'r', encoding='utf-8') as f:
                return f.read()
        except IOError as e:
            error_message = f"Failed to read script file {script_path}: {e}"
            raise IOError(error_message)

    # 2. Check if the script input can be retrieved from configuration
    config_data = get_config()
    if script_input in config_data:
        config_value = config_data[script_input]
        
        # Check if the config value is a file path
        config_file_path = Path(config_value)
        try:
            is_file = config_file_path.is_file()
        except OSError as e:
            logger.warning(f"Config file path could not be checked as a file {config_value[0:25]}...: {e}")
            is_file = False
        if is_file:
            try:
                with open(config_file_path, 'r', encoding='utf-8') as f:
                    return f.read()
            except IOError as e:
                error_message = f"Failed to read script file from config {config_file_path}: {e}"
                raise IOError(error_message)
        
        # If not a file, return the config value as-is
        return config_value
    
    # 3. Treat as inline script
    return script_input