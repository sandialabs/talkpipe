import logging

logger = logging.getLogger(__name__)


import subprocess


def run_command(command: str):
    """
    Runs an external command and yields each line from stdout.

    Args:
        command: The command to run as a string.

    Yields:
        Each line from the command's stdout.
    """
    logger.debug(f"Executing command: {command}")
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, shell=True)
    for line in process.stdout:
        logger.debug(f"Command output: {line.rstrip()}")
        yield line.rstrip()  # Remove trailing newline
    process.wait()  # Wait for the command to complete
    if process.returncode != 0:
        logger.error(f"Command failed with return code {process.returncode}")
        raise subprocess.CalledProcessError(process.returncode, command)
    logger.debug("Command completed successfully")