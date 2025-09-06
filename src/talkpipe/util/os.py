import logging
import subprocess  # nosec B404 - Required for secure command execution with comprehensive validation
import shlex

logger = logging.getLogger(__name__)


class SecurityError(Exception):
    """Raised when a security violation is detected."""
    pass


def run_command(command: str):
    """
    Runs an external command and yields each line from stdout.
    
    Security note: This function implements security checks to prevent
    command injection attacks.

    Args:
        command: The command to run as a string.

    Yields:
        Each line from the command's stdout.
        
    Raises:
        SecurityError: If the command contains dangerous patterns.
        subprocess.CalledProcessError: If the command fails.
    """
    # Security validation
    _validate_command_security(command)
    
    logger.debug(f"Executing validated command: {command}")
    
    # Use shell=False and split command properly to prevent injection
    try:
        # Split command safely using shlex
        command_parts = shlex.split(command)
        
        # Additional validation on command parts
        if not command_parts:
            raise ValueError("Empty command provided")
            
        # Check if the base command is in a safe list (optional additional security)
        base_command = command_parts[0]
        _validate_base_command(base_command)
        
        process = subprocess.Popen(  # nosec B603
            command_parts,  # Secure: validated command parts, whitelist checked, shell=False
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE, 
            text=True, 
            shell=False  # Critical: never use shell=True
        )
        
        for line in process.stdout:
            logger.debug(f"Command output: {line.rstrip()}")
            yield line.rstrip()  # Remove trailing newline
            
        process.wait()  # Wait for the command to complete
        
        if process.returncode != 0:
            # Get stderr for better error reporting
            stderr_output = process.stderr.read() if process.stderr else "No error details available"
            logger.error(f"Command failed with return code {process.returncode}: {stderr_output}")
            raise subprocess.CalledProcessError(process.returncode, command)
            
        logger.debug("Command completed successfully")
        
    except subprocess.CalledProcessError:
        raise  # Re-raise subprocess errors
    except Exception as e:
        logger.error(f"Error executing command '{command}': {e}")
        raise SecurityError(f"Command execution failed: {e}")


def _validate_command_security(command: str):
    """
    Validate that the command does not contain dangerous patterns.
    
    Args:
        command: The command string to validate.
        
    Raises:
        SecurityError: If dangerous patterns are detected.
    """
    # Check for dangerous shell metacharacters and patterns
    dangerous_patterns = [
        ';',    # Command separator
        '&&',   # Command chaining
        '||',   # Command chaining
        '|',    # Pipe (could be used maliciously)
        '$(',   # Command substitution
        '`',    # Command substitution (backticks)
        '>',    # Redirection
        '<',    # Redirection
        '&',    # Background execution
        '\n',   # Newline injection
        '\r',   # Carriage return injection
    ]
    
    for pattern in dangerous_patterns:
        if pattern in command:
            raise SecurityError(f"Security violation: Command contains dangerous pattern '{pattern}'")
    
    # Check for path traversal attempts
    if '..' in command or '~/' in command:
        raise SecurityError("Security violation: Command contains path traversal patterns")
    
    # Check for attempts to access sensitive files
    sensitive_paths = ['/etc/passwd', '/etc/shadow', '/root/', '~root']
    command_lower = command.lower()
    for path in sensitive_paths:
        if path in command_lower:
            raise SecurityError(f"Security violation: Command attempts to access sensitive path '{path}'")


def _validate_base_command(base_command: str):
    """
    Validate that the base command is from an allowed list.
    
    Args:
        base_command: The base command to validate.
        
    Raises:
        SecurityError: If the command is not allowed.
    """
    # Define a whitelist of allowed commands (can be extended as needed)
    allowed_commands = {
        'ls', 'cat', 'echo', 'pwd', 'head', 'tail', 'grep', 'find', 'wc',
        'sort', 'uniq', 'cut', 'awk', 'sed', 'tr', 'date', 'whoami',
        'id', 'uptime', 'df', 'du', 'ps', 'top', 'free', 'mount',
        'python', 'python3', 'pip', 'git', 'curl', 'wget', 'ssh',
        'rsync', 'tar', 'gzip', 'gunzip', 'zip', 'unzip'
    }
    
    # Extract just the command name (remove path if present)
    command_name = base_command.split('/')[-1]
    
    if command_name not in allowed_commands:
        # Log the attempt for security monitoring
        logger.warning(f"Attempted execution of non-whitelisted command: {base_command}")
        raise SecurityError(f"Security violation: Command '{command_name}' is not in the allowed list")
        
    logger.debug(f"Base command '{command_name}' validated successfully")